# input2_Stage_Fault_Return_Courier

**Product:** Smartphone
**Journey code:** DEMO-PHONE-0002
**Expected output:** `ATTR_STAGE_REVERSE_TRANSIT`

## Story
A smartphone (220 g + 75 g packaging) is delivered and returned by the customer intact. Between the return pickup (CP3) and the warehouse (CP4) the box is opened, the phone is swapped for a lighter dummy and the return flyer is re-sealed. The warehouse sees 85 g missing.

## What was recorded
| Checkpoint | Weight readings (g) | Note |
|---|---|---|
| CP1 Seller dispatch (origin hub) | 295.72, 294.71, 294.57 | - |
| CP2 Delivered to customer | 296.14, 294.92, 294.94 | - |
| CP3 Return pickup from customer | 294.98, 295.46, 296.27 | - |
| CP4 Warehouse intake (return hub) | 210.21, 209.64, 210.12 | Return flyer seal ID differs; item tag missing; box re-taped |

## Run it
From the TriNetraAI project folder (virtual environment active):
```
python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs/input2_Stage_Fault_Return_Courier
```

All images and readings in this folder are SIMULATED for demonstration.
