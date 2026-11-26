# input1_Legitimate

**Product:** Cotton Dress
**Journey code:** DEMO-DRESS-0001
**Expected output:** `ATTR_CONFIRMED_LEGITIMATE`

## Story
A customer orders a cotton dress (380 g + 75 g packaging), it does not fit, and they return it unopened. Every checkpoint has good photos, a stable scale and intact seals.

## What was recorded
| Checkpoint | Weight readings (g) | Note |
|---|---|---|
| CP1 Seller dispatch (origin hub) | 454.68, 454.19, 455.24 | - |
| CP2 Delivered to customer | 454.71, 453.36, 454.59 | - |
| CP3 Return pickup from customer | 453.55, 454.09, 456.24 | - |
| CP4 Warehouse intake (return hub) | 455.37, 455.12, 454.62 | - |

## Run it
From the TriNetraAI project folder (virtual environment active):
```
python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs/input1_Legitimate
```

All images and readings in this folder are SIMULATED for demonstration.
