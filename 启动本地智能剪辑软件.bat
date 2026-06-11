@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "PYTHONIOENCODING=utf-8"
echo Starting Smart Video Cut Local Studio...
py -m smart_video_cut.release_preflight --root "%CD%" --port 8769 --require-port-available --strict --format text
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
echo URL: http://127.0.0.1:8769
start "" "http://127.0.0.1:8769"
py -m smart_video_cut.web_app
if errorlevel 1 (
  echo.
  echo Failed to start. Try:
  echo   py -m pip install -e ".[web]"
  echo.
  pause
)
