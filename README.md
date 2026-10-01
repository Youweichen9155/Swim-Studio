# Swim Studio

Bilingual, local swimming-behaviour analysis for single-animal videos. Calibrate a dish or rectangular tank, select head points, review direct-contact intervals, and export distance, speed, trajectories and analysis settings.

[中文说明](README_CN.md) · [Downloads](https://github.com/Youweichen9155/Swim-Studio/releases/latest) · [Quick start](DESKTOP_QUICKSTART.md)

## Download and open

| Platform | Download | Open after extracting |
| --- | --- | --- |
| macOS 15+, Apple Silicon | [Mac application](https://github.com/Youweichen9155/Swim-Studio/releases/download/v1.2.0/Swim-Studio-1.2.0-macOS-AppleSilicon.zip) | `Swim Studio.app` |
| Windows x64 | [Windows application](https://github.com/Youweichen9155/Swim-Studio/releases/download/v1.2.0/Swim-Studio-1.2.0-Windows-x64.zip) | `Swim Studio.exe` |

Python, CoTracker3 and model weights are included. No setup or first-run download is required. Extract the entire package; on Windows keep `_internal` beside the executable. The launcher opens your local browser. Keep it open while analysing.

These builds are not publisher-signed/notarized and may prompt for operating-system verification on first launch. The Mac package is for Apple Silicon, not Intel. The Windows package uses CPU tracking.

## Workflow

1. Import a single-animal video.
2. Select a circular/elliptical dish or rectangular tank and enter its real dimensions.
3. Select 4–6 stable head/eye points on the first frame.
4. Review direct stimulation contact and mark its start/end times, or confirm no contact.
5. Run analysis, check trajectories and the review video, and download results.

Recording FPS, frame sampling, model input size, crop and quality-control settings can be adjusted. Results include tables, PDF/PNG figures, configuration, contact intervals and provenance. Video analysis stays on your computer.

![Illustrated workflow](web/guide-en.svg)

## Source and validation

Source is available in this repository and in the release source archive. To run from source, install Python and `requirements-gui.txt`, then run `python tadpole_gui.py`. Source mode offers a separate first-time model setup; the ready-to-run downloads already include it.

- [Detailed English GUI guide](GUI_GUIDE.md) · [中文操作指南](GUI_GUIDE_CN.md)
- [Validation record](docs/VALIDATION.md) · [Methods](METHODS.md)
- [Command-line and frozen-example reproduction](CLI_REFERENCE.md)
- [Building desktop applications](BUILDING.md)

The included reproduction example contains de-identified cached trajectories and reviewed contact intervals. No original animal video is included.

## Third-party model

Tracking uses Meta's CoTracker3, pinned to a verified source commit and weight checksum. CoTracker carries **CC BY-NC 4.0** terms, including a non-commercial restriction. See [third-party notices](THIRD_PARTY_NOTICES.md) and the bundled licences.
