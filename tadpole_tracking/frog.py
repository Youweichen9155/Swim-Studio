"""Body-aligned posterior silhouette measurements, with visible segmentation QA.

Width is the x95-x05 span of posterior foreground pixels, not foot separation,
joint angle, muscle strength or a pose-model prediction.
"""
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from .arena import raw_to_mm

SIZE = 384
ORIGIN = np.array([SIZE / 2, SIZE * .38])


def metric_matrix(calibration):
    if calibration.get("type") == "rectangle":
        source = np.asarray(calibration["corners_raw_px"], np.float32)
    else:
        source = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], np.float32)
    return cv2.getPerspectiveTransform(source, raw_to_mm(source, calibration).astype(np.float32))


def silhouette(frame, centre, axis, calibration, settings, body_length_mm):
    """Return aligned image, connected mask, core cutoff and physical scale."""
    cm = raw_to_mm(np.asarray([centre]), calibration)[0]
    endpoints = raw_to_mm(np.asarray(axis), calibration)
    forward = endpoints[0] - endpoints[1]
    length = np.linalg.norm(forward)
    if not np.isfinite(length) or not .4 * body_length_mm <= length <= 1.8 * body_length_mm:
        return None
    forward /= length
    right = np.array([-forward[1], forward[0]])
    scale = SIZE / (settings["crop_body_lengths"] * body_length_mm)
    align = np.eye(3)
    align[:2, :2] = np.stack([right, -forward]) * scale
    align[:2, 2] = ORIGIN - align[:2, :2] @ cm
    transform = align @ metric_matrix(calibration)
    bg = 255 if settings["polarity"] == "dark" else 0
    image = cv2.warpPerspective(frame, transform, (SIZE, SIZE), borderValue=(bg, bg, bg))
    available = cv2.warpPerspective(np.ones(frame.shape[:2], np.uint8), transform, (SIZE, SIZE), flags=cv2.INTER_NEAREST)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = (gray < settings["threshold"] if bg else gray > settings["threshold"]).astype(np.uint8)
    mask &= available
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    choices = [k for k in range(1, count) if stats[k, 4] > 30 and np.linalg.norm(centroids[k] - ORIGIN) < scale * body_length_mm]
    if not choices:
        return None
    k = min(choices, key=lambda n: np.linalg.norm(centroids[n] - ORIGIN))
    mask = (labels == k).astype(np.uint8)
    # Clipping and foreground touching the source boundary invalidate the span.
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        return None
    if (mask & (1-cv2.erode(available, np.ones((3,3), np.uint8)))).any():
        return None
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    yy, xx = np.indices(mask.shape)
    torso = (xx-ORIGIN[0])**2 + (yy-ORIGIN[1])**2 < (scale*body_length_mm*.65)**2
    peak = distance[torso].max()
    core_y = np.where(torso & (distance > peak*.5))[0]
    if peak < 2 or len(core_y) < 10:
        return None
    return image, mask, float(np.quantile(core_y, .95)), scale


def posterior_width(mask, cutoff, scale):
    yy, xx = np.where(mask & (np.indices(mask.shape)[0] > cutoff))
    if len(xx) < 15:
        return None
    left, right = np.quantile(xx, [.05, .95])
    return float((right-left)/scale), float(left), float(right), len(xx)


def analyse_hindlimbs(video, tracks, visible, raw_indices, body_table, config, paths, make_video=True):
    settings = config["frog_hindlimb"]
    calibration = config["dish_calibration"]
    body_length = np.linalg.norm(np.diff(raw_to_mm(np.asarray(settings["axis_points_raw_px"]), calibration), axis=0))
    if not np.isfinite(body_length) or body_length <= 0:
        raise ValueError("Invalid calibrated body length")
    cap = cv2.VideoCapture(str(video))
    masks, cutoffs, rows = [], [], []
    centres = body_table[["head_x_px", "head_y_px"]].to_numpy(float)
    valid_body = body_table["track_valid_observed"].to_numpy(bool)
    raw_frame = -1
    # Keep compact binary masks for a second pass, not all decoded source frames.
    for i, target in enumerate(raw_indices):
        frame = None
        while raw_frame < target:
            ok, frame = cap.read()
            if not ok:
                break
            raw_frame += 1
        item = None
        if frame is not None and valid_body[i] and visible[i].all() and np.isfinite(tracks[i]).all():
            item = silhouette(frame, centres[i], tracks[i], calibration, settings, body_length)
        if item is None:
            masks.append(None)
        else:
            _, mask, cutoff, scale = item
            masks.append(np.packbits(mask))
            cutoffs.append(cutoff)
        rows.append({"raw_frame":int(target), "time_s":float(body_table.iloc[i].time_s), "hindlimb_valid":False,
                     "hindlimb_silhouette_spread_mm":np.nan, "posterior_pixels":0})
    cap.release()
    fixed_cutoff = float(np.median(cutoffs)) if cutoffs else np.nan
    scale = SIZE / (settings["crop_body_lengths"] * body_length)
    for i, packed in enumerate(masks):
        if packed is None:
            continue
        value = posterior_width(np.unpackbits(packed).reshape(SIZE, SIZE), fixed_cutoff, scale)
        if value:
            rows[i].update(hindlimb_valid=True, hindlimb_silhouette_spread_mm=value[0], posterior_pixels=value[3])
    table = pd.DataFrame(rows)
    table["fixed_posterior_cutoff_mm_from_body_reference"] = (fixed_cutoff-ORIGIN[1])/scale
    values = table.hindlimb_silhouette_spread_mm.to_numpy().copy()
    valid = np.isfinite(values)
    edges = np.diff(np.r_[False, valid, False].astype(int))
    for a,b in zip(np.where(edges==1)[0],np.where(edges==-1)[0]):
        if b-a >= 5:
            values[a:b] = savgol_filter(values[a:b], 5, 2)
    table["hindlimb_spread_smoothed_mm"] = values
    table.to_csv(paths["tables"] / "10_frog_hindlimb_silhouette.tsv", sep="\t", index=False)
    valid_values = table.hindlimb_silhouette_spread_mm.dropna().to_numpy()
    result = {"hindlimb_valid_fraction":float(valid.mean()), "hindlimb_mean_spread_mm":float(valid_values.mean()) if len(valid_values) else None,
              "hindlimb_spread_p95_minus_p05_mm":float(np.ptp(np.quantile(valid_values,[.05,.95]))) if len(valid_values) else None,
              "hindlimb_metric":"posterior silhouette pixel x95-x05; not toe distance",
              "hindlimb_status":"measured" if len(valid_values) else "no_valid_segmentation"}
    if config["output"]["make_plots"]:
        from .plots import plt, _save_figure
        fig, ax = plt.subplots(figsize=(4.6,2.5))
        ax.plot(table.time_s, table.hindlimb_silhouette_spread_mm, color="#dfb58a", lw=.5, label="Framewise")
        ax.plot(table.time_s, table.hindlimb_spread_smoothed_mm, color="#d47729", lw=1, label="5-frame smoothing")
        ax.set(xlabel="Time (s)", ylabel="Hindlimb silhouette spread (mm)")
        if not len(valid_values):
            ax.text(.5,.5,"No valid segmentation: adjust threshold / axis points",ha="center",transform=ax.transAxes,fontsize=6)
        ax.legend(fontsize=5)
        _save_figure(fig, paths["plots"] / "10_frog_hindlimb_spread")
    # Always provide a compact mask montage; optional full review video.
    samples = set(np.linspace(0,len(rows)-1,min(12,len(rows))).astype(int))
    panels=[]
    cap=cv2.VideoCapture(str(video)); raw_frame=-1
    writer=None
    if make_video:
        fps=config["video"].get("timebase_fps",config["video"]["fps"])/config["model_tracking"]["frame_step"]
        writer=cv2.VideoWriter(str(paths["video"]/"frog_hindlimb_QA.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),fps,(SIZE,SIZE))
        if not writer.isOpened():
            cap.release()
            raise RuntimeError("Could not create hindlimb review video")
    try:
        for i,target in enumerate(raw_indices):
            if not make_video and i not in samples:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES,int(target))
            ok,frame=cap.read()
            item=silhouette(frame,centres[i],tracks[i],calibration,settings,body_length) if ok and np.isfinite(tracks[i]).all() else None
            image=item[0].copy() if item else np.full((SIZE,SIZE,3),240,np.uint8)
            if table.iloc[i].hindlimb_valid:
                mask=np.unpackbits(masks[i]).reshape(SIZE,SIZE)
                posterior=mask.astype(bool)&(np.indices(mask.shape)[0]>fixed_cutoff)
                image[posterior]=(image[posterior]*.4+np.array([40,140,240])*.6).astype(np.uint8)
                value=posterior_width(mask,fixed_cutoff,scale)
                cv2.line(image,(0,int(fixed_cutoff)),(SIZE-1,int(fixed_cutoff)),(160,120,60),1)
                for x in value[1:3]: cv2.line(image,(int(x),int(fixed_cutoff)),(int(x),SIZE-20),(180,120,20),1)
                label=f"Spread {value[0]:.2f} mm"
            else:
                label="Contact / tracking / mask excluded"
            cv2.putText(image,f"{table.iloc[i].time_s:.2f} s  {label}",(8,18),cv2.FONT_HERSHEY_SIMPLEX,.37,(20,20,20),1,cv2.LINE_AA)
            if writer: writer.write(image)
            if i in samples: panels.append(cv2.resize(image,(256,256)))
        if panels:
            montage=np.full(((len(panels)+3)//4*256,4*256,3),255,np.uint8)
            for k,panel in enumerate(panels): montage[k//4*256:(k//4+1)*256,k%4*256:(k%4+1)*256]=panel
            cv2.imwrite(str(paths["plots"]/"11_frog_hindlimb_mask_review.png"),montage)
    finally:
        cap.release()
        if writer: writer.release()
    return result
