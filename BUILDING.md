# Build a standalone application

Build on the target operating system with Python 3.12. The published Windows package uses CPU PyTorch; build the Apple Silicon package on an Apple Silicon Mac. The Mac bundle declares macOS 15 as its minimum version.

```bash
python -m pip install -r requirements-gui.txt -r requirements-build.txt
python -m pip install torch torchvision einops
git clone https://github.com/facebookresearch/co-tracker.git build_model
git -C build_model checkout 82e02e8029753ad4ef13cf06be7f4fc5facdda4d
python scripts/prepare_desktop_assets.py --repository build_model
python -m PyInstaller --noconfirm SwimStudio.spec
```

On Windows, install `torch torchvision` from the official CPU index (`--index-url https://download.pytorch.org/whl/cpu`). The asset preparation step verifies the pinned model source and checkpoint, then records source hashes, package versions and licence notices. Build-time downloads are needed; the finished application runs offline.

Run `tests/create_synthetic_video.py` and `tests/test_standalone.py` as in `.github/workflows/desktop-build.yml`. The packaged test checks served HTML/CSS/JS/SVG assets, frozen numerical results and fresh model inference with no Python/Git on the user PATH, empty external model caches and a blocked download proxy.

Package the complete `dist/Swim Studio` directory on Windows or `dist/Swim Studio.app` on macOS. A publisher certificate and, for macOS, notarization are separate release steps. Do not add raw videos, user projects, credentials or local workspaces to release archives.
