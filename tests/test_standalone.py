#!/usr/bin/env python3
"""Exercise the packaged executable with no Python/Git on its PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('--video', type=Path, required=True, help='Synthetic test recording')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='swim-standalone-') as temp:
        work = Path(temp)
        env = os.environ.copy()
        env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
        env['PATH'] = os.path.join(env.get('SystemRoot', 'C:\\Windows'), 'System32') if os.name == 'nt' else '/usr/bin:/bin'
        env['TORCH_HOME'] = str(work / 'empty-torch-cache')
        env['HF_HOME'] = str(work / 'empty-hf-cache')
        env['HTTP_PROXY'] = env['HTTPS_PROXY'] = 'http://127.0.0.1:9'
        env['NO_PROXY'] = '127.0.0.1,localhost'
        process = subprocess.Popen([str(args.executable.resolve()), '--headless', '--workspace', str(work)], env=env)
        try:
            deadline = time.monotonic() + 120
            while not (work / 'desktop-session.json').exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Standalone server did not start')
                time.sleep(.25)
            url = json.loads((work / 'desktop-session.json').read_text())['url']
            assets = {'': 'text/html', 'app.js': ('text/javascript', 'application/javascript'),
                      'style.css': 'text/css', 'guide-zh.svg': 'image/svg+xml',
                      'guide-en.svg': 'image/svg+xml', 'guide-frog-zh.svg': 'image/svg+xml',
                      'guide-frog-en.svg': 'image/svg+xml', 'frog-real-example.png':'image/png'}
            for asset, expected_type in assets.items():
                with urllib.request.urlopen(url + asset, timeout=30) as response:
                    assert response.status == 200, asset
                    allowed = (expected_type,) if isinstance(expected_type, str) else expected_type
                    assert response.headers.get_content_type() in allowed, asset
                    assert len(response.read()) > 100, asset
            def request(route, data=None, raw=False):
                body = data if raw else (json.dumps(data).encode() if data is not None else None)
                req = urllib.request.Request(url + 'api/' + route, data=body)
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.load(r)
            assert request('runtime')['model_included'] is True
            def run(project):
                project.update(reviewed=True, calibration_reviewed=True)
                request('run', project)
                limit = time.monotonic() + 600
                while time.monotonic() < limit:
                    status = request('status')
                    if status['status'] != 'running':
                        assert status['status'] == 'complete', status
                        return status['summary']
                    time.sleep(.5)
                raise TimeoutError('Standalone worker timed out')
            demo = request('demo', {})
            summary = run(demo)
            assert abs(summary['total_analyzable_distance_mm'] - 340.6404826759847) < 1e-9
            target = request('upload?name=synthetic.mp4', args.video.read_bytes(), raw=True)
            config = target['config']
            config['head_point_selection']['query_points_raw_px'] = [[74,104],[74,116],[84,105],[84,115]]
            config['model_tracking'].update(device='cpu', model_size_px=[384,384])
            config['dish_calibration'] = {'type':'rectangle', 'corners_raw_px': [[15,20],[305,20],[305,220],[15,220]], 'width_mm':200, 'height_mm':85}
            config['output']['make_video_qa'] = True
            tracked = run(target)
            assert tracked['tracked_frames'] == 48
            assert tracked['analyzable_fraction'] > .95
            assert tracked['total_analyzable_distance_mm'] > 0
            assert not (work / 'empty-torch-cache/hub/checkpoints/scaled_online.pth').exists()
            # Exercise the frog worker in the frozen application with the same
            # synthetic recording. Shape assertions belong to test_frog_mode.py.
            config['output']['snapshot_times_s']=[.3,.5]
            config['animal_mode'] = 'frog'
            config['frog_hindlimb'] = {'enabled':True, 'axis_points_raw_px':[[64,110],[96,110]],
                'threshold':120, 'polarity':'dark', 'crop_body_lengths':4.0}
            frog = run(target)
            assert frog['animal_mode'] == 'frog'
            assert 'hindlimb_valid_fraction' in frog
            assert len(frog['requested_snapshots']) == 2
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({'status':'PASS','platform':os.name,'web_assets':list(assets),'cached_demo':summary,'fresh_synthetic_model':tracked,'frog_model':frog,'empty_model_cache':True,'external_download_proxy_blocked':True,'no_python_or_git_from_user_PATH':True}, indent=2))
            print('Standalone application and offline fresh-model tracking: PASS')
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()

if __name__ == '__main__':
    main()
