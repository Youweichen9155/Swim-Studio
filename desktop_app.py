#!/usr/bin/env python3
"""Standalone launcher; no Python, Git or first-run download is needed."""
import argparse
import multiprocessing
import os
from pathlib import Path
import sys
import subprocess


def main():
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        sys.argv.pop(1)
        log = os.environ.get('SWIM_WORKER_LOG')
        if log:
            sys.stdout = sys.stderr = open(log, 'a', encoding='utf-8', buffering=1)
        from gui_worker import main as worker
        worker()
        return
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    from tadpole_tracking.runtime import default_workspace, configure_stdio
    workspace = (args.workspace or default_workspace()).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(workspace / 'launcher.log', 'a', encoding='utf-8', buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout
    configure_stdio()
    os.environ['MPLCONFIGDIR'] = str(workspace / 'matplotlib-cache')
    os.environ['MPLBACKEND'] = 'Agg'
    from tadpole_tracking.gui_server import create_server
    import json
    import threading
    import webbrowser
    server = create_server(workspace, args.port)
    url = f'http://127.0.0.1:{server.server_port}/{server.app.token}/'
    (workspace / 'desktop-session.json').write_text(json.dumps({'pid': os.getpid(), 'url': url}))
    print(url, flush=True)
    if args.headless:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.app.cancel(); server.server_close()
        return
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.title('Swim Studio')
    root.geometry('510x285')
    root.configure(bg='#f3f8f7')
    root.resizable(False, False)
    tk.Label(root, text='Swim Studio', font=('Helvetica', 25, 'bold'), bg='#f3f8f7', fg='#103e3b').pack(pady=(25,8))
    tk.Label(root, text='游泳行为分析 · Swimming behaviour analysis', bg='#f3f8f7', fg='#315d59').pack()
    tk.Label(root, text='模型已内置 · 可离线使用\nModel included · Works offline', bg='#f3f8f7', fg='#315d59').pack(pady=15)
    def open_analysis():
        try:
            if sys.platform == 'darwin':
                subprocess.run(['/usr/bin/open', url], check=True, timeout=10)
            elif os.name == 'nt':
                os.startfile(url)
            elif not webbrowser.open(url):
                raise RuntimeError('No default browser found')
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f'Unable to open browser: {exc}', flush=True)
            root.clipboard_clear(); root.clipboard_append(url)
            messagebox.showinfo('Swim Studio', '请将已复制的地址粘贴到浏览器：\nPaste the copied address into your browser:\n\n' + url)
    tk.Button(root, text='打开分析界面 / Open analysis', command=open_analysis, width=34).pack(pady=5)
    def close():
        if server.app.status()['status'] == 'running' and not messagebox.askyesno('Swim Studio', '分析正在运行，退出将停止任务。\nAnalysis is running. Stop and quit?'):
            return
        server.app.cancel(); server.shutdown(); server.server_close(); root.destroy()
    tk.Button(root, text='退出程序 / Quit', command=close, width=34).pack(pady=5)
    root.protocol('WM_DELETE_WINDOW', close)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not args.no_browser:
        root.after(500, open_analysis)
    root.mainloop()


if __name__ == '__main__':
    main()
