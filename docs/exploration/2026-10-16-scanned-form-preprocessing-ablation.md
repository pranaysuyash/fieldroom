# Scanned-Form Preprocessing Ablation & Miss Taxonomy

**Date:** 2026-10-16  
**Status:** Promoted to `src/pdf_field_lab/raster_cv.py` (`_preprocess_scan_page`, `_estimate_skew_angle`, page-routed `detect_raster_targets`)  
**Closes:** `FFL-SCAN-001`, `FFL-MIX-007`

## 1. Problem Statement & Hypothesis

Prior to this study, `src/pdf_field_lab/raster_cv.py` binarized rendered pages using a single global cutoff (`cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)`) and passed the unnormalized image directly to Tesseract OCR (`--psm 6`). In addition, `analyze()` rendered and OCR-processed every page in a PDF whenever *any* page had fewer than 100 characters of native text (`FFL-MIX-007`).

That baseline fails on three common real-world scan degradations:

1. **Uneven scanner illumination / shadow gradients (`shaded`)**: When background paper brightness drops below `220` across part of the page, a global `220` threshold floods the shaded region into a single foreground blob, destroying rectangular contours and lowering OCR contrast.
2. **Washed-out / faint strokes (`faint`)**: Light grey or copier-faded form borders with pixel intensity $>220$ (e.g. `0.88` grey $\approx 224/255$) produce zero contour pixels under a global `220` threshold. When contours vanish, `detect_raster_targets` silently falls back to proposing a generic `220×24 pt` whitespace box to the right of every colon-terminated label—mis-sizing checkboxes (`16×16 pt`), underlines, and boxes placed below labels.
3. **Small scanner feed skew + sensor speckle (`skewed_noisy`)**: Even a $1.5^\circ\text{–}2.0^\circ$ page rotation causes a `330 pt` horizontal signature rule to span $\Delta y = 330 \sin(1.8^\circ) \approx 10.4\text{ pt}$, exceeding the `height <= 6 * page_scale` horizontal-line gate (`is_line`) and failing `approxPolyDP` 4-corner polygon approximation.

## 2. Preprocessing Architecture (`_preprocess_scan_page`)

We implemented a four-stage deterministic preprocessing pipeline in `src/pdf_field_lab/raster_cv.py`:

1. **Local Illumination Normalization**: Estimate local paper background via a scale-aware Gaussian blur ($\sigma = \max(15.0, 12.0 \times \text{scale})$) and compute foreground difference $\text{diff} = \max(0, \text{background} - \text{gray})$.
2. **Noise-Floor Estimation & Conditional Median Denoising**: Estimate the paper noise floor from the 75th percentile of `diff`. When scanner speckle elevates `noise_floor > 2.0`, apply a $3\times 3$ median filter (`cv2.medianBlur`) before recomputing `diff`.
3. **Adaptive Faint-Stroke Cutoff & OCR Contrast Normalization**: Measure the 85th percentile of foreground stroke differences (`stroke_strength`). When strokes are faint ($0 < \text{stroke\_strength} < 48$), scale the binarization cutoff down proportionally (`max(8, int(max(noise_floor * 2.5 + 5.0, stroke_strength * 0.42)))`) and contrast-stretch `ocr_pil` so Tesseract receives crisp dark text on a white background.
4. **Probabilistic Hough Small-Angle Deskew (`_estimate_skew_angle`)**: Detect horizontal form segments via `cv2.HoughLinesP`, take the median angle across segments within $[-6.5^\circ, +6.5^\circ]$, and when $|\theta_{\text{median}}| \ge 0.35^\circ$, counter-rotate both the grayscale page and contour mask via `cv2.warpAffine`.

## 3. Controlled Ablation Benchmark

### Benchmark Design

Each regime renders a 150 DPI image-only PDF containing **6 ground-truth fields** (`5` drawn geometric controls + `1` borderless whitespace field):

- `Applicant Name:` — `300×32 pt` text rectangle below label
- `Email:` — `300×32 pt` text rectangle below label
- `Agree to terms:` — `16×16 pt` checkbox rectangle below label
- `Date:` — `160 pt` horizontal rule below label
- `Authorized signature:` — `330 pt` horizontal signature rule below label
- `Address:` — borderless whitespace target to the right of colon-terminated label

A target is counted as **Geometry-Matched** only if its predicted `(kind, label)` matches ground truth **and** its bounding box achieves $\text{IoU} \ge 0.35$ against the ground-truth control geometry (preventing fallback `220×24 pt` whitespace guesses from counting as true hits on drawn boxes, checkboxes, or underlines).

### Quantitative Results

| Pipeline Variant | Scan Regime | Expected | Detected | Contour-Backed (`/5`) | Geometry-Matched (`/6`) | Geometry Recall | Geometry Precision | Latency (`ms`/page) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **V0: Fixed Threshold `220`** | `clean` | 6 | 6 | 5 | 6 | `1.000` | `1.000` | 279.4 |
| **V0: Fixed Threshold `220`** | `shaded` | 6 | 0 | 0 | 0 | `0.000` | `0.000` | 166.5 |
| **V0: Fixed Threshold `220`** | `faint` | 6 | 6 | 0 | 1 | `0.167` | `0.167` | 177.5 |
| **V0: Fixed Threshold `220`** | `skewed_noisy` | 6 | 0 | 0 | 0 | `0.000` | `0.000` | 368.3 |
| **V1: + Illumination Norm Only** | `clean` | 6 | 6 | 5 | 6 | `1.000` | `1.000` | 267.0 |
| **V1: + Illumination Norm Only** | `shaded` | 6 | 0 | 0 | 0 | `0.000` | `0.000` | 256.9 |
| **V1: + Illumination Norm Only** | `faint` | 6 | 6 | 5 | 6 | `1.000` | `1.000` | 329.2 |
| **V1: + Illumination Norm Only** | `skewed_noisy` | 6 | 0 | 0 | 0 | `0.000` | `0.000` | 444.4 |
| **V2: + Adaptive Cutoff & OCR Contrast** | `clean` | 6 | 6 | 5 | 6 | `1.000` | `1.000` | 293.0 |
| **V2: + Adaptive Cutoff & OCR Contrast** | `shaded` | 6 | 6 | 5 | 6 | `1.000` | `1.000` | 315.1 |
| **V2: + Adaptive Cutoff & OCR Contrast** | `faint` | 6 | 6 | 5 | 6 | `1.000` | `1.000` | 256.9 |
| **V2: + Adaptive Cutoff & OCR Contrast** | `skewed_noisy` | 6 | 5 | 3 | 3 | `0.500` | `0.600` | 465.6 |
| **V3: Full `_preprocess_scan_page` (+ Deskew)** | `clean` | 6 | 6 | 5 | 6 | **`1.000`** | **`1.000`** | 386.7 |
| **V3: Full `_preprocess_scan_page` (+ Deskew)** | `shaded` | 6 | 6 | 5 | 6 | **`1.000`** | **`1.000`** | 402.8 |
| **V3: Full `_preprocess_scan_page` (+ Deskew)** | `faint` | 6 | 6 | 5 | 6 | **`1.000`** | **`1.000`** | 338.5 |
| **V3: Full `_preprocess_scan_page` (+ Deskew)** | `skewed_noisy` | 6 | 6 | 5 | 6 | **`1.000`** | **`1.000`** | 639.8 |

## 4. Miss Taxonomy & Residual Boundaries

1. **Silent Whitespace Substitution on Faint Scans (Fixed in V1/V2)**:
   - *Mechanism*: When `cv2.threshold(gray, 220, ...)` missed faint borders (`>220` intensity), `geometry_regions` was empty, so the whitespace fallback emitted `220×24 pt` boxes to the right of every colon-ended label (`label_matched = 6/6`, but `geom_matched = 1/6`).
   - *Resolution*: Local background subtraction + adaptive stroke-strength thresholding restores all `5/5` contour detections (`geom_recall = 1.000`).
2. **Shaded Gradient Contrast Collapse (Fixed in V2)**:
   - *Mechanism*: Multiplicative illumination shading both reduces `diff = background - gray` in dark corners and lowers raw grayscale contrast for Tesseract.
   - *Resolution*: Adaptive cutoff + `diff`-based OCR contrast stretching recovers `6/6` fields on `shaded` pages.
3. **Rotated Horizontal Rule Thickening (Fixed in V3)**:
   - *Mechanism*: Without deskew (`V2`), a $1.8^\circ$ skew inflates axis-aligned bounding box height of wide horizontal lines (`Date:`, `Authorized signature:`) above `6 * page_scale`, causing `2/5` contours to drop out (`geom_recall = 0.500`).
   - *Resolution*: Hough line small-angle deskew (`V3`) restores axis alignment before contour extraction (`geom_recall = 1.000`).
4. **Known Residual Limits (Documented for Operator Review)**:
   - **Perspective / Camera Curl**: Affine deskew (`[-6.5°, +6.5°]`) corrects planar scanner rotation but does not uncurl mobile-camera perspective distortion.
   - **Dotted / Dashed Entry Lines**: Disconnected dots or dashes with gaps $>4\text{ px}$ do not form a single contour unless morphologically bridged; conservative horizontal morphological closing remains a candidate follow-up if dotted-line corpora are added.
   - **All raster/OCR detections remain review-required (`review_required=True`, confidence capped at `0.79`)** in accordance with project governance.
