from __future__ import annotations

import pytest
from trinetra_link.fit import fit_thresholds
from trinetra_link.schema.models import Journey


def test_fit_rejects_test_split_name(tmp_path):
    with pytest.raises(ValueError, match="FITTING ISOLATION VIOLATION"):
        fit_thresholds([], split_name="test", output_dir=tmp_path)


def test_fit_rejects_test_journey_id(tmp_path):
    test_journey = Journey(
        journey_code="JRN-TEST-0042",
        status="COMPLETED",
        metadata={"split": "test"},
    )
    with pytest.raises(ValueError, match="Test journey"):
        fit_thresholds([test_journey], split_name="calibration", output_dir=tmp_path)


def _staging_log(tmp_path, code):
    path = tmp_path / "staging_log.csv"
    path.write_text(
        "journey_code,assigned_cell,manipulation_interval,degraded_checkpoint,glare_over_defect\n"
        f"{code},intact,none,none,no\n"
    )
    return path


def test_fit_succeeds_on_calibration_split(tmp_path):
    cal_journey = Journey(
        journey_code="JRN-CALIB-001",
        status="COMPLETED",
        metadata={"split": "calibration"},
    )
    res = fit_thresholds([cal_journey], split_name="calibration", output_dir=tmp_path,
                         staging_log_path=_staging_log(tmp_path, "JRN-CALIB-001"))
    assert 0.30 <= res["theta"] <= 0.90
    assert res["z_weight"] == 3.00
    assert res["tau_bayes"] == 0.80
    assert res["fitted_on_split"] == "calibration"


def test_fit_refuses_journey_without_staging_row(tmp_path):
    cal_journey = Journey(journey_code="JRN-CALIB-002", status="COMPLETED", metadata={"split": "calibration"})
    with pytest.raises(ValueError, match="no staging-log row"):
        fit_thresholds([cal_journey], split_name="calibration", output_dir=tmp_path,
                       staging_log_path=_staging_log(tmp_path, "JRN-OTHER"))


def test_fit_refuses_missing_staging_log(tmp_path):
    cal_journey = Journey(journey_code="JRN-CALIB-003", status="COMPLETED", metadata={"split": "calibration"})
    with pytest.raises(FileNotFoundError):
        fit_thresholds([cal_journey], split_name="calibration", output_dir=tmp_path,
                       staging_log_path=tmp_path / "absent.csv")
