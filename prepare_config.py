#!/usr/bin/env python3
"""Create, inspect, and validate per-video analysis configurations."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from tadpole_tracking.analysis import validate_cache_against_config
from tadpole_tracking.config import (
    COTRACKER_CHECKPOINT_SHA256,
    COTRACKER_CHECKPOINT_URL,
    COTRACKER_COMMIT,
    COTRACKER_MODEL_NAME,
    COTRACKER_REPOSITORY_URL,
    PROGRAM_VERSION,
    SCHEMA_VERSION,
    ConfigError,
    load_config,
    resolve_config_path,
    validate_config,
)
from tadpole_tracking.inputs import (
    configured_video_metadata,
    load_forceps_intervals,
    load_tracking_cache,
    read_video_metadata,
    validate_video_metadata,
    write_json,
)
from tadpole_tracking.model_tracking import verify_cotracker_checkout


def _numbers(value: str, count: int, *, integers: bool = False) -> list[int | float]:
    values = value.split(",")
    if len(values) != count:
        raise argparse.ArgumentTypeError(f"Expected {count} comma-separated values")
    try:
        return [int(item) for item in values] if integers else [float(item) for item in values]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Values must be numeric") from exc


def _query_points(value: str) -> list[list[float]]:
    try:
        points = [[float(item) for item in pair.split(",")] for pair in value.split(";")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Query points must use x,y;x,y format") from exc
    if len(points) < 2 or any(len(point) != 2 for point in points):
        raise argparse.ArgumentTypeError("At least two x,y query points are required")
    return points


def _relative(path: Path, config_path: Path) -> str:
    return os.path.relpath(path.expanduser().resolve(), config_path.parent.resolve())


def _build_config(args: argparse.Namespace) -> tuple[dict[str, Any], Path | None]:
    output = args.output.expanduser().resolve()
    if args.video is not None:
        video_path = args.video.expanduser().resolve()
        metadata = read_video_metadata(video_path)
        video_relative = _relative(video_path, output)
    else:
        missing = [
            name
            for name in ("fps", "frame_count", "width_px", "height_px")
            if getattr(args, name) is None
        ]
        if missing:
            raise ConfigError(
                "Without --video, provide --fps, --frame-count, --width-px, and --height-px"
            )
        metadata = {
            "raw_fps": args.fps,
            "raw_frame_count": args.frame_count,
            "width_px": args.width_px,
            "height_px": args.height_px,
        }
        video_relative = f"../input/{args.logical_name}"

    package_root = Path(__file__).resolve().parent
    cache_path = (
        args.cache.expanduser().resolve()
        if args.cache is not None
        else output.parent / f"{args.analysis_id}_tracking_cache.npz"
    )
    if args.intervals is not None:
        intervals_path = args.intervals.expanduser().resolve()
        create_intervals = None
    else:
        intervals_path = output.parent / f"{args.analysis_id}_forceps_contacts.tsv"
        create_intervals = intervals_path
    config = {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": args.analysis_id,
        "video": {
            "logical_name": args.logical_name,
            "path": video_relative,
            "fps": float(metadata["raw_fps"]),
            "frame_count": int(metadata["raw_frame_count"]),
            "width_px": int(metadata["width_px"]),
            "height_px": int(metadata["height_px"]),
        },
        "model_tracking": {
            "repository_url": COTRACKER_REPOSITORY_URL,
            "commit": COTRACKER_COMMIT,
            "repository_path": _relative(package_root / "third_party/co-tracker", output),
            "model_name": COTRACKER_MODEL_NAME,
            "checkpoint_url": COTRACKER_CHECKPOINT_URL,
            "checkpoint_sha256": COTRACKER_CHECKPOINT_SHA256,
            "cache_path": _relative(cache_path, output),
            "frame_step": args.frame_step,
            "device": args.device,
            "roi_raw_px": _numbers(args.roi, 4, integers=True),
            "model_size_px": _numbers(args.model_size, 2, integers=True),
        },
        "head_point_selection": {
            "query_points_raw_px": _query_points(args.query_points),
            "drop_query_indices": [],
            "minimum_visible_points": 2,
            "maximum_spread_px": args.maximum_spread_px,
        },
        "dish_calibration": {
            "center_raw_px": _numbers(args.dish_center, 2),
            "ellipse_diameters_px": _numbers(args.dish_diameters, 2),
            "ellipse_angle_degrees": args.dish_angle,
            "dish_diameter_mm": args.dish_diameter_mm,
        },
        "forceps_contact_review": {
            "source": "manual_review",
            "intervals_tsv": _relative(intervals_path, output),
            "contact_episode_gap_s": 0.25,
            "stimulation_bout_gap_s": 2.0,
            "minimum_contact_duration_s": 0.12,
            "post_stimulus_window_s": 2.0,
        },
        "analysis": {
            "short_gap_interpolation_s": 0.5,
            "savgol_window_s": 0.5,
            "savgol_polynomial_order": 2,
            "display_interpolation_gap_s": 2.0,
            "maximum_speed_mm_s": 200.0,
            "maximum_normalized_dish_radius": 1.05,
        },
        "output": {
            "directory": f"../run_output/{args.analysis_id}",
            "make_plots": True,
            "make_video_qa": True,
        },
    }
    validate_config(config)
    return config, create_intervals


def command_init(args: argparse.Namespace) -> int:
    output = args.output.expanduser().resolve()
    if output.exists() and not args.overwrite:
        raise ConfigError(f"Refusing to overwrite existing config: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    config, create_intervals = _build_config(args)
    write_json(output, config)
    if create_intervals is not None and not create_intervals.exists():
        create_intervals.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=["start_s", "end_s"]).to_csv(
            create_intervals, sep="\t", index=False
        )
    print(output)
    return 0


def command_check(args: argparse.Namespace) -> int:
    config_path = args.config.expanduser().resolve()
    config = load_config(config_path)
    cache_path = (
        args.cache.expanduser().resolve()
        if args.cache is not None
        else resolve_config_path(config_path, config["model_tracking"]["cache_path"])
    )
    video_path = (
        args.video.expanduser().resolve()
        if args.video is not None
        else resolve_config_path(config_path, config["video"]["path"])
    )
    interval_path = resolve_config_path(
        config_path, config["forceps_contact_review"]["intervals_tsv"]
    )
    repository_path = resolve_config_path(
        config_path, config["model_tracking"]["repository_path"]
    )
    report: dict[str, Any] = {
        "program_version": PROGRAM_VERSION,
        "configuration": "valid",
        "video": "missing_optional_for_cache_reanalysis",
        "cache": "missing",
        "forceps_intervals": "missing",
        "cotracker_checkout": "not_installed",
    }
    if video_path.is_file():
        observed = read_video_metadata(video_path)
        validate_video_metadata(configured_video_metadata(config), observed)
        report["video"] = "valid"
    if cache_path.is_file():
        cache = load_tracking_cache(cache_path)
        validate_cache_against_config(cache, config)
        report["cache"] = f"valid ({len(cache['raw_frame_indices'])} frames)"
    intervals = load_forceps_intervals(interval_path)
    report["forceps_intervals"] = f"valid ({len(intervals)} intervals)"
    if repository_path.is_dir():
        commit = verify_cotracker_checkout(repository_path, config["model_tracking"]["commit"])
        report["cotracker_checkout"] = f"valid ({commit})"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable:
        return executable
    if Path("/usr/bin/git").exists():
        return "/usr/bin/git"
    raise ConfigError("git is required to fetch CoTracker")


def command_fetch_model(args: argparse.Namespace) -> int:
    config_path = args.config.expanduser().resolve()
    config = load_config(config_path)
    target = resolve_config_path(config_path, config["model_tracking"]["repository_path"])
    if target.exists():
        verify_cotracker_checkout(target, config["model_tracking"]["commit"])
        print(target)
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    git = _git_executable()
    # Download into a fresh temporary checkout, so an interrupted fetch is retryable.
    with tempfile.TemporaryDirectory(prefix="cotracker-fetch-", dir=target.parent) as folder:
        staged = Path(folder) / "source"
        commands = [
            [git, "init", str(staged)],
            [git, "-C", str(staged), "remote", "add", "origin", config["model_tracking"]["repository_url"]],
            [git, "-C", str(staged), "fetch", "--depth", "1", "origin", config["model_tracking"]["commit"]],
            [git, "-C", str(staged), "checkout", "--detach", "FETCH_HEAD"],
        ]
        for command in commands:
            subprocess.run(command, check=True)
        verify_cotracker_checkout(staged, config["model_tracking"]["commit"])
        staged.rename(target)
    print(target)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=PROGRAM_VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("init", help="Create a per-video JSON config.")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--analysis-id", required=True)
    create.add_argument("--logical-name", default="recording.mp4")
    create.add_argument("--video", type=Path)
    create.add_argument("--cache", type=Path)
    create.add_argument("--intervals", type=Path)
    create.add_argument("--fps", type=float)
    create.add_argument("--frame-count", type=int)
    create.add_argument("--width-px", type=int)
    create.add_argument("--height-px", type=int)
    create.add_argument("--frame-step", type=int, default=1)
    create.add_argument("--device", choices=["auto", "mps", "cuda", "cpu"], default="auto")
    create.add_argument("--roi", required=True, help="x0,y0,x1,y1")
    create.add_argument("--model-size", required=True, help="width,height")
    create.add_argument("--query-points", required=True, help="x,y;x,y;...")
    create.add_argument("--maximum-spread-px", type=float, required=True)
    create.add_argument("--dish-center", required=True, help="x,y")
    create.add_argument("--dish-diameters", required=True, help="x,y")
    create.add_argument("--dish-angle", type=float, required=True)
    create.add_argument("--dish-diameter-mm", type=float, required=True)
    create.add_argument("--overwrite", action="store_true")
    create.set_defaults(function=command_init)

    check = subparsers.add_parser("check", help="Validate config and available inputs.")
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--video", type=Path)
    check.add_argument("--cache", type=Path)
    check.set_defaults(function=command_check)

    fetch = subparsers.add_parser("fetch-model", help="Fetch the pinned CoTracker commit.")
    fetch.add_argument("--config", type=Path, required=True)
    fetch.set_defaults(function=command_fetch_model)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return int(args.function(args))
    except (ConfigError, FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
