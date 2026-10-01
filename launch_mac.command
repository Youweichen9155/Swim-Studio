#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ -x ".venv-gui/bin/python" ]; then
  .venv-gui/bin/python bootstrap_gui.py
  code=$?
  if [ "$code" -ne 0 ]; then
    read -r -p "Press Return to close / 按回车关闭…" reply
  fi
  exit "$code"
fi
for candidate in python3.12 python3.11 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; then
    "$candidate" bootstrap_gui.py
    code=$?
    if [ "$code" -ne 0 ]; then
      read -r -p "Press Return to close / 按回车关闭…" reply
    fi
    exit "$code"
  fi
done
printf '%s\n' 'Please install Python 3.12 from https://www.python.org/downloads/ and retry.' '请先从 python.org 安装 Python 3.12，再次双击此文件。'
read -r -p 'Press Return to close / 按回车关闭…' reply
exit 1
