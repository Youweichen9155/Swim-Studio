# Validation record — Swim Studio 1.2.0

The local checks below were performed on macOS 15.7.3, Apple Silicon, Python 3.12.14. The Windows/macOS/Linux numerical checks and Windows/macOS browser checks passed on GitHub Actions. Packaged applications passed offline fresh-model tests on macOS and in the Windows build environment. See `mac-standalone-test.json` and `windows-standalone-test.json`.

## Numerical and application tests

`python tests/test_gui_analysis.py`: **10 tests passed**.

- Frozen recording: 4,657 tracked frames; 14 bouts; 340.6404826759847 mm strict distance; 15.90019593671791 mm mean and 11.705457312710088 mm median 2-s distance; 2.19661066484738 mm/s overall mean speed; 0.8359458879106721 analyzable fraction.
- All seven frozen metrics match within 1e-9; the original v1.0 software-lock report remains untouched.
- Four-corner perspective mapping, known physical distances, boundary QC, rotated ellipse versus legacy QC, invalid/degenerate corners and nonfinite/offscreen inputs.
- Rectangular-arena tables and plots; timebase override with preserved frame-index contact membership and recorded encoded FPS.
- Saved-project reload, app-owned output paths, review confirmation, incompatible-cache protection and late-contact rejection.

## Browser workflow

`tests/test_ui.cjs`: **passed** in an isolated local Chrome session on macOS. Checks include both interface languages, cached numerical results, ZIP download, saved result history, illustrated guide, synthetic-video upload/preview, four-corner calibration, head-point selection, contact validation, frame stepping, settings import/export, responsive layout at 390 px, token/Origin checks and no JavaScript exceptions. See `ui-test-report.json`.

## Model execution

A new 48-frame synthetic moving textured target was tracked using the pinned CoTracker3 source and verified checkpoint on CPU. **Passed:** 48 returned frames, 100% analyzable fraction, positive finite distance. This verifies the model/software path; it is not a biological accuracy benchmark. See `model-smoke-report.json` for package versions.

## Original study video: fresh full tracking

The original 1920 × 1080 recording (4,657 frames, approximately 155 s) was imported through the GUI and re-tracked on Apple MPS, using the original 100-mm calibration, six head points and reviewed contact intervals. The model was run from the raw video; the original trajectory cache was not reused for this step.

| Metric | Original audited result | Fresh GUI model run |
|---|---:|---:|
| Strict distance (mm) | 340.640482676 | 340.640446549 |
| Analyzable fraction | 0.835945888 | 0.835945888 |
| Independent stimulation bouts | 14 | 14 |
| Mean 2-s post-stimulus distance (mm) | 15.900195937 | 15.900195469 |

Distance differed by 0.000036127 mm (0.000010606%). Frame indices, query points and visibility masks were identical. The maximum difference in the frame-wise median head position was 0.000329 pixels. These small numerical differences do not change the displayed results. A 24-frame montage spanning the recording was visually checked for gross head-position drift; this is a spot-check, not a manually annotated accuracy benchmark.

The freshly computed trajectories were then reprocessed with the final application code to generate the final reports and the numbered-point QA video. This downstream rerun reused the fresh cache and did not rerun the model. The QA video contains all 4,657 frames; sampled early, contact and late frames were inspected.

## Remaining platform limits

- Windows x64 was validated in the GitHub Windows build environment; diverse end-user hardware has not been individually tested. The Mac build is for Apple Silicon, macOS 15+.
- The local MPS path passed the full real-video run above; CUDA is not tested here.
- Video format support depends on codecs. Constant-frame-rate input is assumed. Standalone bundles include Python, model and weights. They are not publisher-signed/notarized; operating-system verification prompts may appear.

## Packaging validation

The macOS `Invalid asset` issue caused by bundled resource symlinks was corrected. Final packaged tests check the HTML page, JavaScript, CSS and both SVG guides, then run the cached example and a fresh 48-frame model analysis with empty external caches and blocked download proxies. The native Mac launcher was verified to open the default browser, and the saved real-video project was reopened with its results.
