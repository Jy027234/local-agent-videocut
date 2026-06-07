$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
$Url = "http://127.0.0.1:8769"
Start-Process $Url
Write-Host "Starting Smart Video Cut Local Studio..."
Write-Host "URL: $Url"
py -m smart_video_cut.web_app
