"""Resource and worker locations shared by source and standalone builds."""
from pathlib import Path
import json
import os
import sys


def configure_stdio():
    """Keep bilingual progress output readable in Windows redirected streams."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')


def frozen():
    return bool(getattr(sys, 'frozen', False))


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def model_bundle():
    return resource_root() / 'model_bundle'


def default_workspace():
    if sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support'
    elif os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return root / 'Swim Studio' / 'projects'


def worker_command(action, config):
    if frozen():
        return [sys.executable, '--worker', action, str(config)]
    return [sys.executable, '-u', str(resource_root() / 'gui_worker.py'), action, str(config)]


def build_record():
    path = resource_root() / 'build_record.json'
    return json.loads(path.read_text()) if path.is_file() else {}
