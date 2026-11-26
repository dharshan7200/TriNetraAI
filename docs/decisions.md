# TriNetra-Link Architectural & Protocol Decisions

This document logs key binding decisions made during the execution of the research protocol.

---

## Decision D-01: Protocol Amendment v2.6.0 (Gate E-3 Withdrawal)
- **Date:** 2026-10-26
- **Context:** Protocol v2.5 conditioned physical study on Gate E-3 (4 independent human reviewers with Fleiss' $\kappa \ge 0.60$).
- **Decision:** Gate E-3 is formally withdrawn. The study is an **algorithm + dataset paper** comparing TriNetra-Link to 5 algorithmic baselines (B1–B5) across physical experiments E1 (attribution accuracy & abstention), E2 (perturbation robustness), and E3 (architectural ablations). Ground truth is derived deterministically from the physical staging log via code committed and hashed prior to capture.

## Decision D-02: Staging Sample Size and Stratification
- **Date:** 2026-10-26
- **Context:** Scenario cells distribution across the study cohort.
- **Decision:** Total physical cohort fixed at $N=120$ journeys across 8 scenario cells (`intact`: 30, `permitted_flyer`: 12, `forward_transit_damage`: 14, `doorstep_substitution`: 14, `customer_tamper`: 14, `reverse_transit_tamper`: 12, `degraded_evidence`: 12, `ambiguous_evidence`: 12). Shuffled presentation order with fixed seed. Partitioned into a 24-journey calibration set and a 96-journey test set (`split_manifest.json`).

## Decision D-03: Baseline B4 (LLM Judge) Groq Integration & Offline Determinism
- **Status:** Superseded by D-07 (B4 removed).
- **Date:** 2026-10-26
- **Context:** Baseline B4 uses Groq `llama-3.3-70b-versatile` with temperature 0 and prompt `baselines/prompts/llm_judge_v1.txt`.
- **Decision:** When `GROQ_API_KEY` is present in the environment or `.env`, B4 executes live inference against Groq's API with 3 repeated runs. When `GROQ_API_KEY` is unset (such as in offline CI/testing environments), B4 executes a deterministic offline rule-based parser that faithfully mimics the prompt instructions without fabricated claims or network failure.

## Decision D-04: Baseline Scope (Text-Only vs Multimodal LLM)
- **Status:** Superseded by D-07 (B4 removed).
- **Date:** 2026-10-26
- **Context:** Evaluation of potential multimodal extension to Baseline B4.
- **Decision:** As specified in protocol v2.6, Baseline B4 is evaluated as a structured text judge over the 4 checkpoint observation records. Multimodal visual reasoning is benchmarked natively through TriNetra-Link's visual reconciler and homography matching.

## Decision D-05: Gate G-3 and Gate G-4 Set to PENDING Pending Human Physical Execution
- **Date:** 2026-10-26
- **Context:** Audit of Gate G-3 (10-journey physical pilot) and Gate G-4 (scale characterisation $\ge 3$ loads $\times 30$ readings).
- **Decision:** Gates G-3 and G-4 are formally set to **PENDING**. A study gate requiring physical activity can only pass when a human operator physically records that activity. Programmatic simulations or mock test fixtures cannot satisfy physical study gates.

## Decision D-06: Staging Assignment & Truth Manifest Superseded by make_staging_kit.py
- **Date:** 2026-10-26
- **Context:** Verification of physical staging assignment and truth manifest commitments.
- **Decision:** The staging assignment and truth manifest will be REGENERATED with `scripts/make_staging_kit.py` (incorporating layered security seals and weight-matched scenario cells) BEFORE any physical parcel staging occurs. The current pre-generated manifest is formally superseded; no physical journey has been staged under it.


## Decision D-07: Baseline B4 (LLM Judge) Removed
- **Date:** 2026-11-23
- **Context:** Protocol v2.5/v2.6 listed B4, a language-model judge (Llama 3.3 70B via Groq) reading the checkpoint records as text. It needed a paid external API key and was never run: every result so far was produced with B4 skipped.
- **Decision:** B4 is removed from the code, the CLI and the tests. The comparison uses B1 (CP4-only), B2 (endpoints CP1+CP4), B3 (detection equals origin) and B5 (ported V3 rules). The remaining baselines keep their original names, so tables still match the protocol.
- **Reason:** TriNetra-Link is a deterministic, explainable method. The question the study asks is whether interval attribution with a quality gate beats the rules used in practice, which B1, B2, B3 and B5 represent. A language model adds an external dependency, cost and run-to-run variability without answering that question.
- **Effect on the preregistration:** This is a deviation from protocol v2.6, recorded here and stated in the paper. The preregistration documents under `research/` are left unchanged as the dated record of what was planned.
