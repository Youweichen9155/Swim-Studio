"""Loopback-only desktop web UI; no cloud services or web framework required."""
from __future__ import annotations

import copy
import json
import mimetypes
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
import uuid
import zipfile
from .runtime import resource_root, worker_command, frozen

ROOT = resource_root()
# macOS bundles symlink Frameworks/web to Resources/web. Compare canonical
# paths on both sides of the containment check when serving bundled assets.
WEB = (ROOT / "web").resolve()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class Application:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.job = None
        self.process = None

    def project(self, key):
        if not isinstance(key, str) or len(key) != 32 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Invalid project / 项目无效")
        path = self.workspace / key
        if not path.is_dir() or path.is_symlink():
            raise ValueError("Project not found / 项目不存在")
        return path

    def create(self):
        key = uuid.uuid4().hex
        path = self.workspace / key
        path.mkdir()
        return key, path

    def projects(self):
        items = []
        for path in sorted(self.workspace.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                self.project(path.parent.name)
                info = read_json(path)
                items.append({"id": path.parent.name, "name": info["name"], "demo": info.get("demo", False)})
            except (ValueError, OSError, KeyError):
                continue
        return items

    def payload(self, key):
        path = self.project(key)
        return {"id": key, **read_json(path / "project.json"), "config": read_json(path / "config.json"),
                "intervals": (path / "contacts.tsv").read_text(encoding="utf-8")}

    def initialize(self, key, name, metadata=None, demo=False):
        path = self.project(key)
        config = read_json(ROOT / "examples/configs/tadpole_recording_001.json")
        config["analysis_id"] = key
        config["video"]["logical_name"] = name
        config["model_tracking"]["cache_path"] = "tracks.npz"
        config["model_tracking"]["repository_path"] = os.path.relpath(self.workspace / "model/co-tracker", path).replace(os.sep, "/")
        config["forceps_contact_review"]["intervals_tsv"] = "contacts.tsv"
        config["output"]["directory"] = "results"
        if demo:
            config["video"]["path"] = "not_bundled.mp4"
            shutil.copyfile(ROOT / "test_data/example_recording/cotracker_head_points.npz", path / "tracks.npz")
            shutil.copyfile(ROOT / "examples/forceps_intervals/tadpole_recording_001_forceps_contacts.tsv", path / "contacts.tsv")
        else:
            width, height = metadata["width_px"], metadata["height_px"]
            config["schema_version"] = "1.1"
            config["video"].update(path="input" + Path(name).suffix.lower(), fps=metadata["raw_fps"],
                                   frame_count=metadata["raw_frame_count"], width_px=width, height_px=height)
            config["model_tracking"].update(roi_raw_px=[0, 0, width, height], model_size_px=[560, 560], device="cpu")
            config["head_point_selection"].update(query_points_raw_px=[], maximum_spread_px=38, drop_query_indices=[])
            config["dish_calibration"] = {"type": "ellipse", "center_raw_px": [width/2, height/2],
                "ellipse_diameters_px": [width*0.7, height*0.7], "ellipse_angle_degrees": 0, "dish_diameter_mm": 100}
            (path / "contacts.tsv").write_text("start_s\tend_s\n", encoding="utf-8")
        write_json(path / "config.json", config)
        write_json(path / "project.json", {"name": name, "demo": demo, "reviewed": demo, "calibration_reviewed": demo, "created": time.time()})
        return self.payload(key)

    def demo(self):
        key, _ = self.create()
        return self.initialize(key, "Demo · cached recording", demo=True)

    def save(self, data):
        from .config import validate_config
        from .inputs import load_forceps_intervals
        path = self.project(data["id"])
        info = read_json(path / "project.json")
        original = read_json(path / "config.json")
        config = copy.deepcopy(data["config"])
        # File destinations and immutable video metadata are owned by the app.
        for key in ("path", "fps", "frame_count", "width_px", "height_px", "logical_name"):
            config["video"][key] = original["video"][key]
        for key in ("cache_path", "repository_path"):
            config["model_tracking"][key] = original["model_tracking"][key]
        config["forceps_contact_review"]["intervals_tsv"] = "contacts.tsv"
        config["output"]["directory"] = "results"
        config["analysis_id"] = original["analysis_id"]
        validate_config(config)
        if not data.get("calibration_reviewed"):
            raise ValueError("Verify arena calibration / 请先核对容器校准")
        text = data.get("intervals", "start_s\tend_s\n")
        if not isinstance(text, str) or len(text) > 1_000_000:
            raise ValueError("Invalid contact table / 接触时间表无效")
        pending = path / "contacts.pending.tsv"
        pending.write_text(text, encoding="utf-8")
        try:
            intervals = load_forceps_intervals(pending)
            fps = config["video"].get("timebase_fps", config["video"]["fps"])
            end = (config["video"]["frame_count"] - 1) / fps
            if len(intervals) and (intervals["end_s"].max() > end + 1e-6):
                raise ValueError("Contact interval extends past video / 接触区间超出视频")
            if "end_raw_frame" in intervals and len(intervals) and intervals["end_raw_frame"].max() >= config["video"]["frame_count"]:
                raise ValueError("Contact frame exceeds video / 接触帧超出视频")
            if not data.get("reviewed"):
                raise ValueError("Review contact intervals or confirm no contact / 请核对接触区间或确认无接触")
            if info.get("demo") and (config["head_point_selection"]["query_points_raw_px"] != original["head_point_selection"]["query_points_raw_px"] or config["model_tracking"]["frame_step"] != original["model_tracking"]["frame_step"]):
                raise ValueError("Demo cache has fixed query points and sampling / 演示缓存的追踪点及采样固定")
            pending.replace(path / "contacts.tsv")
        finally:
            pending.unlink(missing_ok=True)
        write_json(path / "config.json", config)
        info["reviewed"] = True
        info["calibration_reviewed"] = True
        write_json(path / "project.json", info)
        return self.payload(data["id"])

    def start(self, data, setup=False):
        with self.lock:
            if (self.job and self.job["status"] == "running") or (self.process and self.process.poll() is None):
                raise ValueError("A task is already running / 已有任务正在运行")
            project = self.payload(data["id"]) if setup else self.save(data)
            key = data["id"]
            run = uuid.uuid4().hex[:12]
            path = self.project(key)
            output = path / "runs" / run
            output.mkdir(parents=True)
            config = copy.deepcopy(project["config"])
            # Snapshot configuration and contacts so later edits cannot change an active run.
            config["video"]["path"] = "../../" + config["video"]["path"]
            config["model_tracking"]["cache_path"] = "../../tracks.npz"
            config["model_tracking"]["repository_path"] = os.path.relpath(self.workspace / "model/co-tracker", output).replace(os.sep, "/")
            config["output"]["directory"] = "results"
            write_json(output / "config.json", config)
            shutil.copyfile(path / "contacts.tsv", output / "contacts.tsv")
            if setup:
                command = worker_command("setup", output / "config.json")
            else:
                # Cache reuse requires matching tracking settings, not just point coordinates.
                fingerprint = {"model": project["config"]["model_tracking"], "points": config["head_point_selection"]["query_points_raw_px"]}
                signature = path / "tracking_settings.json"
                reuse = (path / "tracks.npz").is_file() and signature.is_file() and read_json(signature) == fingerprint
                mode = "--cache-only" if project.get("demo") else ("--force-retrack" if not reuse else "")
                command = worker_command("analyse", output / "config.json")
                if mode:
                    command.append(mode)
                write_json(output / "tracking_settings.json", fingerprint)
            self.job = {"id": run, "project": key, "status": "running", "kind": "setup" if setup else "analysis", "log": "", "started": time.time()}
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            env["MPLBACKEND"] = "Agg"
            env["MPLCONFIGDIR"] = str(self.workspace / "matplotlib-cache")
            if frozen():
                env["SWIM_WORKER_LOG"] = str(output / "worker.log")
                (output / "worker.log").touch()
                env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            group_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT,
                                            env=env, text=True, encoding="utf-8", errors="replace", **group_options)
            threading.Thread(target=self._collect, args=(self.process, output, key, setup, self.job), daemon=True).start()
            return self.status()

    def _collect(self, process, output, key, setup, job):
        try:
            reader = (output / 'worker.log').open(encoding='utf-8', errors='replace') if frozen() else process.stdout
            with (output / "run.log").open("w", encoding="utf-8") as logfile:
                while True:
                    line = reader.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        time.sleep(0.1)
                        continue
                    logfile.write(line)
                    logfile.flush()
                    with self.lock:
                        job["log"] = (job["log"] + line)[-24000:]
            code = process.wait()
            if job["status"] == "cancelled":
                return
            job["exit_code"] = code
            if code == 0 and not setup:
                shutil.copyfile(output / "tracking_settings.json", self.project(key) / "tracking_settings.json")
                job["summary"] = read_json(output / "results/reports/00_analysis_summary.json")
                with self.lock:
                    job["log"] += "Packaging results / 打包结果…\n"
                replay = output / "replay"
                replay.mkdir()
                config = read_json(output / "config.json")
                config["video"]["path"] = "original_video_not_bundled.mp4"
                config["model_tracking"].update(cache_path="tracks.npz", repository_path="third_party/co-tracker")
                config["output"]["directory"] = "reanalysis_output"
                write_json(replay / "config.json", config)
                shutil.copyfile(output / "contacts.tsv", replay / "contacts.tsv")
                shutil.copyfile(self.project(key) / "tracks.npz", replay / "tracks.npz")
                (replay / "README.txt").write_text("Use the Swim Studio CLI with --config replay/config.json --cache-only to reproduce tables and plots. Raw video is not bundled.\n使用命令行 --config replay/config.json --cache-only 可复算表格与图形。包内不含原始视频。\n", encoding="utf-8")
                job["files"] = [p.relative_to(output).as_posix() for p in sorted(output.rglob("*")) if p.is_file()]
                archive = output / "results.zip"
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                    for file in output.rglob("*"):
                        if job["status"] == "cancelled":
                            return
                        if file.is_file() and file != archive:
                            bundle.write(file, file.relative_to(output))
            with self.lock:
                if job["status"] != "cancelled":
                    job["status"] = "complete" if code == 0 else "error"
                write_json(output / "completed.json", job)
        except Exception as exc:
            with self.lock:
                job["status"] = "error"
                job["log"] += f"\nCould not finish output / 输出未完成: {exc}\n"
        finally:
            if frozen() and 'reader' in locals():
                reader.close()
            process.stdout.close()

    def status(self):
        with self.lock:
            return copy.deepcopy(self.job) if self.job else {"status": "idle"}

    def cancel(self):
        with self.lock:
            if self.job and self.job["status"] == "running":
                self.job["status"] = "cancelled"
            if self.process and self.process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True)
                else:
                    import signal
                    try:
                        os.killpg(self.process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                process = self.process
                def reap():
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                threading.Thread(target=reap, daemon=True).start()
            return self.status()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    @property
    def app(self):
        return self.server.app

    def reply(self, data, status=200, content_type="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def route(self):
        url = urlsplit(self.path)
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host:
            raise PermissionError("Invalid host")
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + host:
            raise PermissionError("Invalid origin")
        parts = unquote(url.path).strip("/").split("/")
        if not parts or not secrets.compare_digest(parts[0], self.app.token):
            raise PermissionError("Open the link from the launcher / 请使用启动窗口中的链接")
        return "/".join(parts[1:]), parse_qs(url.query)

    def json_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 2_000_000:
            raise ValueError("Invalid request size")
        return json.loads(self.rfile.read(size))

    def do_GET(self):
        try:
            route, query = self.route()
            if route == "api/projects":
                return self.reply(self.app.projects())
            if route == "api/runtime":
                return self.reply({'standalone': frozen(), 'model_included': frozen()})
            if route == "api/status":
                return self.reply(self.app.status())
            if route == "api/history":
                path = self.app.project(query["id"][0])
                files = sorted(path.glob("runs/*/completed.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                return self.reply([read_json(p) for p in files])
            if route == "api/project":
                return self.reply(self.app.payload(query["id"][0]))
            if route == "api/frame":
                import cv2
                path = self.app.project(query["id"][0])
                config = read_json(path / "config.json")
                frame = int(query.get("frame", ["0"])[0])
                if frame < 0 or frame >= config["video"]["frame_count"]:
                    raise ValueError("Frame outside video")
                cap = cv2.VideoCapture(str(path / config["video"]["path"]))
                try:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
                    ok, img = cap.read()
                finally:
                    cap.release()
                if not ok:
                    raise ValueError("Cannot decode frame / 无法解码该帧")
                if img.shape[1] > 1600:
                    img = cv2.resize(img, (1600, round(img.shape[0]*1600/img.shape[1])))
                ok, data = cv2.imencode(".jpg", img)
                if not ok:
                    raise ValueError("JPEG encoding failed")
                return self.reply(data.tobytes(), content_type="image/jpeg")
            if route.startswith("file/"):
                parts = route.split("/", 3)
                project = self.app.project(parts[1])
                relative = "/".join(parts[2:])
                path = (project / relative).resolve()
                if not path.is_relative_to(project) or path.suffix.lower() not in {".json", ".tsv", ".pdf", ".png", ".mp4", ".zip", ".log", ".md"}:
                    raise PermissionError("Invalid file")
                # Stream artifacts, including large QA videos, without loading them in RAM.
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(path.stat().st_size))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                with path.open("rb") as file:
                    shutil.copyfileobj(file, self.wfile)
                return
            filename = route or "index.html"
            path = (WEB / filename).resolve()
            if not path.is_relative_to(WEB) or path.suffix not in {".html", ".css", ".js", ".svg"}:
                raise PermissionError("Invalid asset")
            self.reply(path.read_bytes(), content_type=mimetypes.guess_type(path.name)[0] or "text/plain")
        except PermissionError as exc:
            self.reply({"error": str(exc)}, 403)
        except (ValueError, KeyError, OSError) as exc:
            self.reply({"error": str(exc)}, 400)

    def do_POST(self):
        try:
            route, query = self.route()
            if route == "api/upload":
                if self.app.status()["status"] == "running":
                    raise ValueError("Wait for the running task / 请等待当前任务结束")
                from .inputs import read_video_metadata
                size = int(self.headers.get("Content-Length", "0"))
                name = Path(query.get("name", ["recording.mp4"])[0].replace("\\", "/")).name
                if not 0 < size <= 30 * 1024**3 or Path(name).suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv", ".m4v"}:
                    raise ValueError("Choose an MP4/MOV/AVI/MKV video (max 30 GB) / 请选择视频，最大 30 GB")
                key, path = self.app.create()
                target = path / ("input" + Path(name).suffix.lower())
                if shutil.disk_usage(path).free < size + 512 * 1024**2:
                    raise ValueError("Not enough disk space / 磁盘空间不足")
                with target.open("wb") as file:
                    remaining = size
                    while remaining:
                        chunk = self.rfile.read(min(1024*1024, remaining))
                        if not chunk:
                            raise ValueError("Video copy interrupted / 视频复制中断")
                        file.write(chunk)
                        remaining -= len(chunk)
                return self.reply(self.app.initialize(key, name, read_video_metadata(target)))
            data = self.json_body()
            if route == "api/demo":
                return self.reply(self.app.demo())
            if route == "api/save":
                return self.reply(self.app.save(data))
            if route in {"api/run", "api/setup"}:
                return self.reply(self.app.start(data, setup=route.endswith("setup")))
            if route == "api/cancel":
                return self.reply(self.app.cancel())
            raise ValueError("Unknown action")
        except PermissionError as exc:
            self.reply({"error": str(exc)}, 403)
        except Exception as exc:
            self.reply({"error": str(exc)}, 400)


def create_server(workspace, port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.app = Application(workspace)
    return server
