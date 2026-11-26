# TriNetra-Link: start here

This folder is the complete project: the code (from the `demo-inputs` branch on GitHub), the IEEE paper, the guides and sample outputs.

## Run it (Windows, PowerShell, inside this folder)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
python -m pip install -e ".[dev]"
python -m pytest tests -q                        # expect: 141 passed
python -m trinetra_link.cli app                  # TriNetra-Link Console -> http://127.0.0.1:8600
```
Full step-by-step instructions: `_project_docs/guides/RUN_GUIDE_WINDOWS.md`.

## What runs
| Command | What it is | Address |
|---|---|---|
| `python -m trinetra_link.cli app` | **Console**: pick a journey, press Analyze, read the verdict, download the PDF report | http://127.0.0.1:8600 |
| `python -m trinetra_link.cli serve` | **Capture page** for the phone: live photo and weight checks, time and GPS per photo, saves to `Real_Inputs/` (set `DEVICE_INGEST_TOKEN` first) | http://127.0.0.1:8000 |
| `python -m trinetra_link.cli viewer --demo` | Research viewer on the synthetic demo store | http://127.0.0.1:8501 |
| `python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs --all` | Runs the five demo journeys (one per output type) | terminal |
| `PLACEHOLDER=1 bash reproduce.sh` (Git Bash) | Whole study pipeline on 120 placeholder journeys | terminal |

## What is in `_project_docs/`
| Folder | Contents |
|---|---|
| `paper/` | IEEE conference paper: PDF, Word (.docx), and the LaTeX source for Overleaf |
| `guides/` | Windows run guide, mentor demo guide, every possible output explained, and the capture sheets for Box A, B and C |
| `samples/` | Two dispute reports produced by the console (demo inputs) |

## Honest status
- **Simulated results:** the paper's results come from a simulation study and say so. The demo inputs and placeholder journeys are simulated too, and are watermarked.
- **Real data:** the 120 real journeys are the next phase. The capture page and pipeline are ready for them.
