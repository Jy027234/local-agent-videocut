$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
$Url = "http://127.0.0.1:8777"
Start-Process $Url
Write-Host "Starting FilmGen Studio..."
Write-Host "URL: $Url"
py -m aifilm_studio.cli serve --host 127.0.0.1 --port 8777 --data-dir workspace\filmgen_studio
