#!/usr/bin/env python3
"""Launch the bilingual local swimming-analysis application."""
import argparse
from pathlib import Path
import threading
import webbrowser
from tadpole_tracking.gui_server import create_server
from tadpole_tracking.config import PROGRAM_VERSION
from tadpole_tracking.runtime import configure_stdio


def main():
    configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parent / "gui_workspace")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = create_server(args.workspace, args.port)
    url = f"http://127.0.0.1:{server.server_port}/{server.app.token}/"
    print(f"Swim Studio {PROGRAM_VERSION} · 游泳行为分析\n{url}\nKeep this window open / 使用时请保留此窗口。Ctrl+C: exit / 退出。", flush=True)
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.app.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
