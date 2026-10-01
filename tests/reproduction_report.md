# Reproduction test report

- Release: 1.0.0
- Status: **PASS**
- Mode: cache-only; CoTracker executed: False
- Video SHA256 status: computed_at_runtime
- Video SHA256: `0bcb933238da6b5c8f4d104846d046720c36a121245c9186d451e474e9781b6c`

## Numerical checks

| Metric | Expected | Observed | Absolute error | Pass |
|---|---:|---:|---:|:---:|
| tracked_frames | 4657 | 4657 | 0 | yes |
| independent_stimulation_bouts | 14 | 14 | 0 | yes |
| total_analyzable_distance_mm | 340.6404826759847 | 340.6404826759847 | 0 | yes |
| mean_distance_2s_post_stimulus_mm | 15.90019593671791 | 15.90019593671791 | 0 | yes |
| median_distance_2s_post_stimulus_mm | 11.705457312710088 | 11.705457312710088 | 0 | yes |
| overall_mean_speed_mm_s | 2.196610664847384 | 2.1966106648473827 | 1.33e-15 | yes |
| analyzable_fraction | 0.8359458879106721 | 0.8359458879106721 | 0 | yes |

## Edge cases

- PASS: `empty_manual_interval_table`. Produces an all-false contact mask.
- PASS: `zero_stimulation_bouts`. Returns typed empty event/repeat tables and zero bout IDs.
- PASS: `empty_repeat_plotting`. Creates non-crashing placeholder plots for empty repeats.
- PASS: `three_frame_short_video_motion`. Falls back safely when the Savitzky-Golay window is longer than the clip.
- PASS: `cache_only_did_not_run_model`. The cache path does not import or execute torch/CoTracker.

## Environment

- PASS: `python` expected `3.12.13`, observed `3.12.13`.
- PASS: `torch` expected `2.13.0`, observed `2.13.0`.
- PASS: `torchvision` expected `0.28.0`, observed `0.28.0`.
- PASS: `opencv-python-headless` expected `5.0.0.93`, observed `5.0.0.93`.
- PASS: `numpy` expected `2.3.5`, observed `2.3.5`.
- PASS: `pandas` expected `2.2.3`, observed `2.2.3`.
- PASS: `scipy` expected `1.18.0`, observed `1.18.0`.
- PASS: `matplotlib` expected `3.11.1`, observed `3.11.1`.
