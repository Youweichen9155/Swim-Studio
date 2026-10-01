#!/usr/bin/env python3
"""Prepare verified offline model files and reproducibility metadata."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tadpole_tracking.config import COTRACKER_COMMIT, COTRACKER_CHECKPOINT_SHA256, COTRACKER_CHECKPOINT_URL

def digest(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repository', type=Path, required=True)
    p.add_argument('--checkpoint', type=Path)
    args = p.parse_args()
    git = shutil.which('git') or '/usr/bin/git'
    commit = subprocess.check_output([git, '-C', str(args.repository), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != COTRACKER_COMMIT:
        raise ValueError('CoTracker commit does not match')
    subprocess.run([git, '-C', str(args.repository), 'diff', '--exit-code', 'HEAD'], check=True)
    assets = ROOT / 'build_assets'
    bundle = assets / 'model_bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    checkpoint = args.checkpoint
    if checkpoint is None:
        checkpoint = assets / 'downloaded_scaled_online.pth'
        if not checkpoint.exists():
            urllib.request.urlretrieve(COTRACKER_CHECKPOINT_URL, checkpoint)
    if digest(checkpoint) != COTRACKER_CHECKPOINT_SHA256:
        raise ValueError('Checkpoint SHA256 does not match')
    shutil.copyfile(checkpoint, bundle / 'scaled_online.pth')
    names = subprocess.check_output([git, '-C', str(args.repository), 'ls-files', 'cotracker', 'hubconf.py', 'LICENSE'], text=True).splitlines()
    hashes = {}
    for name in names:
        src = args.repository / name
        if not src.is_file():
            continue
        dest = bundle / 'source' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        hashes[dest.relative_to(bundle).as_posix()] = digest(dest)
    (bundle / 'manifest.json').write_text(json.dumps({'commit': commit, 'checkpoint_sha256': COTRACKER_CHECKPOINT_SHA256, 'files': hashes}, indent=2))
    source = list(ROOT.glob('*.py')) + list((ROOT/'tadpole_tracking').glob('*.py')) + list((ROOT/'web').glob('*'))
    versions = {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}
    (assets / 'build_record.json').write_text(json.dumps({'source_sha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in source if p.is_file()}, 'packages': versions, 'python': sys.version}, indent=2))
    notices = assets / 'third_party_licenses'
    notices.mkdir(exist_ok=True)
    for dist in importlib.metadata.distributions():
        for file in dist.files or []:
            if ('license' in str(file).lower() or 'notice' in str(file).lower()) and ('.dist-info/' in str(file)):
                src = Path(dist.locate_file(file))
                if src.is_file():
                    dst = notices / dist.metadata['Name'] / Path(str(file)).name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
    print(f'Offline assets prepared: {assets}')

if __name__ == '__main__':
    main()
