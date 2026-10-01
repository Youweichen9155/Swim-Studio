# Changelog

## 1.3.0

- Added bilingual Tadpole and Frog / froglet modes, with mode-specific point selection and illustrated help.
- Frog mode exports trunk trajectories and posterior hindlimb silhouette width, with configurable foreground threshold, polarity and crop extent.
- Added body-axis tracking, mask review images/video, validity flags, width curves and frame-level measurements.
- Preserved legacy tadpole results and saved-project compatibility.

## 1.2.0 — Offline standalone applications

- Bundle the Python runtime, pinned CoTracker source and verified weights in a native desktop launcher.
- Keep user projects in a separate writable application-data directory.
- Run analysis workers through the packaged executable, with live logs and no Git/pip/model-download requirement.
- Add packaged-executable tests with an empty model cache and blocked download proxy, plus Windows x64 build automation.

# 1.1.0 — Local visual application

- Bilingual browser UI, local-only data processing and persistent projects.
- Interactive head/eye points, crop, circular-dish outline and four-corner rectangular-tank calibration.
- Explicit timebase override for slow-motion video; frame-based contact times follow that timebase.
- Reviewed-contact editor, adjustable sampling/QC settings and acquisition notes.
- Background jobs, cancellation, result/QA download and cache-only replay bundles.
- Windows/macOS launchers with isolated Python environments, illustrated guides and platform CI.
- Original 1.0 configuration and seven frozen metrics remain supported.
- Verify model weights before loading; interrupted source fetches are retryable.

# Changelog

## 1.0.0

- Frozen configuration-driven analysis package.
- Pinned CoTracker source commit and scaled-online checkpoint SHA256.
- Manual forceps intervals as the primary stimulus input.
- Cache-only numerical reproduction with no model execution.
- Provenance, edge-case handling, bilingual documentation, and sendable archive workflow.
