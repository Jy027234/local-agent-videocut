param(
  [string]$OutputRoot = "release",
  [string]$PackageName = "智子agent智能剪辑软件-Local-Studio-V0.1-免费试用",
  [string]$PythonExecutable = "",
  [switch]$SkipPortableRuntime,
  [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseRoot = Join-Path $Root $OutputRoot
$PackageDir = Join-Path $ReleaseRoot $PackageName
$PortableRuntimeDir = Join-Path $PackageDir ".runtime\python"
$PortableRuntimeMetadata = Join-Path $PackageDir ".runtime\runtime-info.json"

if (Test-Path $PackageDir) {
  Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

function Copy-ItemSafe {
  param([string]$RelativePath)
  $Source = Join-Path $Root $RelativePath
  if (-not (Test-Path $Source)) { return }
  $Destination = Join-Path $PackageDir $RelativePath
  $Parent = Split-Path -Parent $Destination
  if ($Parent) { New-Item -ItemType Directory -Force -Path $Parent | Out-Null }
  Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

$paths = @(
  "src",
  "packages",
  "MOSS-TTS-Nano",
  "examples",
  "docs",
  "README.md",
  "pyproject.toml",
  "index.html"
)

foreach ($path in $paths) {
  Copy-ItemSafe $path
}

New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "workspace\config") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "workspace\output") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "workspace\projects") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir "workspace\voice_samples") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $PackageDir ".runtime") | Out-Null

function Resolve-PythonExecutable {
  param([string]$Requested)
  if ($Requested) { return $Requested }
  $launcherCandidates = @(
    @("py", "-3.12"),
    @("py", "-3.11"),
    @("py")
  )
  foreach ($launcher in $launcherCandidates) {
    try {
      $launcherArgs = @()
      if ($launcher.Length -gt 1) {
        $launcherArgs = $launcher[1..($launcher.Length - 1)]
      }
      $resolved = & $launcher[0] @launcherArgs -c "import sys; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -eq 0 -and $resolved) {
        return ($resolved | Select-Object -First 1).Trim()
      }
    } catch {
    }
  }
  throw "No suitable Python executable found. Please pass -PythonExecutable explicitly."
}

if (-not $SkipPortableRuntime) {
  $SelectedPython = Resolve-PythonExecutable -Requested $PythonExecutable
  Write-Host "Preparing portable runtime with: $SelectedPython"
  $prepareArgs = @(
    (Join-Path $Root "scripts\prepare_portable_runtime.py"),
    "--project-root", "$Root",
    "--runtime-dir", "$PortableRuntimeDir",
    "--metadata-path", "$PortableRuntimeMetadata",
    "--extras", "web", "analysis", "tts",
    "--exclude-dependency", "static-ffmpeg"
  )
  & $SelectedPython @prepareArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Portable runtime preparation failed."
  }
}

function Run-SmokeTest {
  param(
    [string]$Python,
    [string]$PackagePath
  )
  $reportPath = Join-Path $PackagePath ".runtime\smoke-test-report.json"
  $smokeArgs = @(
    (Join-Path $Root "scripts\release_smoke_check.py"),
    "--package-dir", "$PackagePath",
    "--port", "8769",
    "--timeout-seconds", "60",
    "--report-path", "$reportPath"
  )
  & $Python @smokeArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Release smoke test failed. See $reportPath"
  }
}

if ($SkipPortableRuntime -and -not $SkipSmokeTest) {
  throw "Smoke test requires the portable runtime. Remove -SkipPortableRuntime or also pass -SkipSmokeTest."
}

@'
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "PYTHONHOME=%CD%\.runtime\python"
set "PYTHONIOENCODING=utf-8"

if not exist ".runtime\python\python.exe" (
  echo.
  echo Portable runtime is missing. This package is incomplete.
  echo Expected: .runtime\python\python.exe
  echo Please rebuild the release package on the delivery machine.
  echo.
  pause
  exit /b 1
)

echo Starting Zhiziagent Local Studio V0.1 Free Trial...
".runtime\python\python.exe" -m smart_video_cut.release_preflight --root "%CD%" --port 8769 --expect-portable-runtime --require-port-available --strict --format text
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8769"
".runtime\python\python.exe" -m smart_video_cut.web_app
pause
'@ | Set-Content -LiteralPath (Join-Path $PackageDir "启动软件.bat") -Encoding OEM

@'
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
$env:PYTHONHOME = Join-Path $Root ".runtime\python"
$env:PYTHONIOENCODING = "utf-8"
$Python = Join-Path $Root ".runtime\python\python.exe"
if (-not (Test-Path $Python)) {
  throw "Portable runtime missing: $Python"
}
$null = & $Python -m smart_video_cut.release_preflight --root $Root --port 8769 --expect-portable-runtime --require-port-available --strict --format text
if ($LASTEXITCODE -ne 0) {
  throw "Startup preflight failed."
}
$Url = "http://127.0.0.1:8769"
Start-Process $Url
Write-Host "Starting Smart Video Cut Local Studio..."
Write-Host "URL: $Url"
& $Python -m smart_video_cut.web_app
'@ | Set-Content -LiteralPath (Join-Path $PackageDir "启动软件.ps1") -Encoding UTF8

@'
# 智子agent智能剪辑软件 Local Studio V0.1 免费试用版

这是给首个用户试用的本地版剪辑软件。

## 打开方式

1. 解压整个文件夹。
2. 双击 `启动软件.bat` 打开智能剪辑软件。
3. 本发布包已内置独立 Python 运行时，无需额外安装 Python，也不会在首次启动时联网安装依赖。
4. 启动后会自动打开：

```text
http://127.0.0.1:8769
```

## 基本流程

智能剪辑软件：

1. 在“设置”里配置大模型 Key。
2. 在“剪辑视频”里选择风格包、输入视频、输出目录。
3. 填写剪辑目标，点击“生成剪辑标准”。
4. 确认后点击“确认并开始剪辑”。
5. 在“结果与复剪”里查看成片和继续修改。

## 说明

- V0.1 免费试用版不包含收费、扫码、激活功能。
- 视频、音频、样板包和输出结果都保存在本机。
- 默认优先使用项目内 `packages\ffmpeg\bin`。
- MOSS-TTS-Nano 已随包放入，可在“设置”里检测和测试人声。
- 发布包内已自带 `.runtime\python`，正常使用时不依赖本机 Python。

## 常见问题

- 如果点击后没有启动，请先确认 `.runtime\python\python.exe` 是否仍在发布包内。
- 如果提示端口 8769 被占用，请先关闭旧的本地服务窗口再重试。
- 如果剪辑失败，先到“设置”检查大模型和 MOSS-TTS-Nano，再点顶部运行时状态重新检查。
- 输出文件默认在 `workspace\output`。
'@ | Set-Content -LiteralPath (Join-Path $PackageDir "V0.1免费试用说明.md") -Encoding UTF8

Get-ChildItem -LiteralPath $PackageDir -Recurse -Directory -Force -Include __pycache__,.pytest_cache | Remove-Item -Recurse -Force

if (-not $SkipSmokeTest) {
  Run-SmokeTest -Python $SelectedPython -PackagePath $PackageDir
}

Write-Host "V0.1 free trial package created:"
Write-Host $PackageDir
