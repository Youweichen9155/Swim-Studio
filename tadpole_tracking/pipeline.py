"""End-to-end configuration-driven analysis pipeline."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .arena import describe as describe_arena
from .modes import animal_mode, hindlimb_enabled, tracking_queries

from .analysis import (
    apply_query_exclusions,
    build_track_table,
    calibration_table,
    detect_stimulation_bouts,
    forceps_parameter_table,
    make_summary,
    manual_contact_audit,
    sensitivity_tables,
    validate_cache_against_config,
)
from .config import (
    PROGRAM_VERSION,
    effective_config,
    flatten_parameters,
    resolve_config_path,
)
from .inputs import (
    configured_video_metadata,
    installed_software_versions,
    load_forceps_intervals,
    load_tracking_cache,
    read_video_metadata,
    save_tracking_cache,
    sha256_file,
    validate_video_metadata,
    write_json,
)
from .model_tracking import track_video
from .plots import (
    save_analysis_plots,
    save_annotated_video,
    save_stimulation_qa_montage,
    save_tracking_qa_montage,
)


def setup_output_directories(root: Path) -> dict[str, Path]:
    paths = {
        name: root / name for name in ("tables", "plots", "reports", "video", "cache")
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _write_method_note(
    path: Path,
    config: dict[str, Any],
    summary: dict[str, Any],
    interval_count: int,
    input_mode: str,
) -> None:
    calibration = config["dish_calibration"]
    head = config["head_point_selection"]
    review = config["forceps_contact_review"]
    analysis = config["analysis"]
    target = "body reference" if animal_mode(config) == "frog" else "head"
    text = f"""# {animal_mode(config).capitalize()} swimming trajectory analysis

- Program version: {PROGRAM_VERSION}.
- Input mode: {input_mode}. CoTracker was not run when the tracking cache was reused.
- The {target} position is the frame-wise median of {len(head['query_points_raw_px']) - len(head['drop_query_indices'])} retained, jointly propagated selected points. Frames require at least {head['minimum_visible_points']} visible points and median point spread <= {head['maximum_spread_px']:g} px.
- {describe_arena(calibration)}
- The primary forceps input is the manually reviewed TSV ({interval_count} intervals). No legacy resolution-specific automatic forceps detector is used.
- Contact episodes bridge gaps <= {review['contact_episode_gap_s']:.2f} s and must last >= {review['minimum_contact_duration_s']:.2f} s. Episodes separated by <= {review['stimulation_bout_gap_s']:.2f} s form one stimulation bout.
- Contact frames are excluded before strict motion calculation. Gaps <= {analysis['short_gap_interpolation_s']:.2f} s are linearly interpolated, then coordinates are smoothed with a {analysis['savgol_window_s']:.2f}-s, order-{analysis['savgol_polynomial_order']} Savitzky-Golay filter.
- Post-stimulus distance is strict non-contact distance in the {review['post_stimulus_window_s']:.2f} s after each bout. Bouts are repeated observations from one recording, not independent biological replicates.
- Result: {summary['tracked_frames']} frames, {summary['independent_stimulation_bouts']} bouts, strict distance {summary['total_analyzable_distance_mm']:.6f} mm, analyzable fraction {summary['analyzable_fraction']:.6f}.
- Distance accuracy is limited by perspective, dish fitting, nominal dish diameter, video compression, point selection, and manual contact annotation.
"""
    if animal_mode(config) == "frog":
        text += "\n- Frog mode uses visible trunk points. Direct-contact intervals split the trajectory before interpolation and smoothing.\n"
        if hindlimb_enabled(config):
            text += "- Hindlimb spread is the posterior silhouette x95-x05 span in a physically scaled, body-aligned view. A fixed posterior cutoff is estimated from the median torso cutoff across usable frames. Contact, invisible axis points and invalid segmentation are excluded without interpolation. Review the mask montage/video; this is not anatomical toe separation.\n"
    path.write_text(text, encoding="utf-8")


def _program_hashes() -> dict[str, str]:
    from .runtime import frozen, build_record
    if frozen():
        return build_record()['source_sha256']
    package_root = Path(__file__).resolve().parents[1]
    files = [package_root / "tadpole_swimming_tracking.py", package_root / "prepare_config.py"]
    files.extend(sorted((package_root / "tadpole_tracking").glob("*.py")))
    return {
        str(path.relative_to(package_root)): sha256_file(path)
        for path in files
        if path.is_file()
    }


def run_analysis(
    config: dict[str, Any],
    config_path: Path,
    *,
    video_override: Path | None = None,
    cache_override: Path | None = None,
    output_override: Path | None = None,
    cache_only: bool = False,
    force_retrack: bool = False,
    skip_plots: bool = False,
    skip_video_qa: bool = False,
) -> dict[str, Any]:
    from .runtime import configure_stdio
    configure_stdio()
    if cache_only and force_retrack:
        raise ValueError("cache_only and force_retrack cannot both be true")
    config_path = config_path.expanduser().resolve()
    output_root = (
        output_override.expanduser().resolve()
        if output_override is not None
        else resolve_config_path(config_path, config["output"]["directory"])
    )
    paths = setup_output_directories(output_root)
    program_hashes_at_start = _program_hashes()

    configured_video_path = resolve_config_path(config_path, config["video"]["path"])
    video_path = (
        video_override.expanduser().resolve()
        if video_override is not None
        else configured_video_path
    )
    configured_cache_path = resolve_config_path(
        config_path, config["model_tracking"]["cache_path"]
    )
    cache_path = (
        cache_override.expanduser().resolve()
        if cache_override is not None
        else configured_cache_path
    )
    interval_path = resolve_config_path(
        config_path, config["forceps_contact_review"]["intervals_tsv"]
    )
    repository_path = resolve_config_path(
        config_path, config["model_tracking"]["repository_path"]
    )

    metadata = configured_video_metadata(config)
    video_present = video_path.is_file()
    video_sha256 = None
    video_size_bytes = None
    print("Checking video metadata / 检查视频信息…", flush=True)
    if video_present:
        observed_video = read_video_metadata(video_path)
        validate_video_metadata(metadata, observed_video)
        video_sha256 = sha256_file(video_path)
        video_size_bytes = video_path.stat().st_size

    query_points = tracking_queries(config)
    model_was_run = False
    if force_retrack or not cache_path.is_file():
        if cache_only:
            raise FileNotFoundError(f"Tracking cache not found: {cache_path}")
        if not video_present:
            raise FileNotFoundError(
                "Video is required for model tracking; provide --video or place it at video.path"
            )
        print("Tracking body and axis points / 追踪躯干与身体轴…" if animal_mode(config) == "frog" else "Tracking head points / 追踪头部点…", flush=True)
        tracks, visible, raw_indices, tracked_metadata = track_video(
            video_path, config["model_tracking"], query_points, repository_path
        )
        validate_video_metadata(metadata, tracked_metadata)
        metadata.update(tracked_metadata)
        save_tracking_cache(
            cache_path,
            tracks,
            visible,
            raw_indices,
            query_points,
            metadata,
        )
        model_was_run = True
        input_mode = "model_tracking"
    else:
        print("Reading audited trajectories / 读取追踪缓存…", flush=True)
        cached = load_tracking_cache(cache_path)
        validate_cache_against_config(cached, config)
        tracks = cached["tracks_raw_px"]
        visible = cached["visible"]
        raw_indices = cached["raw_frame_indices"]
        query_points = cached["query_points_raw_px"]
        metadata.update(
            {
                "sampled_frame_count": int(len(raw_indices)),
                "device": "not_used_cache_only",
                "model_name": config["model_tracking"]["model_name"],
                "model_commit": config["model_tracking"]["commit"],
                "checkpoint_sha256": config["model_tracking"]["checkpoint_sha256"],
            }
        )
        input_mode = "tracking_cache"

    if "timebase_fps" in config["video"]:
        metadata["encoded_fps"] = float(metadata["raw_fps"])
        metadata["raw_fps"] = float(config["video"]["timebase_fps"])
        metadata["effective_fps"] = metadata["raw_fps"] / int(config["model_tracking"]["frame_step"])
        metadata["timebase_override"] = True

    body_count = len(config["head_point_selection"]["query_points_raw_px"])
    axis_tracks, axis_visible = tracks[:, body_count:].copy(), visible[:, body_count:].copy()
    tracks, visible = tracks[:, :body_count], visible[:, :body_count]
    excluded = list(config["head_point_selection"].get("drop_query_indices", []))
    tracks, visible, retained_query_points = apply_query_exclusions(
        tracks, visible, query_points[:body_count], excluded
    )
    metadata["excluded_query_indices"] = excluded
    metadata["retained_query_point_count"] = int(len(retained_query_points))

    intervals = load_forceps_intervals(interval_path)
    if "timebase_fps" in config["video"] and "start_raw_frame" in intervals:
        # Frame columns are authoritative. Re-express their times on the chosen clock.
        intervals["start_s"] = intervals["start_raw_frame"] / float(metadata["raw_fps"])
        intervals["end_s"] = intervals["end_raw_frame"] / float(metadata["raw_fps"])
    maximum_time = float(raw_indices[-1]) / float(metadata["raw_fps"])
    if len(intervals) and float(intervals["start_s"].max()) > maximum_time + 1.0 / float(
        metadata["raw_fps"]
    ):
        raise ValueError("At least one forceps interval starts after the recording ends")
    contact_audit = manual_contact_audit(
        raw_indices, float(metadata["raw_fps"]), intervals
    )
    print("Calibrating and calculating motion / 校准并计算运动指标…", flush=True)
    table = build_track_table(
        tracks, visible, raw_indices, metadata, contact_audit, config
    )
    events, repeats, bout_ids = detect_stimulation_bouts(
        table,
        float(metadata["effective_fps"]),
        config["forceps_contact_review"],
    )
    table["stimulation_bout"] = bout_ids
    summary = make_summary(table, metadata, events, repeats)
    summary["animal_mode"] = animal_mode(config)
    summary["trajectory_reference"] = "body_point_median" if animal_mode(config) == "frog" else "head_point_median"
    if animal_mode(config) == "frog":
        body_table = table.rename(columns={c:c.replace("head_", "body_") for c in table if c.startswith("head_")})
        body_table.to_csv(paths["tables"] / "01_frame_level_body_trajectory.tsv", sep="\t", index=False)
    if hindlimb_enabled(config):
        if not video_present:
            summary["hindlimb_status"] = "requires_original_video"
            print("Hindlimb silhouettes require the original video / 后肢轮廓复算需要原始视频", flush=True)
        else:
            from .frog import analyse_hindlimbs
            print("Measuring posterior silhouettes / 测量后肢展开轮廓…", flush=True)
            summary.update(analyse_hindlimbs(video_path, axis_tracks, axis_visible, raw_indices, table, config, paths,
                make_video=config["output"]["make_video_qa"] and not skip_video_qa))
    arena = config["dish_calibration"]
    if arena.get("type") == "rectangle":
        summary.update(arena_type="rectangle", arena_width_mm=arena["width_mm"], arena_height_mm=arena["height_mm"])
    else:
        summary["nominal_dish_diameter_mm"] = float(arena["dish_diameter_mm"])

    table.to_csv(
        paths["tables"] / "01_frame_level_head_trajectory.tsv", sep="\t", index=False
    )
    pd.DataFrame({"metric": summary.keys(), "value": summary.values()}).to_csv(
        paths["tables"] / "02_swimming_summary.tsv", sep="\t", index=False
    )
    calibration_table(config).to_csv(
        paths["tables"] / "03_dish_calibration.tsv", sep="\t", index=False
    )
    events.to_csv(
        paths["tables"] / "04_forceps_stimulation_bouts.tsv", sep="\t", index=False
    )
    repeats.to_csv(
        paths["tables"] / "05_post_stimulus_repeat_metrics.tsv", sep="\t", index=False
    )
    bout_sensitivity, smoothing_sensitivity = sensitivity_tables(
        table, float(metadata["effective_fps"]), config
    )
    bout_sensitivity.to_csv(
        paths["tables"] / "06_stimulation_bout_gap_sensitivity.tsv",
        sep="\t",
        index=False,
    )
    smoothing_sensitivity.to_csv(
        paths["tables"] / "07_distance_smoothing_sensitivity.tsv",
        sep="\t",
        index=False,
    )
    intervals.to_csv(
        paths["tables"] / "08_forceps_intervals_used.tsv", sep="\t", index=False
    )
    forceps_parameter_table(config).to_csv(
        paths["tables"] / "09_forceps_contact_parameters.tsv", sep="\t", index=False
    )

    write_json(paths["reports"] / "00_analysis_summary.json", summary)
    write_json(
        paths["reports"] / "01_effective_config.json", effective_config(config)
    )
    parameters = flatten_parameters(config)
    pd.DataFrame(
        [{"parameter": key, "value": value} for key, value in parameters.items()]
    ).to_csv(paths["reports"] / "02_parameter_manifest.tsv", sep="\t", index=False)

    provenance = {
        "program": {
            "name": "tadpole_swimming_tracking",
            "version": PROGRAM_VERSION,
            "source_sha256": program_hashes_at_start,
        },
        "run": {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "input_mode": input_mode,
            "model_was_run": model_was_run,
            "cache_only_requested": cache_only,
            "runtime_video_override_used": video_override is not None,
            "runtime_cache_override_used": cache_override is not None,
            "runtime_output_override_used": output_override is not None,
        },
        "configuration": {
            "logical_name": config_path.name,
            "sha256": sha256_file(config_path),
            "schema_version": config["schema_version"],
            "effective": effective_config(config),
            "parameter_manifest": parameters,
        },
        "video": {
            "logical_name": config["video"]["logical_name"],
            "present_at_runtime": video_present,
            "sha256": video_sha256,
            "sha256_status": (
                "computed_at_runtime" if video_present else "not_computed_no_video"
            ),
            "size_bytes": video_size_bytes,
            "metadata": {
                key: metadata[key]
                for key in ("raw_fps", "raw_frame_count", "width_px", "height_px")
            },
        },
        "tracking_cache": {
            "logical_name": Path(config["model_tracking"]["cache_path"]).name,
            "sha256": sha256_file(cache_path),
            "tracked_frames": int(len(raw_indices)),
            "tracked_points_before_exclusion": int(query_points.shape[0]),
            "retained_points": int(retained_query_points.shape[0]),
        },
        "forceps_review": {
            "logical_name": Path(
                config["forceps_contact_review"]["intervals_tsv"]
            ).name,
            "sha256": sha256_file(interval_path),
            "interval_count": int(len(intervals)),
            "source": "manual_review",
        },
        "model": {
            "repository_url": config["model_tracking"]["repository_url"],
            "commit": config["model_tracking"]["commit"],
            "model_name": config["model_tracking"]["model_name"],
            "checkpoint_url": config["model_tracking"]["checkpoint_url"],
            "checkpoint_sha256": config["model_tracking"]["checkpoint_sha256"],
            "license": "CC BY-NC 4.0; see licenses/CoTracker_LICENSE.md",
        },
        "software": installed_software_versions(),
    }
    write_json(paths["reports"] / "03_provenance.json", provenance)
    _write_method_note(
        paths["reports"] / "04_method_and_interpretation_note.md",
        config,
        summary,
        len(intervals),
        input_mode,
    )

    make_plots = bool(config["output"]["make_plots"]) and not skip_plots
    if make_plots:
        print("Rendering plots / 生成分析图…", flush=True)
        save_analysis_plots(
            table,
            events,
            repeats,
            config,
            paths["plots"],
            float(metadata["effective_fps"]),
        )
    make_video_qa = (
        bool(config["output"]["make_video_qa"])
        and not skip_video_qa
        and video_present
    )
    if make_video_qa:
        print("Rendering review video / 生成轨迹检查视频…", flush=True)
        save_tracking_qa_montage(video_path, table, paths["plots"])
        save_stimulation_qa_montage(video_path, table, events, paths["plots"])
        save_annotated_video(
            video_path,
            table,
            paths["video"] / "tracked_head_QA.mp4",
            float(metadata["effective_fps"]),
            tracks=tracks,
            point_ids=[i + 1 for i in range(body_count) if i not in excluded],
        )

    return {
        "output_root": output_root,
        "summary": summary,
        "provenance": provenance,
        "events": events,
        "repeats": repeats,
        "table": table,
    }
