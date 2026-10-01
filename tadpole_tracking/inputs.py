"""Input readers and small provenance helpers."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

from .config import ConfigError


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_video_metadata(path: Path) -> dict[str, int | float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ConfigError(f"Could not open video: {path}")
    metadata = {
        "raw_fps": float(capture.get(cv2.CAP_PROP_FPS)),
        "raw_frame_count": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width_px": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height_px": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    capture.release()
    if metadata["raw_fps"] <= 0 or metadata["raw_frame_count"] <= 0:
        raise ConfigError(f"Video metadata are invalid: {path}")
    return metadata


def configured_video_metadata(config: dict[str, Any]) -> dict[str, int | float]:
    video = config["video"]
    frame_step = int(config["model_tracking"]["frame_step"])
    return {
        "raw_fps": float(video["fps"]),
        "raw_frame_count": int(video["frame_count"]),
        "width_px": int(video["width_px"]),
        "height_px": int(video["height_px"]),
        "effective_fps": float(video["fps"]) / frame_step,
        "frame_step": frame_step,
    }


def validate_video_metadata(
    configured: dict[str, int | float], observed: dict[str, int | float]
) -> None:
    if abs(float(configured["raw_fps"]) - float(observed["raw_fps"])) > 1e-6:
        raise ConfigError(
            "Video FPS differs from the configuration: "
            f"{observed['raw_fps']} versus {configured['raw_fps']}"
        )
    for key in ("raw_frame_count", "width_px", "height_px"):
        if int(configured[key]) != int(observed[key]):
            raise ConfigError(
                f"Video {key} differs from the configuration: "
                f"{observed[key]} versus {configured[key]}"
            )


def load_forceps_intervals(path: Path) -> pd.DataFrame:
    try:
        table = pd.read_csv(path, sep="\t")
    except FileNotFoundError as exc:
        raise ConfigError(f"Forceps interval table not found: {path}") from exc
    required = ["start_s", "end_s"]
    frame_columns = ["start_raw_frame", "end_raw_frame"]
    allowed = [required, required + frame_columns]
    if list(table.columns) not in allowed:
        raise ConfigError(
            "Forceps interval TSV columns must be either "
            "start_s, end_s or start_s, end_s, start_raw_frame, end_raw_frame"
        )
    if table.empty:
        dtypes: dict[str, type] = {"start_s": float, "end_s": float}
        if frame_columns[0] in table:
            dtypes.update({"start_raw_frame": int, "end_raw_frame": int})
        return table.astype(dtypes)
    for column in required:
        table[column] = pd.to_numeric(table[column], errors="raise")
    if not np.isfinite(table[required].to_numpy(float)).all():
        raise ConfigError("Forceps interval values must be finite")
    if (table["start_s"] < 0).any() or (table["end_s"] <= table["start_s"]).any():
        raise ConfigError("Each forceps interval must satisfy 0 <= start_s < end_s")
    if (np.diff(table["start_s"].to_numpy(float)) < 0).any():
        raise ConfigError("Forceps intervals must be sorted by start_s")
    if frame_columns[0] in table:
        for column in frame_columns:
            numeric = pd.to_numeric(table[column], errors="raise")
            if not np.equal(numeric, np.floor(numeric)).all():
                raise ConfigError(f"{column} must contain integers")
            table[column] = numeric.astype(np.int64)
        if (table["start_raw_frame"] < 0).any() or (
            table["end_raw_frame"] < table["start_raw_frame"]
        ).any():
            raise ConfigError("Reviewed raw-frame bounds are invalid")
    return table


def load_tracking_cache(path: Path) -> dict[str, np.ndarray]:
    try:
        with np.load(path, allow_pickle=False) as cached:
            required = {
                "tracks_raw_px",
                "visible",
                "raw_frame_indices",
                "query_points_raw_px",
            }
            missing = required.difference(cached.files)
            if missing:
                raise ConfigError(
                    f"Tracking cache is missing arrays: {', '.join(sorted(missing))}"
                )
            arrays = {name: cached[name].copy() for name in required}
    except FileNotFoundError as exc:
        raise ConfigError(f"Tracking cache not found: {path}") from exc

    tracks = arrays["tracks_raw_px"]
    visible = arrays["visible"]
    frames = arrays["raw_frame_indices"]
    points = arrays["query_points_raw_px"]
    if tracks.ndim != 3 or tracks.shape[2] != 2 or tracks.shape[0] == 0:
        raise ConfigError("tracks_raw_px must have shape [frames, points, 2]")
    if visible.shape != tracks.shape[:2]:
        raise ConfigError("visible must have shape [frames, points]")
    if frames.ndim != 1 or len(frames) != len(tracks):
        raise ConfigError("raw_frame_indices must have one value per tracked frame")
    if points.shape != tracks.shape[1:]:
        raise ConfigError("query_points_raw_px does not match the tracked point count")
    if not np.issubdtype(frames.dtype, np.integer):
        raise ConfigError("raw_frame_indices must be integers")
    if len(frames) > 1 and (np.diff(frames.astype(np.int64)) <= 0).any():
        raise ConfigError("raw_frame_indices must be strictly increasing")
    if not np.isfinite(tracks).all() or not np.isfinite(points).all():
        raise ConfigError("Tracking cache contains non-finite coordinates")
    return {
        "tracks_raw_px": tracks.astype(np.float32, copy=False),
        "visible": visible.astype(bool, copy=False),
        "raw_frame_indices": frames.astype(np.int64, copy=False),
        "query_points_raw_px": points.astype(np.float32, copy=False),
    }


def save_tracking_cache(
    path: Path,
    tracks: np.ndarray,
    visible: np.ndarray,
    raw_frame_indices: np.ndarray,
    query_points: np.ndarray,
    metadata: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        tracks_raw_px=tracks.astype(np.float32),
        visible=visible.astype(bool),
        raw_frame_indices=raw_frame_indices.astype(np.int64),
        query_points_raw_px=query_points.astype(np.float32),
        metadata_json=np.asarray(json.dumps(metadata, sort_keys=True)),
    )


def installed_software_versions() -> dict[str, str]:
    distributions = {
        "numpy": "numpy",
        "pandas": "pandas",
        "scipy": "scipy",
        "matplotlib": "matplotlib",
        "opencv-python-headless": "opencv-python-headless",
        "torch": "torch",
        "torchvision": "torchvision",
    }
    versions: dict[str, str] = {"python": platform.python_version()}
    for label, distribution in distributions.items():
        try:
            versions[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[label] = "not-installed"
    versions["platform"] = platform.platform()
    versions["python_implementation"] = platform.python_implementation()
    versions["byteorder"] = sys.byteorder
    return versions


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json(item) for item in value]
    if isinstance(value, np.generic):
        return sanitize_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return value.name
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = sanitize_json(value)
    path.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
