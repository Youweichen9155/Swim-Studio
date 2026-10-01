@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv-gui\Scripts\python.exe" (
  ".venv-gui\Scripts\python.exe" bootstrap_gui.py
  goto done
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    py -3.12 bootstrap_gui.py
    goto done
  )
  py -3.11 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    py -3.11 bootstrap_gui.py
    goto done
  )
  py -3.13 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    py -3.13 bootstrap_gui.py
    goto done
  )
)
python bootstrap_gui.py
:done
if errorlevel 1 pause
