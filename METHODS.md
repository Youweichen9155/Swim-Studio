# Methods

## 1. Analysis stages

The workflow deliberately separates four reviewed inputs:

1. **Model tracking** defines the video crop, model input size, CoTracker source, checkpoint, and cached point trajectories.
2. **Dish calibration** defines the dish centre, fitted ellipse diameters and angle, and physical dish diameter.
3. **Head-point selection** defines the raw-frame query points and any points excluded after visual drift review.
4. **Forceps-contact review** defines manually reviewed contact intervals independently of the image tracker.

No automatic forceps detector is used in the v1.0 primary analysis.

## 2. Point tracking and head position

Frames are cropped to the configured raw-pixel ROI and resized to the configured model input. Query points are transformed from raw-frame coordinates into model coordinates. CoTracker3 online jointly propagates all points through the recording. The repository is fixed to commit `82e02e8029753ad4ef13cf06be7f4fc5facdda4d`; the scaled-online checkpoint SHA256 is fixed in the JSON configuration.

For each frame, head position is the coordinate-wise median of retained tracked points. A frame passes tracking QC when at least the configured number of points is visible, median point spread does not exceed the configured threshold, and the head remains within the configured normalized dish radius. Query-point selection and exclusions are saved independently from model parameters.

## 3. Dish calibration

Let raw head position be `p`, fitted dish centre be `c`, fitted ellipse diameters be `(d_x, d_y)`, angle be `theta`, and nominal dish diameter be `D` millimetres. Coordinates are centred, rotated by `theta`, divided by the ellipse semi-axes, and multiplied by `D/2`:

```text
p_mm = rotate(p - c, theta) / (d_x/2, d_y/2) * (D/2)
```

The frozen v1.0 QC radius follows the source analysis and evaluates x/y displacement against the fitted diameters in raw-frame axes before the physical-coordinate rotation. This detail is retained for exact backward reproduction. The example ellipse is nearly circular, so angle sensitivity is small, but the distinction is documented.

## 4. Manual forceps intervals

The primary forceps table contains one reviewed interval per row. `start_s` and `end_s` preserve reviewed time boundaries. Optional inclusive `start_raw_frame` and `end_raw_frame` columns take precedence for frame assignment. They prevent one-frame changes when rounded decimal times are extremely close to video frame times.

Contact gaps no longer than 0.25 s are bridged to form cleaned contact episodes. Episodes shorter than 0.12 s are removed. Cleaned episodes separated by no more than 2.0 s are merged into one stimulation bout. These operations only group reviewed contact labels; they do not infer contact from image intensity or forceps geometry.

## 5. Motion calculation

Contact frames are removed from the strict motion mask before interpolation. Invalid runs no longer than 0.5 s and bounded by valid observations are linearly interpolated. Each coordinate is then smoothed with a second-order Savitzky-Golay filter whose window is the nearest odd frame count to 0.5 s, with a minimum length of five frames.

Step distance is the Euclidean displacement between consecutive analyzable smoothed positions. A step is undefined if either endpoint is not analyzable. Speeds greater than 200 mm/s are treated as invalid jumps. Strict total distance is the sum of retained step distances. Overall speed is strict total distance divided by the time of the last sampled frame, matching the frozen source analysis.

A separate including-contact trajectory is calculated for visual QA. A display-only trace can bridge gaps up to 2.0 s. Neither is used for the strict primary distance.

## 6. Post-stimulus response

For each merged stimulation bout, the response starts at the first sampled frame after the bout. The primary repeat metric is strict non-contact distance during the next 2.0 s, truncated at video end when necessary. Coverage is the fraction of requested response frames with finite strict step distance. Mean and median response summaries include all bouts, while coverage remains explicit in the repeat table.

Bout-level rows from one recording are repeated technical observations from one animal and are not independent biological replicates.

## 7. Provenance

Every run writes:

- program version and SHA256 values for Python source files;
- the effective JSON configuration and a flattened parameter manifest;
- configuration, tracking-cache, and manual-interval SHA256 values;
- video SHA256 calculated only when the video is present at runtime;
- Python and package versions;
- pinned CoTracker repository, commit, model name, checkpoint URL, checkpoint SHA256, and license reminder;
- whether CoTracker was executed or an existing cache was reused.

Runtime absolute paths are not stored.

## 8. Boundary handling

- An empty manual interval table produces zero contact frames and zero bouts.
- Zero bouts produce typed empty event/repeat tables and explicit placeholder plots.
- Short clips that cannot support the requested Savitzky-Golay window retain unsmoothed valid coordinates.
- Cache-only analysis does not import or execute torch/CoTracker.
- A response window that reaches video end is truncated and its coverage is reported.


## 8. GUI 1.1 calibration and timebase extensions

The GUI runs a loopback-only HTTP service with a random session path, Host/Origin checks and no cloud video transfer. Uploaded files are copied into a private local workspace. Each analysis snapshots configuration and reviewed contacts; the export includes cache-only replay inputs.

`dish_calibration.type` is optional. Absent or `legacy_ellipse` preserves the original raw-axis QC rule. `ellipse` uses the same physical coordinate transform with rotation-aware boundary QC. `rectangle` maps four perimeter-ordered image corners to a rectangle centred at (0, 0), with edge 1→2 mapped to width and edge 2→3 to height, using an OpenCV four-point homography. Rectangle boundary QC is max(abs(x)/(width/2), abs(y)/(height/2)). The configured boundary tolerance applies to that normalized quantity. This assumes coplanar motion; it does not correct refraction or lens distortion. See [OpenCV transformation documentation](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html).

Video metadata are always checked against the encoded file. Optional `video.timebase_fps` then sets the analysis clock (e.g., actual acquisition FPS for a slow-motion export). The encoded FPS is retained separately. Frame-index contact annotations are re-expressed on the selected clock; time-only tables are interpreted in the selected timebase. The override affects time, speed, smoothing/interpolation durations and response windows. The GUI requires calibration and contact review confirmation before a run.

Tracking settings and original query coordinates determine cache reuse. Excluding existing point IDs or changing downstream calibration/QC reuses matching trajectories; changing query locations, crop, frame step or model input settings triggers new tracking. Numerical output definitions otherwise remain the v1.0 definitions above.


## Frog mode (v1.3.0)

Frog mode tracks selected central trunk features rather than head/eye features. Visible trunk points define a median reference trajectory. Two additional CoTracker queries (snout and rear trunk centre) define the anterior axis; they do not enter the trunk median. The calibrated view is rotated anterior-up with a fixed physical scale derived from the initial body-axis length. Grayscale thresholding (dark or light polarity), a 3×3 closing operation and the connected component nearest the trunk reference define foreground. Border-clipped masks and axes outside 0.4–1.8 times initial length are rejected.

A distance transform identifies the thick torso core within 0.65 body lengths of the reference. The 95th percentile of core y-coordinates is found in each accepted frame; the median of those cutoffs defines a fixed posterior boundary for the recording. Width is x95−x05 over foreground pixels below that boundary, converted to mm. This follows the posterior silhouette-width concept used in the earlier frog analysis; the general application uses user-set contrast thresholding rather than a recording-specific clean-background subtraction. It is not toe separation or a joint-angle measurement.

Direct-contact frames, invisible axis points and invalid body tracking are excluded. Width is never interpolated across missing frames. A five-frame order-2 Savitzky–Golay curve is provided only within continuous valid segments; summary means and P95−P5 ranges use unsmoothed valid values. Always inspect the mask montage, video and valid-frame fraction. No camera-motion correction or automatic behavioural classification is implemented. Existing tadpole configurations retain their original numerical processing for reproducibility.
