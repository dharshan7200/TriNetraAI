from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

from trinetra_link.schema.models import CheckpointObservation


def order_corner_points(pts: np.ndarray) -> np.ndarray:
    """Order coordinates: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def rectify_surface_homography(
    image: np.ndarray,
    corners: Optional[np.ndarray | List[List[float]]] = None,
    target_dim: Tuple[int, int] = (256, 256),
) -> np.ndarray:
    """
    Rectify parcel face using a 4-point homography projection.
    If corners are not specified, automatic corner contour detection is used,
    falling back to uniform full-frame scaling.
    """
    tw, th = target_dim
    dst_corners = np.array([
        [0, 0],
        [tw - 1, 0],
        [tw - 1, th - 1],
        [0, th - 1]
    ], dtype="float32")

    if corners is not None and len(corners) == 4:
        src_corners = order_corner_points(np.array(corners, dtype="float32"))
    else:
        # Automatic rectangular polygon detector
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_quad = None
        max_area = 0.0
        h_img, w_img = gray.shape[:2]

        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4:
                area = cv2.contourArea(approx)
                if area > 0.2 * (h_img * w_img) and area > max_area:
                    max_area = area
                    best_quad = approx.reshape(4, 2)

        if best_quad is not None:
            src_corners = order_corner_points(best_quad.astype("float32"))
        else:
            # Fallback to entire image frame
            src_corners = np.array([
                [0, 0],
                [w_img - 1, 0],
                [w_img - 1, h_img - 1],
                [0, h_img - 1]
            ], dtype="float32")

    M = cv2.getPerspectiveTransform(src_corners, dst_corners)
    rectified = cv2.warpPerspective(image, M, (tw, th))
    return rectified


def compute_visual_change_score(
    image_a: np.ndarray,
    image_b: np.ndarray,
    corners_a: Optional[np.ndarray | List[List[float]]] = None,
    corners_b: Optional[np.ndarray | List[List[float]]] = None,
) -> float:
    """
    Compute change score from structural dissimilarity: 1.0 - SSIM.
    Values range from 0.0 (identical structure) to 1.0 (complete divergence).
    """
    rect_a = rectify_surface_homography(image_a, corners_a)
    rect_b = rectify_surface_homography(image_b, corners_b)

    gray_a = cv2.cvtColor(rect_a, cv2.COLOR_BGR2GRAY) if rect_a.ndim == 3 else rect_a
    gray_b = cv2.cvtColor(rect_b, cv2.COLOR_BGR2GRAY) if rect_b.ndim == 3 else rect_b

    similarity = float(ssim(gray_a, gray_b))
    change_score = float(np.clip(1.0 - similarity, 0.0, 1.0))
    return round(change_score, 4)


def _ecc_run(moving: np.ndarray, fixed: np.ndarray, motion: int, init: np.ndarray,
             tmask_full: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """Coarse-to-fine ECC; returns a 3x3 warp (fixed -> moving coordinates) or None."""
    h, w = fixed.shape[:2]
    warp = init.astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
    try:
        for scale in (0.25, 0.5, 1.0):
            sw, sh = int(w * scale), int(h * scale)
            f = cv2.GaussianBlur(cv2.resize(fixed, (sw, sh)), (0, 0), 1.5).astype(np.float32)
            m = cv2.GaussianBlur(cv2.resize(moving, (sw, sh)), (0, 0), 1.5).astype(np.float32)
            tmask = None if tmask_full is None else cv2.resize(tmask_full, (sw, sh), interpolation=cv2.INTER_NEAREST)
            S = np.diag([scale, scale, 1.0]).astype(np.float32)
            Sinv = np.diag([1 / scale, 1 / scale, 1.0]).astype(np.float32)
            ws = (S @ warp @ Sinv).astype(np.float32)
            if motion == cv2.MOTION_AFFINE:
                _, a = cv2.findTransformECC(f, m, ws[:2].copy(), motion, criteria, tmask, 5)
                ws = np.vstack([a, [0, 0, 1]]).astype(np.float32)
            else:
                _, ws = cv2.findTransformECC(f, m, ws, motion, criteria, tmask, 5)
            warp = (Sinv @ ws @ S).astype(np.float32)
    except cv2.error:
        return None
    return warp


def _orb_warp(moving: np.ndarray, fixed: np.ndarray, tmask: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """Feature-based homography (ORB, ratio test, RANSAC); warp maps fixed -> moving coordinates."""
    orb = cv2.ORB_create(nfeatures=2000, fastThreshold=10)
    kf, df = orb.detectAndCompute(fixed, tmask)
    km, dm = orb.detectAndCompute(moving, None)
    if df is None or dm is None or len(kf) < 10 or len(km) < 10:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(df, dm, k=2)
    good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.8 * n.distance]
    if len(good) < 10:
        return None
    src = np.float32([kf[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([km[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 2.0)
    if H is None or inl is None or int(inl.sum()) < 10:
        return None
    return H.astype(np.float32)


def _ecc_warp(moving: np.ndarray, fixed: np.ndarray, ignore: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    """Best of identity, affine ECC and homography ECC by normalised correlation on the usable surface."""
    tmask = None if ignore is None else (ignore == 0).astype(np.uint8)
    use = np.ones(fixed.shape, bool) if ignore is None else ignore == 0
    eye = np.eye(3, dtype=np.float32)
    affine = _ecc_run(moving, fixed, cv2.MOTION_AFFINE, eye, tmask)
    homog = _ecc_run(moving, fixed, cv2.MOTION_HOMOGRAPHY, affine if affine is not None else eye, tmask)
    feat = _orb_warp(moving, fixed, tmask)
    refined = _ecc_run(moving, fixed, cv2.MOTION_HOMOGRAPHY, feat, tmask) if feat is not None else None
    fb = cv2.GaussianBlur(fixed, (0, 0), 1.5).astype(np.float32)
    best, best_res = None, np.inf
    for cand in (eye, affine, homog, feat, refined):
        if cand is None or not np.all(np.isfinite(cand)):
            continue
        warped = _apply_warp(cv2.GaussianBlur(moving, (0, 0), 1.5), cand, fixed.shape).astype(np.float32)
        valid = _apply_warp(np.full_like(moving, 255), cand, fixed.shape) > 200
        sel = valid & use
        if sel.sum() < 0.5 * sel.size:
            continue
        x, y = warped[sel], fb[sel]
        x, y = (x - x.mean()) / (x.std() + 1e-6), (y - y.mean()) / (y.std() + 1e-6)
        res = -float(np.mean(x * y))  # negative correlation: lower is better, invariant to exposure gain
        if res < best_res:
            best, best_res = cand, res
    return None if best is None or np.allclose(best, eye) else best


def _apply_warp(img: np.ndarray, warp: Optional[np.ndarray], shape: Tuple[int, int]) -> np.ndarray:
    if warp is None:
        return img
    return cv2.warpPerspective(img, warp, (shape[1], shape[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)


def compute_local_change_score(image_a: np.ndarray, image_b: np.ndarray, block: int = 24) -> float:
    """Registered local change score in [0, 1].

    Aligns B onto A by feature homography, normalises brightness, smooths sensor noise and
    surface texture, then returns the largest block-mean structural dissimilarity. Unlike the
    global 1 - SSIM score, a small local edit (cut tape, re-tape patch) dominates the score and
    small pose differences are removed by registration.
    """
    def specular(img: np.ndarray) -> np.ndarray:
        # Same definition as the quality gate: very bright and unsaturated pixels are glare, not surface.
        if img.ndim != 3:
            return np.zeros((240, 320), np.uint8)
        hsv = cv2.cvtColor(cv2.resize(img, (320, 240), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)
        raw = (((hsv[:, :, 2] > 240) & (hsv[:, :, 1] < 30)) * 255).astype(np.uint8)
        # Glare is one large saturated blob; scattered bright pixels on tape or paper are surface.
        raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(raw)
        keep = np.zeros_like(raw)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= 300:
                keep[labels == i] = 255
        return keep

    ga = cv2.cvtColor(image_a, cv2.COLOR_BGR2GRAY) if image_a.ndim == 3 else image_a
    gb = cv2.cvtColor(image_b, cv2.COLOR_BGR2GRAY) if image_b.ndim == 3 else image_b
    ga = cv2.resize(ga, (320, 240), interpolation=cv2.INTER_AREA)
    gb = cv2.resize(gb, (320, 240), interpolation=cv2.INTER_AREA)
    # Glare in either capture is excluded from alignment and from the change score.
    spec_any = cv2.dilate(np.maximum(specular(image_a), specular(image_b)), np.ones((41, 41), np.uint8))
    warp = _ecc_warp(gb, ga, ignore=spec_any)  # align B onto A; B's glare mask follows the same warp
    gb = _apply_warp(gb, warp, ga.shape)
    valid = _apply_warp(np.full_like(ga, 255), warp, ga.shape)
    spec_b = _apply_warp(specular(image_b), warp, ga.shape)
    if image_a.ndim == 3 and image_b.ndim == 3:
        # Glare brightens a region towards white relative to the other capture; tamper marks darken or
        # recolour it. Mask regions that became much brighter and whiter after exposure normalisation.
        hsv_a = cv2.cvtColor(cv2.resize(image_a, (320, 240), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv_b = cv2.cvtColor(_apply_warp(cv2.resize(image_b, (320, 240), interpolation=cv2.INTER_AREA), warp, ga.shape),
                             cv2.COLOR_BGR2HSV).astype(np.float32)
        va, vb = hsv_a[:, :, 2], hsv_b[:, :, 2]
        vb_n = vb * (np.median(va) / max(float(np.median(vb)), 1.0))
        va_n = va * (np.median(vb) / max(float(np.median(va)), 1.0))
        brighter_b = (vb > 225) & (hsv_b[:, :, 1] < 80) & (vb_n - va > 30)
        brighter_a = (va > 225) & (hsv_a[:, :, 1] < 80) & (va_n - vb > 30)
        rel = cv2.morphologyEx(((brighter_a | brighter_b) * 255).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        spec_b = np.maximum(spec_b, rel)
    # Score mask: only where glare differs between captures (a surface bright in both, such as tape, stays in).
    spec_a = specular(image_a)
    differs = np.maximum(cv2.subtract(spec_b, spec_a), cv2.subtract(spec_a, spec_b))
    glare = cv2.dilate(differs, np.ones((41, 41), np.uint8)) > 0
    fa, fb = ga.astype(np.float32), gb.astype(np.float32)
    m = cv2.erode((valid > 200).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0  # drop warp borders
    m &= ~glare
    margin = 12  # capture borders are replicated pixels, not parcel surface
    m[:margin, :] = False
    m[-margin:, :] = False
    m[:, :margin] = False
    m[:, -margin:] = False
    if m.sum() < 0.5 * m.size:
        m = np.ones_like(m, bool)
    fb = (fb - fb[m].mean()) / (fb[m].std() + 1e-6) * fa[m].std() + fa[m].mean()
    fa = cv2.GaussianBlur(fa, (0, 0), 1.5)
    fb = cv2.GaussianBlur(np.clip(fb, 0, 255), (0, 0), 1.5)
    _, smap = ssim(fa, fb, data_range=255.0, full=True)
    diss = np.where(m, 1.0 - smap, 0.0)
    cnt = m.astype(np.float32)
    hb, wb = diss.shape[0] // block, diss.shape[1] // block
    d = diss[: hb * block, : wb * block].reshape(hb, block, wb, block).sum(axis=(1, 3))
    c = cnt[: hb * block, : wb * block].reshape(hb, block, wb, block).sum(axis=(1, 3))
    means = np.where(c > 0.6 * block * block, d / np.maximum(c, 1.0), 0.0)
    return round(float(np.clip(means.max(), 0.0, 1.0)), 4)


_VISUAL_SCORE_CACHE: Dict[Tuple[str, str, str], float] = {}


def reconcile_visual(
    obs_baseline: CheckpointObservation,
    obs_current: CheckpointObservation,
    visual_threshold: float = 0.25,
    image_arrays_a: Optional[Dict[str, np.ndarray]] = None,
    image_arrays_b: Optional[Dict[str, np.ndarray]] = None,
    method: str = "global",
) -> Tuple[bool, Dict[str, float]]:
    """
    Multimodal visual surface reconciliation across corresponding package faces.
    Returns (is_visual_anomaly, per_side_change_scores).
    """
    side_scores: Dict[str, float] = {}
    is_anomaly = False

    # Map side -> ImageRef
    images_a = {img.side: img for img in obs_baseline.images}
    images_b = {img.side: img for img in obs_current.images}

    common_sides = set(images_a.keys()).intersection(images_b.keys())
    if not common_sides:
        return False, {}

    for side in common_sides:
        ref_a = images_a[side]
        ref_b = images_b[side]
        # Fast path 1: identical cryptographic hash or path guarantees 0.0 change score
        if (image_arrays_a is None and image_arrays_b is None) and (
            (ref_a.sha256 and ref_b.sha256 and ref_a.sha256 == ref_b.sha256) or (ref_a.path and ref_a.path == ref_b.path)
        ):
            side_scores[side] = 0.0
            continue

        # Fast path 2: cached comparison score (only when loaded from files)
        use_cache = (image_arrays_a is None and image_arrays_b is None) and bool(ref_a.path and ref_b.path)
        cache_key = (str(ref_a.path), str(ref_b.path), method) if use_cache else ("", "", "")
        if use_cache and cache_key in _VISUAL_SCORE_CACHE:
            score = _VISUAL_SCORE_CACHE[cache_key]
            side_scores[side] = score
            if score > visual_threshold:
                is_anomaly = True
            continue

        arr_a = image_arrays_a.get(side) if image_arrays_a else None
        arr_b = image_arrays_b.get(side) if image_arrays_b else None

        if arr_a is None and Path(images_a[side].path).exists():
            arr_a = cv2.imread(str(images_a[side].path))
        if arr_b is None and Path(images_b[side].path).exists():
            arr_b = cv2.imread(str(images_b[side].path))

        if arr_a is not None and arr_b is not None:
            if method == "local":
                score = compute_local_change_score(arr_a, arr_b)
            else:
                score = compute_visual_change_score(arr_a, arr_b)
            if use_cache and cache_key != ("", "", ""):
                _VISUAL_SCORE_CACHE[cache_key] = score
            side_scores[side] = score
            if score > visual_threshold:
                is_anomaly = True

    return is_anomaly, side_scores
