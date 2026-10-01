# Third-party software and model notices

## CoTracker3

- Project: **CoTracker3: Simpler and Better Point Tracking by Pseudo-Labelling Real Videos**
- Authors: Nikita Karaev, Iurii Makarov, Jianyuan Wang, Natalia Neverova, Andrea Vedaldi, and Christian Rupprecht
- Source: <https://github.com/facebookresearch/co-tracker>
- Paper: <https://arxiv.org/abs/2410.11831>
- Frozen source commit: `82e02e8029753ad4ef13cf06be7f4fc5facdda4d`
- Model entry point: `cotracker3_online`
- Checkpoint source: <https://huggingface.co/facebook/cotracker3/resolve/main/scaled_online.pth>
- Frozen checkpoint SHA256: `205d34789f19699d64b22cf93f9b697f15f28d4025240e31532e504109837218`

**License reminder:** the majority of CoTracker is distributed under Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0). This includes a non-commercial restriction. Review the upstream repository and `licenses/CoTracker_LICENSE.md` before redistribution or any commercial use. Some upstream components have separate MIT or Apache-2.0 terms; consult the upstream notices for their exact scope.

The source-code archive does not include CoTracker source code or model weights. The standalone macOS and Windows applications include the pinned CoTracker source, verified weights and licence notices. The included `.npz` reproduction example contains only de-identified cached point coordinates, visibility values, frame indices and query points. No raw animal video is bundled.

## Python dependencies

The runtime uses NumPy, pandas, SciPy, Matplotlib, OpenCV, PyTorch, TorchVision and einops. Each standalone application records its actual package versions in `build_record.json` and includes dependency licence notices. `requirements-lock.txt` preserves the historical v1.0 environment; it is not the dependency lock for the desktop release. Their upstream projects and license texts remain authoritative:

- NumPy: <https://numpy.org/>
- pandas: <https://pandas.pydata.org/>
- SciPy: <https://scipy.org/>
- Matplotlib: <https://matplotlib.org/>
- OpenCV: <https://opencv.org/>
- PyTorch and TorchVision: <https://pytorch.org/>

