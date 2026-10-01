#!/usr/bin/env python3
"""Cache-only numerical regression and edge-case tests for release v1.0."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tadpole_tracking.analysis import (  # noqa: E402
    EVENT_COLUMNS,
    REPEAT_COLUMNS,
    compute_motion,
    detect_stimulation_bouts,
    manual_contact_audit,
)
from tadpole_tracking.config import PROGRAM_VERSION, load_config  # noqa: E402
from tadpole_tracking.inputs import installed_software_versions, write_json  # noqa: E402
from tadpole_tracking.pipeline import run_analysis  # noqa: E402
from tadpole_tracking.plots import (  # noqa: E402
    save_repeat_distance_plot,
    save_repeat_trajectory_plot,
    save_stimulation_timeline,
)


EXPECTED_SOFTWARE = {
    "python": "3.12.13",
    "torch": "2.13.0",
    "torchvision": "0.28.0",
    "opencv-python-headless": "5.0.0.93",
    "numpy": "2.3.5",
    "pandas": "2.2.3",
    "scipy": "1.18.0",
    "matplotlib": "3.11.1",
}

FLOAT_TOLERANCES = {
    "total_analyzable_distance_mm": 1e-9,
    "mean_distance_2s_post_stimulus_mm": 1e-9,
    "median_distance_2s_post_stimulus_mm": 1e-9,
    "overall_mean_speed_mm_s": 1e-12,
    "analyzable_fraction": 1e-12,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--video",
        type=Path,
        help="Optional runtime video used only for metadata validation and SHA256.",
    )
    parser.add_argument("--keep-work", action="store_true")
    return parser.parse_args()


def _metric_checks(
    observed: dict[str, object], expected: dict[str, object]
) -> list[dict[str, object]]:
    checks = []
    for name, expected_value in expected.items():
        observed_value = observed[name]
        if isinstance(expected_value, int):
            error = abs(int(observed_value) - expected_value)
            tolerance = 0
        else:
            error = abs(float(observed_value) - float(expected_value))
            tolerance = FLOAT_TOLERANCES[name]
        checks.append(
            {
                "metric": name,
                "expected": expected_value,
                "observed": observed_value,
                "absolute_error": error,
                "tolerance": tolerance,
                "pass": bool(error <= tolerance),
            }
        )
    return checks


def _edge_case_checks(
    result: dict[str, object], config: dict[str, object], work: Path
) -> list[dict[str, object]]:
    table = result["table"].copy()
    fps = float(table["time_s"].iloc[1] - table["time_s"].iloc[0]) ** -1
    empty_intervals = pd.DataFrame(columns=["start_s", "end_s"]).astype(float)
    audit = manual_contact_audit(
        table["raw_frame"].to_numpy(np.int64), fps, empty_intervals
    )
    no_contact = int(audit["forceps_near_head"].sum()) == 0

    zero_table = table.copy()
    zero_table["forceps_near_head"] = False
    zero_table["forceps_present"] = False
    zero_table["forceps_distance_px"] = np.nan
    events, repeats, bout_ids = detect_stimulation_bouts(
        zero_table, fps, config["forceps_contact_review"]
    )
    zero_bouts = (
        events.empty
        and repeats.empty
        and list(events.columns) == EVENT_COLUMNS
        and list(repeats.columns) == REPEAT_COLUMNS
        and not bout_ids.any()
    )

    plot_directory = work / "edge_case_plots"
    plot_directory.mkdir(parents=True, exist_ok=True)
    save_repeat_distance_plot(repeats, plot_directory)
    save_repeat_trajectory_plot(
        zero_table.iloc[:3], repeats, config["dish_calibration"], plot_directory
    )
    save_stimulation_timeline(
        zero_table.iloc[:3],
        events,
        repeats,
        fps,
        config["forceps_contact_review"],
        plot_directory,
    )
    expected_plots = [
        "03_post_stimulus_repeat_distance.pdf",
        "04_post_stimulus_repeat_trajectories.pdf",
        "05_stimulation_timeline_and_response_windows.pdf",
    ]
    empty_plotting = all((plot_directory / name).is_file() for name in expected_plots)

    short_mm = np.asarray([[0.0, 0.0], [0.25, 0.0], [0.5, 0.0]])
    short_valid = np.asarray([True, True, True])
    short_result = compute_motion(
        short_mm,
        short_valid,
        30.0,
        config["analysis"],
    )
    short_video = (
        all(len(array) == 3 for array in short_result)
        and np.isfinite(short_result[3][1:]).all()
    )

    return [
        {
            "case": "empty_manual_interval_table",
            "pass": bool(no_contact),
            "detail": "Produces an all-false contact mask.",
        },
        {
            "case": "zero_stimulation_bouts",
            "pass": bool(zero_bouts),
            "detail": "Returns typed empty event/repeat tables and zero bout IDs.",
        },
        {
            "case": "empty_repeat_plotting",
            "pass": bool(empty_plotting),
            "detail": "Creates non-crashing placeholder plots for empty repeats.",
        },
        {
            "case": "three_frame_short_video_motion",
            "pass": bool(short_video),
            "detail": "Falls back safely when the Savitzky-Golay window is longer than the clip.",
        },
        {
            "case": "cache_only_did_not_run_model",
            "pass": bool(
                not result["provenance"]["run"]["model_was_run"]
                and "torch" not in sys.modules
            ),
            "detail": "The cache path does not import or execute torch/CoTracker.",
        },
    ]


def _markdown_report(report: dict[str, object]) -> str:
    lines = [
        "# Reproduction test report",
        "",
        f"- Release: {report['program_version']}",
        f"- Status: **{report['status']}**",
        f"- Mode: cache-only; CoTracker executed: {report['model_was_run']}",
        f"- Video SHA256 status: {report['video_sha256_status']}",
        f"- Video SHA256: `{report['video_sha256'] or 'not computed'}`",
        "",
        "## Numerical checks",
        "",
        "| Metric | Expected | Observed | Absolute error | Pass |",
        "|---|---:|---:|---:|:---:|",
    ]
    for check in report["metric_checks"]:
        lines.append(
            f"| {check['metric']} | {check['expected']} | {check['observed']} | "
            f"{check['absolute_error']:.3g} | {'yes' if check['pass'] else 'no'} |"
        )
    lines.extend(["", "## Edge cases", ""])
    for check in report["edge_case_checks"]:
        lines.append(
            f"- {'PASS' if check['pass'] else 'FAIL'}: `{check['case']}`. {check['detail']}"
        )
    lines.extend(["", "## Environment", ""])
    for check in report["software_checks"]:
        lines.append(
            f"- {'PASS' if check['pass'] else 'FAIL'}: `{check['software']}` "
            f"expected `{check['expected']}`, observed `{check['observed']}`."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    config_path = ROOT / "examples/configs/tadpole_recording_001.json"
    expected_path = ROOT / "tests/expected_metrics.json"
    work = ROOT / "tests/_reproduction_work"
    report_json = ROOT / "tests/reproduction_report.json"
    report_markdown = ROOT / "tests/reproduction_report.md"
    if work.exists():
        shutil.rmtree(work)
    config = load_config(config_path)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    result = run_analysis(
        config,
        config_path,
        video_override=args.video,
        output_override=work / "analysis_output",
        cache_only=True,
        skip_plots=True,
        skip_video_qa=True,
    )
    metric_checks = _metric_checks(result["summary"], expected)
    edge_checks = _edge_case_checks(result, config, work)
    observed_software = installed_software_versions()
    software_checks = [
        {
            "software": name,
            "expected": expected_version,
            "observed": observed_software.get(name),
            "pass": observed_software.get(name) == expected_version,
        }
        for name, expected_version in EXPECTED_SOFTWARE.items()
    ]
    passed = (
        all(check["pass"] for check in metric_checks)
        and all(check["pass"] for check in edge_checks)
        and all(check["pass"] for check in software_checks)
    )
    provenance = result["provenance"]
    report = {
        "program_version": PROGRAM_VERSION,
        "test_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "input_mode": provenance["run"]["input_mode"],
        "model_was_run": provenance["run"]["model_was_run"],
        "video_sha256_status": provenance["video"]["sha256_status"],
        "video_sha256": provenance["video"]["sha256"],
        "config_sha256": provenance["configuration"]["sha256"],
        "cache_sha256": provenance["tracking_cache"]["sha256"],
        "forceps_tsv_sha256": provenance["forceps_review"]["sha256"],
        "metric_checks": metric_checks,
        "edge_case_checks": edge_checks,
        "software_checks": software_checks,
    }
    write_json(report_json, report)
    report_markdown.write_text(_markdown_report(report), encoding="utf-8")
    if not args.keep_work:
        shutil.rmtree(work)
    print(f"Reproduction test: {report['status']}")
    print(report_markdown)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
