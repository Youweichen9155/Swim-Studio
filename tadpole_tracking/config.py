"""Configuration loading, validation, and path handling."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any


PROGRAM_VERSION = "1.3.0"
SCHEMA_VERSION = "1.0"
COTRACKER_REPOSITORY_URL = "https://github.com/facebookresearch/co-tracker.git"
COTRACKER_COMMIT = "82e02e8029753ad4ef13cf06be7f4fc5facdda4d"
COTRACKER_MODEL_NAME = "cotracker3_online"
COTRACKER_CHECKPOINT_URL = (
    "https://huggingface.co/facebook/cotracker3/resolve/main/scaled_online.pth"
)
COTRACKER_CHECKPOINT_SHA256 = (
    "205d34789f19699d64b22cf93f9b697f15f28d4025240e31532e504109837218"
)


class ConfigError(ValueError):
    """Raised when a recording configuration is invalid."""


def load_config(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    validate_config(config)
    return config


def _require_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{key!r} must be a JSON object")
    return value


def _require_number(
    parent: dict[str, Any], key: str, label: str, *, positive: bool = False
) -> float:
    value = parent.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ConfigError(f"{label} must be finite")
    if positive and number <= 0:
        raise ConfigError(f"{label} must be greater than zero")
    return number


def _require_pair(parent: dict[str, Any], key: str, label: str) -> list[float]:
    value = parent.get(key)
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"{label} must contain exactly two numbers")
    if any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in value):
        raise ConfigError(f"{label} must contain exactly two numbers")
    return [float(item) for item in value]


def _require_relative_path(parent: dict[str, Any], key: str, label: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty relative path")
    if Path(value).expanduser().is_absolute():
        raise ConfigError(
            f"{label} must be relative; use a command-line override for runtime absolute paths"
        )
    return value


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise ConfigError("The top-level JSON value must be an object")
    if config.get("schema_version") not in {"1.0", "1.1"}:
        raise ConfigError(
            f"schema_version must be '1.0' or '1.1'; received {config.get('schema_version')!r}"
        )
    from .modes import validate_mode
    try:
        validate_mode(config)
    except (ValueError, TypeError, KeyError) as exc:
        raise ConfigError(str(exc)) from exc
    analysis_id = config.get("analysis_id")
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise ConfigError("analysis_id must be a non-empty string")

    video = _require_mapping(config, "video")
    logical_name = video.get("logical_name")
    if not isinstance(logical_name, str) or not logical_name.strip():
        raise ConfigError("video.logical_name must be a non-empty de-identified label")
    _require_relative_path(video, "path", "video.path")
    _require_number(video, "fps", "video.fps", positive=True)
    for key in ("frame_count", "width_px", "height_px"):
        value = _require_number(video, key, f"video.{key}", positive=True)
        if not value.is_integer():
            raise ConfigError(f"video.{key} must be an integer")

    model = _require_mapping(config, "model_tracking")
    _require_relative_path(model, "cache_path", "model_tracking.cache_path")
    _require_relative_path(model, "repository_path", "model_tracking.repository_path")
    if model.get("repository_url") != COTRACKER_REPOSITORY_URL:
        raise ConfigError(f"model_tracking.repository_url must be {COTRACKER_REPOSITORY_URL}")
    if model.get("commit") != COTRACKER_COMMIT:
        raise ConfigError(f"model_tracking.commit must be {COTRACKER_COMMIT}")
    if model.get("model_name") != COTRACKER_MODEL_NAME:
        raise ConfigError(f"model_tracking.model_name must be {COTRACKER_MODEL_NAME}")
    if model.get("checkpoint_url") != COTRACKER_CHECKPOINT_URL:
        raise ConfigError("model_tracking.checkpoint_url does not match the frozen v1.0 value")
    if model.get("checkpoint_sha256") != COTRACKER_CHECKPOINT_SHA256:
        raise ConfigError("model_tracking.checkpoint_sha256 does not match the frozen v1.0 value")
    roi = model.get("roi_raw_px")
    if (
        not isinstance(roi, list)
        or len(roi) != 4
        or any(not isinstance(item, int) or isinstance(item, bool) for item in roi)
        or roi[2] <= roi[0]
        or roi[3] <= roi[1]
    ):
        raise ConfigError("model_tracking.roi_raw_px must be [x0, y0, x1, y1]")
    size = model.get("model_size_px")
    if (
        not isinstance(size, list)
        or len(size) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in size)
    ):
        raise ConfigError("model_tracking.model_size_px must contain two positive integers")
    frame_step = model.get("frame_step")
    if not isinstance(frame_step, int) or isinstance(frame_step, bool) or frame_step < 1:
        raise ConfigError("model_tracking.frame_step must be a positive integer")
    if model.get("device") not in {"auto", "mps", "cuda", "cpu"}:
        raise ConfigError("model_tracking.device must be auto, mps, cuda, or cpu")

    head = _require_mapping(config, "head_point_selection")
    points = head.get("query_points_raw_px")
    if not isinstance(points, list) or len(points) < 2:
        raise ConfigError("head_point_selection.query_points_raw_px needs at least two points")
    for point in points:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in point)
        ):
            raise ConfigError("Each head query point must be [x, y]")
    dropped = head.get("drop_query_indices", [])
    if (
        not isinstance(dropped, list)
        or any(not isinstance(item, int) or isinstance(item, bool) for item in dropped)
        or len(set(dropped)) != len(dropped)
        or any(item < 0 or item >= len(points) for item in dropped)
    ):
        raise ConfigError("head_point_selection.drop_query_indices is invalid")
    if len(points) - len(dropped) < 2:
        raise ConfigError("At least two query points must remain after exclusions")
    minimum_visible = head.get("minimum_visible_points")
    if (
        not isinstance(minimum_visible, int)
        or isinstance(minimum_visible, bool)
        or minimum_visible < 1
        or minimum_visible > len(points) - len(dropped)
    ):
        raise ConfigError("head_point_selection.minimum_visible_points is invalid")
    _require_number(head, "maximum_spread_px", "head_point_selection.maximum_spread_px", positive=True)

    from .arena import validate_arena
    try:
        validate_arena(_require_mapping(config, "dish_calibration"))
    except (ValueError, TypeError) as exc:
        raise ConfigError(str(exc)) from exc
    if "timebase_fps" in video:
        _require_number(video, "timebase_fps", "video.timebase_fps", positive=True)
    if roi[0] < 0 or roi[1] < 0 or roi[2] > video["width_px"] or roi[3] > video["height_px"]:
        raise ConfigError("ROI extends outside video / 裁剪框超出视频范围")
    for x, y in points:
        if not (math.isfinite(x) and math.isfinite(y) and roi[0] <= x < roi[2] and roi[1] <= y < roi[3]):
            raise ConfigError("Head point outside ROI / 头部点超出裁剪范围")

    review = _require_mapping(config, "forceps_contact_review")
    _require_relative_path(review, "intervals_tsv", "forceps_contact_review.intervals_tsv")
    for key in (
        "contact_episode_gap_s",
        "stimulation_bout_gap_s",
        "minimum_contact_duration_s",
        "post_stimulus_window_s",
    ):
        _require_number(review, key, f"forceps_contact_review.{key}", positive=True)
    if review.get("source") != "manual_review":
        raise ConfigError("forceps_contact_review.source must be manual_review in v1.0")

    analysis = _require_mapping(config, "analysis")
    for key in (
        "short_gap_interpolation_s",
        "savgol_window_s",
        "display_interpolation_gap_s",
        "maximum_speed_mm_s",
        "maximum_normalized_dish_radius",
    ):
        _require_number(analysis, key, f"analysis.{key}", positive=True)
    order = analysis.get("savgol_polynomial_order")
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise ConfigError("analysis.savgol_polynomial_order must be a positive integer")

    output = _require_mapping(config, "output")
    _require_relative_path(output, "directory", "output.directory")
    for key in ("make_plots", "make_video_qa"):
        if not isinstance(output.get(key), bool):
            raise ConfigError(f"output.{key} must be true or false")


def resolve_config_path(config_path: Path, relative_value: str) -> Path:
    """Resolve a configuration-relative path without storing the absolute result."""
    return (config_path.expanduser().resolve().parent / relative_value).resolve()


def effective_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a clean copy suitable for provenance output."""
    return copy.deepcopy(config)


def flatten_parameters(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested configuration values into a parameter manifest."""
    flattened: dict[str, Any] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else key
            flattened.update(flatten_parameters(value[key], child))
    else:
        flattened[prefix] = value
    return flattened
