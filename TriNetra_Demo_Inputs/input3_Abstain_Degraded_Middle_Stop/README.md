# input3_Abstain_Degraded_Middle_Stop

**Product:** Smartwatch
**Journey code:** DEMO-WATCH-0003
**Expected output:** `ATTR_ABSTAIN_DEGRADED`

## Story
A smartwatch (62 g + 75 g packaging) is delivered fine. The return pickup (CP3) happens at night: the scale shows ERROR and the photos are dark and blurred. At the warehouse (CP4) the watch is missing. It could have been taken by the customer or by the return courier.

## What was recorded
| Checkpoint | Weight readings (g) | Note |
|---|---|---|
| CP1 Seller dispatch (origin hub) | 136.69, 136.82, 136.65 | - |
| CP2 Delivered to customer | 136.40, 137.58, 137.02 | - |
| CP3 Return pickup from customer | scale ERROR | Night pickup: scale showed ERROR, photos dark and blurred |
| CP4 Warehouse intake (return hub) | 95.20, 95.18, 95.01 | Box seal ID differs; item tag missing |

## Run it
From the TriNetraAI project folder (virtual environment active):
```
python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs/input3_Abstain_Degraded_Middle_Stop
```

All images and readings in this folder are SIMULATED for demonstration.
