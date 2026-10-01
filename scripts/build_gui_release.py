#!/usr/bin/env python3
"""Bundle source, launchers and de-identified examples, excluding workspaces."""
from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / 'VERSION').read_text().strip()
output = ROOT / 'dist'
output.mkdir(exist_ok=True)
archive = output / f'swim-studio-{version}-windows-macos.zip'
folders = ['tadpole_tracking', 'web', 'docs', 'examples', 'test_data', 'tests', 'scripts', 'licenses', '.github']
files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in {'.py', '.md', '.txt', '.yml', '.command', '.bat'}]
files += [ROOT / 'VERSION', ROOT / '.gitignore']
for folder in folders:
    files.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name != 'ui-test-failure.png')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(set(files)):
        z.write(p, f'swim-studio-{version}/{p.relative_to(ROOT).as_posix()}')
    assert z.testzip() is None
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(output / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n')
print(f'{archive}\n{len(set(files))} files; {archive.stat().st_size:,} bytes\nSHA256 {digest}')
