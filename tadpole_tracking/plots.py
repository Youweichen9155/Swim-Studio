"""Publication-oriented plots and optional video QA outputs."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection

from .analysis import cleaned_contact_episode_runs


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "font.size": 7,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "axes.linewidth": 0.7,
        "pdf.fonttype": 42,
        "legend.frameon": False,
        "savefig.facecolor": "white",
    }
)


def _save_figure(fig: plt.Figure, base: Path, *, png_dpi: int = 600) -> None:
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".png"), dpi=png_dpi, bbox_inches="tight")
    plt.close(fig)


def path_segments(
    table: pd.DataFrame, *, display: bool = False
) -> tuple[np.ndarray, np.ndarray]:
    if display:
        xy = table[["head_x_mm_display", "head_y_mm_display"]].to_numpy(float)
        finite = np.isfinite(xy).all(axis=1)
        valid_step = np.r_[False, finite[1:] & finite[:-1]]
    else:
        xy = table[["head_x_mm_smooth", "head_y_mm_smooth"]].to_numpy(float)
        valid_step = np.isfinite(table["step_distance_mm"].to_numpy(float))
    segments: list[list[np.ndarray]] = []
    times: list[float] = []
    for index in range(1, len(table)):
        if valid_step[index]:
            segments.append([xy[index - 1], xy[index]])
            times.append(float(table.iloc[index]["time_s"]))
    return np.asarray(segments), np.asarray(times)


def _arena_patch(calibration, **kwargs):
    from .arena import half_extents
    x, y = half_extents(calibration)
    if calibration.get("type") == "rectangle":
        return mpl.patches.Rectangle((-x, -y), 2*x, 2*y, **kwargs)
    return mpl.patches.Circle((0, 0), x, **kwargs)


def save_trajectory_plot(
    table: pd.DataFrame, calibration: dict[str, Any], plots: Path
) -> None:
    fig, axis = plt.subplots(figsize=(3.45, 3.55), facecolor="white")
    segments, times = path_segments(table, display=True)
    if len(segments):
        line = LineCollection(segments, cmap="viridis", linewidths=0.85, alpha=0.9)
        line.set_array(times)
        axis.add_collection(line)
        colorbar = fig.colorbar(line, ax=axis, fraction=0.045, pad=0.02)
        colorbar.set_label("Time (s)", fontsize=6)
        colorbar.ax.tick_params(labelsize=5.5, length=2)
    from .arena import half_extents
    half_x, half_y = half_extents(calibration)
    radius = max(half_x, half_y)
    axis.add_patch(
        _arena_patch(
            calibration,
            fill=False,
            edgecolor="#374151",
            linewidth=0.7,
            linestyle=(0, (3, 2)),
        )
    )
    good = table[table["display_analyzable"]]
    if len(good):
        axis.scatter(
            good.iloc[0]["head_x_mm_display"],
            good.iloc[0]["head_y_mm_display"],
            s=18,
            c="#009E73",
            zorder=4,
        )
        axis.scatter(
            good.iloc[-1]["head_x_mm_display"],
            good.iloc[-1]["head_y_mm_display"],
            s=20,
            c="#D55E00",
            marker="X",
            zorder=4,
        )
    margin = max(2.0, radius * 0.06)
    scale_length = min(10.0, radius * 0.5)
    bar_y = half_y - max(3.0, radius * 0.10)
    bar_x0 = -half_x + max(3.0, radius * 0.10)
    axis.plot(
        [bar_x0, bar_x0 + scale_length],
        [bar_y, bar_y],
        color="#111827",
        lw=1.5,
        solid_capstyle="butt",
    )
    axis.text(
        bar_x0 + scale_length / 2.0,
        bar_y - 0.15 * scale_length,
        f"{scale_length:g} mm",
        ha="center",
        va="bottom",
        fontsize=6,
    )
    axis.set_xlim(-half_x - margin, half_x + margin)
    axis.set_ylim(half_y + margin, -half_y - margin)
    axis.set_aspect("equal")
    axis.axis("off")
    fig.tight_layout(pad=0.2)
    _save_figure(fig, plots / "01_time_colored_swimming_trajectory")


def save_distance_plot(table: pd.DataFrame, plots: Path) -> None:
    time = table["time_s"].to_numpy(float)
    cumulative = table["cumulative_distance_mm"].to_numpy(float)
    cumulative_all = table["cumulative_distance_including_contact_mm"].to_numpy(float)
    speed = table["speed_mm_s"].to_numpy(float)
    if len(time) > 1:
        time_step = float(np.nanmedian(np.diff(time)))
        window = max(3, int(round(1.0 / time_step))) if time_step > 0 else 3
    else:
        window = 3
    speed_roll = pd.Series(speed).rolling(
        window, center=True, min_periods=max(1, window // 3)
    ).median()
    fig, axes = plt.subplots(
        2,
        1,
        figsize=(3.65, 3.25),
        sharex=True,
        gridspec_kw={"hspace": 0.12},
    )
    axes[0].plot(
        time,
        cumulative_all,
        color="#9CA3AF",
        lw=0.75,
        ls=(0, (3, 2)),
        label="Including contact",
    )
    axes[0].plot(
        time, cumulative, color="#2A9D8F", lw=1.15, label="Strict non-contact"
    )
    axes[0].set_ylabel("Cumulative distance (mm)")
    axes[0].legend(loc="upper left", fontsize=5.5, handlelength=2.2)
    axes[1].plot(time, speed_roll, color="#E76F51", lw=0.8)
    axes[1].set_ylabel("Speed (mm s$^{-1}$)")
    axes[1].set_xlabel("Time (s)")
    for axis in axes:
        axis.grid(axis="y", color="#E5E7EB", lw=0.4)
        axis.tick_params(labelsize=6, length=2.5, width=0.6)
    fig.subplots_adjust(left=0.17, right=0.98, bottom=0.14, top=0.98, hspace=0.12)
    _save_figure(fig, plots / "02_cumulative_distance_and_speed")


def save_repeat_distance_plot(repeats: pd.DataFrame, plots: Path) -> None:
    fig, axis = plt.subplots(figsize=(2.15, 2.35), facecolor="white")
    if repeats.empty:
        axis.text(
            0.5,
            0.5,
            "No stimulation bouts",
            transform=axis.transAxes,
            ha="center",
            va="center",
            color="#6B7280",
            fontsize=7,
        )
        axis.set_axis_off()
        fig.tight_layout(pad=0.45)
        _save_figure(fig, plots / "03_post_stimulus_repeat_distance")
        return
    values = repeats["distance_2s_post_stimulus_mm"].to_numpy(float)
    adequate = repeats["coverage_fraction_fixed_window"].to_numpy(float) >= 0.8
    colors = np.where(adequate, "#176B63", "#6B7280")
    mean_value = float(np.nanmean(values))
    standard_deviation = float(np.nanstd(values, ddof=1)) if len(values) > 1 else 0.0
    jitter = np.linspace(-0.14, 0.14, len(values))
    axis.bar(
        [0], [mean_value], width=0.58, color="#66C2A5", alpha=0.62, edgecolor="none"
    )
    axis.errorbar(
        [0],
        [mean_value],
        yerr=[standard_deviation],
        fmt="none",
        ecolor="#111827",
        elinewidth=0.75,
        capsize=2.5,
        capthick=0.75,
        zorder=3,
    )
    axis.scatter(
        jitter,
        values,
        s=18,
        color=colors,
        edgecolor="white",
        linewidth=0.35,
        zorder=4,
    )
    axis.set_ylabel("Distance in 2 s (mm)")
    axis.set_xticks([0], ["Post-stimulus"])
    axis.set_xlim(-0.48, 0.48)
    axis.grid(axis="y", color="#E5E7EB", lw=0.4)
    axis.tick_params(labelsize=6, length=2.5, width=0.6)
    upper = max(float(np.nanmax(values)), mean_value + standard_deviation, 1e-6)
    axis.text(
        0,
        upper * 1.07,
        f"n = {len(values)} bouts",
        ha="center",
        va="bottom",
        fontsize=6,
    )
    axis.set_ylim(0, upper * 1.23)
    if (~adequate).any():
        handle = mpl.lines.Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markerfacecolor="#6B7280",
            markeredgecolor="white",
            markersize=4,
            label="Coverage <80%",
        )
        axis.legend(
            handles=[handle],
            loc="upper right",
            fontsize=5.1,
            handletextpad=0.25,
            borderaxespad=0.1,
        )
    fig.tight_layout(pad=0.45)
    _save_figure(fig, plots / "03_post_stimulus_repeat_distance")


def save_repeat_trajectory_plot(
    table: pd.DataFrame,
    repeats: pd.DataFrame,
    calibration: dict[str, Any],
    plots: Path,
) -> None:
    if repeats.empty:
        fig, axis = plt.subplots(figsize=(3.0, 1.8), facecolor="white")
        axis.text(
            0.5,
            0.5,
            "No stimulation bouts",
            transform=axis.transAxes,
            ha="center",
            va="center",
            color="#6B7280",
            fontsize=7,
        )
        axis.set_axis_off()
        fig.tight_layout(pad=0.35)
        _save_figure(fig, plots / "04_post_stimulus_repeat_trajectories")
        return
    count = len(repeats)
    columns = min(4, count)
    rows = int(math.ceil(count / columns))
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(1.72 * columns, 1.75 * rows),
        facecolor="white",
        squeeze=False,
    )
    flat_axes = axes.reshape(-1)
    from .arena import half_extents
    half_x, half_y = half_extents(calibration)
    radius = max(half_x, half_y)
    margin = max(2.0, radius * 0.06)
    for axis, (_, repeat) in zip(flat_axes, repeats.iterrows()):
        subset = table.iloc[
            int(repeat["response_start_frame_index"]) : int(
                repeat["response_end_frame_index_exclusive"]
            )
        ].reset_index(drop=True)
        segments, times = path_segments(subset)
        if len(segments):
            line = LineCollection(segments, cmap="viridis", linewidths=1.0, alpha=0.95)
            line.set_array(times - times.min())
            axis.add_collection(line)
        axis.add_patch(
            _arena_patch(
                calibration,
                fill=False,
                edgecolor="#9CA3AF",
                linewidth=0.55,
                linestyle=(0, (3, 2)),
            )
        )
        good = subset[np.isfinite(subset["step_distance_mm"])]
        if len(good):
            axis.scatter(
                good.iloc[0]["head_x_mm_smooth"],
                good.iloc[0]["head_y_mm_smooth"],
                s=8,
                c="#009E73",
                zorder=4,
            )
            axis.scatter(
                good.iloc[-1]["head_x_mm_smooth"],
                good.iloc[-1]["head_y_mm_smooth"],
                s=9,
                c="#D55E00",
                marker="X",
                zorder=4,
            )
        axis.set_title(
            f"{int(repeat['stimulus_bout'])} | "
            f"{repeat['distance_2s_post_stimulus_mm']:.1f} mm",
            fontsize=6,
            pad=1,
        )
        axis.set_xlim(-half_x - margin, half_x + margin)
        axis.set_ylim(half_y + margin, -half_y - margin)
        axis.set_aspect("equal")
        axis.axis("off")
    for axis in flat_axes[count:]:
        axis.axis("off")
    fig.tight_layout(pad=0.35, w_pad=0.25, h_pad=0.3)
    _save_figure(fig, plots / "04_post_stimulus_repeat_trajectories")


def save_stimulation_timeline(
    table: pd.DataFrame,
    events: pd.DataFrame,
    repeats: pd.DataFrame,
    fps: float,
    review_config: dict[str, Any],
    plots: Path,
) -> None:
    episodes = cleaned_contact_episode_runs(table, fps, review_config)
    times = table["time_s"].to_numpy(float)
    fig, axis = plt.subplots(figsize=(4.8, 1.55), facecolor="white")
    for start, end in episodes:
        axis.broken_barh(
            [(times[start], times[end] - times[start] + 1.0 / fps)],
            (2.08, 0.42),
            facecolors="#D55E00",
            edgecolors="none",
        )
    for _, event in events.iterrows():
        axis.broken_barh(
            [
                (
                    event["start_time_s"],
                    event["end_time_s"] - event["start_time_s"] + 1.0 / fps,
                )
            ],
            (1.16, 0.42),
            facecolors="#7B6FD0",
            edgecolors="none",
        )
        axis.text(
            (event["start_time_s"] + event["end_time_s"]) / 2.0,
            1.77,
            str(int(event["stimulus_bout"])),
            ha="center",
            va="center",
            fontsize=5,
            color="#374151",
        )
    for _, repeat in repeats.iterrows():
        axis.broken_barh(
            [
                (
                    repeat["response_start_time_s"],
                    repeat["nominal_response_window_s"],
                )
            ],
            (0.24, 0.42),
            facecolors="#2A9D8F",
            edgecolors="none",
        )
    axis.set_yticks([2.29, 1.37, 0.45])
    axis.set_yticklabels(
        ["Contact episodes", "Stimulation bouts", "2-s response windows"]
    )
    axis.set_xlim(0, times[-1] + 1.0 / fps)
    axis.set_ylim(0, 2.75)
    axis.set_xlabel("Time (s)")
    axis.tick_params(labelsize=5.8, length=2.2, width=0.6)
    axis.spines["left"].set_visible(False)
    fig.tight_layout(pad=0.4)
    _save_figure(fig, plots / "05_stimulation_timeline_and_response_windows")


def save_tracking_qa_montage(
    video_path: Path, table: pd.DataFrame, plots: Path
) -> None:
    capture = cv2.VideoCapture(str(video_path))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    picks = np.linspace(0, len(table) - 1, min(24, len(table))).astype(int)
    fig, axes = plt.subplots(4, 6, figsize=(7.2, 9.2), squeeze=False)
    for axis in axes.ravel():
        axis.axis("off")
    for axis, index in zip(axes.ravel(), picks):
        row = table.iloc[index]
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(row["raw_frame"]))
        ok, frame = capture.read()
        if not ok:
            continue
        axis.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        color = "#009E73" if row["analyzable"] else "#D55E00"
        axis.scatter(
            row["head_x_px"],
            row["head_y_px"],
            s=28,
            facecolors="none",
            edgecolors=color,
            linewidths=1,
        )
        axis.set_title(f"{row['time_s']:.1f} s", fontsize=6)
        axis.set_xlim(0, width)
        axis.set_ylim(height, 0)
        axis.axis("off")
    capture.release()
    fig.tight_layout(pad=0.3)
    _save_figure(fig, plots / "06_tracking_QA_montage", png_dpi=400)


def save_stimulation_qa_montage(
    video_path: Path, table: pd.DataFrame, events: pd.DataFrame, plots: Path
) -> None:
    if events.empty:
        fig, axis = plt.subplots(figsize=(3.0, 1.8), facecolor="white")
        axis.text(
            0.5,
            0.5,
            "No stimulation bouts",
            transform=axis.transAxes,
            ha="center",
            va="center",
            color="#6B7280",
            fontsize=7,
        )
        axis.set_axis_off()
        _save_figure(fig, plots / "07_stimulation_bout_QA_montage", png_dpi=400)
        return
    capture = cv2.VideoCapture(str(video_path))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    columns = min(4, len(events))
    rows = int(math.ceil(len(events) / columns))
    fig, axes = plt.subplots(
        rows, columns, figsize=(1.8 * columns, 2.65 * rows), squeeze=False
    )
    flat_axes = axes.reshape(-1)
    for axis, (_, event) in zip(flat_axes, events.iterrows()):
        row = table.iloc[int(event["closest_frame_index"])]
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(row["raw_frame"]))
        ok, frame = capture.read()
        if ok:
            axis.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            axis.scatter(
                row["head_x_px"],
                row["head_y_px"],
                s=42,
                facecolors="none",
                edgecolors="#00C853",
                linewidths=1.1,
            )
        axis.set_title(
            f"Bout {int(event['stimulus_bout'])}: "
            f"{event['start_time_s']:.1f}-{event['end_time_s']:.1f} s\n"
            f"{int(event['contact_episode_count'])} contact episode(s)",
            fontsize=6,
        )
        axis.set_xlim(0, width)
        axis.set_ylim(height, 0)
        axis.axis("off")
    for axis in flat_axes[len(events) :]:
        axis.axis("off")
    capture.release()
    fig.tight_layout(pad=0.3)
    _save_figure(fig, plots / "07_stimulation_bout_QA_montage", png_dpi=400)


def save_annotated_video(
    video_path: Path, table: pd.DataFrame, output_path: Path, fps: float,
    tracks: np.ndarray | None = None, point_ids: list[int] | None = None,
) -> None:
    capture = cv2.VideoCapture(str(video_path))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = 0.5 if width > 800 else 1.0
    output_size = (int(round(width * scale)), int(round(height * scale)))
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, output_size
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("Could not create QA video / 无法创建检查视频")
    trail: list[tuple[tuple[int, int], bool]] = []
    current_raw_frame = -1
    for track_index, (_, row) in enumerate(table.iterrows()):
        target = int(row["raw_frame"])
        ok = False
        frame = None
        while current_raw_frame < target:
            ok, frame = capture.read()
            if not ok:
                break
            current_raw_frame += 1
        if not ok or frame is None:
            continue
        if scale != 1.0:
            frame = cv2.resize(frame, output_size, interpolation=cv2.INTER_AREA)
        if tracks is not None:
            for query_index, coordinate in enumerate(tracks[track_index]):
                location = tuple(np.rint(coordinate * scale).astype(int))
                label = point_ids[query_index] if point_ids is not None else query_index + 1
                cv2.circle(frame, location, 2, (0, 210, 255), -1, cv2.LINE_AA)
                cv2.putText(frame, str(label), (location[0]+3, location[1]-3),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 80, 255), 1, cv2.LINE_AA)
        point = (
            int(round(float(row["head_x_px"]) * scale)),
            int(round(float(row["head_y_px"]) * scale)),
        )
        color = (115, 158, 0) if row["analyzable"] else (0, 106, 213)
        trail.append((point, bool(row["analyzable"])))
        trail = trail[-max(2, int(round(2 * fps))) :]
        for index in range(1, len(trail)):
            if trail[index - 1][1] and trail[index][1]:
                cv2.line(
                    frame,
                    trail[index - 1][0],
                    trail[index][0],
                    (160, 190, 70),
                    1,
                    cv2.LINE_AA,
                )
        cv2.circle(
            frame,
            point,
            max(4, int(round(7 * scale))),
            color,
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            f"{row['time_s']:5.1f} s",
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
        if row["forceps_near_head"]:
            cv2.putText(
                frame,
                "contact excluded",
                (8, 44),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 106, 213),
                1,
                cv2.LINE_AA,
            )
        writer.write(frame)
    capture.release()
    writer.release()


def save_analysis_plots(
    table: pd.DataFrame,
    events: pd.DataFrame,
    repeats: pd.DataFrame,
    config: dict[str, Any],
    plots: Path,
    fps: float,
) -> None:
    plots.mkdir(parents=True, exist_ok=True)
    save_trajectory_plot(table, config["dish_calibration"], plots)
    save_distance_plot(table, plots)
    save_repeat_distance_plot(repeats, plots)
    save_repeat_trajectory_plot(table, repeats, config["dish_calibration"], plots)
    save_stimulation_timeline(
        table,
        events,
        repeats,
        fps,
        config["forceps_contact_review"],
        plots,
    )
