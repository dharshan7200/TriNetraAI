# input4_Abstain_No_Reference

**Product:** Running Shoes
**Journey code:** DEMO-SHOES-0004
**Expected output:** `ATTR_ABSTAIN_DEGRADED`

## Story
A pair of running shoes (900 g + 75 g packaging). The seller's dispatch record (CP1) is useless: the scale errored and the photos are dark and blurred. Later checkpoints are fine and the warehouse finds one shoe missing, but there is no trustworthy reference to compare against.

## What was recorded
| Checkpoint | Weight readings (g) | Note |
|---|---|---|
| CP1 Seller dispatch (origin hub) | scale ERROR | Seller packed in a dark store room: scale ERROR, photos dark and blurred |
| CP2 Delivered to customer | 974.46, 974.09, 975.53 | - |
| CP3 Return pickup from customer | 974.58, 975.32, 974.79 | - |
| CP4 Warehouse intake (return hub) | 654.20, 655.10, 655.53 | One shoe missing (320 g lighter) |

## Run it
From the TriNetraAI project folder (virtual environment active):
```
python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs/input4_Abstain_No_Reference
```

All images and readings in this folder are SIMULATED for demonstration.
