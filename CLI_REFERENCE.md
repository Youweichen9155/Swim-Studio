# Tadpole swimming trajectory and post-stimulus distance analysis v1.0

This is a standalone, configuration-driven release for:

1. multi-point tadpole head tracking with CoTracker3;
2. pixel-to-millimetre calibration from a fitted dish ellipse;
3. manually reviewed forceps-contact intervals;
4. strict non-contact distance, speed, and 2-s post-stimulus distance;
5. tabular, graphical, method, and provenance outputs.

The release does not contain the raw video. It does not use the legacy resolution-specific automatic forceps detector by default. The manually reviewed TSV is the primary stimulus input.

## Quick start

```bash
conda env create -f environment.yml
conda activate tadpole-swimming-tracking-v1

python prepare_config.py check \
  --config examples/configs/tadpole_recording_001.json

python tadpole_swimming_tracking.py \
  --config examples/configs/tadpole_recording_001.json \
  --cache-only
```

The last command reanalyses the included 182 KB cache and never runs CoTracker. Results are written to `example_run/tadpole_recording_001/`. Analysis tables and plots work without a video; video QA is skipped and the provenance records that no video SHA256 was computed.

## Reproduction test

```bash
python tests/run_reproduction_test.py
```

To validate video metadata and calculate its SHA256 at runtime without rerunning the model:

```bash
python tests/run_reproduction_test.py --video ./input/recording.mp4
```

The frozen reports are `tests/reproduction_report.md` and `tests/reproduction_report.json`.

Expected cache-only v1.0 results are 4,657 frames, 14 stimulation bouts, 340.6404827 mm strict distance, 15.9001959 mm mean 2-s distance, 11.7054573 mm median 2-s distance, 2.1966107 mm/s overall speed, and a 0.8359459 analyzable fraction.

## Per-video inputs

Each recording uses:

- one JSON configuration separating video metadata, model tracking, head-point selection, dish calibration, manual forceps review, and numerical analysis;
- one forceps interval TSV with `start_s` and `end_s`;
- either the original video or an audited CoTracker `.npz` cache.

The example TSV also contains `start_raw_frame` and `end_raw_frame`. These optional columns freeze reviewed frame membership when a six-decimal time boundary is close enough to a frame time to be ambiguous under floating-point comparison. They are recommended after frame-by-frame review.

Create a new configuration with `prepare_config.py init`; inspect it with `prepare_config.py check`. All JSON paths must be relative. Runtime overrides supplied with `--video`, `--cache`, or `--output` are not written to results.

## Full tracking

Fetch and verify the pinned model source:

```bash
python prepare_config.py fetch-model --config examples/configs/new_recording.json
```

Then run:

```bash
python tadpole_swimming_tracking.py \
  --config examples/configs/new_recording.json \
  --video ./input/new_recording.mp4 \
  --force-retrack
```

Model tracking, dish calibration, head-point selection, and manual contact review are independent QA stages. A change to any stage should be recorded in the corresponding JSON section or TSV and reviewed again.

## Outputs

- `tables/01_frame_level_head_trajectory.tsv`: frame-level coordinates, validity, distance, speed, and stimulation status;
- `tables/02_swimming_summary.tsv`: primary summary metrics;
- `tables/04_forceps_stimulation_bouts.tsv`: merged stimulation bouts;
- `tables/05_post_stimulus_repeat_metrics.tsv`: one 2-s response row per bout;
- `plots/`: PDF and 600 dpi PNG analysis figures;
- `video/tracked_head_QA.mp4`: optional video-based QA;
- `reports/01_effective_config.json`: effective configuration snapshot;
- `reports/02_parameter_manifest.tsv`: flattened parameter list;
- `reports/03_provenance.json`: program, input hashes, software, and model provenance.

See `METHODS.md` for the algorithm and `THIRD_PARTY_NOTICES.md` for model origin and the CoTracker non-commercial license reminder.

