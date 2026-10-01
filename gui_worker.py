#!/usr/bin/env python3
"""Isolated GUI jobs; failures and cancellation cannot freeze the interface."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    from tadpole_tracking.runtime import configure_stdio
    configure_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "analyse"])
    parser.add_argument("config", type=Path)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--force-retrack", action="store_true")
    args = parser.parse_args()
    if args.action == "setup":
        from tadpole_tracking.runtime import frozen
        if frozen():
            print('Model included; ready to analyse / 模型已内置，可直接分析。', flush=True)
            return
        from prepare_config import command_fetch_model
        print("Installing tracking dependencies / 安装追踪依赖…", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(Path(__file__).with_name("requirements-model.txt"))], check=True)
        print("Fetching pinned CoTracker source / 获取固定版本模型源码…", flush=True)
        command_fetch_model(args)
        print("Downloading and verifying weights / 下载并校验模型权重…", flush=True)
        from tadpole_tracking.config import load_config, resolve_config_path
        from tadpole_tracking.model_tracking import _load_model
        config = load_config(args.config)
        _load_model(config["model_tracking"], resolve_config_path(args.config, config["model_tracking"]["repository_path"]), "cpu")
        print("Ready / 准备完成", flush=True)
    else:
        from tadpole_tracking.config import load_config
        from tadpole_tracking.pipeline import run_analysis
        print("Loading inputs / 读取输入…", flush=True)
        result = run_analysis(load_config(args.config), args.config, cache_only=args.cache_only, force_retrack=args.force_retrack)
        print(f"Completed / 完成：{result['summary']['total_analyzable_distance_mm']:.3f} mm", flush=True)


if __name__ == "__main__":
    main()
