# Datasheet for Dataset: TriNetra Physical Supply-Chain Attribution Cohort

Standardized documentation following the *Datasheets for Datasets* framework (Gebru et al., *CACM* 2021).

> **Status (2026-11-14): planned dataset.** No journeys have been captured yet. This datasheet describes the dataset as designed; counts, dates and the commitment manifest must be filled in from the real capture before release.

---

## 1. Motivation

- **For what purpose was the dataset created?**  
  To evaluate algorithms for multimodal chain-of-custody verification and physical tamper attribution across supply chain transfer intervals. Unlike prior unimodal or synthetic benchmarks, TriNetra will capture physical manipulations staged by the team under controlled conditions, including real sensor noise, packaging tare changes, and deliberate capture degradations.
- **Who created the dataset and who funded it?**  
  Created by the TriNetra-Link Research Initiative under Protocol Amendment v2.6.0.
- **What grant or institutional support funded it?**  
  To be stated by the authors (no external funding is recorded in the repository).

---

## 2. Composition

- **What do the instances that comprise the dataset represent?**  
  Each instance represents a complete 4-checkpoint supply chain journey of a physical retail parcel:
  1. Intake Checkpoint 1 (CP1): Origin logistics fulfillment center.
  2. Transit Checkpoint 2 (CP2): Carrier facility, after forward transit (end of S1).
  3. Handover Checkpoint 3 (CP3): Doorstep hand-over to the customer and collection of the return (end of S2).
  4. Disposition Checkpoint 4 (CP4): Return processing hub, after reverse transit (end of S3).
- **How many instances are there in total?** (planned)  
  - $N = 120$ physical evaluation journeys.
  - $N = 10$ pilot calibration journeys (`PILOT-01` .. `PILOT-10`, strictly excluded from all benchmarks).
  - Total checkpoint observations: 480 evaluation observations + 40 pilot observations.
- **What is the breakdown across scenario cells?**  
  The 120 evaluation journeys are partitioned across 8 canonical supply-chain scenario cells:
  1. `intact`: $n = 30$ (Legitimate transit, zero physical tampering).
  2. `permitted_flyer`: $n = 12$ (Legitimate logistics tare adjustment, +15.0g flyer-bag addition).
  3. `forward_transit_damage`: $n = 14$ (Mechanical carton breach in forward transit $S_1$).
  4. `doorstep_substitution`: $n = 14$ (Substituted item surrogate at customer delivery point $S_1$).
  5. `customer_tamper`: $n = 14$ (Item extracted / counterfeit seal applied during custody $S_2$).
  6. `reverse_transit_tamper`: $n = 12$ (Pilferage in reverse carrier leg $S_3$).
  7. `degraded_evidence`: $n = 12$ (Staged tamper with bounding checkpoint sensor failure or underexposure).
  8. `ambiguous_evidence`: $n = 12$ (Staged tamper with bounding checkpoints obscured by deliberate glare).
- **Does the dataset contain all possible instances or a sample?**  
  A balanced, staged sample designed to stress-test multimodal attribution under both intact handling and sophisticated physical tampering.
- **What data does each instance contain?**  
  - Checkpoint metadata (device UUID, operator ID, timestamps in UTC).
  - Repeated digital weight readings (minimum 3 readings per checkpoint) and scale health status.
  - Security seal QR code payloads, serial numbers, and IMEI identifiers.
  - Multi-surface photographic evidence (TOP, FRONT, SEAL) with SHA-256 byte digests.

---

## 3. Collection Process

- **How were data collected?**  
  Physical packages will be handled according to the Standard Operating Procedures (`docs/staging_SOP.md` and `docs/capture_SOP.md`).
- **What mechanisms will be used to record data?**  
  - Handheld mobile web capture client (`trinetra_link/ingest/static/capture.html`) connected to FastAPI server.
  - Digital commercial bench scales characterized for empirical Gaussian noise $\sigma$ and linearity drift $\delta$.
  - Continuous overhead 1080p video recording of all staging manipulations.
- **Who will be involved in the data collection process?**  
  Team members acting as stagers and, separately, as capture operators who do not see the staging assignment.

---

## 4. Preprocessing, Cleaning & Labeling

- **Will any preprocessing/cleaning be done?**  
  Photographic evidence will be preserved as raw captures alongside normalized 4-corner planar homography projections. Scale readings will be preserved as raw floats.
- **How will ground truth be determined?**  
  Under Protocol Amendment v2.6.0, ground truth will not rely on subjective human reviewers. It is derived deterministically from the filmed physical staging log via code committed to the repository before capture starts (Gate G-2):
  - Determinability $\Omega^* \in \{\text{OBS\_DETERMINABLE}, \text{OBS\_DEGRADED\_INCOMPLETE}, \text{OBS\_INDISTINGUISHABLE}\}$.
  - Ground-truth stage label $\in \{\text{ATTR\_CONFIRMED\_LEGITIMATE}, \text{ATTR\_STAGE(1)}, \text{ATTR\_STAGE(2)}, \text{ATTR\_STAGE(3)}, \text{ATTR\_ABSTAIN\_DEGRADED}, \text{ATTR\_ABSTAIN\_INDISTINGUISHABLE}\}$.
- **Will a commitment procedure be used?**  
  Yes. Before capture starts, a salted SHA-256 commitment manifest will be generated (`trinetra truth commit`) and committed with the hash of the determinability-rule code (Gate G-2). The earlier manifest is superseded and must be regenerated from `scripts/make_staging_kit.py`.

---

## 5. Uses

- **Has the dataset been used for tasks before?**  
  Not yet. It is intended to evaluate the TriNetra-Link framework against 5 baseline methods (B1: CP4-only, B2: Endpoints, B3: Unlinked first-detection, B4: Groq LLM Judge, B5: Ported V3 rules), controlled sensor perturbations (E2), and architectural ablations (E3).
- **What tasks should the dataset NOT be used for?**  
  Not intended for facial or biometric identification. The capture SOP keeps faces and personal data out of frame; any image that shows them must be removed before release.

---

## 6. Distribution & Maintenance

- **How will the dataset be distributed?**  
  Under the Open Data Commons / Creative Commons Attribution 4.0 International (CC BY 4.0) license. Staging sheets and ground truth files are embargoed in `data/restricted/` to preserve double-blinding during blind evaluations.
- **Who maintains the dataset?**  
  The authors, via the GitHub repository's issues and releases.
