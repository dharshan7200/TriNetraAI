# How to run and test TriNetra-Link on your Windows PC

Every step below was tested on a fresh download of the project (github.com/dharshan7200/TriNetraAI, main branch). Each step tells you what you should see when it has worked.

| Step | What it does | Time |
|---|---|---|
| 1 | Install Python and Git (one time) | 10 min |
| 2 | Download the project and install it | 2–3 min |
| 3 | Run the 141 automated tests | under 1 min |
| 4 | Run the demo pipeline | about 1 min |
| 5 | Open the TriNetra-Link Console (the main app) | 1 min |
| 6 | Run the full study pipeline on the 120 placeholder journeys | about 6 min |
| 7 | Re-run the simulation study behind the IEEE paper (optional) | 1–1.5 h, plus sweeps |
| 8 | Capture your own boxes with the phone capture page | 1 min to start |

---

## Step 1: Install Python and Git (one time)

1. **Python 3.12.** Download it from python.org/downloads. In the installer, tick **"Add python.exe to PATH"** before you click Install. Python 3.11 or newer works.
2. **Git for Windows.** Download it from git-scm.com and keep the default options. It also installs **Git Bash**, which you need in Step 6.

Open a new **PowerShell** window and check both are installed:

```powershell
python --version     # should say Python 3.12.x (3.11 or newer is fine)
git --version
```

## Step 2: Download the project and install it

Use a new folder. Don't reuse `C:\Users\admin\Downloads\trinetraai`, which still has the broken empty git setup from before.

```powershell
cd $HOME\Documents
git clone -b demo-inputs https://github.com/dharshan7200/TriNetraAI
cd TriNetraAI

python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell says *"running scripts is disabled on this system"*, run this once and then run the Activate line again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

When the environment is active, your prompt starts with `(.venv)`. Now install the project:

```powershell
$env:PYTHONUTF8 = "1"
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

> **Important:** `$env:PYTHONUTF8 = "1"` makes Python read and write text as UTF-8. Some outputs contain symbols such as θ, σ and —, which can fail with Windows' default encoding. Set it every time you open a new PowerShell window, together with the Activate line. To set it permanently, run `setx PYTHONUTF8 1` once and then open a new window.

**Every time you come back:** open PowerShell, then run `cd $HOME\Documents\TriNetraAI`, `.\.venv\Scripts\Activate.ps1` and `$env:PYTHONUTF8 = "1"`.

## Step 3: Run the automated tests

```powershell
python -m pytest tests -q
```

✅ **Expected:** `141 passed` (about 35 s). One warning is normal.

## Step 4: Run the demo pipeline

```powershell
python -m trinetra_link.cli demo run
```

✅ **Expected:** a table of methods and accuracies, ending with
`[PASS] All demo artifacts successfully watermarked: 'SYNTHETIC DRY RUN — NOT A RESULT'`

The outputs are in `results\SYNTHETIC_DRY_RUN_<date_time>\eval\`. Open the PNG files (risk–coverage figures) and the CSV tables. These demo numbers are synthetic fixtures, not results.

## Step 5: Open the TriNetra-Link Console (the main app)

```powershell
python -m trinetra_link.cli app
```

Open **http://127.0.0.1:8600** in Chrome or Edge.

1. **Pick a journey on the left.** The five demo journeys are there, and anything you capture appears under "Your captures".
2. **See the inputs.** Each checkpoint's photos, weights and seals show before you press anything.
3. **Press "Analyze journey".** A parcel moves CP1 → CP4, each checkpoint shows its trust score and state, and the verdict stamp drops.
4. **Read the verdict:** what happened, what to do, why, the evidence status, and the time-and-place check. Click any checkpoint to compare its photos with CP1.
5. **Press "Download report (PDF)"** for a one-page dispute report.

Press **Ctrl+C** in PowerShell to stop it. The older research viewer still works with `python -m trinetra_link.cli viewer --demo` (port 8501).

## Step 6: Run the full study pipeline on the 120 placeholder journeys

This is the same pipeline you will later run on the 120 real journeys, step for step. It checks the repository guards, runs the data linter and the tests, fits the thresholds on the 24 calibration journeys, and then runs experiments E1 (full and field masks), E2 and E3 on the 96 test journeys.

`reproduce.sh` is a bash script, so use **Git Bash**. In File Explorer, right-click inside the `TriNetraAI` folder, choose **"Open Git Bash here"**, then run:

```bash
source .venv/Scripts/activate
export PYTHONUTF8=1
PLACEHOLDER=1 bash reproduce.sh
```

✅ **Expected (about 6 min):**
- Four stages: `[1/4] … [4/4]`.
- `ALL REMEDIATION GUARDS PASSED`.
- The E1 table, for example `TriNetra-Link (Alg 1) | Acc (DET): 0.882 …`.
- An ablation summary.
- The last line: `Results written to results/reproduce_PLACEHOLDER_<date_time>/`.

That folder contains `e1_full`, `e1_field`, `e2`, `e3` and `fit.log`, each with CSV and LaTeX tables and PNG figures. Every file is marked **PLACEHOLDER — NOT A RESULT**. That's deliberate: the placeholder journeys are simulated.

## Step 7: Re-run the simulation study behind the IEEE paper (optional, long)

Run this in PowerShell (Step 2 environment active). It needs about **3 GB of free disk space**.

```powershell
python -m trinetra_link.sim.run_study main --out results\sim
```

The first line ("benchmark … 960 …") appears after a few minutes. The run takes **1–1.5 hours** and ends with `E3 done`.

✅ **Check it matches the paper:**
- The `fit` line shows `'local': (0.7, 0.06)` and `'global': (0.5, 0.7)`.
- In `results\sim\results\methods_full.json`, Algorithm 1 has stage accuracy **0.899**.

The run is deterministic (seed 2026), so you should get exactly the paper's numbers.

**Sensitivity sweeps (Fig. 3).** Start these only after the main study has finished, because each sweep waits for the main study's `fit_params.json`. If you start one first, it sits silently forever. Each sweep takes about 10–20 min:

```powershell
foreach ($v in 0.5,1,2,4) { python -m trinetra_link.sim.run_study sweep --param sigma_multiplier --value $v --out results\sim }
foreach ($v in 0,1,2,4)   { python -m trinetra_link.sim.run_study sweep --param nuisance_scale   --value $v --out results\sim }
foreach ($v in 0,8,16,24) { python -m trinetra_link.sim.run_study sweep --param pose_jitter_px   --value $v --out results\sim }
```

Each sweep prints `sweep <name>=<value> done` when it finishes.

**Rebuild the paper's numbers and figures from your run.** Unzip `TriNetra_Link_IEEE_Conference.zip`, for example to `$HOME\Documents\paper`, then run:

```powershell
python $HOME\Documents\paper\TriNetra_Link_IEEE_Conference\latex\scripts\make_results.py results\sim $HOME\Documents\paper\TriNetra_Link_IEEE_Conference\latex
```

✅ **Expected:** `ok 80 macros`. Then upload the `latex` folder to Overleaf, or compile it, to get the PDF with your own numbers.

## Step 8: Capture your own boxes with the phone capture page

```powershell
$env:DEVICE_INGEST_TOKEN = "choose-a-long-random-password-here"
python -m trinetra_link.cli serve --port 8000
```

- **On the same PC:** open **http://127.0.0.1:8000** and enter the same token in "Device Token".
- **From a phone on the same Wi-Fi:** find your PC's IPv4 address with `ipconfig` and open `http://192.168.x.x:8000` on the phone. The camera and location need the Chrome setting `chrome://flags` → "Insecure origins treated as secure" with that address. Allow Windows Firewall for Python (private networks) if asked.

What the page does for you:
- **Checks every photo immediately** (too dark, blurry, glare) and tells you how to fix it. Take the same side again to replace a photo.
- **Checks the three weighings** as you type them.
- **Records each photo's time and GPS location**, if you allow location.
- **Saves every checkpoint to `Real_Inputs\<journey code>\`**: `journey.json`, `readings.csv`, the original photos in `images`, and stamped copies (time and place printed under the photo) in `images_stamped`.
- **Seals each checkpoint** into the evidence chain. The console then shows "Evidence intact", or names what was changed.

Your captures appear in the console automatically. The three box capture sheets (Box A, B and C PDFs) say exactly what to enter at each checkpoint. Type your **real** scale readings.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| `python` opens the Microsoft Store or "not found" | Reinstall Python with "Add to PATH" ticked, or use `py -3.12` instead of `python` in Step 2 |
| "running scripts is disabled" | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `UnicodeEncodeError` / `charmap codec can't encode` | You forgot `$env:PYTHONUTF8 = "1"` (PowerShell) or `export PYTHONUTF8=1` (Git Bash) |
| `ModuleNotFoundError: trinetra_link` | The environment isn't active: run `.\.venv\Scripts\Activate.ps1` (PowerShell) or `source .venv/Scripts/activate` (Git Bash) |
| `bash: reproduce.sh` errors in PowerShell | Run Step 6 in **Git Bash**, not PowerShell |
| A sweep prints nothing for a long time | The main study (Step 7) hasn't finished; the sweep waits for it |
| Port 8501 / 8000 already in use | Add `--port 8502` (or another free number) |

## What is real and what is simulated

Everything you run today uses simulated data: the demo fixtures, the 120 placeholder journeys and the 960-journey simulation study. The software marks every output that way, and those outputs must not be reported as real-parcel results. Once the 120 real journeys are captured into the store (`docs/capture_SOP.md`), `bash reproduce.sh` (without `PLACEHOLDER=1`) runs the same pipeline on the real data, unchanged.
