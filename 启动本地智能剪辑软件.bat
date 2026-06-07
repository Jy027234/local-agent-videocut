@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
echo Starting Smart Video Cut Local Studio...
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
