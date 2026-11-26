# input5_Abstain_Indistinguishable_Glare

**Product:** Wireless Headphones
**Journey code:** DEMO-HEADPH-0005
**Expected output:** `ATTR_ABSTAIN_INDISTINGUISHABLE`

## Story
Wireless headphones (250 g + 75 g packaging). The box gets a crushed corner, but nothing is removed: the weight and all seals stay the same. The only evidence would be in the photos, and strong glare covers the box top at both the return pickup (CP3) and the warehouse (CP4).

## What was recorded
| Checkpoint | Weight readings (g) | Note |
|---|---|---|
| CP1 Seller dispatch (origin hub) | 325.51, 324.50, 325.17 | - |
| CP2 Delivered to customer | 325.45, 324.82, 324.35 | - |
| CP3 Return pickup from customer | 324.30, 324.45, 325.01 | Strong glare over the box top (reported) |
| CP4 Warehouse intake (return hub) | 325.05, 324.26, 324.51 | Strong glare over the box top (reported) |

## Run it
From the TriNetraAI project folder (virtual environment active):
```
python TriNetra_Demo_Inputs/run_demo_input.py TriNetra_Demo_Inputs/input5_Abstain_Indistinguishable_Glare
```

All images and readings in this folder are SIMULATED for demonstration.
