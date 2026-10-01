# Swim Studio

Local, bilingual swimming analysis for **tadpoles and frogs/froglets**. Choose the animal mode before importing a video.

[中文说明](README_CN.md) · [Mac / Windows applications and source](https://github.com/Youweichen9155/Swim-Studio/releases/latest) · [User guide](GUI_GUIDE.md)

| Mode | Points to select | Measurements |
| --- | --- | --- |
| **Tadpole** | 4–6 stable head/eye features | Swimming distance, speed and trajectory |
| **Frog / froglet** | 4–6 central trunk features; snout and rear-trunk axis points | Trunk-referenced distance and speed, posterior hindlimb silhouette width over time |

## Workflow

1. Choose **Tadpole** or **Frog / froglet**, then import one-animal video.
2. Calibrate the dish or tank using its measured dimensions in mm.
3. Select stable head points for tadpoles or trunk points for frogs in the first frame. For frogs, also mark the snout and rear trunk centre with **Body axis**.
4. Check acquisition FPS. Manually mark direct stimulation contact, or confirm no contact.
5. Run analysis. Review the trajectory; for frogs also check the orange posterior mask and adjust foreground threshold if necessary.
6. Export tables, PDF/PNG plots, settings and review videos. Save projects to resume later.

### Tadpole guide

![Tadpole workflow](web/guide-en.svg)

### Frog guide

![Frog workflow](web/guide-frog-en.svg)

Enter `0.3, 0.5` under **Snapshots at chosen times** to export original frames, paired video/silhouette panels, separate silhouette PNG/PDF figures and a snapshot manifest. The hindlimb CSV/TSV contains time, frame number, width in mm and cm, and validity. Untracked or invalid frames retain missing measurements.

![Real frame and matched silhouette](web/frog-real-example.png)

Same-frame measurement example. Its value uses the example calibration; each project is measured using its own frames and calibration.

Frog mode measures the **5th–95th percentile width of posterior silhouette pixels** in a body-aligned view. This describes opening and closing of the hindlimb region; it is not toe-to-toe distance, a joint angle or a force measurement. Poorly segmented or occluded frames remain missing. Check both trajectory and hindlimb valid-frame coverage.

Use a fixed camera and approximately planar swimming. Camera motion is not corrected. For silhouette analysis, the animal should contrast clearly with the background; reflections, transparent animals or overlapping limbs may prevent reliable segmentation. Use the same settings and observation windows when comparing groups.

## Files and setup

The release page contains macOS Apple Silicon (macOS 15+) and Windows x64 applications with the runtime and model included. These packages are unsigned. For running from source, see [the user guide](GUI_GUIDE.md) and [build instructions](BUILDING.md).

- [中文操作指南](GUI_GUIDE_CN.md) · [Measurement definitions](METHODS.md)
- [Command-line reference](CLI_REFERENCE.md)
- [Release notes](CHANGELOG.md)

Videos are processed locally and are not included in this repository. The example contains de-identified cached tadpole trajectories. CoTracker3 is licensed under **CC BY-NC 4.0**, including its non-commercial restriction; see [third-party notices](THIRD_PARTY_NOTICES.md).
