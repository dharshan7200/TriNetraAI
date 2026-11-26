"""Evidence chain, capture-time quality checks and the dispute report."""
import hashlib
import json
import shutil
import sqlite3

import cv2
import pytest
from fastapi.testclient import TestClient

from trinetra_link.config import REPO_ROOT
from trinetra_link.integrity.chain import genesis_hash, seal_journey, verify_chain
from trinetra_link.schema.models import CheckpointObservation
from trinetra_link.store.database import Store

DEMO = REPO_ROOT / "TriNetra_Demo_Inputs"
PHONE = DEMO / "input2_Stage_Fault_Return_Courier"
TOKEN = "test-token-evidence"


def load_folder(folder):
    data = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    cps = []
    for c in data["checkpoints"]:
        c = {k: v for k, v in c.items() if k in CheckpointObservation.model_fields}
        c["images"] = [{**im, "path": str(folder / im["path"])} for im in c["images"]]
        cps.append(CheckpointObservation(**c))
    return cps


# ------------------------------------------------------------------ evidence chain
def test_demo_journeys_are_sealed_and_intact():
    for folder in sorted(DEMO.glob("input*")):
        res = verify_chain(load_folder(folder))
        assert res["status"] == "intact", (folder.name, res["problems"])
        assert res["photos_checked"] == 12


def _copy(tmp_path):
    dst = tmp_path / "j"
    shutil.copytree(PHONE, dst)
    return dst


def _edit(folder, fn):
    p = folder / "journey.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    fn(data)
    p.write_text(json.dumps(data), encoding="utf-8")


def test_edited_reading_breaks_the_chain(tmp_path):
    d = _copy(tmp_path)
    _edit(d, lambda j: j["checkpoints"][3]["weights_g"].__setitem__(0, 295.0))
    res = verify_chain(load_folder(d))
    assert res["status"] == "broken"
    assert any("CP4" in p and "changed after capture" in p for p in res["problems"])


def test_replaced_photo_breaks_the_chain(tmp_path):
    d = _copy(tmp_path)
    shutil.copy(d / "images" / "CP1_TOP.jpg", d / "images" / "CP4_TOP.jpg")
    res = verify_chain(load_folder(d))
    assert res["status"] == "broken"
    assert any("TOP photo was replaced" in p for p in res["problems"])


def test_removed_checkpoint_breaks_the_link(tmp_path):
    d = _copy(tmp_path)
    _edit(d, lambda j: j["checkpoints"].pop(2))
    res = verify_chain(load_folder(d))
    assert res["status"] == "broken"
    assert any("link to CP2" in p for p in res["problems"])


def test_unsealed_records_are_reported_not_failed(tmp_path):
    cps = [c.model_copy(update={"record_hash": None, "prev_record_hash": None}) for c in load_folder(PHONE)]
    assert verify_chain(cps)["status"] == "unsealed"


def test_chain_survives_a_store_round_trip(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    sealed = seal_journey(load_folder(PHONE))
    assert sealed[0].prev_record_hash == genesis_hash(sealed[0].journey_code)
    for cp in sealed:
        store.insert_checkpoint(cp)
    back = store.list_checkpoints(sealed[0].journey_code)
    assert [c.record_hash for c in back] == [c.record_hash for c in sealed]
    assert verify_chain(back)["status"] == "intact"


def test_old_store_is_upgraded_with_chain_columns(tmp_path):
    db = tmp_path / "old.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE checkpoints (id INTEGER PRIMARY KEY, journey_code VARCHAR, cp_index INTEGER, ts_utc DATETIME, "
                "device_id VARCHAR, operator_id VARCHAR, weights_json VARCHAR, scale_id VARCHAR, scale_status VARCHAR, "
                "calibration_date VARCHAR, images_json VARCHAR, seals_json VARCHAR, seal_qr VARCHAR, serial VARCHAR, imei VARCHAR, "
                "carrier_log VARCHAR, identifier_source VARCHAR, glare_reported BOOLEAN, permitted_packaging_change BOOLEAN, "
                "tare_delta_g FLOAT, app_version VARCHAR, created_at DATETIME)")
    con.commit()
    con.close()
    Store(db)
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(checkpoints)")}
    assert {"prev_record_hash", "record_hash"} <= cols


# ------------------------------------------------------------------ capture: live checks and sealing on upload
@pytest.fixture
def ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINETRA_DB_PATH", str(tmp_path / "store.sqlite"))
    monkeypatch.setenv("DEVICE_INGEST_TOKEN", TOKEN)
    from trinetra_link.ingest.api import app
    return TestClient(app)


def _photo(path):
    return {"file": ("top.jpg", path.read_bytes(), "image/jpeg")}


def test_photo_check_flags_dark_and_blurry_and_passes_good(ingest):
    h = {"X-Device-Token": TOKEN}
    good = ingest.post("/quality/photo", files=_photo(DEMO / "input1_Legitimate/images/CP1_TOP.jpg"), headers=h).json()
    assert good["ok"] and good["issues"] == []
    dark = ingest.post("/quality/photo", files=_photo(DEMO / "input3_Abstain_Degraded_Middle_Stop/images/CP3_TOP.jpg"), headers=h).json()
    assert not dark["ok"] and "dark" in {i["code"] for i in dark["issues"]}
    img = cv2.GaussianBlur(cv2.imread(str(DEMO / "input1_Legitimate/images/CP1_TOP.jpg")), (0, 0), 6)
    blur = ingest.post("/quality/photo", files={"file": ("b.jpg", cv2.imencode(".jpg", img)[1].tobytes(), "image/jpeg")}, headers=h).json()
    assert not blur["ok"] and "blur" in {i["code"] for i in blur["issues"]}
    glare = ingest.post("/quality/photo", files=_photo(DEMO / "input5_Abstain_Indistinguishable_Glare/images/CP3_TOP.jpg"), headers=h).json()
    assert "glare_spot" in {t["code"] for t in glare["tips"]}
    assert ingest.post("/quality/photo", files=_photo(DEMO / "input1_Legitimate/images/CP1_TOP.jpg")).status_code == 401


def test_readings_check(ingest):
    h = {"X-Device-Token": TOKEN}
    assert ingest.post("/quality/readings", json={"weights_g": [450, 451, 450]}, headers=h).json()["ok"]
    spread = ingest.post("/quality/readings", json={"weights_g": [450, 456, 450]}, headers=h).json()
    assert not spread["ok"] and spread["issues"][0]["code"] == "spread"
    assert ingest.post("/quality/readings", json={"weights_g": [], "scale_status": "ERROR"}, headers=h).json()["issues"][0]["code"] == "status"


def test_uploads_are_sealed_and_export_stays_verifiable(ingest, tmp_path):
    h = {"X-Device-Token": TOKEN}
    src = json.loads((PHONE / "journey.json").read_text(encoding="utf-8"))
    hashes = []
    for cp in src["checkpoints"]:
        files, client_hashes = [], {}
        for im in cp["images"]:
            b = (PHONE / im["path"]).read_bytes()
            name = {"TOP": "top", "LABEL": "front", "SEAL": "seal"}[im["side"]] + ".jpg"
            files.append(("files", (name, b, "image/jpeg")))
            client_hashes[name] = hashlib.sha256(b).hexdigest()
        meta = {k: cp[k] for k in ("weights_g", "scale_status", "seal_qr", "serial", "imei", "identifier_source",
                                   "glare_reported", "seals", "ts_utc")}
        meta.update(scale_id="SCALE-T", client_hashes=client_hashes, device_id="D", operator_id="O")
        r = ingest.post(f"/journeys/JRN-CHAIN/checkpoints/{cp['cp_index']}", files=files, data={"data": json.dumps(meta)}, headers=h)
        assert r.status_code == 201, r.text
        hashes.append(r.json()["record_hash"])
    assert len(set(hashes)) == 4 and all(hashes)
    exported = tmp_path / "Real_Inputs" / "JRN-CHAIN"
    assert verify_chain(load_folder(exported))["status"] == "intact"


# ------------------------------------------------------------------ dispute report
def test_report_is_a_one_page_pdf():
    from trinetra_link.console.app import create_console_app

    client = TestClient(create_console_app())
    r = client.get("/api/report/demo:input2_Stage_Fault_Return_Courier")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "DEMO-PHONE-0002" in r.headers["content-disposition"]
    assert client.get("/api/report/demo:..").status_code == 404


# ------------------------------------------------------------------ photo time and place
def _upload_with_meta(ingest, code, meta_for):
    h = {"X-Device-Token": TOKEN}
    src = json.loads((PHONE / "journey.json").read_text(encoding="utf-8"))
    for cp in src["checkpoints"]:
        files, client_hashes, photo_meta = [], {}, {}
        for im in cp["images"]:
            b = (PHONE / im["path"]).read_bytes()
            name = {"TOP": "top", "LABEL": "front", "SEAL": "seal"}[im["side"]] + ".jpg"
            files.append(("files", (name, b, "image/jpeg")))
            client_hashes[name] = hashlib.sha256(b).hexdigest()
            photo_meta[name] = meta_for(cp["cp_index"], name)
        meta = {k: cp[k] for k in ("weights_g", "scale_status", "seal_qr", "serial", "imei", "identifier_source",
                                   "glare_reported", "seals", "ts_utc")}
        meta.update(scale_id="SCALE-T", client_hashes=client_hashes, photo_meta=photo_meta, device_id="D", operator_id="O")
        r = ingest.post(f"/journeys/{code}/checkpoints/{cp['cp_index']}", files=files, data={"data": json.dumps(meta)}, headers=h)
        assert r.status_code == 201, r.text


def _now_local(minutes_ago=0):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone(timedelta(hours=5, minutes=30))) - timedelta(minutes=minutes_ago)).isoformat()


def test_photo_time_and_place_are_stored_sealed_and_stamped(ingest, tmp_path):
    from trinetra_link.integrity.stamp import provenance_checks

    base = {1: (12.9000, 80.1000), 2: (12.9500, 80.1500), 3: (12.9600, 80.1600), 4: (13.0000, 80.2000)}
    _upload_with_meta(ingest, "JRN-GEO", lambda k, n: {"captured_at": _now_local(1), "lat": base[k][0], "lon": base[k][1], "accuracy_m": 8})
    folder = tmp_path / "Real_Inputs" / "JRN-GEO"
    cps = load_folder(folder)
    assert all(im.lat is not None and im.captured_at for cp in cps for im in cp.images)
    assert all(cp.received_at_utc is not None for cp in cps)
    assert verify_chain(cps)["status"] == "intact"
    prov = provenance_checks(cps)
    assert prov["status"] == "ok" and len(prov["moves"]) == 3
    # the original is untouched; the stamped copy adds a strip below it
    from PIL import Image
    orig = Image.open(folder / "images" / "CP4_TOP.jpg")
    stamped = Image.open(folder / "images_stamped" / "CP4_TOP.jpg")
    assert stamped.height > orig.height and stamped.width == orig.width
    top4 = next(im for im in cps[3].images if im.side == "top")
    assert hashlib.sha256((folder / "images" / "CP4_TOP.jpg").read_bytes()).hexdigest() == top4.sha256
    # moving a photo's location afterwards breaks the chain
    _edit(folder, lambda j: j["checkpoints"][2]["images"][0].__setitem__("lat", 11.0))
    assert verify_chain(load_folder(folder))["status"] == "broken"


def test_old_or_scattered_photos_are_flagged(ingest, tmp_path):
    from trinetra_link.integrity.stamp import provenance_checks

    def meta(k, name):
        if k == 3 and name == "top.jpg":
            return {"captured_at": _now_local(180), "lat": 12.90, "lon": 80.10, "accuracy_m": 10}  # 3 h old
        if k == 4 and name == "seal.jpg":
            return {"captured_at": _now_local(1), "lat": 13.50, "lon": 80.10, "accuracy_m": 10}  # ~67 km away
        return {"captured_at": _now_local(1), "lat": 12.90, "lon": 80.10, "accuracy_m": 10}

    _upload_with_meta(ingest, "JRN-ODD", meta)
    prov = provenance_checks(load_folder(tmp_path / "Real_Inputs" / "JRN-ODD"))
    assert prov["status"] == "flagged"
    assert any("CP3" in f and "before the checkpoint was uploaded" in f for f in prov["flags"])
    assert any("CP4" in f and "apart" in f for f in prov["flags"])


def test_out_of_range_location_is_rejected(ingest):
    h = {"X-Device-Token": TOKEN}
    b = (PHONE / "images" / "CP1_TOP.jpg").read_bytes()
    meta = {"weights_g": [1, 1, 1], "scale_id": "S", "device_id": "D", "operator_id": "O",
            "photo_meta": {"top.jpg": {"lat": 123.0, "lon": 80.0}}}
    r = ingest.post("/journeys/JRN-BAD/checkpoints/1", files=[("files", ("top.jpg", b, "image/jpeg"))],
                    data={"data": json.dumps(meta)}, headers=h)
    assert r.status_code == 400


# ------------------------------------------------------------------ lessons from the first real captures
def test_reused_photo_is_flagged_and_warned(ingest, tmp_path):
    from trinetra_link.integrity.stamp import provenance_checks

    h = {"X-Device-Token": TOKEN}
    b = (PHONE / "images" / "CP1_TOP.jpg").read_bytes()
    meta = {"weights_g": [300, 300.2, 300.1], "scale_id": "S", "device_id": "D", "operator_id": "O"}
    r1 = ingest.post("/journeys/JRN-REUSE/checkpoints/1", files=[("files", ("top.jpg", b, "image/jpeg"))],
                     data={"data": json.dumps(meta)}, headers=h)
    assert r1.status_code == 201 and r1.json()["warnings"] == []
    r2 = ingest.post("/journeys/JRN-REUSE/checkpoints/2", files=[("files", ("top.jpg", b, "image/jpeg"))],
                     data={"data": json.dumps(meta)}, headers=h)
    assert r2.status_code == 201 and "same photo file as CP1 TOP" in r2.json()["warnings"][0]
    prov = provenance_checks(load_folder(tmp_path / "Real_Inputs" / "JRN-REUSE"))
    assert prov["status"] == "flagged" and any("CP2 TOP is the same photo file as CP1 TOP" in f for f in prov["flags"])


def test_cp1_reference_photo_for_framing_guide(ingest):
    h = {"X-Device-Token": TOKEN}
    b = (PHONE / "images" / "CP1_TOP.jpg").read_bytes()
    meta = {"weights_g": [300, 300.2, 300.1], "scale_id": "S", "device_id": "D", "operator_id": "O"}
    assert ingest.get("/journeys/JRN-REF/reference/top", headers=h).status_code == 404
    ingest.post("/journeys/JRN-REF/checkpoints/1", files=[("files", ("top.jpg", b, "image/jpeg"))],
                data={"data": json.dumps(meta)}, headers=h)
    r = ingest.get("/journeys/JRN-REF/reference/TOP", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert ingest.get("/journeys/JRN-REF/reference/seal", headers=h).status_code == 404
    assert ingest.get("/journeys/JRN-REF/reference/top").status_code == 401
