"""Dish calibration, manual stimulus handling, and motion quantification."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from .config import ConfigError
from .arena import raw_to_mm, normalized_boundary


EVENT_COLUMNS = [
    "stimulus_bout",
    "start_frame_index",
    "end_frame_index",
    "closest_frame_index",
    "start_time_s",
    "end_time_s",
    "bout_duration_s",
    "contact_episode_count",
    "detected_contact_duration_s",
    "minimum_forceps_head_distance_px",
]

REPEAT_COLUMNS = [
    "stimulus_bout",
    "response_start_frame_index",
    "response_end_frame_index_exclusive",
    "response_start_time_s",
    "response_end_time_s",
    "nominal_response_window_s",
    "analyzable_time_in_fixed_window_s",
    "coverage_fraction_fixed_window",
    "distance_2s_post_stimulus_mm",
    "mean_speed_over_analyzable_2s_mm_s",
    "speed_95th_percentile_2s_mm_s",
    "next_stimulus_or_video_end_s",
    "inter_bout_response_duration_s",
    "analyzable_time_inter_bout_s",
    "inter_bout_distance_mm",
]


def apply_query_exclusions(
    tracks: np.ndarray,
    visible: np.ndarray,
    query_points: np.ndarray,
    excluded: list[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    keep = [index for index in range(tracks.shape[1]) if index not in excluded]
    if len(keep) < 2:
        raise ConfigError("Query-point exclusions leave fewer than two head points")
    return tracks[:, keep], visible[:, keep], query_points[keep]


def validate_cache_against_config(
    cache: dict[str, np.ndarray], config: dict[str, Any]
) -> None:
    expected = np.asarray(
        config["head_point_selection"]["query_points_raw_px"], dtype=np.float32
    )
    observed = cache["query_points_raw_px"]
    if expected.shape != observed.shape or not np.allclose(expected, observed, atol=1e-4):
        raise ConfigError("Cached query points do not match head_point_selection")
    frame_step = int(config["model_tracking"]["frame_step"])
    frames = cache["raw_frame_indices"]
    if len(frames) > 1 and not np.all(np.diff(frames) == frame_step):
        raise ConfigError("Cached raw frame spacing does not match model_tracking.frame_step")
    expected_count = int(math.ceil(config["video"]["frame_count"] / frame_step))
    if len(frames) != expected_count:
        raise ConfigError(
            f"Cached frame count is {len(frames)}; expected {expected_count} from configuration"
        )


def manual_contact_audit(
    raw_indices: np.ndarray,
    raw_fps: float,
    intervals: pd.DataFrame,
) -> pd.DataFrame:
    times = raw_indices.astype(float) / raw_fps
    contact = np.zeros(len(raw_indices), dtype=bool)
    for row in intervals.itertuples(index=False):
        if hasattr(row, "start_raw_frame"):
            contact |= (raw_indices >= int(row.start_raw_frame)) & (
                raw_indices <= int(row.end_raw_frame)
            )
        else:
            contact |= (times >= float(row.start_s)) & (times <= float(row.end_s))
    return pd.DataFrame(
        {
            "forceps_present": contact,
            "forceps_near_head": contact,
            "forceps_distance_px": np.where(contact, 0.0, np.nan),
            "forceps_area_px": np.zeros(len(raw_indices), dtype=int),
            "forceps_review_source": np.where(contact, "manual_interval", "none"),
        }
    )


def interpolate_short_gaps(
    values: np.ndarray, valid: np.ndarray, max_gap: int
) -> tuple[np.ndarray, np.ndarray]:
    filled = values.copy()
    interpolated = np.zeros(len(values), dtype=bool)
    start = 0
    while start < len(values):
        if valid[start]:
            start += 1
            continue
        end = start
        while end < len(values) and not valid[end]:
            end += 1
        gap = end - start
        if start > 0 and end < len(values) and gap <= max_gap:
            for dimension in range(values.shape[1]):
                filled[start:end, dimension] = np.linspace(
                    values[start - 1, dimension],
                    values[end, dimension],
                    gap + 2,
                )[1:-1]
            interpolated[start:end] = True
        start = end
    return filled, interpolated


def compute_motion(
    mm: np.ndarray,
    observed_valid: np.ndarray,
    fps: float,
    analysis_config: dict[str, Any],
    *,
    smoothing_window_s: float | None = None,
    max_gap_s: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(mm) == 0:
        raise ConfigError("Motion analysis requires at least one frame")
    if smoothing_window_s is None:
        smoothing_window_s = float(analysis_config["savgol_window_s"])
    if max_gap_s is None:
        max_gap_s = float(analysis_config["short_gap_interpolation_s"])
    polynomial_order = int(analysis_config["savgol_polynomial_order"])
    max_gap = max(1, int(round(max_gap_s * fps)))
    mm_filled, interpolated = interpolate_short_gaps(
        mm, observed_valid, max_gap=max_gap
    )
    analyzable = observed_valid | interpolated
    smooth = np.full_like(mm_filled, np.nan, dtype=float)
    smooth_window = max(5, int(round(smoothing_window_s * fps)))
    if smooth_window % 2 == 0:
        smooth_window += 1
    if smooth_window <= polynomial_order:
        smooth_window = polynomial_order + 1
        if smooth_window % 2 == 0:
            smooth_window += 1

    for dimension in range(2):
        series = mm_filled[:, dimension].astype(float, copy=True)
        series[~analyzable] = np.nan
        good = np.flatnonzero(np.isfinite(series))
        if len(good) < smooth_window or len(series) < smooth_window:
            smooth[:, dimension] = series
            continue
        missing = ~np.isfinite(series)
        series[missing] = np.interp(np.flatnonzero(missing), good, series[good])
        smooth[:, dimension] = savgol_filter(
            series, smooth_window, polynomial_order, mode="interp"
        )
        smooth[~analyzable, dimension] = np.nan

    dt = 1.0 / fps
    step_distance = np.full(len(smooth), np.nan)
    if len(smooth) > 1:
        delta = np.linalg.norm(np.diff(smooth, axis=0), axis=1)
        consecutive = analyzable[1:] & analyzable[:-1]
        step_distance[1:] = np.where(consecutive, delta, np.nan)
    speed = step_distance / dt
    jump = np.isfinite(speed) & (
        speed > float(analysis_config["maximum_speed_mm_s"])
    )
    step_distance[jump] = np.nan
    speed[jump] = np.nan
    cumulative = np.nancumsum(np.nan_to_num(step_distance, nan=0.0))
    return smooth, interpolated, analyzable, step_distance, speed, cumulative


def build_track_table(
    tracks: np.ndarray,
    visible: np.ndarray,
    raw_indices: np.ndarray,
    metadata: dict[str, Any],
    contact_audit: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    calibration = config["dish_calibration"]
    head_config = config["head_point_selection"]
    analysis_config = config["analysis"]
    center_raw = np.median(tracks, axis=1)
    spread = np.median(
        np.linalg.norm(tracks - center_raw[:, None, :], axis=2), axis=1
    )
    visible_count = visible.sum(axis=1)
    normalized_radius = normalized_boundary(center_raw, calibration)
    base_valid = (
        np.isfinite(normalized_radius)
        & (visible_count >= int(head_config["minimum_visible_points"]))
        & (spread <= float(head_config["maximum_spread_px"]))
        & (
            normalized_radius
            <= float(analysis_config["maximum_normalized_dish_radius"])
        )
    )
    strict_valid = base_valid & (~contact_audit["forceps_near_head"].to_numpy(bool))
    mm = raw_to_mm(center_raw, calibration)
    smooth, interpolated, analyzable, step_distance, speed, cumulative = compute_motion(
        mm, strict_valid, float(metadata["effective_fps"]), analysis_config
    )
    (
        smooth_all,
        interpolated_all,
        analyzable_all,
        step_distance_all,
        speed_all,
        cumulative_all,
    ) = compute_motion(mm, base_valid, float(metadata["effective_fps"]), analysis_config)
    (
        smooth_display,
        interpolated_display,
        analyzable_display,
        _,
        _,
        _,
    ) = compute_motion(
        mm,
        base_valid,
        float(metadata["effective_fps"]),
        analysis_config,
        max_gap_s=float(analysis_config["display_interpolation_gap_s"]),
    )

    table = pd.DataFrame(
        {
            "sampled_frame": np.arange(len(raw_indices)),
            "raw_frame": raw_indices,
            "time_s": raw_indices / float(metadata["raw_fps"]),
            "head_x_px": center_raw[:, 0],
            "head_y_px": center_raw[:, 1],
            "head_x_mm": mm[:, 0],
            "head_y_mm": mm[:, 1],
            "head_x_mm_smooth": smooth[:, 0],
            "head_y_mm_smooth": smooth[:, 1],
            "head_x_mm_smooth_including_contact": smooth_all[:, 0],
            "head_y_mm_smooth_including_contact": smooth_all[:, 1],
            "head_x_mm_display": smooth_display[:, 0],
            "head_y_mm_display": smooth_display[:, 1],
            "visible_query_points": visible_count,
            "query_spread_px": spread,
            "dish_normalized_radius": normalized_radius,
            "track_valid_observed": strict_valid,
            "track_valid_observed_including_contact": base_valid,
            "short_gap_interpolated": interpolated,
            "analyzable": analyzable,
            "step_distance_mm": step_distance,
            "speed_mm_s": speed,
            "cumulative_distance_mm": cumulative,
            "short_gap_interpolated_including_contact": interpolated_all,
            "analyzable_including_contact": analyzable_all,
            "display_gap_interpolated": interpolated_display,
            "display_analyzable": analyzable_display,
            "step_distance_including_contact_mm": step_distance_all,
            "speed_including_contact_mm_s": speed_all,
            "cumulative_distance_including_contact_mm": cumulative_all,
        }
    )
    return pd.concat([table, contact_audit.reset_index(drop=True)], axis=1)


def bridge_boolean_gaps(mask: np.ndarray, max_gap: int) -> np.ndarray:
    bridged = mask.astype(bool).copy()
    start = 0
    while start < len(bridged):
        if bridged[start]:
            start += 1
            continue
        end = start
        while end < len(bridged) and not bridged[end]:
            end += 1
        if start > 0 and end < len(bridged) and end - start <= max_gap:
            bridged[start:end] = True
        start = end
    return bridged


def boolean_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    changes = np.diff(np.r_[False, mask.astype(bool), False].astype(int))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1) - 1
    return list(zip(starts, ends))


def cleaned_contact_episode_runs(
    table: pd.DataFrame, fps: float, review_config: dict[str, Any]
) -> list[tuple[int, int]]:
    raw_contact = table["forceps_near_head"].to_numpy(bool)
    episode_mask = bridge_boolean_gaps(
        raw_contact,
        max_gap=max(
            1, int(round(float(review_config["contact_episode_gap_s"]) * fps))
        ),
    )
    minimum_frames = max(
        1, int(round(float(review_config["minimum_contact_duration_s"]) * fps))
    )
    return [
        (start, end)
        for start, end in boolean_runs(episode_mask)
        if end - start + 1 >= minimum_frames
    ]


def detect_stimulation_bouts(
    table: pd.DataFrame,
    fps: float,
    review_config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    episodes = cleaned_contact_episode_runs(table, fps, review_config)
    cleaned_episode_mask = np.zeros(len(table), dtype=bool)
    for start, end in episodes:
        cleaned_episode_mask[start : end + 1] = True
    bout_mask = bridge_boolean_gaps(
        cleaned_episode_mask,
        max_gap=max(
            1, int(round(float(review_config["stimulation_bout_gap_s"]) * fps))
        ),
    )
    bouts = boolean_runs(bout_mask)
    bout_ids = np.zeros(len(table), dtype=int)
    event_rows: list[dict[str, Any]] = []
    repeat_rows: list[dict[str, Any]] = []
    dt = 1.0 / fps
    times = table["time_s"].to_numpy(float)
    strict_step = table["step_distance_mm"].to_numpy(float)
    strict_speed = table["speed_mm_s"].to_numpy(float)

    for bout_id, (start, end) in enumerate(bouts, start=1):
        bout_ids[start : end + 1] = bout_id
        contained = [(a, b) for a, b in episodes if a >= start and b <= end]
        distance_slice = table.loc[start:end, "forceps_distance_px"].to_numpy(float)
        if np.isfinite(distance_slice).any():
            local_minimum = int(np.nanargmin(distance_slice))
            closest_index = start + local_minimum
            minimum_distance = float(distance_slice[local_minimum])
        else:
            closest_index = start
            minimum_distance = np.nan
        event_rows.append(
            {
                "stimulus_bout": bout_id,
                "start_frame_index": start,
                "end_frame_index": end,
                "closest_frame_index": closest_index,
                "start_time_s": times[start],
                "end_time_s": times[end],
                "bout_duration_s": (end - start + 1) * dt,
                "contact_episode_count": len(contained),
                "detected_contact_duration_s": float(
                    cleaned_episode_mask[start : end + 1].sum() * dt
                ),
                "minimum_forceps_head_distance_px": minimum_distance,
            }
        )

        response_start_index = min(end + 1, len(table))
        requested_frames = max(
            1, int(round(float(review_config["post_stimulus_window_s"]) * fps))
        )
        response_end_index = min(response_start_index + requested_frames, len(table))
        fixed = np.zeros(len(table), dtype=bool)
        fixed[response_start_index:response_end_index] = True
        next_start_index = bouts[bout_id][0] if bout_id < len(bouts) else len(table)
        full = np.zeros(len(table), dtype=bool)
        full[response_start_index:next_start_index] = True
        response_start = (
            times[response_start_index]
            if response_start_index < len(table)
            else times[-1] + dt
        )
        response_end = response_start + (response_end_index - response_start_index) * dt
        next_start = (
            times[next_start_index]
            if next_start_index < len(table)
            else times[-1] + dt
        )
        fixed_finite = fixed & np.isfinite(strict_step)
        full_finite = full & np.isfinite(strict_step)
        fixed_distance = float(np.nansum(strict_step[fixed]))
        full_distance = float(np.nansum(strict_step[full]))
        fixed_coverage = float(fixed_finite.sum() * dt)
        full_coverage = float(full_finite.sum() * dt)
        finite_fixed_speed = strict_speed[fixed]
        repeat_rows.append(
            {
                "stimulus_bout": bout_id,
                "response_start_frame_index": response_start_index,
                "response_end_frame_index_exclusive": response_end_index,
                "response_start_time_s": response_start,
                "response_end_time_s": response_end,
                "nominal_response_window_s": response_end - response_start,
                "analyzable_time_in_fixed_window_s": fixed_coverage,
                "coverage_fraction_fixed_window": fixed_finite.sum()
                / max(fixed.sum(), 1),
                "distance_2s_post_stimulus_mm": fixed_distance,
                "mean_speed_over_analyzable_2s_mm_s": (
                    fixed_distance / fixed_coverage if fixed_coverage > 0 else np.nan
                ),
                "speed_95th_percentile_2s_mm_s": (
                    float(np.nanquantile(finite_fixed_speed, 0.95))
                    if np.isfinite(finite_fixed_speed).any()
                    else np.nan
                ),
                "next_stimulus_or_video_end_s": next_start,
                "inter_bout_response_duration_s": next_start - response_start,
                "analyzable_time_inter_bout_s": full_coverage,
                "inter_bout_distance_mm": full_distance,
            }
        )

    events = pd.DataFrame(event_rows, columns=EVENT_COLUMNS)
    repeats = pd.DataFrame(repeat_rows, columns=REPEAT_COLUMNS)
    return events, repeats, bout_ids


def make_summary(
    table: pd.DataFrame,
    metadata: dict[str, Any],
    events: pd.DataFrame,
    repeats: pd.DataFrame,
) -> dict[str, Any]:
    analyzable = table["analyzable"].to_numpy(bool)
    speed = table.loc[analyzable, "speed_mm_s"].dropna()
    duration = float(table["time_s"].iloc[-1])
    strict_distance = float(table["cumulative_distance_mm"].iloc[-1])
    return {
        "video_duration_s": duration,
        "tracked_frames": int(len(table)),
        "analyzable_frames": int(analyzable.sum()),
        "analyzable_fraction": float(analyzable.mean()),
        "forceps_near_head_frames": int(table["forceps_near_head"].sum()),
        "total_analyzable_distance_mm": strict_distance,
        "trackable_distance_including_contact_mm": float(
            table["cumulative_distance_including_contact_mm"].iloc[-1]
        ),
        "overall_mean_speed_mm_s": strict_distance / duration if duration > 0 else None,
        "mean_speed_during_analyzable_steps_mm_s": (
            float(speed.mean()) if len(speed) else None
        ),
        "median_speed_during_analyzable_steps_mm_s": (
            float(speed.median()) if len(speed) else None
        ),
        "speed_95th_percentile_mm_s": (
            float(speed.quantile(0.95)) if len(speed) else None
        ),
        "detected_short_contact_episodes": int(
            events["contact_episode_count"].sum() if len(events) else 0
        ),
        "independent_stimulation_bouts": int(len(events)),
        "median_distance_2s_post_stimulus_mm": (
            float(repeats["distance_2s_post_stimulus_mm"].median())
            if len(repeats)
            else None
        ),
        "mean_distance_2s_post_stimulus_mm": (
            float(repeats["distance_2s_post_stimulus_mm"].mean())
            if len(repeats)
            else None
        ),
        **metadata,
    }


def calibration_table(config: dict[str, Any]) -> pd.DataFrame:
    calibration = config["dish_calibration"]
    if calibration.get("type") == "rectangle":
        rows = [{"parameter": "width_mm", "value": calibration["width_mm"]},
                {"parameter": "height_mm", "value": calibration["height_mm"]}]
        for i, (x, y) in enumerate(calibration["corners_raw_px"]):
            rows.extend([{"parameter": f"corner_{i+1}_x_px", "value": x},
                         {"parameter": f"corner_{i+1}_y_px", "value": y}])
        return pd.DataFrame(rows)
    return pd.DataFrame(
        {
            "parameter": [
                "center_x_px",
                "center_y_px",
                "diameter_x_px",
                "diameter_y_px",
                "angle_deg",
                "dish_diameter_mm",
            ],
            "value": [
                *calibration["center_raw_px"],
                *calibration["ellipse_diameters_px"],
                calibration["ellipse_angle_degrees"],
                calibration["dish_diameter_mm"],
            ],
        }
    )


def forceps_parameter_table(config: dict[str, Any]) -> pd.DataFrame:
    review = config["forceps_contact_review"]
    return pd.DataFrame(
        {
            "parameter": [
                "input_source",
                "contact_gap_bridge_s",
                "stimulation_bout_gap_s",
                "minimum_contact_duration_s",
                "post_stimulus_response_window_s",
            ],
            "value": [
                review["source"],
                review["contact_episode_gap_s"],
                review["stimulation_bout_gap_s"],
                review["minimum_contact_duration_s"],
                review["post_stimulus_window_s"],
            ],
        }
    )


def sensitivity_tables(
    table: pd.DataFrame, fps: float, config: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    review = config["forceps_contact_review"]
    episodes = cleaned_contact_episode_runs(table, fps, review)
    episode_mask = np.zeros(len(table), dtype=bool)
    for start, end in episodes:
        episode_mask[start : end + 1] = True
    bout_rows = []
    for gap_s in (0.5, 1.0, 1.5, 2.0, 2.5):
        merged = bridge_boolean_gaps(
            episode_mask, max_gap=max(1, int(round(gap_s * fps)))
        )
        bout_rows.append(
            {
                "maximum_gap_merged_s": gap_s,
                "stimulation_bout_count": len(boolean_runs(merged)),
            }
        )

    mm = table[["head_x_mm", "head_y_mm"]].to_numpy(float)
    valid = table["track_valid_observed"].to_numpy(bool)
    smoothing_rows = []
    for window_s in (0.3, 0.5, 0.7):
        _, _, _, step_distance, speed, _ = compute_motion(
            mm,
            valid,
            fps,
            config["analysis"],
            smoothing_window_s=window_s,
        )
        finite_speed = speed[np.isfinite(speed)]
        smoothing_rows.append(
            {
                "smoothing_window_s": window_s,
                "strict_non_contact_distance_mm": float(np.nansum(step_distance)),
                "median_speed_mm_s": (
                    float(np.median(finite_speed)) if len(finite_speed) else np.nan
                ),
                "speed_95th_percentile_mm_s": (
                    float(np.quantile(finite_speed, 0.95))
                    if len(finite_speed)
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(bout_rows), pd.DataFrame(smoothing_rows)
