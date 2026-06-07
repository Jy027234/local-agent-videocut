# Smart Video Cut Local Studio

本仓库提供一个本地优先的智能剪辑产品代码库，核心包括：

- `smart_video_cut`：本地剪辑 UI、任务编排、项目历史、样板包、协议与本地工具链
- `video_editing_toolkit`：内置剪辑运行时封装
- `aifilm_studio`：可选的本地生成伴生应用
- `desktop/electron`：Windows 本地壳

仓库只保留产品代码、测试和最小启动脚本。
本地模型、权重、运行缓存、输出素材、打包产物和私有工作区内容均不包含在版本库内。

## Repository Layout

```text
src/
  smart_video_cut/         Local Studio 主产品
  video_editing_toolkit/   内置剪辑运行时
  aifilm_studio/           伴生生成应用
desktop/electron/          Electron 壳
scripts/                   交付与辅助脚本
tests/                     自动化测试
```

## Quick Start

安装开发依赖：

```powershell
py -m pip install -e ".[web,dev]"
```

启动本地剪辑服务：

```powershell
py -m smart_video_cut.web_app
```

或使用根目录启动脚本：

```powershell
.\启动本地智能剪辑软件.ps1
```

默认访问地址：

```text
http://127.0.0.1:8769
```

## Optional Features

以下能力按需安装，不随仓库附带：

- 视觉分析依赖
- Edge TTS / 本地 TTS 相关依赖
- 本地 FFmpeg 运行时
- Ollama、本地模型、语音模型与权重文件

按需安装示例：

```powershell
py -m pip install -e ".[analysis,tts-edge,web,dev]"
```

## Tests

运行全量测试：

```powershell
py -m pytest -q
```

## Electron Shell

```powershell
cd desktop/electron
npm install
npm start
```

## Notes

- 仓库不提交模型目录、样音、输出视频、工作区缓存、打包结果和本机私有配置。
- UI 中部分路径示例仍使用 Windows 占位路径，实际运行时会按本机工作目录生成推荐路径。
