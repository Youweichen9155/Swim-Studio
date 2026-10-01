"""Arena geometry. Legacy ellipse coordinates remain numerically unchanged."""
from __future__ import annotations

import math
import cv2
import numpy as np


def validate_arena(calibration: dict) -> None:
    mode = calibration.get("type", "legacy_ellipse")
    if mode not in {"legacy_ellipse", "ellipse", "rectangle"}:
        raise ValueError("Unknown arena type / 未知容器类型")
    if mode == "rectangle":
        corners = np.asarray(calibration.get("corners_raw_px", []), dtype=float)
        if corners.shape != (4, 2) or not np.isfinite(corners).all():
            raise ValueError("Select four tank corners in perimeter order / 沿边界依次选取四角")
        edges = np.roll(corners, -1, axis=0) - corners
        turns = edges[:, 0] * np.roll(edges[:, 1], -1) - edges[:, 1] * np.roll(edges[:, 0], -1)
        if not ((turns > 1e-5).all() or (turns < -1e-5).all()):
            raise ValueError("Tank corners must form a convex quadrilateral / 四角须组成凸四边形")
        if abs(cv2.contourArea(corners.astype(np.float32))) < 25:
            raise ValueError("Tank area is too small / 所选容器区域过小")
        sizes = np.asarray([calibration.get("width_mm", 0), calibration.get("height_mm", 0)], dtype=float)
    else:
        if np.asarray(calibration.get("center_raw_px", [])).shape != (2,):
            raise ValueError("Ellipse centre must contain x and y / 椭圆中心需包含 x、y")
        sizes = np.asarray(calibration.get("ellipse_diameters_px", []), dtype=float)
        if sizes.shape != (2,):
            raise ValueError("Specify both ellipse diameters / 请指定两个椭圆直径")
        values = [*calibration["center_raw_px"], calibration.get("ellipse_angle_degrees", 0), calibration.get("dish_diameter_mm", 0)]
        if not np.isfinite(values).all() or float(values[-1]) <= 0:
            raise ValueError("Invalid dish dimensions / 培养皿尺寸无效")
    if not np.isfinite(sizes).all() or (sizes <= 0).any():
        raise ValueError("Arena dimensions must be positive / 容器尺寸必须为正值")


def raw_to_mm(xy: np.ndarray, calibration: dict) -> np.ndarray:
    xy = np.asarray(xy, dtype=float)
    if calibration.get("type") == "rectangle":
        w, h = calibration["width_mm"], calibration["height_mm"]
        target = np.asarray([[-w/2, -h/2], [w/2, -h/2], [w/2, h/2], [-w/2, h/2]], np.float32)
        matrix = cv2.getPerspectiveTransform(np.asarray(calibration["corners_raw_px"], np.float32), target)
        homogeneous = np.column_stack([xy, np.ones(len(xy))]) @ matrix.T
        with np.errstate(divide="ignore", invalid="ignore"):
            return homogeneous[:, :2] / homogeneous[:, 2:3]
    center = np.asarray(calibration["center_raw_px"], dtype=float)
    diameters = np.asarray(calibration["ellipse_diameters_px"], dtype=float)
    theta = math.radians(float(calibration["ellipse_angle_degrees"]))
    rotation = np.asarray([[math.cos(theta), math.sin(theta)], [-math.sin(theta), math.cos(theta)]], dtype=float)
    return ((xy - center) @ rotation.T) / (diameters / 2.0) * (float(calibration["dish_diameter_mm"]) / 2.0)


def normalized_boundary(xy: np.ndarray, calibration: dict) -> np.ndarray:
    mode = calibration.get("type", "legacy_ellipse")
    if mode == "legacy_ellipse":
        # Frozen v1.0 used raw axes for QC; do not alter old recordings.
        center, diam = np.asarray(calibration["center_raw_px"]), np.asarray(calibration["ellipse_diameters_px"])
        return np.sqrt(((xy[:, 0] - center[0]) / (diam[0]/2))**2 + ((xy[:, 1] - center[1]) / (diam[1]/2))**2)
    mm = raw_to_mm(xy, calibration)
    if mode == "rectangle":
        return np.max(np.abs(mm) / np.asarray([calibration["width_mm"]/2, calibration["height_mm"]/2]), axis=1)
    return np.linalg.norm(mm, axis=1) / (calibration["dish_diameter_mm"]/2)


def half_extents(calibration: dict) -> tuple[float, float]:
    if calibration.get("type") == "rectangle":
        return calibration["width_mm"]/2, calibration["height_mm"]/2
    radius = calibration["dish_diameter_mm"]/2
    return radius, radius


def describe(calibration: dict) -> str:
    if calibration.get("type") == "rectangle":
        return (f"Four ordered corners are mapped by a planar homography to a "
                f"{calibration['width_mm']:g} x {calibration['height_mm']:g}-mm rectangle.")
    return (f"The fitted ellipse ({calibration['ellipse_diameters_px'][0]:.3f} x "
            f"{calibration['ellipse_diameters_px'][1]:.3f} px, "
            f"{calibration['ellipse_angle_degrees']:g} degrees) maps to a "
            f"{calibration['dish_diameter_mm']:g}-mm circle; "
            f"QC mode: {calibration.get('type', 'legacy_ellipse')}.")
