"""Start a disposable local app and run its Playwright UI test suite."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    node=os.environ.get('NODE_BINARY') or shutil.which('node')
    if not node: raise RuntimeError('Node.js and Playwright are required for UI tests')
    with tempfile.TemporaryDirectory(prefix='swim-ui-') as temporary:
        folder=Path(temporary)
        video=folder/'synthetic.mp4'
        subprocess.run([sys.executable,str(ROOT/'tests/create_synthetic_video.py'),str(video)],check=True)
        server=subprocess.Popen([sys.executable,'-u',str(ROOT/'tadpole_gui.py'),'--no-browser','--workspace',str(folder/'workspace')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
        try:
            url=None
            for line in server.stdout:
                match=re.search(r'http://127\.0\.0\.1:\d+/[^\s]+/',line)
                if match:
                    url=match.group();break
            if not url:raise RuntimeError('Local test server did not start')
            subprocess.run([node,str(ROOT/'tests/test_ui.cjs'),url,str(video)],check=True)
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()
    return 0

if __name__=='__main__':raise SystemExit(main())
