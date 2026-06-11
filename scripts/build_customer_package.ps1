param(
  [string]$OutputRoot = "release",
  [string]$PackageName = "智子agent智能剪辑软件-Local-Studio-V0.1-免费试用"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseRoot = Join-Path $Root $OutputRoot
$PackageDir = Join-Path $ReleaseRoot $PackageName

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

@'
@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Creating local Python environment...
  py -3.12 -m venv .venv || py -3.11 -m venv .venv || py -m venv .venv
)

echo [2/2] Checking dependencies...
".venv\Scripts\python.exe" -c "import fastapi,uvicorn,pydantic" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -e ".[web,analysis,tts]"
)

echo Starting Zhiziagent Local Studio V0.1 Free Trial...
start "" "http://127.0.0.1:8769"
".venv\Scripts\python.exe" -m smart_video_cut.web_app
pause
'@ | Set-Content -LiteralPath (Join-Path $PackageDir "启动软件.bat") -Encoding OEM

@'
# 智子agent智能剪辑软件 Local Studio V0.1 免费试用版

这是给首个用户试用的本地版剪辑软件。

## 打开方式

1. 解压整个文件夹。
2. 双击 `启动软件.bat` 打开智能剪辑软件。
3. 第一次启动会创建本地 Python 环境并安装依赖，完成后会打开：

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

## 常见问题

- 如果没有 Python，请安装 Python 3.11 或 3.12，并勾选 Add Python to PATH。
- 如果剪辑失败，先到“设置”检查大模型和 MOSS-TTS-Nano，再点顶部运行时状态重新检查。
- 输出文件默认在 `workspace\output`。
'@ | Set-Content -LiteralPath (Join-Path $PackageDir "V0.1免费试用说明.md") -Encoding UTF8

Get-ChildItem -LiteralPath $PackageDir -Recurse -Directory -Force -Include __pycache__,.pytest_cache | Remove-Item -Recurse -Force

Write-Host "V0.1 free trial package created:"
Write-Host $PackageDir
