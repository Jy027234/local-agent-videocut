$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
$env:PYTHONIOENCODING = "utf-8"
$Url = "http://127.0.0.1:8769"
py -m smart_video_cut.release_preflight --root $Root --port 8769 --require-port-available --strict --format text
if ($LASTEXITCODE -ne 0) {
    throw "Startup preflight failed."
}
Start-Process $Url
Write-Host "Starting Smart Video Cut Local Studio..."
Write-Host "URL: $Url"
py -m smart_video_cut.web_app
