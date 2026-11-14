# TriNetra-Link Research Execution Status

**Protocol Version:** 2.6.0 (Amended)  
**Last Updated (UTC):** 2026-11-14  
**Active Git Branch:** `research/trinetra-link`

---

## 1. Study Gates Verification

| Gate | Protocol Requirement | Status | Verification Reference |
|---|---|---|---|
| **Gate G-1** | Protocol Amendment v2.6 committed and tagged `v2.6.0-amendment` | **PASSED** | Git tag `v2.6.0-amendment`, commit `7e4873c` |
| **Gate G-2** | Truth-ledger commitment manifest for 120 journeys (salted SHA-256) committed with determinability rule hash | **SUPERSEDED** | Regenerate with make_staging_kit.py before staging |
| **Gate G-3** | 10-journey pilot completed end-to-end; app, scale & SOP verified; quality floors frozen | **PENDING** | Awaiting physical pilot staging and capture sheets recorded by human operator |
| **Gate G-4** | Scale characterisation completed ($\ge 3$ loads $\times 30$ readings) and `scales.json` committed | **PENDING** | Awaiting physical scale readings ($\ge 3$ loads $\times 30$ readings) recorded by human operator |

---

## 2. Component Implementation Status

- [x] **Phase A: Core Method Package (`trinetra_link/`)**
  - Pydantic v2 schemas and SQLite append-only store (`store/`).
  - Metadata-only Quality Gate evaluating $q_k \in [0, 1]$ (`quality/`).
  - Multimodal Reconcilers: Weight anomaly testing, Identity parity rules 1–6, Homography visual change score (`reconcile/`).
  - Attribution Algorithm 1 (deterministic interval isolation) and Bayesian quality-exponent coalescence (`attribution/`).
  - Model fitting CLI `trinetra fit --split calibration` (`fit.py`).
  - **Tests:** 115 passing in `tests/`; 75% line coverage of `trinetra_link/` (2026-11-14).

- [x] **Phase B: Capture Path**
  - High-throughput FastAPI Ingest API (`ingest/api.py`).
  - Mobile web capture interface with live camera viewfinder & SHA-256 hashing (`ingest/static/capture.html`); refuses submissions without photos, records layered seals, identifier source and glare.
  - Native Android multipart client (`android/.../TriNetraLinkClient.kt`) — **not yet wired to the ingest API; use the web capture page for the study.**
  - Complete Mobile Capture Standard Operating Procedure (`docs/capture_SOP.md`).

- [x] **Phase C: Staging, Scale, and Truth Tools**
  - Empirical scale characterisation and noise fitting (`scale/characterise.py`).
  - Seeded 8-cell physical staging assignment for $N = 120$ packages (`staging/assign.py`).
  - Append-only physical staging log with overhead video SHA-256 tracking (`staging/log.py`).
  - Deterministic ground-truth derivation rule $\Omega^*$ (`staging/determinability.py`).
  - Stratified 24 calibration / 96 test split manifest (`staging/split.py`).
  - Gate G-3 pilot check verification (`staging/pilot.py`); refuses to pass without 10 captured, non-synthetic pilot journeys.

- [x] **Phase D: Baselines and Experiments**
  - Baseline B1: Terminal CP4-only rule (`baselines/b1_cp4.py`).
  - Baseline B2: Origin CP1 + Destination CP4 endpoints rule (`baselines/b2_endpoints.py`).
  - Baseline B3: Unlinked "detection = origin" sequential rule (`baselines/b3_unlinked.py`).
  - Baseline B4: Groq `llama-3.3-70b-versatile` LLM Judge with deterministic offline fallback (`baselines/b4_llm_judge.py`). The paper must report B4 only from a run with a real `GROQ_API_KEY`.
  - Baseline B5: Ported legacy V3 heuristic rules (`baselines/b5_v3_rules.py`).
  - Experiment E1: Primary benchmark evaluation, Table III generation (CSV/LaTeX), risk-coverage curves, bootstrap 95% CIs, exact McNemar tests (`eval/e1.py`).
  - Experiment E2: Controlled capture perturbations (drops, pixel-level blur and darkening, scale drift) (`eval/e2.py`).
  - Experiment E3: Architectural component ablations, including No Layered Seals (`eval/e3.py`).
  - E1–E3 load captured journeys from the store and refuse label-built journeys outside `--pipeline-self-test`.

- [x] **Phase E: Viewer, Documentation, and Reproducibility**
  - Blinded read-only research visualizer web application (`trinetra_link/viewer/`).
  - Comprehensive physical staging Standard Operating Procedure (`docs/staging_SOP.md`).
  - Standardized dataset documentation (`docs/datasheet.md`).
  - One-command reproduction script (`reproduce.sh`).
  - MIT / CC BY 4.0 licensing and Citation File Format (`CITATION.cff`).

---

## 3. Physical Trial Data Execution Status

0 real journeys collected. Only a watermarked synthetic dry run has been executed.
No courier network is involved; journeys will be staged by the team.


## 4. Review fixes (2026-11-14)

The November 2026 review found that several code paths could produce numbers that were not earned. All of the following are fixed and covered by tests (`tests/test_gap_fixes.py` and updated suites):

- Pilot check no longer fabricates passing fixtures; `fit` refuses an empty calibration split and loads journeys from the store.
- E1/E2/E3 run on captured journeys only; label-rebuilt journeys are allowed only as a watermarked self-test.
- E2 blur and darkening perturb pixels; DEG ground truth applies only when the perturbed checkpoint bounds the manipulation interval; E2/E3 use the fitted θ and scales.
- Seal layers that were not recorded are UNK, not INTACT; the No Layered Seals ablation keeps serial/IMEI/seal-QR identity checks.
- Glare and manual identifier entry are structured fields (`glare_reported`, `identifier_source`), not free-text keywords; the synthetic generator no longer leaks the answer through the legacy seal QR.
- Baselines B1–B3 treat missing weights as no evidence; empty subgroups report n/a; E1 reports customer misattribution per method.
- Operational policy maps each attribution to a distinct decision code.
- Ingest API: no default token, header-only token with constant-time compare, CORS off unless `TRINETRA_CORS_ORIGINS` is set; capture page has no pre-filled values and no mock-photo fallback.
- Packaging (`pyproject.toml`), pinned ruff, and `pytest tests/` in CI.
