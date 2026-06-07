@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
echo Starting FilmGen Studio...
echo URL: http://127.0.0.1:8777
start "" "http://127.0.0.1:8777"
py -m aifilm_studio.cli serve --host 127.0.0.1 --port 8777 --data-dir workspace\filmgen_studio
if errorlevel 1 (
  echo.
  echo Failed to start. Try:
  echo   py -m pip install -e ".[filmgen]"
  echo.
  pause
)
