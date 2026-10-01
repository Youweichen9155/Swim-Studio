#!/usr/bin/env python3
"""Run tadpole swimming trajectory and post-stimulus distance analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tadpole_tracking.config import ConfigError, PROGRAM_VERSION, load_config
from tadpole_tracking.pipeline import run_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configuration-driven tadpole swimming trajectory analysis."
    )
    parser.add_argument("--version", action="version", version=PROGRAM_VERSION)
    parser.add_argument("--config", type=Path, required=True, help="Per-video JSON config.")
    parser.add_argument(
        "--video",
        type=Path,
        help="Runtime video override. Its absolute path is never written to results.",
    )
    parser.add_argument("--cache", type=Path, help="Runtime tracking-cache override.")
    parser.add_argument("--output", type=Path, help="Runtime output-directory override.")
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Require and reuse the tracking cache; never run CoTracker.",
    )
    parser.add_argument(
        "--force-retrack",
        action="store_true",
        help="Ignore an existing cache and run the pinned CoTracker model.",
    )
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--skip-video-qa", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config_path = args.config.expanduser().resolve()
        config = load_config(config_path)
        result = run_analysis(
            config,
            config_path,
            video_override=args.video,
            cache_override=args.cache,
            output_override=args.output,
            cache_only=args.cache_only,
            force_retrack=args.force_retrack,
            skip_plots=args.skip_plots,
            skip_video_qa=args.skip_video_qa,
        )
    except (ConfigError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = result["summary"]
    print(f"Output: {result['output_root']}")
    print(f"Tracked frames: {summary['tracked_frames']}")
    print(f"Stimulation bouts: {summary['independent_stimulation_bouts']}")
    print(f"Strict distance (mm): {summary['total_analyzable_distance_mm']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

