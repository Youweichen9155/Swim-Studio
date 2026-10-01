"""CoTracker-specific video tracking, isolated from downstream analysis."""

from __future__ import annotations

import shutil
import json
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .config import ConfigError
from .inputs import read_video_metadata, sha256_file


def choose_device(requested: str) -> str:
    import torch

    if requested != "auto":
        if requested == "mps" and not torch.backends.mps.is_available():
            raise ConfigError("MPS was requested but is not available")
        if requested == "cuda" and not torch.cuda.is_available():
            raise ConfigError("CUDA was requested but is not available")
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _git_executable() -> str:
    found = shutil.which("git")
    if found:
        return found
    fallback = Path("/usr/bin/git")
    if fallback.exists():
        return str(fallback)
    raise ConfigError("git is required to verify the pinned CoTracker checkout")


def verify_cotracker_checkout(repository: Path, expected_commit: str) -> str:
    if not repository.is_dir():
        raise ConfigError(
            "Pinned CoTracker checkout not found. Run "
            "'python prepare_config.py fetch-model --config CONFIG.json' first."
        )
    result = subprocess.run(
        [_git_executable(), "-C", str(repository), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ConfigError(f"Could not inspect CoTracker checkout: {result.stderr.strip()}")
    observed = result.stdout.strip()
    if observed != expected_commit:
        raise ConfigError(
            f"CoTracker checkout is at {observed}; required commit is {expected_commit}"
        )
    return observed


def _prepare_frame(
    frame_bgr: np.ndarray, roi: list[int], model_size: list[int]
) -> np.ndarray:
    x0, y0, x1, y1 = roi
    if x0 < 0 or y0 < 0 or x1 > frame_bgr.shape[1] or y1 > frame_bgr.shape[0]:
        raise ConfigError("model_tracking.roi_raw_px extends outside the video frame")
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)[y0:y1, x0:x1]
    return cv2.resize(rgb, tuple(model_size), interpolation=cv2.INTER_AREA)


def _raw_points_to_model(
    points: np.ndarray, roi: list[int], model_size: list[int]
) -> np.ndarray:
    x0, y0, x1, y1 = roi
    scale = np.asarray(
        [model_size[0] / (x1 - x0), model_size[1] / (y1 - y0)],
        dtype=np.float32,
    )
    transformed = (points - np.asarray([x0, y0], dtype=np.float32)) * scale
    if (
        (transformed[:, 0] < 0).any()
        or (transformed[:, 1] < 0).any()
        or (transformed[:, 0] >= model_size[0]).any()
        or (transformed[:, 1] >= model_size[1]).any()
    ):
        raise ConfigError("At least one head query point lies outside the tracking ROI")
    return transformed


def _model_points_to_raw(
    points: np.ndarray, roi: list[int], model_size: list[int]
) -> np.ndarray:
    x0, y0, x1, y1 = roi
    scale = np.asarray(
        [(x1 - x0) / model_size[0], (y1 - y0) / model_size[1]],
        dtype=np.float32,
    )
    return points * scale + np.asarray([x0, y0], dtype=np.float32)


def _load_model(model_config: dict[str, Any], repository: Path, device: str):
    import torch
    from .runtime import frozen, model_bundle

    if frozen():
        bundle = model_bundle()
        manifest = json.loads((bundle / 'manifest.json').read_text())
        if manifest['commit'] != model_config['commit']:
            raise ConfigError('Bundled model version mismatch / 内置模型版本不符')
        for name, digest in manifest['files'].items():
            if sha256_file(bundle / name) != digest:
                raise ConfigError(f'Bundled model is damaged / 内置模型文件损坏: {name}')
        checkpoint = bundle / 'scaled_online.pth'
        if sha256_file(checkpoint) != model_config['checkpoint_sha256']:
            raise ConfigError('Bundled model SHA256 mismatch / 内置模型校验不符')
        from cotracker.predictor import CoTrackerOnlinePredictor
        model = CoTrackerOnlinePredictor(checkpoint=None, window_len=16, v2=False)
        model.model.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True))
        return model.to(device).eval(), model_config['checkpoint_sha256']

    verify_cotracker_checkout(repository, model_config["commit"])
    checkpoint_name = Path(model_config["checkpoint_url"]).name
    checkpoint_path = Path(torch.hub.get_dir()) / "checkpoints" / checkpoint_name
    if not checkpoint_path.is_file():
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = checkpoint_path.with_suffix(".download")
        torch.hub.download_url_to_file(model_config["checkpoint_url"], str(temporary))
        if sha256_file(temporary) != model_config["checkpoint_sha256"]:
            temporary.unlink(missing_ok=True)
            raise ConfigError("Downloaded model SHA256 mismatch / 模型下载校验不符")
        temporary.replace(checkpoint_path)
    observed_sha = sha256_file(checkpoint_path)
    if observed_sha != model_config["checkpoint_sha256"]:
        raise ConfigError(
            "CoTracker checkpoint SHA256 mismatch: "
            f"{observed_sha} versus {model_config['checkpoint_sha256']}"
        )
    model = torch.hub.load(str(repository), model_config["model_name"], source="local",
                           pretrained=False, trust_repo=True)
    model.model.load_state_dict(torch.load(checkpoint_path, map_location="cpu", weights_only=True))
    model = model.to(device).eval()
    return model, observed_sha


def track_video(
    video_path: Path,
    model_config: dict[str, Any],
    query_points_raw: np.ndarray,
    repository: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Run the pinned CoTracker model and return raw-frame point trajectories."""
    import torch

    frame_step = int(model_config["frame_step"])
    roi = [int(value) for value in model_config["roi_raw_px"]]
    model_size = [int(value) for value in model_config["model_size_px"]]
    device = choose_device(model_config["device"])
    video_metadata = read_video_metadata(video_path)
    model, checkpoint_sha = _load_model(model_config, repository, device)

    points = _raw_points_to_model(query_points_raw.copy(), roi, model_size)
    query = np.concatenate(
        [
            np.zeros((len(points), 1), dtype=np.float32),
            points[:, 0:1],
            points[:, 1:2],
        ],
        axis=1,
    )
    queries = torch.tensor(query, dtype=torch.float32, device=device)[None]

    capture = cv2.VideoCapture(str(video_path))
    buffer: list[np.ndarray] = []
    sampled_raw_indices: list[int] = []
    buffer_start = 0
    initialized = False
    last_start = -1
    predictions = None
    visibility = None
    raw_index = 0

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if raw_index % frame_step == 0:
            sampled_raw_indices.append(raw_index)
            buffer.append(_prepare_frame(frame, roi, model_size))
            if len(buffer) == model.step * 2:
                chunk = (
                    torch.from_numpy(np.stack(buffer))
                    .permute(0, 3, 1, 2)[None]
                    .float()
                    .to(device)
                )
                if not initialized:
                    model(
                        video_chunk=chunk,
                        is_first_step=True,
                        queries=queries,
                        add_support_grid=True,
                    )
                    initialized = True
                predictions, visibility = model(
                    video_chunk=chunk, add_support_grid=True
                )
                last_start = buffer_start
                buffer = buffer[model.step :]
                buffer_start += model.step
        raw_index += 1
        if raw_index % max(1, int(video_metadata["raw_fps"] * 5)) == 0:
            print(f"Tracking / 追踪 {raw_index}/{video_metadata['raw_frame_count']} frames", flush=True)
    capture.release()

    sampled_n = len(sampled_raw_indices)
    if sampled_n == 0:
        raise ConfigError("No video frames were read")
    if last_start + model.step * 2 < sampled_n:
        while len(buffer) < model.step * 2:
            buffer.append(buffer[-1].copy())
        chunk = (
            torch.from_numpy(np.stack(buffer))
            .permute(0, 3, 1, 2)[None]
            .float()
            .to(device)
        )
        if not initialized:
            model(
                video_chunk=chunk,
                is_first_step=True,
                queries=queries,
                add_support_grid=True,
            )
        predictions, visibility = model(video_chunk=chunk, add_support_grid=True)

    if predictions is None or visibility is None:
        raise ConfigError("CoTracker returned no predictions")
    tracks = predictions[0, :sampled_n].detach().cpu().numpy()
    visible = visibility[0, :sampled_n].detach().cpu().numpy().astype(bool)
    tracks = _model_points_to_raw(tracks, roi, model_size)
    raw_indices = np.asarray(sampled_raw_indices, dtype=np.int64)
    metadata = {
        **video_metadata,
        "sampled_frame_count": sampled_n,
        "effective_fps": float(video_metadata["raw_fps"]) / frame_step,
        "frame_step": frame_step,
        "device": device,
        "model_name": model_config["model_name"],
        "model_commit": model_config["commit"],
        "checkpoint_sha256": checkpoint_sha,
    }
    return tracks, visible, raw_indices, metadata
