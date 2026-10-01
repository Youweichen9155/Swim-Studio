"""Animal-specific annotations; omitted mode preserves existing tadpole projects."""
import numpy as np


def animal_mode(config):
    return config.get("animal_mode", "tadpole")


def frog_defaults():
    return {"enabled": True, "axis_points_raw_px": [], "threshold": 120,
            "polarity": "dark", "crop_body_lengths": 4.0}


def hindlimb_enabled(config):
    return animal_mode(config) == "frog" and config.get("frog_hindlimb", {}).get("enabled", False)


def tracking_queries(config):
    points = list(config["head_point_selection"]["query_points_raw_px"])
    if hindlimb_enabled(config):
        points += config["frog_hindlimb"]["axis_points_raw_px"]
    return np.asarray(points, dtype=np.float32)


def validate_mode(config):
    if animal_mode(config) not in {"tadpole", "frog"}:
        raise ValueError("Choose Tadpole or Frog / 请选择蝌蚪或小蛙模式")
    f = config.get("frog_hindlimb", {})
    if not isinstance(f, dict) or not isinstance(f.get("enabled", False), bool):
        raise ValueError("Invalid hindlimb settings / 后肢设置无效")
    if not hindlimb_enabled(config):
        return
    points = np.asarray(f.get("axis_points_raw_px", []), dtype=float)
    if points.shape != (2, 2) or not np.isfinite(points).all() or np.linalg.norm(points[0]-points[1]) < 5:
        raise ValueError("Mark snout and rear trunk centre / 请依次标记吻端和躯干后端中点")
    x0, y0, x1, y1 = config["model_tracking"]["roi_raw_px"]
    if not ((points[:, 0] >= x0) & (points[:, 0] < x1) & (points[:, 1] >= y0) & (points[:, 1] < y1)).all():
        raise ValueError("Body-axis points must be inside the crop / 身体轴点须在裁剪框内")
    threshold = f.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not 1 <= threshold <= 254:
        raise ValueError("Foreground threshold must be 1–254 / 前景阈值应为 1–254")
    if f.get("polarity") not in {"dark", "light"}:
        raise ValueError("Choose dark or light foreground / 请选择深色或浅色动物")
    scale = f.get("crop_body_lengths")
    if isinstance(scale, bool) or not isinstance(scale, (float, int)) or not 2 <= scale <= 8:
        raise ValueError("Hindlimb crop must span 2–8 body lengths / 后肢窗口应为 2–8 个体长")
