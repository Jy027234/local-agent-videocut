from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_index_points_to_local_server() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    assert "http://127.0.0.1:8769" in html
    assert "启动本地智能剪辑软件.bat" in html
    assert "不会自动启动 Python 本地服务" in html


def test_static_index_contains_local_workflows() -> None:
    html = (ROOT / "src" / "smart_video_cut" / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "src" / "smart_video_cut" / "static" / "app.js").read_text(encoding="utf-8")
    html = html + "\n" + js

    assert "/static/app.css" in html
    assert "/static/app.js" in html
    assert "/api/check" in html
    assert "智子agent智能剪辑软件 Local Studio" in html
    assert "商品：智子agent" not in html
    assert "点击重新检查运行时" in html
    assert "status-button" in html
    assert "/api/local-config" in html
    assert "/api/activation" not in html
    assert "/api/payment-qr" not in html
    assert "付费激活" not in html
    assert "机器码" not in html
    assert "激活软件" not in html
    assert "paidFeatureReady" not in html
    assert "initializeApp" in html
    assert "LOCAL_DRAFT_KEY" in html
    assert ".then(loadPackages)" not in html
    assert "/api/memory" in html
    assert "/api/memory/feedback" in html
    assert "/api/llm-config" in html
    assert "/api/llm-test" in html
    assert "/api/ollama/status" in html
    assert "/api/ollama/models" in html
    assert "/api/ollama/apply" in html
    assert "/api/ollama/models" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/files" in html
    assert "/api/edit-brief" in html
    assert "/api/director/chat" in html
    assert "/api/director/chat" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/agent/orchestrate" in html
    assert "/api/agent/orchestrate" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/filmgen/edit-pack/preview" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/filmgen/subtitle-handoff/preview" in html
    assert "/api/filmgen/subtitle-handoff/preview" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/filmgen/export-handoff/validate" in html
    assert "/api/filmgen/export-handoff/validate" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/filmgen/edit-brief" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/worker/package" in html
    assert "/api/worker/package/load" in html
    assert "/api/worker/run" in html
    assert "/api/worker/run" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/build" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/inspect" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/run" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/dropbox/init" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/dropbox/import" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/dropbox/run" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/dropbox/monitor/start" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/dropbox/monitor/stop" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/protocol/dropbox/monitor/status" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/recent-runs" in html
    assert "DELETE" in html
    assert "/api/projects" in html
    assert "/api/projects/rebuild" in html
    assert "/api/folders/scan" in html
    assert "/api/repair-dialogue" in html
    assert "/api/deployment/guide" in html
    assert "/api/projects" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/folders/scan" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/moss-tts/status" in html
    assert "/api/moss-tts/setup" in html
    assert "/api/moss-tts/test" in html
    assert "/api/moss-tts/history" in html
    assert "/api/voice-samples" in html
    assert "/api/style-packages" in html
    assert "/api/template/analyze" in html
    assert "/api/template/analyze" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/cut" in html
    assert "/api/voice-profile" in html
    assert "/api/voice-profile/confirm" in html
    assert "/api/voice-profile/confirm" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/voice-profile/refs" in html
    assert "/api/voice/system-tts/voices" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/voice/system-tts/test" in html
    assert "/api/voice/system-tts/test" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/material/calibration" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "素材分析校准" in html
    assert "校准样本集" in html
    assert "materialSampleSet" in html
    assert "materialRoleThreshold" in html
    assert "calibrateMaterialAnalysis" in html
    assert "applyMaterialCalibration" in html
    assert "material_analysis" in html
    assert "calibrated" in html
    assert "/api/bgm/library" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "/api/bgm/library/playlist" in html
    assert "/api/bgm/library/playlist" in Path(ROOT / "src" / "smart_video_cut" / "web_app.py").read_text(encoding="utf-8")
    assert "MOSS-TTS-Nano" in html
    assert "模型与连接" in html
    assert "Ollama 离线模型" in html
    assert "检测 Ollama" in html
    assert "读取本地模型" in html
    assert "使用所选模型" in html
    assert "ollamaModelSelect" in html
    assert "checkOllamaStatus" in html
    assert "loadOllamaModels" in html
    assert "applySelectedOllamaModel" in html
    assert "推荐：多模态质检 + 文本规划" in html
    assert "我的偏好" in html
    assert "参考我保存过的偏好" in html
    assert "纯文本模型不能直接看画面" in html
    assert "目标时长(秒)" in html
    assert "字幕字号(px)" in html
    assert "BGM 音量(dB)" in html
    assert "查看结果" in html
    assert "确认后生成第一版" in html
    assert "说出你想要的效果" in html
    assert "AI 助手帮你整理要求" in html
    assert "生成多 Agent 编排" in html
    assert "agentOrchestrationResult" in html
    assert "orchestrateLocalAgents" in html
    assert "renderAgentOrchestration" in html
    assert "本地多 Agent 编排" in html
    assert "第一次使用，就按这 3 步" in html
    assert "第一次用，先套一个起步方案" in html
    assert "firstRunGuide" in html
    assert "现在该做什么" in html
    assert "去完成当前这一步" in html
    assert "runWorkflowGuideAction" in html
    assert "renderWorkflowGuide" in html
    assert "refreshGuidedFeedbacks" in html
    assert "LOCAL_ONBOARDING_KEY" in html
    assert "BEGINNER_PRESETS" in html
    assert "applyBeginnerPreset" in html
    assert "renderFirstRunGuide" in html
    assert "suggestOutputDir" in html
    assert "自动填写推荐路径" in html
    assert "不会覆盖旧成片" in html
    assert "当前这版会保存到这里" in html
    assert "playReviewVideo" in html
    assert "reviewActionButtons" in html
    assert "setupFeedback" in html
    assert "assistantFeedback" in html
    assert "confirmFeedback" in html
    assert "buildRequestFailureMessage" in html
    assert "buildEditResultGuidance" in html
    assert "第一版已经出来了" in html
    assert "这次没能顺利出片" in html
    assert "去模型与声音设置" in html
    assert "回到开始剪辑" in html
    assert "这一步还没完成" in html
    assert "系统当前卡在" in html
    assert "模型连接成功" in html
    assert "Ollama 还没就绪" in html
    assert "本地模型列表已刷新" in html
    assert "步骤 1 已准备好" in html
    assert "还没生成剪辑标准" in html
    assert "步骤 1：样板、素材和保存位置" in html
    assert "显示高级工具" in html
    assert "toggleAdvancedMode" in html
    assert "scrollToStep" in html
    assert "点击上面的卡片，可以直接跳到对应位置" in html
    assert "助手模式" in html
    assert "混合 LLM" in html
    assert "directorMode" in html
    assert "chatWithDirector" in html
    assert "applyDirectorOverrides" in html
    assert "runDirectorAction" in html
    assert "director_chat.v0" in html
    assert "声音与音乐" in html
    assert "字幕方式" in html
    assert "外部字幕交接" in html
    assert "高级：外部字幕交接验收" in html
    assert "previewSubtitleHandoff" in html
    assert "subtitleHandoffPath" in html
    assert "不加内容字幕" in html
    assert "字幕内容或要求" in html
    assert "场景备注" in html
    assert "不加新配音" in html
    assert 'option value="fixture"' in html
    assert 'fixture_voice">测试占位音' not in html
    assert "systemTtsControls" in html
    assert "systemVoice" in html
    assert "刷新系统语音" in html
    assert "语音筛选" in html
    assert "试听系统 TTS" in html
    assert "systemTtsPreview" in html
    assert "testSystemTts" in html
    assert "renderSystemTtsVoiceOptions" in html
    assert "fixtureVoiceControls" in html
    assert "fixtureDuration" in html
    assert "fixtureSampleRate" in html
    assert "loadSystemTtsVoices" in html
    assert "system_voice" in html
    assert "fixture_duration_seconds" in html
    assert "本地生成 BGM" in html
    assert "本地音乐模型 BGM" in html
    assert "本地素材库 BGM" in html
    assert "bgmLibraryControls" in html
    assert "scanBgmLibrary" in html
    assert "renderBgmLibraryPlaylist" in html
    assert "useBgmLibraryItem" in html
    assert "bgm_library_dir" in html
    assert "bgm_library_query" in html
    assert "外部导出交接" in html
    assert "BGM 音频输入" in html
    assert "subtitle_handoff" in html
    assert "filmgen_handoff" in html
    assert "外部导出交接验收" in html
    assert "filmgenExportHandoffPath" in html
    assert "validateFilmgenExportHandoff" in html
    assert "renderFilmgenExportHandoffValidation" in html
    assert "deleteRecentRun" in html
    assert "查看成片" in html
    assert "继续修改" in html
    assert "查看版本" in html
    assert "更多操作" in html
    assert "删除这条记录" in html
    assert "history-item" in html
    assert "本地音乐文件" in html
    assert "试听所选音乐" in html
    assert "加入素材列表" in html
    assert "多个原视频素材" in html
    assert "素材分工" in html
    assert "生成剪辑标准时会先规划素材分工" in html
    assert "视觉分析" in html
    assert "顺序规划" in html
    assert "多模态复核" in html
    assert "提取并保存风格包" in html
    assert "样板视频自动分析" in html
    assert "分析参考视频" in html
    assert "applyTemplateAnalysisSuggestions" in html
    assert "renderTemplateAnalysis" in html
    assert "reference_analysis" in Path(ROOT / "src" / "smart_video_cut" / "style_package.py").read_text(encoding="utf-8")
    assert "确认并生成第一版" in html
    assert "时间线预览（可选）" in html
    assert "生成时间线预览" in html
    assert "应用时间线编辑" in html
    assert "/api/timeline" in html
    assert "/api/timeline/edit" in html
    assert "timeline_override" in html
    assert "collectTimelineEdits" in html
    assert "moveTimelineSegment" in html
    assert "startTimelineDrag" in html
    assert 'draggable="true"' in html
    assert "timelineSourcePreview" in html
    assert "预览素材" in html
    assert "替换素材" in html
    assert "时间线历史" in html
    assert "loadTimelineVersions" in html
    assert "revertTimelineVersion" in html
    assert "回退到此版本" in html
    assert "项目历史与版本" in html
    assert "loadProjectVersionCenter" in html
    assert "startVersionReEdit" in html
    assert "基于版本复剪" in html
    assert "项目库" in html
    assert "项目历史" in html
    assert "还没有项目记录" in html
    assert "查看项目" in html
    assert "直接播放成片" in html
    assert "扫描新素材" in html
    assert "扫描已有成片" in html
    assert "素材预览" in html
    assert "安装与部署引导" in html
    assert "loadProjectLibrary" in html
    assert "rebuildProjectLibrary" in html
    assert "scanInputFolder" in html
    assert "scanOutputFolder" in html
    assert "previewStudioMedia" in html
    assert "预览成片" in html
    assert "项目清单" in html
    assert "project_manifest.json" in html
    assert "项目包导出 / 导入" in html
    assert "exportProjectPack" in html
    assert "loadProjectPack" in html
    assert "applyLoadedProjectPack" in html
    assert "本地 Worker 任务包" in html
    assert "worker_task_package.json" in html
    assert "completion.json" in html
    assert "createWorkerTaskPackage" in html
    assert "loadWorkerTaskPackage" in html
    assert "runWorkerTaskPackage" in html
    assert "workerTaskPreview" in html
    assert "本地协议检查" in html
    assert "local_toolkit_protocol.json" in html
    assert "buildLocalToolkitProtocol" in html
    assert "inspectLocalToolkitProtocol" in html
    assert "runLocalProtocol" in html
    assert "protocolPreview" in html
    assert "标准协议投递箱" in html
    assert "protocolDropboxDir" in html
    assert "protocolDropboxSourcePath" in html
    assert "protocolDropboxLabel" in html
    assert "protocolDropboxInterval" in html
    assert "protocolDropboxMaxCycles" in html
    assert "protocolDropboxHistoryLimit" in html
    assert "protocolDropboxAlertsOnly" in html
    assert "protocolDropboxRequeueQueue" in html
    assert "protocolDropboxRequeueMaxFiles" in html
    assert "initProtocolDropbox" in html
    assert "importProtocolDropboxItem" in html
    assert "runProtocolDropbox" in html
    assert "startProtocolDropboxMonitor" in html
    assert "stopProtocolDropboxMonitor" in html
    assert "refreshProtocolDropboxMonitor" in html
    assert "loadProtocolDropboxHistory" in html
    assert "requeueProtocolDropboxFailed" in html
    assert "setProtocolDropboxMonitorPolling" in html
    assert "标准协议投递箱自动轮询" in html
    assert "仅看告警历史" in html
    assert "回投失败文件" in html
    assert "/api/packs/project/export" in html
    assert "/api/packs/load" in html
    assert "统一包索引" in html
    assert "高级：迁移、批量和自动化工具" in html
    assert "还没有样板" in html
    assert "还没选样板" in html
    assert "loadAllPacks" in html
    assert "validatePackFromIndex" in html
    assert "/api/packs/validate" in html
    assert "缺失路径" in html
    assert "点击应用后保存版本" in html
    assert "已载入历史时间线" in html
    assert "声音样音与音色" in html
    assert "MOSS-TTS-Nano 说明" in html
    assert "生成样例人声" in html
    assert "样音试听确认" in html
    assert "确认并用于剪辑" in html
    assert "confirmVoiceProfileRef" in html
    assert "latestVoiceProfileRef" in html
    assert "require_saved_profile" in html
    assert "真人音色采集与模仿" in html
    assert "MOSS 内置音色" in html
    assert "MOSS 生成特征" in html
    assert "MOSS 测试试听" in html
    assert "已生成样音" in html
    assert "mossSampleHistory" in html
    assert "friendlyMossError" in html
    assert "开始录音" in html
    assert 'id="stopRecordingButton"' in html
    assert "withButtonState" in html
    assert "正在请求浏览器麦克风权限" in html
    assert "麦克风已开启，可以开始说话" in html
    assert "prompt_audio_path" in html
