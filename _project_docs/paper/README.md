# TriNetra-Link — IEEE conference paper (6 pages, IEEEtran)

## What is here
- `TriNetra_Link_IEEE_Conference.pdf`: the compiled paper (6 pages, two-column IEEE conference format).
- `latex/`: the full source. Upload this folder (zipped) to Overleaf with **New Project → Upload Project**; it compiles with pdfLaTeX.
  - `paper.tex` is the main file, and `refs.bib` holds the 23 references.
  - `gen/` contains the numbers and tables generated from the simulation results. Do not edit these by hand.
  - `fig/` contains Figures 1–3.
  - `scripts/` contains the scripts that regenerate `gen/` and `fig/` from a study run.

## Fill in before submitting
1. Authors: done (Sanjai L, Dharshan D, Kanagavel A. K., Dr. S. Shanmuga Priya, Dr. Lavanya G).
2. Acknowledgment: done (thanks the AI & DS department, Saveetha Engineering College).
3. Double-blind review: if the conference asks for it, replace the author block with "Anonymous Authors" and remove the GitHub link until the camera-ready version.
4. Check the conference's page limit. The paper is exactly 6 pages; most IEEE conferences allow 6, some allow 4+2 or 8.
5. Run IEEE PDF eXpress if the conference requires it, which is usually at the camera-ready stage.

## Honesty note
All results are from a simulation study, and the paper says so in the abstract, the Results and the Limitations sections. Do not describe them as real-parcel results. When the 120 physical journeys are captured, rerun the pipeline and replace the numbers.

## Regenerating the numbers
From the TriNetraAI repository root, with its virtual environment active. Run the main study first: each sweep waits for the main study's `fit_params.json`.
```
python -m trinetra_link.sim.run_study main --out results/sim
python -m trinetra_link.sim.run_study sweep --param sigma_multiplier --value 0.5 --out results/sim
# ...repeat for sigma_multiplier 1 2 4, nuisance_scale 0 1 2 4, pose_jitter_px 0 8 16 24
python PATH/TO/latex/scripts/make_results.py results/sim PATH/TO/latex
```
Then recompile `paper.tex`.
