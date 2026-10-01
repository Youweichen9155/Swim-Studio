#!/usr/bin/env python3
"""Create an isolated Python environment and launch the desktop UI."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent

def main():
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        print('Install Python 3.12 from https://www.python.org/downloads/\n请先安装 Python 3.12。')
        return 1
    directory = ROOT / '.venv-gui'
    python = directory / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Creating isolated environment / 创建独立运行环境…', flush=True)
        venv.EnvBuilder(with_pip=True).create(directory)
    requirements = ROOT / 'requirements-gui.txt'
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = directory / '.swim-requirements'
    if not marker.is_file() or marker.read_text() != digest:
        print('Installing analysis libraries (first launch needs internet) / 首次启动联网安装分析依赖…', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        marker.write_text(digest)
    return subprocess.call([str(python), str(ROOT / 'tadpole_gui.py')])

if __name__ == '__main__':
    raise SystemExit(main())
