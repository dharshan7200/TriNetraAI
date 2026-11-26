# TriNetra-Link: Checkpoint Physical Capture Standard Operating Procedure (SOP)

**Document Version:** 2.6.0  
**Target:** Physical Checkpoints CP1, CP2, CP3, CP4  
**Applies to:** Field Operators, Staging Coordinators, and Ingest Clients  

---

## 1. Objective and Core Principles

This SOP defines the standardized, non-fabricable physical observation procedure across all four physical journey checkpoints:
- **CP1:** Origin hub intake, before forward transit (reference observation for every comparison)
- **CP2:** Carrier facility, after forward transit — closes stage **S1**
- **CP3:** Doorstep hand-over: delivery to the customer and collection of the return — closes stage **S2** (customer custody)
- **CP4:** Return processing hub, after reverse transit — closes stage **S3**

These definitions match the protocol (v2.5, amended v2.6) and the pipeline: an anomaly first seen at CP(k+1) after an intact CP(k) is attributed to stage S(k).

**Key Mandates:**
1. Zero simulated or invented measurements. Every weight, photo, and serial number must reflect genuine empirical capture.
2. In the absence of automated BLE telemetry, records must be entered truthfully with `scale_status = MANUAL`.
3. Checkpoints must be recorded in strict chronological sequence ($CP1 \to CP2 \to CP3 \to CP4$).

---

## 2. Photographic Evidence Protocol

### 2.1 Fixed Angles & Framing
For every parcel at each checkpoint, capture photographic evidence under the following standardized angles:
- **Surface 1: Front Face (Orthogonal)**
  - Angle: Perpendicular $90^\circ \pm 5^\circ$.
  - Distance: $35 \text{ cm} \text{ to } 45 \text{ cm}$.
  - Framing: The full package front surface (including shipping label and barcodes) must be centered within the viewfinder guide.
- **Surface 2: Top / Seal Surface (Orthogonal or Isometric)**
  - Angle: $90^\circ$ overhead or $45^\circ$ isometric.
  - Distance: $30 \text{ cm} \text{ to } 40 \text{ cm}$.
  - Framing: Clearly captures the primary tape seam, tamper-evident tape, and carton closure flaps.
- **Surface 3: Tamper Seal Close-Up (Macro)**
  - Angle: Perpendicular $90^\circ$.
  - Distance: $10 \text{ cm} \text{ to } 15 \text{ cm}$.
  - Framing: Macro focus directly on the security seal QR code and serrated tamper micro-perforations.
- **Surface 4: Back Surface (Orthogonal)**
  - Angle: Perpendicular $90^\circ$.
  - Distance: $35 \text{ cm} \text{ to } 45 \text{ cm}$.

### 2.2 Photo Count
- **Minimum Acceptable:** $\ge 2$ orthogonal surfaces (Front Face and Top/Seal Face).
- **Standard Protocol:** 4 images per checkpoint.

### 2.3 Lighting and Exposure Standards
- **Illumination:** Diffuse ambient lighting ($500 \text{ to } 1000 \text{ lux}$).
- **Glare Management:** Do not use direct, harsh on-camera flash directly perpendicular to glossy packaging tape. Angle flash or use ambient diffuse LED to maintain specular highlight fraction $< 15\%$.
- **Luminance Range:** Mean 8-bit grayscale luminance must satisfy $30 \le \bar{L} \le 240$.
- **Sharpness Floor:** Laplacian focus variance must satisfy normalized $\ge 0.10$ (sharp focus, zero hand-shake motion blur).
- **Resolution Floor:** Minimum $640 \times 480$ pixels; recommended $1280 \times 720$ pixels or higher.

---

## 3. Scale Telemetry Protocol (Three Repeated Weighings)

### 3.1 Equipment Setup
- Position the digital balance on a solid, level, vibration-free surface away from direct HVAC air currents.
- Power on the scale and ensure zero tare indicator reads exactly `0.00 g`.

### 3.2 Repeated Measurement Procedure
1. Place the parcel on the center of the weighing platform. Wait 2 seconds until the display weight settles.
2. Record **Reading 1** ($w_1$).
3. Remove parcel from platform completely. Verify zero return.
4. Replace parcel on platform. Record **Reading 2** ($w_2$).
5. Remove and replace parcel once more. Record **Reading 3** ($w_3$).

### 3.3 Stability and Status
- **Spread Tolerance:** The absolute spread $\max(w_1, w_2, w_3) - \min(w_1, w_2, w_3)$ must not exceed $2.0 \text{ g}$.
- **Scale Status:**
  - If BLE automatic stream is active: `scale_status = OK`.
  - If manual entry from digital display: `scale_status = MANUAL`.
  - If balance display fluctuates continuously: `scale_status = UNSTABLE`.
  - If scale shows overload or error code: `scale_status = ERROR`.

---

## 4. Legitimate Packaging Modifications (Tare Adjustment)

In operational logistics, legitimate package reinforcement (e.g. carrier adding protective over-taping, corner reinforcements, or repacking into a protective pouch) may occur:
1. If legitimate packaging modification occurred, select **Permitted Packaging Change = YES**.
2. Measure and record the tare weight of the added packaging material in grams under **Tare Delta ($g$)** (`tare_delta_g`).
3. Note the operational carrier justification in the **Carrier Custody Log Notes**.

---

## 5. Security Seal and Unit Identity

1. **Security Seal QR:** Scan or transcribe the alphanumeric payload of the tamper-evident security seal. If the seal has been cut, re-taped, peeled, or substituted, record the new seal payload and add custody notes.
2. **Layered seals:** For each layer (L1_FWD flyer seal, L1_RET return flyer seal from CP3, L2_BOX carton seal, L3_ITEM item seal) enter the ID read and its state (INTACT, TORN, MISSING, UNREADABLE). Leave a layer blank if it was not inspected; it is then scored as unknown, never as intact.
3. **Identifier source:** Under *How were seal, serial and IMEI obtained?* choose **Scanned** or **Typed from the label** when they were read directly from the parcel, and **Read off the photos** only when they came from the photos. Set *Glare over a seal or defect?* to **Yes** whenever reflections hid part of a surface, even after re-capture.
4. **Serial Number:** Record the external barcode serial number on the manufacturer label.
5. **IMEI:** For cellular devices, verify IMEI matches expected documentation.

---

## 6. Error Handling & Remediation Checklist

| Error Condition | Immediate Operator Action |
|---|---|
| **Quality Gate Warning: Underexposed / Dark Image** | Relocate parcel under direct overhead diffuse light. Re-capture photo. |
| **Quality Gate Warning: Blurry / Out of Focus** | Tap screen to refocus on package printed text. Hold camera steady; re-snap. |
| **Quality Gate Warning: High Specular Glare** | Tilt camera $10^\circ$ to prevent directional reflection off packing tape. |
| **Scale Spread Exceeds 2.0g** | Check for draft, cord tension, or uneven feet. Re-tare scale and re-weigh. |
| **Network Failure during Ingest Upload** | The capture page does not buffer offline. Keep the page open, restore the connection and press Submit again; if the page was closed, re-capture the checkpoint and note it in the custody log. |
| **Server Rejection: Hash Mismatch** | Local file corrupted during transmission. Re-submit form. |
