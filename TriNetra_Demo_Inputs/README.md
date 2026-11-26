# TriNetra-Link Demo Inputs: one folder per output type

Five ready-made parcel journeys. Each one runs through the real TriNetra-Link pipeline and gives one specific output.
**Everything here is SIMULATED for demonstration.** The images carry a "SIMULATED DEMO IMAGE" watermark.

| Folder | Product | Expected output | What happened |
|---|---|---|---|
| `input1_Legitimate` | Cotton Dress | `ATTR_CONFIRMED_LEGITIMATE` | Returned unopened; nothing changed anywhere |
| `input2_Stage_Fault_Return_Courier` | Smartphone | `ATTR_STAGE_REVERSE_TRANSIT` (Stage S3) | Phone swapped for a dummy between return pickup and warehouse (85 g missing, seals changed, new serial/IMEI) |
| `input3_Abstain_Degraded_Middle_Stop` | Smartwatch | `ATTR_ABSTAIN_DEGRADED` | Watch missing at CP4, but CP3 (return pickup) had a scale ERROR and dark, blurred photos |
| `input4_Abstain_No_Reference` | Running Shoes | `ATTR_ABSTAIN_DEGRADED` | One shoe missing at CP4, but the seller's CP1 record is unusable, so there is no reference |
| `input5_Abstain_Indistinguishable_Glare` | Wireless Headphones | `ATTR_ABSTAIN_INDISTINGUISHABLE` | Box corner crushed; weight and seals unchanged; glare reported over the box at CP3 and CP4 |

## What each folder contains
```
inputN_.../
  journey.json          the 4 checkpoints: weight readings, scale, seals, serial/IMEI, photos, glare flag
  images/CP1_TOP.jpg    3 photos per checkpoint (TOP, LABEL, SEAL) x 4 checkpoints = 12 photos
  scales.json           scale calibration (noise sigma and drift delta per scale)
  expected_output.json  the output this journey should give
  README.md             the story and the recorded weights
  output.json           written when you run it
```

## How to run
Copy this `TriNetra_Demo_Inputs` folder into your `TriNetraAI` project folder. Then, in PowerShell:
```powershell
cd $HOME\Documents\TriNetra\TriNetraAI
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"

# one input
python TriNetra_Demo_Inputs\run_demo_input.py TriNetra_Demo_Inputs\input1_Legitimate

# all five, with a pass/fail summary
python TriNetra_Demo_Inputs\run_demo_input.py TriNetra_Demo_Inputs --all
```
The last line should read: `5/5 demo inputs gave the expected output`.

For each journey the runner prints:
- every checkpoint's weight, trust score q and state (INTACT, ANOM or UNK);
- the output label with its plain-English meaning;
- the reason and the operational decision;
- whether the output matches the expected one.

It uses the parameters fitted in the paper's simulation study: θ = 0.70, local visual score with γ = 0.06, weight test z = 3.

## Regenerating the inputs
`python TriNetra_Demo_Inputs\make_demo_inputs.py TriNetra_Demo_Inputs` rebuilds all five folders. The images and readings are produced from fixed seeds, so you get the same journeys every time.

## Evidence chain (tamper check)
Every checkpoint carries a fingerprint (`record_hash`). It covers the readings, the scale, the seals and IDs, the notes, and the SHA-256 of every photo, plus the fingerprint of the previous checkpoint (`prev_record_hash`). The capture server seals each upload the same way.

To see it work, copy a folder, change one weight in its `journey.json` (or replace one photo), and open it in the console (`python -m trinetra_link.cli app`). The page and the PDF report then say exactly which checkpoint was changed after capture.

## Photo time and location
The capture page records, for every photo, the phone's time (with its timezone) and its GPS location with an accuracy radius. It also records the server's own receive time for each checkpoint. All of these are sealed into the evidence chain, so changing a time or moving a location later breaks it.

The original photos are never altered, because the analysis compares them pixel by pixel and a printed stamp would look like a change. Stamped copies, with the journey, checkpoint, time and place printed in a strip under the photo, are shown in the console, used in the PDF report and saved to `Real_Inputs/<journey>/images_stamped/`.

The console and the report flag two problems that time and place make visible. One is a photo taken more than 15 minutes before its checkpoint was uploaded (an old photo may have been reused). The other is photos of one checkpoint taken more than 200 m apart. The demo inputs were generated without time or location, so they show "No photo time or location was recorded."

Location is personal data, because CP3 is usually a customer's home. The phone asks for permission, and if the operator refuses, photos are saved with time only.
