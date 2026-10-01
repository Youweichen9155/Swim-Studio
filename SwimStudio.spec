# Build separately on each target OS. Includes runtime, model and offline assets.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
assets = root / 'build_assets'
if not (assets / 'model_bundle/manifest.json').is_file():
    raise RuntimeError('Run scripts/prepare_desktop_assets.py first')
datas = [(str(root / name), name) for name in ['web', 'examples', 'test_data', 'licenses']]
datas += [(str(assets / 'model_bundle'), 'model_bundle'),
          (str(assets / 'build_record.json'), '.'),
          (str(assets / 'third_party_licenses'), 'third_party_licenses'),
          (str(root / 'THIRD_PARTY_NOTICES.md'), '.')]
for name in ['numpy', 'pandas', 'scipy', 'matplotlib', 'opencv-python-headless', 'torch', 'torchvision', 'einops']:
    datas += copy_metadata(name)
a = Analysis([str(root / 'desktop_app.py')],
    pathex=[str(root), str(assets / 'model_bundle/source')],
    binaries=[], datas=datas,
    hiddenimports=['gui_worker', 'cotracker.predictor', 'tkinter', 'tkinter.messagebox', 'matplotlib.backends.backend_pdf'],
    hookspath=[], hooksconfig={'matplotlib': {'backends': ['Agg']}},
    excludes=['pytest', 'IPython', 'notebook', 'tensorboard', 'triton'],
    noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Swim Studio', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Swim Studio')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='Swim Studio.app', icon=None,
        bundle_identifier='org.swimstudio.analysis',
        info_plist={'CFBundleShortVersionString': '1.2.0', 'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '15.0'})
