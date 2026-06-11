const $ = (id) => document.getElementById(id);
    const status = $("status");
    const resultCards = $("resultCards");
    const resultDetails = $("resultDetails");
    let packages = [];
    let allPacks = null;
    let recentRuns = [];
    let projectLibrary = [];
    let projectLibrarySearchTimer = null;
    let latestResult = null;
    let latestTemplateAnalysis = null;
    let pickerState = { targetId: "", mode: "file", extensions: "" };
    let briefReady = false;
    let inputVideos = [];
    let timelineBase = null;
    let timelineOverride = null;
    let timelineDraggedSegmentId = "";
    let timelineVersions = [];
    let activeProjectOutputDir = "";
    let activeProjectManifest = null;
    let loadedProjectPack = null;
    let resolvedProjectPack = null;
    let voiceRecorder = null;
    let voiceRecordStream = null;
    let voiceRecordChunks = [];
    let voiceRecordingStartButton = null;
    let voiceRecordingStopButton = null;
    let systemTtsVoicesLoaded = false;
    let systemTtsVoicesLoading = false;
    let systemTtsVoiceOptions = [];
    let systemTtsDefaultVoice = "";
    let systemTtsPlatform = "";
    let directorChatHistory = [];
    let latestDirectorResponse = null;
    let latestDirectorRequestSnapshot = "";
    let latestAgentOrchestration = null;
    let latestMaterialCalibration = null;
    let latestVoiceProfileResult = null;
    let latestVoiceProfileRef = null;
    let latestVoiceProfileRefs = [];
    let latestWorkerTaskPackage = null;
    let latestWorkerCompletion = null;
    let latestProtocolInspection = null;
    let protocolDropboxMonitorPoller = null;
    let localConfigSummary = null;
    let preferredOutputLabelHint = "";
    let draftReady = false;
    let advancedToolsVisible = false;
    let workflowGuideAction = {type: "step", targetId: "setupStep"};
    const buttonStates = new WeakMap();
    const LOCAL_DRAFT_KEY = "smart_video_cut.local_studio.draft.v1";
    const LOCAL_UI_MODE_KEY = "smart_video_cut.local_studio.ui_mode.v1";
    const LOCAL_ONBOARDING_KEY = "smart_video_cut.local_studio.onboarding.v1";
    const BEGINNER_PRESETS = [
      {
        id: "fast_vertical",
        label: "15 秒竖屏快闪",
        summary: "适合短视频投放，先抓眼球，再快速切细节。",
        userRequest: "做成 15 秒竖屏快闪广告，开头先抓眼球，再快速切到产品细节，节奏明快，适合短视频投放。",
        duration: 15,
        aspect: "9:16",
        resolution: "720x1280",
        quality: "standard",
        subtitleMode: "auto",
        voiceProvider: "system_tts",
      },
      {
        id: "landscape_explainer",
        label: "20 秒横屏讲解",
        summary: "适合讲清卖点和使用场景，节奏更稳。",
        userRequest: "做成 20 秒横屏产品讲解片，先展示整体，再交代核心卖点和使用场景，节奏清楚，信息稳定。",
        duration: 20,
        aspect: "16:9",
        resolution: "1280x720",
        quality: "standard",
        subtitleMode: "auto",
        voiceProvider: "system_tts",
      },
      {
        id: "silent_preview",
        label: "无配音预览版",
        summary: "先看画面结构和节奏，适合第一轮确认。",
        userRequest: "先做一版无配音预览，重点看镜头顺序、节奏和字幕是否合适，方便我先确认画面结构。",
        duration: 20,
        aspect: "9:16",
        resolution: "720x1280",
        quality: "draft",
        subtitleMode: "auto",
        voiceProvider: "none",
      }
    ];
    const LOCAL_DRAFT_FIELD_IDS = [
      "stylePackage","inputVideo","outputDir","userRequest","directorMode","voiceoverText","duration","aspect","resolution",
      "quality","subtitleMode","subtitleLocation","subtitlePrompt","subtitleSize","subtitleColor","outlineColor","outlineWidth","subtitleHandoffPath",
      "materialVisualAnalysis","materialSampleSet","materialVisualPreset","materialRoleThreshold","materialFrameSampleCount","materialThumbnailMaxSide","materialSampleSetPath",
      "voiceProvider","systemVoice","systemVoiceFilter","systemRate","systemVolume","fixtureDuration","fixtureSampleRate",
      "bgmStyle","bgmAudioPath","bgmLibraryDir","bgmLibraryQuery","bgmStart","bgmVolume","voiceVolume","originalAudioMode","removeOriginalVoice",
      "filmgenExportHandoffPath","projectSearch","inputScanDir","outputScanDir","mossPromptAudioPath","mossVoice","mossProfile","mossTestOutputDir","useMemory","executeReal","allowEdge",
      "voiceOutputDir","sampleText","voiceProviderProfile","sampleOutcome","voiceProfileResultPath","voiceProfileOutcome","voiceProfileRating","voiceProfileNotes","ollamaModelSelect",
      "workerPackageName","workerPackageDir","workerPackagePath","protocolOutputDir","protocolInspectPath",
      "protocolDropboxDir","protocolDropboxSourcePath","protocolDropboxLabel","protocolDropboxInterval","protocolDropboxMaxCycles",
      "protocolDropboxHistoryLimit","protocolDropboxAlertsOnly","protocolDropboxRequeueQueue","protocolDropboxRequeueMaxFiles"
    ];

    const RECENT_PATHS_KEY = "smart_video_cut.recent_paths.v1";
    const MAX_RECENT_PATHS = 5;
    const LEGACY_DRAFT_FIELD_ALIASES = {
      filmgenExportHandoffPath: ["externalExportHandoffPath"]
    };

    function normalizeSubtitleMode(value) {
      const mode = String(value ?? "").trim();
      if (!mode) return mode;
      if (mode === "external" || mode === "external_handoff") return "filmgen";
      return mode;
    }

    function normalizeDropboxQueueId(value) {
      const queueId = String(value ?? "").trim();
      if (queueId === "external_handoffs") return "filmgen_handoffs";
      return queueId;
    }

    function toast(message, type = "info", duration = 2800) {
      const el = $("toast");
      if (!el) return;
      el.textContent = message;
      el.className = "toast " + type;
      el.classList.add("show");
      setTimeout(() => el.classList.remove("show"), duration);
    }

    function recordRecentPath(path) {
      if (!path) return;
      try {
        const list = JSON.parse(localStorage.getItem(RECENT_PATHS_KEY) || "[]");
        const filtered = list.filter((p) => p !== path);
        filtered.unshift(path);
        localStorage.setItem(RECENT_PATHS_KEY, JSON.stringify(filtered.slice(0, MAX_RECENT_PATHS)));
      } catch {}
    }

    function getRecentPaths() {
      try {
        return JSON.parse(localStorage.getItem(RECENT_PATHS_KEY) || "[]");
      } catch {
        return [];
      }
    }

    function renderRecentPaths(inputId, containerId) {
      const container = $(containerId);
      if (!container) return;
      const paths = getRecentPaths();
      if (!paths.length) {
        container.innerHTML = "";
        return;
      }
      container.innerHTML = paths.map((p) => `<button type="button" onclick="setValue('${inputId}', '${p.replace(/'/g, "\'")}')">${p.split(/[\\/]/).pop() || p}</button>`).join("");
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function assignmentSourceLabel(source) {
      if (source === "multimodal_thumbnail_role_review") return "多模态复核";
      if (source === "ffmpeg_frame_probe_role_assignment") return "视觉分析";
      return "顺序规划";
    }

    function toggleHelp(id) {
      $(id).classList.toggle("active");
    }

    function applyUiMode(enabled) {
      advancedToolsVisible = enabled;
      document.body.classList.toggle("expert-mode", enabled);
      document.body.classList.toggle("beginner-mode", !enabled);
      const toggle = $("advancedModeToggle");
      if (toggle) {
        toggle.textContent = enabled ? "隐藏高级工具" : "显示高级工具";
        toggle.classList.toggle("neutral", enabled);
        toggle.classList.toggle("secondary", !enabled);
      }
      const hint = $("advancedModeHint");
      if (hint) {
        hint.textContent = enabled
          ? "当前已显示高级工具：你会看到自动化、外部交接和细颗粒度调参。"
          : "当前是普通视图：高级调参、自动化工具和外部交接默认收起，需要时再点右上角打开。";
      }
    }

    function toggleAdvancedMode() {
      applyUiMode(!advancedToolsVisible);
      try {
        localStorage.setItem(LOCAL_UI_MODE_KEY, advancedToolsVisible ? "advanced" : "beginner");
      } catch {}
    }

    function restoreUiMode() {
      let savedMode = "beginner";
      try {
        savedMode = localStorage.getItem(LOCAL_UI_MODE_KEY) || "beginner";
      } catch {}
      applyUiMode(savedMode === "advanced");
    }

    function scrollToStep(stepId) {
      const target = $(stepId);
      if (!target) return;
      if (target.tagName === "DETAILS") target.open = true;
      target.scrollIntoView({behavior: "smooth", block: "start"});
      const focusTarget = target.querySelector("input, textarea, select, button");
      if (focusTarget) {
        setTimeout(() => focusTarget.focus({preventScroll: true}), 220);
      }
    }

    function localPath(pathKey, fallback = "") {
      return String(localConfigSummary?.paths?.[pathKey] || fallback || "").trim();
    }

    function basenameFromPath(value) {
      const parts = String(value || "").split(/[\\/]/).filter(Boolean);
      return parts.length ? parts[parts.length - 1] : "";
    }

    function sanitizeFolderSegment(value, fallback = "case") {
      const cleaned = String(value || "")
        .trim()
        .replace(/\.[^./\\]+$/, "")
        .replace(/[\\/:*?"<>|]+/g, " ")
        .replace(/\s+/g, "-")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 36);
      return cleaned || fallback;
    }

    function timestampFolderSuffix() {
      const now = new Date();
      const pad = (value) => String(value).padStart(2, "0");
      return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}`;
    }

    function selectedStyleLabel() {
      const selectLabel = $("stylePackageSelect")?.selectedOptions?.[0]?.textContent?.split(" - ")[0]?.trim();
      if (selectLabel) return selectLabel;
      return basenameFromPath($("stylePackage")?.value || "");
    }

    function suggestedOutputLabel() {
      const videoLabel = basenameFromPath(normalizeInputVideos()[0] || $("inputVideo")?.value || "");
      return selectedStyleLabel() || videoLabel || "本地剪辑";
    }

    function composeSuggestedOutputDir(labelHint = "") {
      const root = localPath("output_root", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output").replace(/[\\/]+$/, "");
      const folderLabel = sanitizeFolderSegment(labelHint || preferredOutputLabelHint || suggestedOutputLabel(), "case");
      return `${root}\\${folderLabel}_${timestampFolderSuffix()}`;
    }

    function onboardingDismissed() {
      try {
        return localStorage.getItem(LOCAL_ONBOARDING_KEY) === "hidden";
      } catch {
        return false;
      }
    }

    function toggleFirstRunGuide(hidden = true) {
      try {
        if (hidden) {
          localStorage.setItem(LOCAL_ONBOARDING_KEY, "hidden");
        } else {
          localStorage.removeItem(LOCAL_ONBOARDING_KEY);
        }
      } catch {}
      renderFirstRunGuide();
    }

    function updateLocalPathPlaceholders() {
      const defaults = {
        stylePackage: `${localPath("packages_dir", "D:\\个人文件\\个人开发\\智能剪辑软件\\packages")}\\door-flash`,
        outputDir: localPath("default_output_dir", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output\\case001"),
        outputScanDir: localPath("output_root", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output"),
        projectPackOutputDir: localPath("default_output_dir", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output\\case001"),
        protocolOutputDir: localPath("default_output_dir", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output\\case001"),
        protocolInspectPath: localPath("default_protocol_path", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output\\case001\\local_toolkit_protocol.json"),
        feedbackOutputDir: localPath("default_output_dir", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output\\case001"),
        voiceOutputDir: localPath("default_output_dir", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output\\case001"),
        mossTestOutputDir: localPath("default_output_dir", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output\\case001"),
        protocolDropboxDir: localPath("protocol_dropbox_root", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\protocol_dropbox"),
      };
      Object.entries(defaults).forEach(([id, value]) => {
        const el = $(id);
        if (el && value) el.placeholder = value;
      });
    }

    function suggestOutputDir(force = false, labelHint = "") {
      const el = $("outputDir");
      if (!el) return "";
      const current = String(el.value || "").trim();
      if (!force && current) return current;
      if (labelHint) preferredOutputLabelHint = labelHint;
      const nextValue = composeSuggestedOutputDir(labelHint);
      el.value = nextValue;
      saveLocalDraft();
      renderOutputDirHelper();
      refreshGuidedFeedbacks();
      status.textContent = "已填写推荐保存位置";
      return nextValue;
    }

    function applyBeginnerPreset(presetId) {
      const preset = BEGINNER_PRESETS.find((item) => item.id === presetId);
      if (!preset) return;
      setValue("userRequest", preset.userRequest);
      setValue("duration", preset.duration);
      setValue("aspect", preset.aspect);
      setValue("resolution", preset.resolution);
      setValue("quality", preset.quality);
      setValue("subtitleMode", preset.subtitleMode);
      setValue("voiceProvider", preset.voiceProvider);
      updateSubtitleControls();
      updateVoiceControls();
      suggestOutputDir(true, preset.label);
      markBriefStale();
      renderMessage("已套用起步方案", `${preset.label}：先检查目标，再生成剪辑标准。`);
      scrollToStep("assistantStep");
    }

    function runWorkflowGuideAction() {
      if (workflowGuideAction.type === "panel" && workflowGuideAction.panel) {
        switchPanel(workflowGuideAction.panel);
        return;
      }
      scrollToStep(workflowGuideAction.targetId || "setupStep");
    }

    function renderCurrentResultEmpty() {
      $("currentResult").innerHTML = `
        <div class="summary-item empty-state">
          <strong>还没有成片</strong>
          <span class="hint">先在“开始剪辑”页做出第一版，完成后这里会自动显示视频、输出目录和复剪入口。</span>
          <div class="actions">
            <button class="secondary" onclick="switchPanel('cut')">去开始剪辑</button>
          </div>
        </div>
      `;
    }

    function playReviewVideo(path) {
      const selected = String(path || "").trim();
      if (!selected) return;
      $("videoPreview").src = `/api/media-preview?path=${encodeURIComponent(selected)}`;
      $("videoPreview").style.display = "block";
      $("videoPreview").scrollIntoView({behavior: "smooth", block: "center"});
      $("videoPreview").play().catch(() => {
        status.textContent = "已定位到成片播放器，可点击播放";
      });
      switchPanel("review");
    }

    function reviewActionButtons({videoPath = "", outputDir = "", editLabel = "回到剪辑页"} = {}) {
      const actions = [];
      if (videoPath) {
        actions.push(`<button onclick="playReviewVideo('${escapeJs(videoPath)}')">播放成片</button>`);
      }
      if (editLabel) {
        actions.push(`<button class="neutral" onclick="switchPanel('cut')">${escapeHtml(editLabel)}</button>`);
      }
      if (outputDir) {
        actions.push(`<button class="neutral" onclick="loadProjectVersionCenter('${escapeJs(outputDir)}', null)">查看版本</button>`);
      }
      return actions.length ? `<div class="actions">${actions.join("")}</div>` : "";
    }

    function renderRecentRunsEmpty() {
      $("recentRuns").innerHTML = `
        <div class="summary-item empty-state">
          <strong>还没有成片历史</strong>
          <span class="hint">先回到“开始剪辑”做出第一版；完成后这里会自动出现最近结果。</span>
          <div class="actions">
            <button class="secondary" onclick="switchPanel('cut')">去开始剪辑</button>
          </div>
        </div>
      `;
    }

    function renderProjectLibraryEmpty() {
      $("projectLibraryList").innerHTML = `
        <div class="summary-item empty-state">
          <strong>还没有项目记录</strong>
          <span class="hint">你可以先完成一次剪辑，或者点击“重建索引”扫描已有输出目录。</span>
          <div class="actions">
            <button class="secondary" onclick="switchPanel('cut')">去开始剪辑</button>
          </div>
        </div>
      `;
    }

    function focusTemplateBuilder() {
      switchPanel("package");
      const input = $("templateVideo");
      if (!input) return;
      input.scrollIntoView({behavior: "smooth", block: "center"});
      setTimeout(() => input.focus({preventScroll: true}), 180);
    }

    function renderPackageListEmpty() {
      $("packageList").innerHTML = `
        <div class="summary-item empty-state">
          <strong>还没有样板</strong>
          <span class="hint">先拿一条参考视频生成样板；以后再剪同类视频时，就能直接复用这一套默认风格。</span>
          <div class="actions">
            <button class="secondary" onclick="focusTemplateBuilder()">去创建样板</button>
          </div>
        </div>
      `;
    }

    function renderFirstRunGuide() {
      const box = $("firstRunGuide");
      if (!box) return;
      if (onboardingDismissed()) {
        box.innerHTML = `
          <div class="summary-item">
            <strong>新手建议已收起</strong>
            <span class="hint">需要时可以重新打开，也可以只让系统自动填写一个新的保存目录。</span>
            <div class="actions">
              <button class="secondary" type="button" onclick="toggleFirstRunGuide(false)">重新打开新手建议</button>
              <button class="neutral" type="button" onclick="suggestOutputDir(true)">自动填写推荐路径</button>
            </div>
          </div>
        `;
        return;
      }
      const root = localPath("output_root", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output");
      const suggested = composeSuggestedOutputDir();
      box.innerHTML = `
        <div class="summary-item">
          <strong>第一次用，先套一个起步方案</strong>
          <div class="chip-row">
            <span class="chip ok">普通用户推荐</span>
            <span class="chip">默认输出目录</span>
            <span class="chip">${escapeHtml(shortPath(root))}</span>
          </div>
          <span class="hint">你可以先点一个最接近的方案。系统会自动填写目标、时长、比例，并给这次剪辑安排一个新的保存目录，不会覆盖旧成片。</span>
          <div class="preset-grid">
            ${BEGINNER_PRESETS.map((preset) => `
              <button class="preset-button" type="button" onclick="applyBeginnerPreset('${escapeJs(preset.id)}')">
                <strong>${escapeHtml(preset.label)}</strong>
                <span class="mini">${escapeHtml(preset.summary)}</span>
              </button>
            `).join("")}
          </div>
          <div class="soft-callout path-callout">
            默认输出根目录：${escapeHtml(root)}
            <br>
            推荐新目录：${escapeHtml(suggested)}
          </div>
          <div class="actions">
            <button class="secondary" type="button" onclick="suggestOutputDir(true)">只填写推荐路径</button>
            <button class="neutral" type="button" onclick="toggleFirstRunGuide(true)">先隐藏这块</button>
          </div>
        </div>
      `;
    }

    function renderOutputDirHelper() {
      const box = $("outputDirHelp");
      if (!box) return;
      const current = String($("outputDir")?.value || "").trim();
      const suggested = composeSuggestedOutputDir();
      const root = localPath("output_root", "D:\\个人文件\\个人开发\\智能剪辑软件\\workspace\\output");
      if (!current) {
        box.innerHTML = `
          <div class="summary-item">
            <strong>建议先确定保存位置</strong>
            <span class="hint">系统会在默认输出根目录下新建独立子目录，把成片、版本和交接文件放在一起，不会覆盖旧成片。</span>
            <div class="path-text">默认输出根目录：${escapeHtml(root)}</div>
            <div class="path-text">推荐目录：${escapeHtml(suggested)}</div>
            <div class="actions">
              <button class="secondary" type="button" onclick="suggestOutputDir(true)">自动填写推荐路径</button>
            </div>
          </div>
        `;
        return;
      }
      box.innerHTML = `
        <div class="summary-item">
          <strong>当前这版会保存到这里</strong>
          <span class="hint">系统会把成片、版本历史和交接文件都写到这个目录里。想单独开新版本时，可以一键换成新的推荐目录。</span>
          <div class="path-text">${escapeHtml(current)}</div>
          <div class="actions">
            <button class="neutral" type="button" onclick="suggestOutputDir(true)">换成新的推荐目录</button>
          </div>
        </div>
      `;
    }

    function currentDirectorSnapshot() {
      return JSON.stringify({
        user_request: String($("userRequest")?.value || "").trim(),
        director_message: String($("directorMessage")?.value || "").trim()
      });
    }

    function collectWorkflowState() {
      const styleReady = Boolean(String($("stylePackage")?.value || "").trim());
      const inputCount = normalizeInputVideos().length;
      const outputReady = Boolean(String($("outputDir")?.value || "").trim());
      const requestReady = Boolean(String($("userRequest")?.value || "").trim());
      const briefText = String($("briefText")?.value || "").trim();
      const hasBrief = Boolean(briefText);
      const canStart = briefReady && hasBrief;
      const latestOutput = String(latestResult?.output_dir || "").trim();
      const latestRequest = String(latestResult?.user_request || "").trim();
      const latestBrief = String(latestResult?.confirmed_brief || "").trim();
      const missingSetup = [];
      if (!styleReady) missingSetup.push("样板");
      if (!inputCount) missingSetup.push("原视频");
      if (!outputReady) missingSetup.push("保存位置");
      return {
        styleReady,
        inputCount,
        outputReady,
        requestReady,
        briefText,
        hasBrief,
        canStart,
        missingSetup,
        setupReady: missingSetup.length === 0,
        resultMatchesCurrent: Boolean(
          latestResult?.ok &&
          latestResult?.copied_output_video &&
          latestOutput &&
          latestOutput === String($("outputDir")?.value || "").trim() &&
          latestRequest === String($("userRequest")?.value || "").trim() &&
          latestBrief === briefText
        ),
        directorCurrent: latestDirectorRequestSnapshot === currentDirectorSnapshot()
      };
    }

    function renderModuleFeedback(containerId, {tone = "", title, body, chips = [], action = null, secondaryAction = null}) {
      const box = $(containerId);
      if (!box) return;
      box.innerHTML = `
        <div class="summary-item">
          <strong>${escapeHtml(title)}</strong>
          ${chips.length ? `<div class="chip-row">${chips.map((item) => `<span class="chip ${escapeHtml(item.tone || "")}">${escapeHtml(item.label || "")}</span>`).join("")}</div>` : ""}
          <span class="hint">${escapeHtml(body)}</span>
          ${(action || secondaryAction) ? `<div class="actions">
            ${action ? `<button class="secondary" onclick="${action.code}">${escapeHtml(action.label)}</button>` : ""}
            ${secondaryAction ? `<button class="neutral" onclick="${secondaryAction.code}">${escapeHtml(secondaryAction.label)}</button>` : ""}
          </div>` : ""}
        </div>
      `;
    }

    function renderSetupFeedback() {
      const state = collectWorkflowState();
      const packLabel = $("stylePackageSelect")?.selectedOptions?.[0]?.textContent?.trim() || "已选样板";
      if (!state.styleReady) {
        renderModuleFeedback("setupFeedback", {
          tone: "warn",
          title: "还没选样板",
          body: packages.length
            ? "先选一个已有样板，后面的时长、比例和字幕默认值会自动更贴近你的成片风格。"
            : "当前还没有可用样板。你可以先去“样板与素材”里用参考视频创建一个。",
          chips: [{label: packages.length ? `已有样板 ${packages.length}` : "暂无样板", tone: packages.length ? "" : "warn"}],
          action: packages.length
            ? {label: "去步骤 1", code: "scrollToStep('setupStep')"}
            : {label: "去创建样板", code: "focusTemplateBuilder()"}
        });
        return;
      }
      if (!state.inputCount) {
        renderModuleFeedback("setupFeedback", {
          tone: "warn",
          title: "还没加入原视频素材",
          body: "至少加入 1 个原视频，系统才能帮你生成剪辑标准并安排素材分工。",
          chips: [{label: packLabel, tone: "ok"}, {label: "素材 0 个", tone: "warn"}],
          action: {label: "去加素材", code: "scrollToStep('setupStep')"}
        });
        return;
      }
      if (!state.outputReady) {
        renderModuleFeedback("setupFeedback", {
          tone: "warn",
          title: "还没选成片保存位置",
          body: "建议先指定成片保存目录，生成标准和出片后都更容易找到结果。",
          chips: [{label: packLabel, tone: "ok"}, {label: `素材 ${state.inputCount} 个`, tone: "ok"}],
          action: {label: "去选保存位置", code: "scrollToStep('setupStep')"}
        });
        return;
      }
      renderModuleFeedback("setupFeedback", {
        tone: "ok",
        title: "步骤 1 已准备好",
        body: "样板、素材和保存位置都已经就绪。下一步可以直接说出你想要的效果。",
        chips: [{label: packLabel, tone: "ok"}, {label: `素材 ${state.inputCount} 个`, tone: "ok"}, {label: "保存位置已填写", tone: "ok"}],
        action: {label: "去步骤 2", code: "scrollToStep('assistantStep')"}
      });
    }

    function renderAssistantFeedback() {
      const state = collectWorkflowState();
      const currentRequest = String($("userRequest")?.value || "").trim();
      if (!state.requestReady) {
        renderModuleFeedback("assistantFeedback", {
          tone: "warn",
          title: "还没写目标",
          body: "直接写一句“这条视频想做成什么样”就行，不需要专业术语。",
          chips: [{label: "步骤 2 待填写", tone: "warn"}],
          action: {label: "去写目标", code: "scrollToStep('assistantStep')"}
        });
        return;
      }
      if (latestDirectorResponse?.ok && !state.directorCurrent) {
        renderModuleFeedback("assistantFeedback", {
          tone: "warn",
          title: "你改过目标，建议重新发给助手",
          body: "为了避免助手还在参考旧要求，最好把现在的目标再发送一次，让建议参数和后续步骤保持一致。",
          chips: [{label: "目标已更新", tone: "warn"}],
          action: {label: "重新发给助手", code: "scrollToStep('assistantStep')"},
          secondaryAction: {label: "直接生成标准", code: "scrollToStep('confirmStep')"}
        });
        return;
      }
      if (latestDirectorResponse?.ok) {
        const missing = latestDirectorResponse.missing_inputs || [];
        renderModuleFeedback("assistantFeedback", {
          tone: missing.length ? "warn" : "ok",
          title: missing.length ? "助手已回复，但还差一点信息" : "助手已整理你的目标",
          body: latestDirectorResponse.assistant_message || "助手已经给出理解和建议参数。",
          chips: [
            {label: missing.length ? `待补 ${missing.length} 项` : "建议已就绪", tone: missing.length ? "warn" : "ok"},
            {label: currentRequest.length > 18 ? `${currentRequest.slice(0, 18)}...` : currentRequest, tone: ""}
          ],
          action: latestDirectorResponse.settings_overrides && Object.keys(latestDirectorResponse.settings_overrides).length
            ? {label: "应用建议参数", code: "applyDirectorOverrides()"}
            : {label: "去步骤 3", code: "scrollToStep('confirmStep')"},
          secondaryAction: {label: "继续补充要求", code: "scrollToStep('assistantStep')"}
        });
        return;
      }
      renderModuleFeedback("assistantFeedback", {
        tone: "ok",
        title: "目标已经写好了",
        body: "你可以直接发给助手，让它帮你整理要求；如果目标已经很明确，也可以跳过这一步，直接去生成剪辑标准。",
        chips: [{label: "步骤 2 已填写", tone: "ok"}],
        action: {label: "发给助手", code: "scrollToStep('assistantStep')"},
        secondaryAction: {label: "去步骤 3", code: "scrollToStep('confirmStep')"}
      });
    }

    function renderConfirmFeedback() {
      const state = collectWorkflowState();
      if (state.resultMatchesCurrent) {
        renderModuleFeedback("confirmFeedback", {
          tone: "ok",
          title: "这一版已经生成",
          body: "建议先去“查看结果”播放成片；如果还想改字幕、节奏或镜头，再回来继续复剪。",
          chips: [{label: "步骤 3 已出片", tone: "ok"}],
          action: {label: "查看结果", code: "switchPanel('review')"},
          secondaryAction: {label: "继续改这一版", code: "scrollToStep('confirmStep')"}
        });
        return;
      }
      if (!state.setupReady || !state.requestReady) {
        renderModuleFeedback("confirmFeedback", {
          tone: "warn",
          title: "还不能开始生成第一版",
          body: "先把前面的准备补齐，再来生成剪辑标准和第一版成片。",
          chips: [
            {label: `步骤 1 ${state.setupReady ? "已就绪" : "待补齐"}`, tone: state.setupReady ? "ok" : "warn"},
            {label: `步骤 2 ${state.requestReady ? "已填写" : "待填写"}`, tone: state.requestReady ? "ok" : "warn"}
          ],
          action: {label: "回到前面补齐", code: "runWorkflowGuideAction()"}
        });
        return;
      }
      if (!state.hasBrief) {
        renderModuleFeedback("confirmFeedback", {
          tone: "warn",
          title: "还没生成剪辑标准",
          body: "先生成一次剪辑标准，确认系统理解没跑偏，再开始输出第一版会更稳。",
          chips: [{label: "步骤 3 待生成标准", tone: "warn"}],
          action: {label: "去生成标准", code: "scrollToStep('confirmStep')"}
        });
        return;
      }
      if (!state.canStart) {
        renderModuleFeedback("confirmFeedback", {
          tone: "warn",
          title: "剪辑标准需要重新确认",
          body: "你改过素材、样板或目标，之前生成的标准已经过期。重新生成后再开始出片。",
          chips: [{label: "待重新确认", tone: "warn"}],
          action: {label: "重新生成标准", code: "scrollToStep('confirmStep')"}
        });
        return;
      }
      renderModuleFeedback("confirmFeedback", {
        tone: "ok",
        title: "可以开始生成第一版",
        body: "剪辑标准已经就绪。现在可以直接点“确认并生成第一版”，也可以先去看时间线预览。",
        chips: [{label: "步骤 3 可开剪", tone: "ok"}],
        action: {label: "去生成第一版", code: "scrollToStep('confirmStep')"},
        secondaryAction: {label: "看时间线预览", code: "document.querySelector('.timeline-workbench')?.scrollIntoView({behavior:'smooth', block:'start'})"}
      });
    }

    function refreshGuidedFeedbacks() {
      renderFirstRunGuide();
      renderWorkflowGuide();
      renderSetupFeedback();
      renderAssistantFeedback();
      renderConfirmFeedback();
      renderOutputDirHelper();
    }

    function renderWorkflowGuide() {
      const box = $("workflowGuide");
      if (!box) return;
      const state = collectWorkflowState();
      let title = "现在该做什么";
      let summary = "把这 3 步走完，就能稳定生成第一版。";
      let buttonLabel = "去完成当前这一步";
      workflowGuideAction = {type: "step", targetId: "setupStep"};
      if (state.resultMatchesCurrent) {
        title = "第一版已经生成";
        summary = "建议先去“查看结果”播放成片；如果只想小改字幕、节奏或镜头，再回来填写复剪意见。";
        buttonLabel = "查看结果";
        workflowGuideAction = {type: "panel", panel: "review"};
      } else if (!state.setupReady) {
        title = "先完成步骤 1";
        summary = `还差 ${state.missingSetup.join("、")}。先把样板、原视频和保存位置补齐，再继续写目标。`;
        buttonLabel = "去补步骤 1";
        workflowGuideAction = {type: "step", targetId: "setupStep"};
      } else if (!state.requestReady) {
        title = "补一句你想要的效果";
        summary = "不用写得专业，只要像和剪辑师说话一样告诉系统“要做成什么样”就可以。";
        buttonLabel = "去写目标";
        workflowGuideAction = {type: "step", targetId: "assistantStep"};
      } else if (!state.hasBrief) {
        title = "先生成剪辑标准";
        summary = "系统还没把你的目标整理成可确认的执行标准。先生成一次，再决定是否开剪。";
        buttonLabel = "去生成标准";
        workflowGuideAction = {type: "step", targetId: "confirmStep"};
      } else if (!state.canStart) {
        title = "重新确认剪辑标准";
        summary = "你改过素材或要求，之前的剪辑标准已经过期。重新生成一次后，再开始输出第一版。";
        buttonLabel = "去重新生成";
        workflowGuideAction = {type: "step", targetId: "confirmStep"};
      } else {
        title = "可以开始生成第一版";
        summary = "样板、素材、目标和剪辑标准都已就绪。现在点“确认并生成第一版”就可以开始。";
        buttonLabel = "去确认并开始";
        workflowGuideAction = {type: "step", targetId: "confirmStep"};
      }
      box.innerHTML = `
        <div class="summary-item">
          <strong>${escapeHtml(title)}</strong>
          <div class="chip-row">
            <span class="chip ${state.setupReady ? "ok" : "warn"}">步骤 1 ${state.setupReady ? "已就绪" : "待补齐"}</span>
            <span class="chip ${state.requestReady ? "ok" : "warn"}">步骤 2 ${state.requestReady ? "已填写" : "待填写"}</span>
            <span class="chip ${state.resultMatchesCurrent ? "ok" : state.canStart ? "ok" : state.hasBrief ? "warn" : ""}">步骤 3 ${state.resultMatchesCurrent ? "已出片" : state.canStart ? "可开剪" : state.hasBrief ? "待重新确认" : "待生成标准"}</span>
            <span class="chip">${state.inputCount} 个素材</span>
          </div>
          <span class="hint">${escapeHtml(summary)}</span>
          <div class="actions">
            <button class="secondary" onclick="runWorkflowGuideAction()">${escapeHtml(buttonLabel)}</button>
            ${state.resultMatchesCurrent ? `<button class="neutral" onclick="scrollToStep('confirmStep')">继续改这一版</button>` : ""}
          </div>
        </div>
      `;
    }

    function registerBeginnerFieldListeners() {
      [
        "stylePackage", "inputVideo", "outputDir", "userRequest", "voiceoverText", "briefText"
      ].forEach((id) => {
        const el = $(id);
        if (!el || el.dataset.beginnerListenerBound === "true") return;
        const eventName = el.tagName === "SELECT" || el.type === "checkbox" ? "change" : "input";
        el.addEventListener(eventName, () => {
          if (["stylePackage", "inputVideo", "userRequest", "voiceoverText"].includes(id)) {
            markBriefStale();
            return;
          }
          refreshGuidedFeedbacks();
        });
        el.dataset.beginnerListenerBound = "true";
      });
    }

    function setButtonBusy(button, busyText) {
      if (!button || !button.classList || !("disabled" in button)) return;
      if (!buttonStates.has(button)) {
        buttonStates.set(button, {html: button.innerHTML, disabled: button.disabled});
      }
      button.disabled = true;
      button.classList.add("busy");
      button.setAttribute("aria-busy", "true");
      if (busyText) button.textContent = busyText;
    }

    function restoreButton(button) {
      if (!button || !button.classList || !("disabled" in button)) return;
      const previous = buttonStates.get(button);
      if (!previous) return;
      button.innerHTML = previous.html;
      button.disabled = previous.disabled;
      button.classList.remove("busy");
      button.removeAttribute("aria-busy");
      buttonStates.delete(button);
    }

    async function withButtonState(button, busyText, action) {
      setButtonBusy(button, busyText);
      try {
        return await action();
      } finally {
        restoreButton(button);
      }
    }

    function toggleToolsDropdown() {
      $("toolsMenu").classList.toggle("open");
    }

    let currentWizardStep = 1;

    function goToWizardStep(step) {
      currentWizardStep = step;
      // Update progress indicators
      document.querySelectorAll(".wizard-step-indicator").forEach((el) => {
        const elStep = parseInt(el.dataset.wizardStep, 10);
        el.classList.toggle("active", elStep === step);
        el.classList.toggle("completed", elStep < step);
      });
      // Scroll to the step section
      const targets = {1: "setupStep", 2: "assistantStep", 3: "confirmStep"};
      scrollToStep(targets[step] || "setupStep");
    }

    function switchPanel(name) {
      document.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.panel === name);
      });
      document.querySelectorAll("[data-panel-button]").forEach((button) => {
        button.classList.toggle("active", button.dataset.panelButton === name);
      });
      if (name === "review") loadRecentRuns();
      if (name === "library") {
        loadProjectLibrary();
        loadDeploymentGuide();
      }
      if (name === "package") {
        loadPackages();
        if ($("protocolDropboxDir")?.value?.trim()) {
          refreshProtocolDropboxMonitor(null, true).catch(() => {});
        }
      }
      if (name === "settings") loadMossSampleHistory();
    }

    function payloadProblemText(payload) {
      if (typeof payload === "string") return payload;
      if (!payload || typeof payload !== "object") return "";
      return String(
        payload.error ||
        payload.detail ||
        payload.message ||
        payload.reason ||
        payload.stage ||
        ""
      ).trim();
    }

    function humanizeProblemText(value) {
      const raw = String(value || "").trim();
      if (!raw) return "";
      const normalized = raw.toLowerCase();
      const mapped = {
        missing_model: "还没有选好要用的模型",
        missing_api_key: "还没有填写可用的 API Key",
        missing_base_url: "还没有填写模型服务地址",
        http_error: "模型服务返回了错误",
        urlerror: "当前连不到模型服务或本地运行服务",
        runtimeerror: "本地运行环境还没准备好",
        moss_tts_runtime_not_ready: "MOSS 配音环境还没准备好",
        permissionerror: "当前目录没有写入权限",
        filenotfounderror: "系统找不到需要的文件",
        valueerror: "当前输入内容还不完整",
      };
      if (mapped[normalized]) return mapped[normalized];
      if (normalized.includes("missing_model")) return mapped.missing_model;
      if (normalized.includes("missing_api_key")) return mapped.missing_api_key;
      if (normalized.includes("missing_base_url")) return mapped.missing_base_url;
      if (normalized.includes("urlerror")) return mapped.urlerror;
      if (normalized.includes("runtimeerror")) return mapped.runtimeerror;
      if (normalized.includes("moss_tts_runtime_not_ready")) return mapped.moss_tts_runtime_not_ready;
      if (normalized.includes("permission")) return mapped.permissionerror;
      if (normalized.includes("no such file") || normalized.includes("not found")) return mapped.filenotfounderror;
      if (normalized.includes("_")) {
        return raw.replaceAll("_", " ");
      }
      return raw;
    }

    function requestTargetLabel(url) {
      const value = String(url || "");
      if (value.startsWith("/api/cut")) return "生成第一版";
      if (value.startsWith("/api/edit-brief")) return "生成剪辑标准";
      if (value.startsWith("/api/timeline/edit")) return "应用时间线编辑";
      if (value.startsWith("/api/timeline")) return "生成时间线预览";
      if (value.startsWith("/api/director/chat")) return "发送给助手";
      if (value.startsWith("/api/llm-config")) return "保存模型设置";
      if (value.startsWith("/api/llm-test")) return "测试模型连接";
      if (value.startsWith("/api/ollama")) return "读取本地 Ollama";
      if (value.startsWith("/api/moss-tts")) return "生成本地配音";
      if (value.startsWith("/api/style-packages")) return "读取样板";
      return "当前操作";
    }

    function renderActionButtonsHtml(actions = []) {
      const valid = actions.filter((item) => item && item.label && item.code);
      if (!valid.length) return "";
      return `
        <div class="actions">
          ${valid.map((item) => `<button class="${escapeHtml(item.tone || "neutral")}" onclick="${item.code}">${escapeHtml(item.label)}</button>`).join("")}
        </div>
      `;
    }

    function renderHintListHtml(lines = []) {
      const valid = lines.filter(Boolean);
      if (!valid.length) return "";
      return valid.map((item, index) => `<div class="hint">${escapeHtml(`${index + 1}. ${item}`)}</div>`).join("");
    }

    function buildRequestFailureMessage(url, payload, statusCode = 0) {
      const target = requestTargetLabel(url);
      const rawProblem = payloadProblemText(payload);
      const friendlyProblem = humanizeProblemText(rawProblem);
      const normalized = rawProblem.toLowerCase();
      const tips = [];
      const actions = [];

      if (url.startsWith("/api/cut") || url.startsWith("/api/edit-brief") || url.startsWith("/api/timeline")) {
        actions.push({label: "回到开始剪辑", code: "switchPanel('cut')", tone: "secondary"});
      }

      if (normalized.includes("missing_model") || normalized.includes("missing_api_key") || normalized.includes("missing_base_url") || normalized.includes("urlerror") || normalized.includes("runtimeerror")) {
        tips.push("先到“高级设置”检查模型地址、模型名称和 API Key 是否可用。");
        tips.push("如果你当前用的是本地 Ollama，先确认本地服务已经启动。");
        actions.push({label: "去模型与声音设置", code: "switchPanel('settings')", tone: "neutral"});
      } else if (normalized.includes("output_dir") || normalized.includes("permission")) {
        tips.push("回到步骤 1，重新选择一个你有写入权限的保存目录。");
        tips.push("尽量不要把成片直接写到系统受限目录里。");
        actions.push({label: "去检查保存位置", code: "scrollToStep('setupStep')", tone: "neutral"});
      } else if (normalized.includes("input_video") || normalized.includes("no such file") || normalized.includes("not found")) {
        tips.push("回到步骤 1，确认原视频路径仍然存在，并重新加入素材列表。");
        tips.push("如果素材刚被移动过，最好重新选择一次。");
        actions.push({label: "去检查素材", code: "scrollToStep('setupStep')", tone: "neutral"});
      } else if (normalized.includes("style_package")) {
        tips.push("先确认样板目录还存在，再重新点一次“用于剪辑”或重新选择目录。");
        actions.push({label: "去检查样板", code: "scrollToStep('setupStep')", tone: "neutral"});
      } else if (normalized.includes("brief")) {
        tips.push("先重新生成一次剪辑标准，确认系统理解没跑偏后再开始。");
        actions.push({label: "去重新生成标准", code: "scrollToStep('confirmStep')", tone: "neutral"});
      } else if (normalized.includes("ffmpeg")) {
        tips.push("先看“本地运行状态”里 FFmpeg 是否可用，再重试这一步。");
        tips.push("如果刚替换过运行环境，重启本地服务后再试一次。");
      } else if (statusCode >= 500) {
        tips.push("这次更像是运行时异常。先检查路径和模型配置，再重试一次。");
        tips.push("原始技术详情已经保留在下方，方便继续排查。");
      } else {
        tips.push("先检查这一步前面的输入是否都已经填好。");
        tips.push("如果你刚改过素材、样板或目标，最好重新生成一次剪辑标准。");
      }

      return {
        title: `${target}没完成`,
        tone: "warn",
        body: {
          summary: friendlyProblem ? `系统卡在：${friendlyProblem}。` : `“${target}”这一步还没有顺利完成。`,
          chips: [
            {label: target, tone: "warn"},
            ...(statusCode ? [{label: `HTTP ${statusCode}`, tone: "warn"}] : []),
          ],
          tips,
          actions,
          detail: payload,
        },
      };
    }

    async function requestJson(url, body, uiOptions = {}) {
      const fetchOptions = body ? {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      } : {};
      const response = await fetch(url, fetchOptions);
      const text = await response.text();
      let payload;
      try { payload = JSON.parse(text); } catch { payload = text; }
      if (!response.ok) {
        const failure = buildRequestFailureMessage(url, payload, response.status);
        status.textContent = failure.title;
        status.classList.add("error");
        if (!uiOptions.silent) renderMessage(failure.title, failure.body, failure.tone);
        return payload;
      }
      status.classList.remove("error");
      if (!uiOptions.silent) renderPayload(payload);
      return payload;
    }

    function renderMessage(title, body, tone = "ok") {
      const chipClass = tone === "warn" ? "warn" : "ok";
      if (body && typeof body === "object" && !Array.isArray(body)) {
        const summary = String(body.summary || body.message || body.reason || body.detail || "").trim();
        const chips = Array.isArray(body.chips) ? body.chips.filter(Boolean) : [];
        const tips = Array.isArray(body.tips) ? body.tips.filter(Boolean) : [];
        const actions = Array.isArray(body.actions) ? body.actions.filter(Boolean) : [];
        resultCards.innerHTML = `
          <div class="summary-item">
            <strong>${escapeHtml(title)}</strong>
            <div class="chip-row">
              <span class="chip ${chipClass}">${escapeHtml(tone === "warn" ? "需要处理" : "已完成")}</span>
              ${chips.map((item) => `<span class="chip ${escapeHtml(item.tone || "")}">${escapeHtml(item.label || "")}</span>`).join("")}
            </div>
            ${summary ? `<span class="hint">${escapeHtml(summary)}</span>` : ""}
            ${renderHintListHtml(tips)}
            ${renderActionButtonsHtml(actions)}
          </div>
        `;
        resultDetails.textContent = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body, null, 2);
        return;
      }
      resultCards.innerHTML = `<div class="summary-item"><strong>${escapeHtml(title)}</strong><span class="chip ${chipClass}">${escapeHtml(String(body))}</span></div>`;
      resultDetails.textContent = typeof body === "string" ? body : JSON.stringify(body, null, 2);
    }

    function renderPayload(payload) {
      resultDetails.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
      if (payload && payload.schema === "smart_video_cut.local.director_chat.v0") {
        renderDirectorChatResult(payload);
        renderMessage("总导演已回复", payload.assistant_message || "已生成建议动作");
        return;
      }
      if (payload && payload.schema === "smart_video_cut.local.agent_orchestration.v0") {
        renderAgentOrchestration(payload);
        renderMessage("多 Agent 编排已生成", payload.summary?.recommended_next_action?.label || "请检查各 Agent 状态");
        return;
      }
      if (payload && payload.schema === "smart_video_cut.local.edit_brief.v0") {
        renderMessage("剪辑标准已生成", "请检查概要，确认后再开始剪辑");
        return;
      }
      if (payload && payload.schema === "smart_video_cut.local.worker_task_package.v0") {
        renderWorkerTaskPreview(payload);
        renderMessage("Worker 任务包已更新", payload.package_path || "请检查任务包摘要");
        return;
      }
        if (payload && payload.schema === "smart_video_cut.local.worker_completion.v0") {
          renderWorkerTaskPreview(payload);
          renderMessage(payload.ok ? "Worker 任务包已执行" : "Worker 任务包执行失败", payload.completion_path || payload.error || "请检查 completion");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.toolkit_protocol.v0") {
          renderProtocolPreview(payload);
          renderMessage(payload.ok ? "本地协议清单已生成" : "本地协议清单不完整", payload.protocol_path || payload.output_dir || "请检查协议摘要", payload.ok ? "ok" : "warn");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.toolkit_protocol_inspection.v0") {
          renderProtocolPreview(payload);
          renderMessage(payload.ok ? "本地协议检查完成" : "本地协议检查失败", payload.path || payload.reason || "请检查协议摘要", payload.ok ? "ok" : "warn");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.protocol_dropbox.v0") {
          renderProtocolPreview(payload);
          renderMessage("标准协议投递箱已就绪", payload.dropbox_dir || payload.manifest_path || "请检查投递箱摘要");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.protocol_dropbox_import.v0") {
          renderProtocolPreview(payload);
          renderMessage(payload.ok ? "协议已投递到标准队列" : "协议投递失败", payload.imported_path || payload.source_path || "请检查投递结果", payload.ok ? "ok" : "warn");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.protocol_dropbox_run.v0") {
          renderProtocolPreview(payload);
          renderMessage(payload.ok ? "标准协议投递箱执行完成" : "标准协议投递箱执行有异常", payload.status_path || payload.dropbox_dir || "请检查队列摘要", payload.ok ? "ok" : "warn");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.protocol_dropbox_monitor.v0") {
          renderProtocolPreview(payload);
          renderMessage(payload.running ? "标准协议投递箱正在自动轮询" : "标准协议投递箱轮询状态已更新", payload.monitor_path || payload.dropbox_dir || "请检查轮询看板", payload.ok ? "ok" : "warn");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.protocol_dropbox_history.v0") {
          renderProtocolPreview(payload);
          renderMessage("标准协议投递箱历史已加载", payload.history_path || payload.dropbox_dir || "请检查历史摘要", payload.last_alert_level === "warn" ? "warn" : "ok");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.protocol_dropbox_requeue.v0") {
          renderProtocolPreview(payload);
          renderMessage(payload.moved_count > 0 ? "失败文件已回投到标准队列" : "没有可回投的失败文件", payload.dropbox_dir || payload.manifest_path || "请检查回投结果", payload.moved_count > 0 ? "ok" : "warn");
          return;
        }
        if (payload && payload.schema === "smart_video_cut.local.edit_result.v0") {
          renderEditResult(payload);
          return;
        }
      if (payload && payload.available !== undefined && payload.media_tools) {
        renderRuntime(payload);
        return;
      }
      if (payload && payload.package) {
        renderMessage("风格包已保存", payload.package_dir || payload.package.name);
        return;
      }
      if (payload && payload.audio_path) {
        renderMessage(payload.ok ? "样音已生成" : "样音生成失败", payload.audio_path || payload.reason || "请查看技术详情", payload.ok ? "ok" : "warn");
        return;
      }
      if (payload && payload.ok === false) {
        const failure = buildRequestFailureMessage("", payload, 0);
        renderMessage("这一步还没完成", {
          ...failure.body,
          chips: (failure.body.chips || []).filter((item) => item.label !== "当前操作"),
        }, "warn");
        return;
      }
      renderMessage("操作完成", "结果已更新");
    }

    function directorContextPayload() {
      const payload = collectEditPayload();
      return {
        style_package: payload.style_package,
        input_video: payload.input_video,
        input_videos: payload.input_videos,
        output_dir: payload.output_dir,
        user_request: payload.user_request,
        voiceover_text: $("voiceoverText").value,
        confirmed_brief: $("briefText").value,
        execute_real_render: $("executeReal").checked,
        subtitle_handoff_path: $("subtitleHandoffPath").value,
        bgm_audio_path: $("bgmAudioPath").value,
        bgm_library_dir: $("bgmLibraryDir").value,
        voice_profile_ref: latestVoiceProfileRef,
        settings_overrides: payload.settings_overrides,
        has_timeline_override: Boolean(payload.timeline_override),
        timeline_override: payload.timeline_override
      };
    }

    async function chatWithDirector(button = null) {
      const message = $("directorMessage").value.trim() || $("userRequest").value.trim();
      if (!message) {
        status.textContent = "请先写一句要和导演沟通的话";
        return null;
      }
      return withButtonState(button, "沟通中", async () => {
        status.textContent = "总导演正在理解需求";
        const payload = await requestJson("/api/director/chat", {
          message,
          history: directorChatHistory,
          director_mode: $("directorMode").value,
          context: directorContextPayload()
        }, {silent: true});
        latestDirectorResponse = payload;
        latestDirectorRequestSnapshot = currentDirectorSnapshot();
        directorChatHistory.push({role: "user", content: message});
        directorChatHistory.push({role: "assistant", content: payload.assistant_message || ""});
        renderDirectorChatResult(payload);
        refreshGuidedFeedbacks();
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "总导演已给出建议" : "总导演沟通失败";
        return payload;
      });
    }

    async function orchestrateLocalAgents(button = null) {
      const message = $("directorMessage").value.trim() || $("userRequest").value.trim();
      return withButtonState(button, "编排中", async () => {
        status.textContent = "本地多 Agent 正在拆解任务";
        const payload = await requestJson("/api/agent/orchestrate", {
          message,
          history: directorChatHistory,
          director_mode: $("directorMode").value,
          context: directorContextPayload()
        }, {silent: true});
        latestAgentOrchestration = payload;
        if (payload.director_result) {
          latestDirectorResponse = payload.director_result;
          latestDirectorRequestSnapshot = currentDirectorSnapshot();
          renderDirectorChatResult(payload.director_result);
        }
        renderAgentOrchestration(payload);
        refreshGuidedFeedbacks();
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "多 Agent 编排已生成" : "多 Agent 编排失败";
        return payload;
      });
    }

    function renderDirectorChatResult(payload) {
      const box = $("directorChatResult");
      if (!box) return;
      if (!payload || !payload.ok) {
        box.innerHTML = `<div class="summary-item"><span class="hint">导演回复为空，请重新发送。</span></div>`;
        return;
      }
      const missing = (payload.missing_inputs || []).map((item) =>
        `<span class="chip warn">缺 ${escapeHtml(item.label || item.field || "")}</span>`
      ).join("");
      const actionCards = (payload.suggested_actions || []).map((item) => `
        <div class="director-action">
          <span>${escapeHtml(item.label || item.action_id || "建议动作")}</span>
          <button class="neutral" onclick="runDirectorAction('${escapeJs(item.action_id || "")}', '${escapeJs(item.api_endpoint || "")}', this)">执行</button>
        </div>
      `).join("");
      const overrideSummary = directorOverrideSummary(payload.settings_overrides || {});
      const llm = payload.llm_result || {};
      box.innerHTML = `
        <div class="summary-item">
          <strong>${escapeHtml(payload.assistant_message || "我理解了。")}</strong>
          <div class="chip-row">
            <span class="chip ok">意图 ${escapeHtml(payload.intent || "clarify")}</span>
            <span class="chip">模式 ${escapeHtml(payload.mode || "local_rule_director")}</span>
            ${payload.memory_context_applied ? `<span class="chip ok">已读取本地记忆</span>` : ""}
            ${llm.reason ? `<span class="chip ${llm.ok ? "ok" : "warn"}">LLM ${escapeHtml(llm.reason)}</span>` : ""}
            ${missing}
          </div>
          ${overrideSummary ? `<div class="notice">${escapeHtml(overrideSummary)}</div>` : ""}
        </div>
        ${actionCards || `<div class="summary-item"><span class="hint">暂无建议动作。</span></div>`}
      `;
    }

    function renderAgentOrchestration(payload) {
      const box = $("agentOrchestrationResult");
      if (!box) return;
      if (!payload || !payload.ok) {
        box.innerHTML = `<div class="summary-item"><span class="hint">多 Agent 编排为空，请重新生成。</span></div>`;
        return;
      }
      const summary = payload.summary || {};
      const recommended = summary.recommended_next_action || {};
      const agents = payload.agents || [];
      const agentCards = agents.map((agent) => {
        const missing = (agent.required_inputs || []).map((item) =>
          `<span class="chip warn">缺 ${escapeHtml(item.label || item.field || "")}</span>`
        ).join("");
        const findings = (agent.findings || []).slice(0, 3).map((item) =>
          `<span class="hint">${escapeHtml(item)}</span>`
        ).join("");
        const actions = (agent.tool_plan || []).slice(0, 2).map((action) => `
          <div class="director-action">
            <span>${escapeHtml(action.label || action.action_id || "建议动作")}</span>
            <button class="neutral" onclick="runOrchestrationAction('${escapeJs(action.action_id || "")}', '${escapeJs(action.api_endpoint || "")}', this)">执行</button>
          </div>
        `).join("");
        return `
          <div class="summary-item">
            <strong>${escapeHtml(agent.name || agent.agent_id || "Agent")}</strong>
            <div class="chip-row">
              <span class="chip ${agent.status === "blocked" ? "warn" : agent.status === "ready" ? "ok" : ""}">${escapeHtml(agentStatusLabel(agent.status))}</span>
              <span class="chip">信心 ${escapeHtml(agent.confidence ?? "")}</span>
              ${missing}
            </div>
            <span class="mini">${escapeHtml(agent.role || "")}</span>
            ${findings}
            ${agent.next_step ? `<div class="notice">${escapeHtml(agent.next_step)}</div>` : ""}
            ${actions}
          </div>
        `;
      }).join("");
      box.innerHTML = `
        <div class="summary-item">
          <strong>本地多 Agent 编排</strong>
          <div class="chip-row">
            <span class="chip ok">Agent ${escapeHtml(summary.agent_count || agents.length)}</span>
            <span class="chip ${summary.blocked_agents ? "warn" : "ok"}">阻塞 ${escapeHtml(summary.blocked_agents || 0)}</span>
            <span class="chip ${summary.run_ready ? "ok" : "warn"}">${summary.run_ready ? "可进入开剪门禁" : "需补齐输入"}</span>
          </div>
          <div class="notice">推荐下一步：${escapeHtml(recommended.label || "检查编排结果")}</div>
        </div>
        ${agentCards}
      `;
    }

    function agentStatusLabel(statusValue) {
      if (statusValue === "ready") return "就绪";
      if (statusValue === "blocked") return "阻塞";
      if (statusValue === "warning") return "风险";
      if (statusValue === "disabled") return "关闭";
      return statusValue || "未知";
    }

    function directorOverrideSummary(overrides) {
      const items = [];
      if (overrides.video?.target_duration_seconds) items.push(`时长 ${overrides.video.target_duration_seconds} 秒`);
      if (overrides.video?.aspect_ratio) items.push(`比例 ${overrides.video.aspect_ratio}`);
      if (overrides.video?.resolution) items.push(`分辨率 ${overrides.video.resolution}`);
      if (overrides.subtitle?.mode) items.push(`字幕 ${overrides.subtitle.mode}`);
      if (overrides.voice?.provider) items.push(`配音 ${overrides.voice.provider}`);
      if (overrides.audio?.bgm_style) items.push(`BGM ${overrides.audio.bgm_style}`);
      return items.length ? `可应用参数：${items.join("、")}` : "";
    }

    function applyDirectorOverrides() {
      const overrides = latestDirectorResponse?.settings_overrides || {};
      if (!Object.keys(overrides).length) {
        status.textContent = "当前没有可应用的导演参数建议";
        return;
      }
      applyDirectorOverrideValues(overrides);
      resultDetails.textContent = JSON.stringify(latestDirectorResponse, null, 2);
      status.textContent = "已应用导演建议参数";
      markBriefStale();
      refreshGuidedFeedbacks();
    }

    function applyDirectorOverrideValues(overrides) {
      if (overrides.video?.target_duration_seconds) setValue("duration", overrides.video.target_duration_seconds);
      if (overrides.video?.aspect_ratio) setValue("aspect", overrides.video.aspect_ratio);
      if (overrides.video?.resolution) setValue("resolution", overrides.video.resolution);
      if (overrides.subtitle?.mode) setValue("subtitleMode", normalizeSubtitleMode(overrides.subtitle.mode));
      if (overrides.voice?.provider) setValue("voiceProvider", overrides.voice.provider);
      if (overrides.audio?.bgm_style) setValue("bgmStyle", overrides.audio.bgm_style);
      updateSubtitleControls();
      updateVoiceControls();
      updateBgmControls();
    }

    async function runDirectorAction(actionId, endpoint, button = null) {
      if (actionId === "apply_settings_overrides") {
        applyDirectorOverrides();
        return null;
      }
      if (actionId === "generate_timeline") return generateTimelinePreview(button);
      if (actionId === "generate_edit_brief") return generateBrief(button);
      if (actionId === "run_cut") return cutVideo(button);
      if (actionId === "open_version_center") {
        switchPanel("review");
        status.textContent = "请在结果页选择版本复剪";
        return null;
      }
      if (actionId === "external_handoff" || actionId === "filmgen_handoff") {
        status.textContent = "请确认剪辑标准后开始剪辑，完成后会生成外部交接文件";
        return null;
      }
      if (actionId === "confirm_voice_profile") {
        switchPanel("settings");
        status.textContent = "请在设置页试听并确认 voice_profile_ref";
        return null;
      }
      status.textContent = endpoint ? `建议调用 ${endpoint}` : "请先补齐建议动作需要的输入";
      return null;
    }

    async function runOrchestrationAction(actionId, endpoint, button = null) {
      return runDirectorAction(actionId, endpoint, button);
    }

    function renderRuntime(payload) {
      const media = payload.media_tools || {};
      const ffmpeg = media.ffmpeg || {};
      const ffprobe = media.ffprobe || {};
      $("runtimeChips").innerHTML = [
        `<span class="chip ${payload.available ? "ok" : "warn"}">剪辑运行时 ${payload.available ? "可用" : "异常"}</span>`,
        `<span class="chip ${ffmpeg.available ? "ok" : "warn"}">FFmpeg ${ffmpeg.available ? "可用" : "未找到"}</span>`,
        `<span class="chip ${ffprobe.available ? "ok" : "warn"}">FFprobe ${ffprobe.available ? "可用" : "未找到"}</span>`
      ].join("");
      resultCards.innerHTML = `
        <div class="summary-item"><strong>运行时状态</strong><span class="path-text">${escapeHtml(payload.bundled_runtime_dir || "")}</span></div>
        <div class="summary-item"><strong>FFmpeg</strong><span class="path-text">${escapeHtml(ffmpeg.path || "未找到")}</span></div>
        <div class="summary-item"><strong>FFprobe</strong><span class="path-text">${escapeHtml(ffprobe.path || "未找到")}</span></div>
      `;
    }

    async function checkRuntime(button = null) {
      return withButtonState(button, "检查中", async () => {
        status.textContent = "检查运行时";
        const payload = await requestJson("/api/check", null, {silent: true});
        renderRuntime(payload);
        status.textContent = payload && payload.media_tools && payload.media_tools.ready ? "运行时可用" : "运行时需配置";
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        return payload;
      });
    }

    function normalizeFieldValue(id, value) {
      if (id === "subtitleMode") return normalizeSubtitleMode(value);
      if (id === "protocolDropboxRequeueQueue") return normalizeDropboxQueueId(value);
      return value;
    }

    function setValue(id, value) {
      if (value !== undefined && value !== null) $(id).value = normalizeFieldValue(id, value);
    }

    function fieldValue(id) {
      const el = $(id);
      if (!el) return null;
      return el.type === "checkbox" ? el.checked : el.value;
    }

    function setFieldValue(id, value) {
      const el = $(id);
      if (!el || value === undefined || value === null) return;
      if (el.type === "checkbox") {
        el.checked = Boolean(value);
      } else {
        el.value = String(normalizeFieldValue(id, value));
      }
    }

    function saveLocalDraft() {
      if (!draftReady) return;
      const fields = {};
      LOCAL_DRAFT_FIELD_IDS.forEach((id) => {
        fields[id] = fieldValue(id);
      });
      const payload = {
        schema: LOCAL_DRAFT_KEY,
        saved_at: Date.now(),
        fields,
        input_videos: normalizeInputVideos()
      };
      localStorage.setItem(LOCAL_DRAFT_KEY, JSON.stringify(payload));
    }

    function restoreLocalDraft() {
      let payload = null;
      try {
        payload = JSON.parse(localStorage.getItem(LOCAL_DRAFT_KEY) || "null");
      } catch {
        payload = null;
      }
      if (!payload || payload.schema !== LOCAL_DRAFT_KEY || !payload.fields) {
        draftReady = true;
        return;
      }
      LOCAL_DRAFT_FIELD_IDS.forEach((id) => {
        const aliases = LEGACY_DRAFT_FIELD_ALIASES[id] || [];
        const value = payload.fields[id] ?? aliases.map((alias) => payload.fields[alias]).find((item) => item !== undefined);
        setFieldValue(id, value);
      });
      inputVideos = Array.isArray(payload.input_videos) ? payload.input_videos.filter(Boolean) : [];
      renderInputVideos();
      updateBgmControls();
      updateSubtitleControls();
      updateVoiceControls();
      previewPromptAudio();
      draftReady = true;
      status.textContent = "已恢复本地草稿";
      refreshGuidedFeedbacks();
    }

    async function loadPackages(button = null) {
      return withButtonState(button, "刷新中", async () => {
        const payload = await requestJson("/api/style-packages", null, {silent: true});
        packages = payload.packages || [];
        const select = $("stylePackageSelect");
        select.innerHTML = packages.length
          ? packages.map((pkg, index) => `<option value="${index}">${escapeHtml(pkg.name)} - ${escapeHtml(pkg.reference_label || "参考视频")}</option>`).join("")
          : `<option value="">还没有风格包</option>`;
        if (packages.length && !$("stylePackage").value) {
          select.value = "0";
          selectPackageFromList();
        }
        renderPackageList();
        refreshGuidedFeedbacks();
        await loadAllPacks(null);
        return packages;
      });
    }

    async function loadAllPacks(button = null) {
      return withButtonState(button, "刷新中", async () => {
        const payload = await requestJson("/api/packs", null, {silent: true});
        allPacks = payload;
        renderAllPackIndex(payload);
        return payload;
      });
    }

    async function loadProjectLibrary(button = null) {
      return withButtonState(button, "刷新中", async () => {
        const params = new URLSearchParams({
          query: $("projectSearch")?.value || "",
          limit: "60"
        });
        const payload = await requestJson(`/api/projects?${params.toString()}`, null, {silent: true});
        projectLibrary = payload.projects || [];
        renderProjectLibrary(payload);
        return payload;
      });
    }

    function loadProjectLibraryDebounced() {
      clearTimeout(projectLibrarySearchTimer);
      projectLibrarySearchTimer = setTimeout(() => loadProjectLibrary(null), 250);
    }

    async function rebuildProjectLibrary(button = null) {
      return withButtonState(button, "重建中", async () => {
        const payload = await requestJson("/api/projects/rebuild", {
          output_root: $("outputScanDir")?.value || "",
          limit: 500
        }, {silent: true});
        projectLibrary = payload.projects || [];
        renderProjectLibrary({projects: projectLibrary, project_count: projectLibrary.length, db_path: payload.db_path});
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = `项目库已重建：${payload.indexed_count || 0} 个项目`;
        return payload;
      });
    }

    function renderProjectLibrary(payload) {
      const box = $("projectLibraryList");
      if (!box) return;
      const projects = payload.projects || [];
      if (!projects.length) {
        renderProjectLibraryEmpty();
        return;
      }
      box.innerHTML = projects.map((project, index) => `
        <div class="summary-item">
          <strong>${escapeHtml(project.style_package_name || project.project_id || "本地项目")}</strong>
          <span class="path-text">${escapeHtml(project.output_dir || "")}</span>
          <div class="chip-row">
            <span class="chip ${project.ok ? "ok" : "warn"}">${project.ok ? "完成" : "未完成"}</span>
            <span class="chip">v${escapeHtml(project.current_version || 0)} / ${escapeHtml(project.version_count || 0)}</span>
            <span class="chip">${escapeHtml(project.input_video_count || 0)} 个素材</span>
            <span class="chip">${project.execute_real_render ? "真实渲染" : "计划模式"}</span>
          </div>
          <span class="hint">${escapeHtml(project.user_request || "未记录剪辑目标")}</span>
          <span class="mini">常用：先查看项目，再决定是否继续修改。</span>
          <div class="actions">
            <button onclick="openProjectFromLibrary(${index})">查看项目</button>
            <button class="neutral" onclick="useProjectFromLibrary(${index})">继续修改</button>
            ${project.copied_output_video ? `<button class="neutral" onclick="playReviewVideo('${escapeJs(project.copied_output_video)}')">直接播放成片</button>` : ""}
          </div>
        </div>
      `).join("");
    }

    function openProjectFromLibrary(index) {
      const project = projectLibrary[index];
      if (!project) return;
      activeProjectOutputDir = project.output_dir || "";
      activeProjectManifest = project.project_manifest || null;
      $("currentResult").innerHTML = `
        <div class="summary-item"><strong>${escapeHtml(project.style_package_name || project.project_id || "本地项目")}</strong><span class="path-text">${escapeHtml(project.output_dir || "")}</span><span class="hint">建议先播放成片确认结果，再决定是否继续修改这版。</span>${reviewActionButtons({videoPath: project.copied_output_video || "", outputDir: project.output_dir || "", editLabel: "回到剪辑页继续调整"})}</div>
        <div class="summary-item"><strong>成片文件</strong><span class="path-text">${escapeHtml(project.copied_output_video || "无")}</span></div>
        <div class="summary-item"><strong>版本中心</strong><span>当前 v${escapeHtml(project.current_version || 0)}，共 ${escapeHtml(project.version_count || 0)} 个版本</span></div>
        <div class="summary-item"><strong>项目清单</strong><span class="path-text">${escapeHtml(project.project_manifest_path || "")}</span></div>
      `;
      if (project.copied_output_video) playReviewVideo(project.copied_output_video);
      if (project.output_dir) loadProjectVersionCenter(project.output_dir, null);
      switchPanel("review");
      status.textContent = "已打开项目库项目";
    }

    function useProjectFromLibrary(index) {
      const project = projectLibrary[index];
      if (!project) return;
      const manifest = project.project_manifest || {};
      const latestResult = manifest.latest_result || {};
      const style = manifest.style_package || {};
      if (style.path) setValue("stylePackage", style.path);
      inputVideos = Array.isArray(manifest.input_videos) ? manifest.input_videos.filter(Boolean) : [];
      if (inputVideos.length) setValue("inputVideo", inputVideos[0]);
      renderInputVideos();
      setValue("outputDir", project.output_dir ? `${project.output_dir}_recut` : "");
      if (project.user_request || latestResult.user_request) setValue("userRequest", project.user_request || latestResult.user_request);
      if (latestResult.confirmed_brief) setValue("briefText", latestResult.confirmed_brief);
      activeProjectOutputDir = project.output_dir || "";
      activeProjectManifest = manifest;
      markBriefStale();
      refreshGuidedFeedbacks();
      switchPanel("cut");
      status.textContent = "项目已载入剪辑页，可填写返修要求后复剪";
    }

    async function scanInputFolder(button = null) {
      return scanFolder({
        button,
        folderId: "inputScanDir",
        scanType: "input",
        targetId: "inputFolderScanResult"
      });
    }

    async function scanOutputFolder(button = null) {
      return scanFolder({
        button,
        folderId: "outputScanDir",
        scanType: "output",
        targetId: "outputFolderScanResult"
      });
    }

    async function scanFolder({button = null, folderId, scanType, targetId}) {
      const folder = $(folderId).value.trim();
      if (!folder) {
        status.textContent = "请先选择要扫描的文件夹";
        return null;
      }
      return withButtonState(button, "扫描中", async () => {
        const payload = await requestJson("/api/folders/scan", {
          folder,
          scan_type: scanType,
          recursive: true,
          limit: 120
        }, {silent: true});
        renderFolderScan(payload, targetId, scanType);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? `扫描完成：${payload.item_count || 0} 个项目` : "文件夹扫描失败";
        return payload;
      });
    }

    function renderFolderScan(payload, targetId, scanType) {
      const box = $(targetId);
      const items = payload.items || [];
      const counts = payload.category_counts || {};
      if (!payload.ok) {
        box.innerHTML = `<div class="summary-item"><span class="chip warn">${escapeHtml(payload.reason || "scan_failed")}</span><span class="path-text">${escapeHtml(payload.folder || "")}</span></div>`;
        return;
      }
      const summary = `<div class="summary-item"><strong>扫描完成</strong><div class="chip-row"><span class="chip">视频 ${escapeHtml(counts.video || 0)}</span><span class="chip">音频 ${escapeHtml(counts.audio || 0)}</span><span class="chip">图片 ${escapeHtml(counts.image || 0)}</span><span class="chip">项目 ${escapeHtml(payload.project_count || 0)}</span></div></div>`;
      const cards = items.slice(0, 24).map((item) => {
        const canUseVideo = scanType === "input" && item.category === "video";
        const canPreview = item.previewable;
        const isOutputVideo = scanType === "output" && item.category === "video";
        const primaryButton = canUseVideo
          ? `<button onclick="useScannedVideo('${escapeJs(item.path || "")}')">加入剪辑素材</button>`
          : isOutputVideo
            ? `<button onclick="previewStudioMedia('${escapeJs(item.path || "")}')">预览成片</button>`
            : canPreview
              ? `<button onclick="previewStudioMedia('${escapeJs(item.path || "")}')">预览素材</button>`
              : "";
        const secondaryButton = canUseVideo && canPreview
          ? `<button class="neutral" onclick="previewStudioMedia('${escapeJs(item.path || "")}')">先预览素材</button>`
          : "";
        const actionHint = canUseVideo
          ? "如果这条素材准备拿来剪，直接加入素材列表最快。"
          : isOutputVideo
            ? "常用：先预览成片，再决定是否回到项目继续修改。"
            : canPreview
              ? "这条素材支持直接预览。"
              : "这条文件当前不支持直接预览。";
        return `
          <div class="summary-item">
            <strong>${escapeHtml(item.name || "文件")}</strong>
            <span class="path-text">${escapeHtml(item.path || "")}</span>
            <div class="chip-row">
              <span class="chip">${escapeHtml(item.category || "")}</span>
              <span class="chip">${escapeHtml(formatBytes(item.size_bytes || 0))}</span>
            </div>
            <span class="mini">${escapeHtml(actionHint)}</span>
            <div class="actions">
              ${primaryButton}
              ${secondaryButton}
            </div>
          </div>
        `;
      }).join("");
      box.innerHTML = summary + (cards || `<div class="summary-item"><span class="hint">没有找到可用媒体文件。</span></div>`);
    }

    function useScannedVideo(path) {
      addInputVideo(path);
      switchPanel("cut");
      status.textContent = "已加入输入素材列表";
    }

    function previewStudioMedia(path) {
      const text = String(path || "");
      const lower = text.toLowerCase();
      const videoExt = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"];
      const audioExt = [".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"];
      const imageExt = [".jpg", ".jpeg", ".png", ".webp", ".bmp"];
      const url = `/api/media-preview?path=${encodeURIComponent(text)}`;
      clearAudioElement($("studioAudioPreview"));
      clearAudioElement($("studioVideoPreview"));
      $("studioImagePreview").style.display = "none";
      $("studioImagePreview").removeAttribute("src");
      if (videoExt.some((ext) => lower.endsWith(ext))) {
        $("studioVideoPreview").src = url;
        $("studioVideoPreview").style.display = "block";
      } else if (audioExt.some((ext) => lower.endsWith(ext))) {
        $("studioAudioPreview").src = url;
        $("studioAudioPreview").style.display = "block";
      } else if (imageExt.some((ext) => lower.endsWith(ext))) {
        $("studioImagePreview").src = url;
        $("studioImagePreview").style.display = "block";
      }
      $("studioPreviewInfo").textContent = text;
      switchPanel("library");
    }

    function formatBytes(value) {
      const size = Number(value) || 0;
      if (size < 1024) return `${size} B`;
      if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
      if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
      return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
    }

    async function loadDeploymentGuide(button = null) {
      return withButtonState(button, "检查中", async () => {
        const payload = await requestJson("/api/deployment/guide", null, {silent: true});
        renderDeploymentGuide(payload);
        return payload;
      });
    }

    function renderDeploymentGuide(payload) {
      const box = $("deploymentGuide");
      if (!box || !payload) return;
      const ffmpeg = payload.ffmpeg || {};
      const shell = payload.desktop_shell || {};
      const electron = shell.electron || {};
      const pack = payload.customer_package || {};
      box.innerHTML = `
        <div class="summary-item">
          <strong>FFmpeg 自动检测</strong>
          <span class="chip ${ffmpeg.ready ? "ok" : "warn"}">${ffmpeg.ready ? "可用" : "需安装"}</span>
          <span class="path-text">${escapeHtml(ffmpeg.ffmpeg_path || ffmpeg.install_hint || "")}</span>
        </div>
        <div class="summary-item">
          <strong>客户安装包脚本</strong>
          <span class="chip ok">${escapeHtml(pack.status || "unknown")}</span>
          <span class="path-text">${escapeHtml(pack.script || "")}</span>
        </div>
        <div class="summary-item">
          <strong>Tauri/Electron 桌面壳</strong>
          <span class="chip ${electron.ready ? "ok" : "warn"}">${escapeHtml(shell.status || "planned")}</span>
          <span class="hint">${escapeHtml(shell.recommended_path || "")}</span>
          <span class="path-text">${escapeHtml(electron.package_command || electron.reason || "")}</span>
        </div>
      `;
    }

    function renderAllPackIndex(payload) {
      const box = $("allPackIndex");
      if (!box) return;
      if (!payload) {
        box.innerHTML = `<div class="summary-item"><span class="hint">统一包索引尚未加载。</span></div>`;
        return;
      }
      const groups = [
        ["项目包", "project_packs"],
        ["风格包 v1", "style_packs"],
        ["素材包", "material_packs"],
        ["旧版风格包", "legacy_style_packages"]
      ];
      const cards = groups.flatMap(([label, key]) => {
        const items = Array.isArray(payload[key]) ? payload[key] : [];
        if (!items.length) {
          return [`<div class="summary-item"><strong>${escapeHtml(label)}</strong><span class="hint">暂无</span></div>`];
        }
        return items.map((item) => renderPackIndexCard(label, key, item));
      });
      box.innerHTML = cards.join("");
    }

    function renderPackIndexCard(label, key, item) {
      const validation = item.validation || {};
      const warningCount = (validation.warnings || []).length;
      const errorCount = (validation.errors || []).length;
      const tone = errorCount ? "warn" : warningCount ? "warn" : "ok";
      const validationText = errorCount
        ? `${errorCount} 个错误`
        : warningCount ? `${warningCount} 个提示` : "引用正常";
      const canUseAsStyle = key === "style_packs" || key === "legacy_style_packages";
      const canUseAsProject = key === "project_packs";
      return `
        <div class="summary-item">
          <strong>${escapeHtml(item.name || label)}</strong>
          <span class="path-text">${escapeHtml(item.path || "")}</span>
          <div class="chip-row">
            <span class="chip">${escapeHtml(label)}</span>
            <span class="chip ${tone}">${escapeHtml(validationText)}</span>
            <span class="chip">${escapeHtml(shortSchema(item.schema || ""))}</span>
          </div>
          ${packValidationMessages(validation)}
          <div class="actions">
            <button class="neutral" onclick="validatePackFromIndex('${escapeJs(item.path || item.json_path || "")}', this)">校验</button>
            ${canUseAsStyle ? `<button class="secondary" onclick="useStylePackPath('${escapeJs(item.path || "")}')">用于剪辑</button>` : ""}
            ${canUseAsProject ? `<button class="secondary" onclick="loadProjectPackFromIndex('${escapeJs(item.path || "")}', this)">载入项目包</button>` : ""}
          </div>
        </div>
      `;
    }

    function packValidationMessages(validation) {
      const messages = [...(validation.errors || []), ...(validation.warnings || [])];
      if (!messages.length) return "";
      return `<div class="notice">${messages.slice(0, 4).map((item) =>
        `${escapeHtml(item.message || item.code || "引用提示")}${item.path ? `：${escapeHtml(shortPath(item.path))}` : ""}`
      ).join("<br>")}</div>`;
    }

    function shortSchema(schema) {
      return String(schema || "").replace("smart_video_cut.local.", "");
    }

    async function validatePackFromIndex(path, button = null) {
      if (!path) return null;
      return withButtonState(button, "校验中", async () => {
        const loaded = await requestJson(`/api/packs/load?path=${encodeURIComponent(path)}`, null, {silent: true});
        if (!loaded?.pack) {
          resultDetails.textContent = JSON.stringify(loaded, null, 2);
          status.textContent = "包载入失败";
          return loaded;
        }
        const payload = await requestJson("/api/packs/validate", {pack: loaded.pack}, {silent: true});
        resultDetails.textContent = JSON.stringify({loaded, validation: payload}, null, 2);
        status.textContent = (payload.validation?.warnings || []).length ? "包校验有提示" : "包校验通过";
        await loadAllPacks(null);
        return payload;
      });
    }

    function useStylePackPath(path) {
      if (!path) return;
      setValue("stylePackage", path);
      switchPanel("cut");
      markBriefStale();
      refreshGuidedFeedbacks();
      status.textContent = "已选择风格包用于剪辑";
    }

    async function loadProjectPackFromIndex(path, button = null) {
      if (!path) return null;
      setValue("projectPackPath", path);
      const payload = await loadProjectPack(button);
      switchPanel("package");
      return payload;
    }

    function selectPackageFromList() {
      const index = Number($("stylePackageSelect").value);
      const pkg = packages[index];
      if (!pkg) return;
      $("stylePackage").value = pkg.path || "";
      applyPackageDefaults(pkg);
      markBriefStale();
      refreshGuidedFeedbacks();
    }

    function applyPackageDefaults(pkg) {
      const video = pkg.video || {};
      const subtitle = pkg.subtitle || {};
      const audio = pkg.audio || {};
      const voice = pkg.voice || {};
      setValue("duration", video.target_duration_seconds);
      setValue("aspect", video.aspect_ratio);
      setValue("resolution", video.resolution);
      setValue("quality", video.quality);
      setValue("subtitleMode", subtitle.enabled === false ? "none" : normalizeSubtitleMode(subtitle.mode || "auto"));
      setValue("subtitleLocation", subtitle.location_info || "");
      setValue("subtitlePrompt", subtitle.custom_prompt || "");
      setValue("subtitleSize", subtitle.font_size);
      setValue("subtitleColor", subtitle.font_color);
      setValue("outlineColor", subtitle.outline_color);
      setValue("outlineWidth", subtitle.outline_width);
      setValue("bgmStyle", audio.bgm_style);
      setValue("bgmAudioPath", audio.bgm_audio_path || "");
      setValue("bgmLibraryDir", audio.bgm_library_dir || "");
      setValue("bgmLibraryQuery", audio.bgm_library_query || "");
      setValue("bgmStart", audio.bgm_start_seconds || 0);
      setValue("bgmVolume", audio.bgm_volume_db);
      setValue("voiceVolume", audio.voice_volume_db);
      setValue("voiceProvider", voice.provider);
      setValue("systemVoice", voice.system_voice || voice.voice_name || "");
      setValue("systemRate", voice.system_rate ?? 0);
      setValue("systemVolume", voice.system_volume ?? 100);
      setValue("fixtureDuration", voice.fixture_duration_seconds ?? 1);
      setValue("fixtureSampleRate", voice.fixture_sample_rate ?? 16000);
      setValue("mossVoice", voice.moss_voice);
      setValue("mossProfile", voice.moss_profile);
      $("removeOriginalVoice").checked = audio.remove_original_voice !== false;
      $("originalAudioMode").value = audio.remove_original_voice === false ? "keep" : "remove";
      updateBgmControls();
      updateSubtitleControls();
      updateVoiceControls();
      refreshGuidedFeedbacks();
    }

    function renderPackageList() {
      const box = $("packageList");
      if (!packages.length) {
        renderPackageListEmpty();
        return;
      }
      box.innerHTML = packages.map((pkg, index) => `
        <div class="list-item">
          <strong>${escapeHtml(pkg.name)}</strong>
          <div class="path-text">${escapeHtml(pkg.path)}</div>
          <div class="chip-row">
            <span class="chip">${escapeHtml(pkg.video?.target_duration_seconds || 20)} 秒</span>
            <span class="chip">${escapeHtml(pkg.video?.aspect_ratio || "9:16")}</span>
            <span class="chip">${escapeHtml(pkg.video?.resolution || "720x1280")}</span>
          </div>
          <button class="secondary" onclick="usePackage(${index})">用于剪辑</button>
        </div>
      `).join("");
    }

    function usePackage(index) {
      $("stylePackageSelect").value = String(index);
      selectPackageFromList();
      refreshGuidedFeedbacks();
      switchPanel("cut");
    }

    async function loadLocalConfig() {
      const payload = await requestJson("/api/local-config", null, {silent: true});
      localConfigSummary = payload || null;
      updateLocalPathPlaceholders();
      if (payload.llm) {
        setValue("llmProvider", payload.llm.provider);
        setValue("llmBaseUrl", payload.llm.base_url);
        setValue("llmModel", payload.llm.model);
        setValue("llmProfile", payload.llm.recommendation_profile);
        setValue("llmCapability", payload.llm.model_capability);
        setValue("llmTimeout", payload.llm.timeout_seconds);
        setValue("llmTemperature", payload.llm.temperature);
        $("allowCloudText").checked = payload.llm.allow_cloud_llm_for_text_only !== false;
        $("allowMediaUpload").checked = payload.llm.allow_media_upload_to_llm === true;
        $("llmApiKey").placeholder = payload.llm.api_key_set ? "已保存，留空则继续使用" : "请输入 API Key";
      }
      if (payload.voice_model) {
        setValue("voiceModelName", payload.voice_model.display_name);
        setValue("voiceModelRepo", payload.voice_model.repo_url);
        setValue("voiceModelDir", payload.voice_model.install_dir);
        $("voiceModelEnabled").checked = payload.voice_model.enabled !== false;
      }
      renderFirstRunGuide();
      renderOutputDirHelper();
    }

    async function loadMemory(button = null) {
      return withButtonState(button, "刷新中", async () => {
        const payload = await requestJson("/api/memory", null, {silent: true});
        const preview = payload.context_preview || "还没有启用的本地记忆。";
        $("memoryPreview").textContent = [
          `记忆条数：${payload.entry_count || 0}`,
          `启用条数：${payload.enabled_count || 0}`,
          "",
          preview
        ].join("\n");
        return payload;
      });
    }

    function collectSettingsOverrides() {
      const subtitleMode = normalizeSubtitleMode($("subtitleMode").value);
      const voiceProvider = $("voiceProvider").value;
      const voiceMode = voiceProvider === "none" ? "none" : $("voiceoverText").value.trim() ? "provided_text" : "generated_male_ad_copy";
      const mossParams = mossGenerationParams();
      return {
        video: {
          target_duration_seconds: Number($("duration").value),
          aspect_ratio: $("aspect").value,
          resolution: $("resolution").value,
          quality: $("quality").value
        },
        subtitle: {
          enabled: subtitleMode !== "none",
          mode: subtitleMode,
          custom_prompt: $("subtitlePrompt").value,
          location_info: $("subtitleLocation").value,
          font_size: Number($("subtitleSize").value),
          font_color: $("subtitleColor").value,
          outline_color: $("outlineColor").value,
          outline_width: Number($("outlineWidth").value)
        },
        material_analysis: {
          enable_visual_analysis: $("materialVisualAnalysis").value !== "false",
          visual_quality_preset: $("materialVisualPreset").value,
          frame_sample_count: Number($("materialFrameSampleCount").value),
          thumbnail_max_side: Number($("materialThumbnailMaxSide").value),
          role_confidence_threshold: Number($("materialRoleThreshold").value),
          calibration_sample_set: $("materialSampleSet").value
        },
        audio: {
          bgm_style: $("bgmStyle").value,
          bgm_audio_path: $("bgmStyle").value === "local_audio" ? $("bgmAudioPath").value : "",
          bgm_library_dir: $("bgmStyle").value === "library" ? $("bgmLibraryDir").value : "",
          bgm_library_query: $("bgmLibraryQuery").value,
          bgm_start_seconds: Number($("bgmStart").value),
          bgm_volume_db: Number($("bgmVolume").value),
          voice_volume_db: Number($("voiceVolume").value),
          remove_original_voice: $("removeOriginalVoice").checked && $("originalAudioMode").value !== "keep"
        },
        voice: {
          provider: voiceProvider,
          mode: voiceMode,
          gender: "male",
          prompt_audio_path: $("mossPromptAudioPath").value,
          moss_voice: $("mossVoice").value,
          moss_profile: $("mossProfile").value,
          sample_mode: mossParams.sample_mode,
          text_temperature: mossParams.text_temperature,
          audio_temperature: mossParams.audio_temperature,
          seed: mossParams.seed,
          voice_profile_ref: latestVoiceProfileRef,
          require_saved_profile: Boolean(latestVoiceProfileRef),
          system_voice: $("systemVoice").value,
          system_rate: Number($("systemRate").value),
          system_volume: Number($("systemVolume").value),
          fixture_duration_seconds: Number($("fixtureDuration").value),
          fixture_sample_rate: Number($("fixtureSampleRate").value)
        }
      };
    }

    function addInputVideoFromField() {
      addInputVideo($("inputVideo").value);
    }

    function addInputVideo(path) {
      const selected = String(path || "").trim();
      if (!selected) return;
      if (!inputVideos.includes(selected)) inputVideos.push(selected);
      if (!$("inputVideo").value) $("inputVideo").value = selected;
      renderInputVideos();
      markBriefStale();
    }

    function removeInputVideo(index) {
      inputVideos.splice(index, 1);
      $("inputVideo").value = inputVideos[0] || $("inputVideo").value;
      renderInputVideos();
      markBriefStale();
    }

    function clearInputVideos() {
      inputVideos = [];
      renderInputVideos();
      markBriefStale();
    }

    function normalizeInputVideos() {
      const values = inputVideos
        .map((item) => String(item || "").trim())
        .filter(Boolean);
      const current = String($("inputVideo").value || "").trim();
      if (current) values.push(current);
      return [...new Set(values)];
    }

    function renderInputVideos() {
      const values = normalizeInputVideos();
      inputVideos = values;
      const box = $("inputVideosList");
      if (!values.length) {
        box.innerHTML = `<div class="summary-item"><span class="hint">可添加多个原视频素材，生成剪辑标准时会先规划素材分工。</span></div>`;
        refreshGuidedFeedbacks();
        return;
      }
      box.innerHTML = values.map((path, index) => `
        <div class="material-item">
          <span class="path-text">${index + 1}. ${escapeHtml(path)}</span>
          <button class="neutral" onclick="removeInputVideo(${index})">移除</button>
        </div>
      `).join("");
      refreshGuidedFeedbacks();
    }

    function collectEditPayload() {
      const selectedVideos = normalizeInputVideos();
      const confirmedBrief = String($("briefText").value || "").trim();
      const existingTaskId = latestResult?.task_id || activeProjectManifest?.latest_result?.task_id || null;
      const payload = {
        style_package: $("stylePackage").value,
        input_video: selectedVideos[0] || "",
        input_videos: selectedVideos,
        output_dir: $("outputDir").value,
        user_request: $("userRequest").value,
        project_id: "local_project",
        voiceover_text: $("voiceProvider").value === "none" ? null : $("voiceoverText").value || null,
        use_memory: $("useMemory").checked,
        execute_real_render: $("executeReal").checked,
        allow_edge_tts: $("allowEdge").checked,
        settings_overrides: collectSettingsOverrides(),
        confirmed_brief: confirmedBrief || null,
        task_id: existingTaskId
      };
      if (timelineOverride) payload.timeline_override = timelineOverride;
      return payload;
    }

    function markBriefStale() {
      briefReady = false;
      $("startCutButton").disabled = true;
      markTimelineStale();
      saveLocalDraft();
      refreshGuidedFeedbacks();
    }

    function markTimelineStale() {
      if (!timelineBase && !timelineOverride) return;
      timelineBase = null;
      timelineOverride = null;
      const button = $("applyTimelineButton");
      if (button) button.disabled = true;
      renderTimelineState("warn", "时间线需重新生成");
      const track = $("timelineTrack");
      if (track) {
        track.innerHTML = `<div class="timeline-empty"><span class="hint">素材、风格包或参数已变化，请重新生成时间线预览。</span></div>`;
      }
    }

    function renderTimelineState(tone, text, extra = []) {
      const box = $("timelineStatus");
      if (!box) return;
      const chipClass = tone === "warn" ? "warn" : tone === "ok" ? "ok" : "";
      box.innerHTML = [
        `<span class="chip ${chipClass}">${escapeHtml(text)}</span>`,
        ...extra.map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
      ].join("");
    }

    async function generateTimelinePreview(button = null) {
      return withButtonState(button, "生成中", async () => {
        status.textContent = "生成时间线预览";
        const payload = await requestJson("/api/timeline", collectEditPayload(), {silent: true});
        if (!payload || !payload.timeline) {
          renderTimelineState("warn", payload?.error || "时间线生成失败");
          resultDetails.textContent = JSON.stringify(payload, null, 2);
          return payload;
        }
        timelineBase = payload.timeline;
        timelineOverride = null;
        renderTimeline(payload.timeline, payload.validation_errors || []);
        $("applyTimelineButton").disabled = false;
        renderPayload(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "时间线预览已生成" : "时间线需要调整";
        return payload;
      });
    }

    function renderTimeline(timeline, validationErrors = []) {
      const segments = Array.isArray(timeline?.segments) ? timeline.segments : [];
      const total = segments.reduce((sum, segment) => sum + Number(segment.duration_seconds || 0), 0);
      const target = Number(timeline?.target_duration_seconds || 0);
      const stateTone = validationErrors.length ? "warn" : "ok";
      renderTimelineState(
        stateTone,
        validationErrors.length ? "时间线需调整" : timelineOverride ? "已应用编辑时间线" : "预览就绪",
        [`${segments.length} 个片段`, `总时长 ${total.toFixed(1)} 秒`, target ? `目标 ${target} 秒` : ""].filter(Boolean)
      );
      const track = $("timelineTrack");
      if (!segments.length) {
        track.innerHTML = `<div class="timeline-empty"><span class="hint">当前时间线没有片段。</span></div>`;
        return;
      }
      const warningHtml = validationErrors.length
        ? `<div class="summary-item"><strong>校验提示</strong><span class="path-text">${escapeHtml(validationErrors.join("\n"))}</span></div>`
        : "";
      track.innerHTML = warningHtml + segments.map((segment, index) => `
        <div class="timeline-segment" draggable="true"
          data-segment-id="${escapeHtml(segment.segment_id)}"
          data-original-position="${index}"
          data-source-file="${escapeHtml(segment.source_file || "")}"
          data-thumbnail-path="${escapeHtml(segment.thumbnail_path || "")}"
          ondragstart="startTimelineDrag(event)"
          ondragover="handleTimelineDragOver(event)"
          ondrop="dropTimelineSegment(event)"
          ondragend="endTimelineDrag(event)">
          <div class="timeline-ruler">
            <button type="button" class="timeline-drag-handle" title="拖拽排序">拖拽</button>
            <div class="timeline-index">#${index + 1}<br>${escapeHtml(Number(segment.timeline_start_seconds || 0).toFixed(1))}s</div>
          </div>
          ${timelinePreviewHtml(segment)}
          <div>
            <strong>${escapeHtml(segment.shot_intent || segment.segment_id)}</strong>
            <div class="path-text">${escapeHtml(segment.source_file || "未绑定素材")}</div>
            <div class="chip-row">
              <span class="chip">${escapeHtml(segment.segment_id)}</span>
              ${segment.locked ? `<span class="chip warn">锁定</span>` : ""}
            </div>
            <label>片段说明<textarea data-field="caption" oninput="markTimelineDirty('有未应用说明修改')">${escapeHtml(segment.caption || "")}</textarea></label>
          </div>
          <div>
            <label>时长(秒)<input data-field="duration" type="number" min="0.3" step="0.1" value="${escapeHtml(segment.duration_seconds || 1)}" oninput="markTimelineDirty('有未应用时长修改')"></label>
            <label>镜头意图<input data-field="shotIntent" value="${escapeHtml(segment.shot_intent || "")}" disabled></label>
            <label>替换素材<select data-field="sourceIndex" onchange="markTimelineDirty('有未应用素材替换')">${timelineSourceOptions(segment.source_material_index)}</select></label>
          </div>
          <div class="actions">
            <button class="neutral" onclick="moveTimelineSegment(this, -1)">上移</button>
            <button class="neutral" onclick="moveTimelineSegment(this, 1)">下移</button>
            <button class="danger" onclick="toggleTimelineDelete(this)">删除</button>
          </div>
        </div>
      `).join("");
    }

    function mediaPreviewUrl(path) {
      return `/api/media-preview?path=${encodeURIComponent(path || "")}`;
    }

    function timelinePreviewHtml(segment) {
      const thumbnail = String(segment.thumbnail_path || "").trim();
      const source = String(segment.source_file || "").trim();
      const media = thumbnail || source;
      const visual = thumbnail
        ? `<img class="timeline-thumb" src="${escapeHtml(mediaPreviewUrl(thumbnail))}" alt="片段缩略图">`
        : `<div class="timeline-thumb-placeholder">暂无缩略图</div>`;
      const previewButton = source
        ? `<button type="button" class="neutral" onclick="previewTimelineSource(this)">预览素材</button>`
        : `<span class="mini">未绑定素材</span>`;
      return `
        <div class="timeline-preview">
          ${visual}
          <span class="mini">${escapeHtml(media ? shortPath(media) : "无预览素材")}</span>
          ${previewButton}
        </div>
      `;
    }

    function timelineSourceOptions(currentIndex) {
      const videos = normalizeInputVideos();
      if (!videos.length) return `<option value="">未绑定素材</option>`;
      return videos.map((path, index) => {
        const selected = Number(currentIndex) === index ? " selected" : "";
        const thumbnail = timelineThumbnailForSource(index);
        return `<option value="${index}" data-thumbnail="${escapeHtml(thumbnail)}"${selected}>${index + 1}. ${escapeHtml(shortPath(path))}</option>`;
      }).join("");
    }

    function timelineThumbnailForSource(sourceIndex) {
      const segments = timelineBase?.segments || timelineOverride?.segments || [];
      const match = segments.find((segment) =>
        Number(segment.source_material_index) === Number(sourceIndex) && String(segment.thumbnail_path || "").trim()
      );
      return match ? String(match.thumbnail_path || "") : "";
    }

    function markTimelineDirty(message = "时间线有未应用编辑") {
      if (!timelineBase) return;
      const button = $("applyTimelineButton");
      if (button) button.disabled = false;
      renderTimelineState("warn", message, ["点击应用后保存版本"]);
    }

    function previewTimelineSource(button) {
      const card = button.closest(".timeline-segment");
      if (!card) return;
      const selected = card.querySelector('[data-field="sourceIndex"]')?.value;
      const videos = normalizeInputVideos();
      const source = selected !== undefined && selected !== "" ? videos[Number(selected)] : card.dataset.sourceFile;
      if (!source) {
        status.textContent = "当前片段没有可预览素材";
        return;
      }
      const preview = $("timelineSourcePreview");
      preview.src = mediaPreviewUrl(source);
      preview.style.display = "block";
      preview.scrollIntoView({block: "nearest"});
      status.textContent = "已载入片段素材预览";
    }

    function startTimelineDrag(event) {
      const card = event.target.closest(".timeline-segment");
      if (!card || card.dataset.deleted === "true") return;
      timelineDraggedSegmentId = card.dataset.segmentId || "";
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", timelineDraggedSegmentId);
    }

    function handleTimelineDragOver(event) {
      const card = event.target.closest(".timeline-segment");
      const track = $("timelineTrack");
      if (!card || !track || !timelineDraggedSegmentId) return;
      event.preventDefault();
      const dragged = [...track.querySelectorAll(".timeline-segment")]
        .find((item) => item.dataset.segmentId === timelineDraggedSegmentId);
      if (!dragged || dragged === card) return;
      const rect = card.getBoundingClientRect();
      const insertAfter = event.clientY > rect.top + rect.height / 2;
      track.insertBefore(dragged, insertAfter ? card.nextSibling : card);
      renumberTimelineCards();
      markTimelineDirty("有未应用拖拽排序");
    }

    function dropTimelineSegment(event) {
      event.preventDefault();
      endTimelineDrag(event);
      renumberTimelineCards();
      markTimelineDirty("有未应用拖拽排序");
    }

    function endTimelineDrag(event) {
      const card = event.target.closest(".timeline-segment");
      if (card) card.classList.remove("dragging");
      document.querySelectorAll(".timeline-segment.dragging").forEach((item) => item.classList.remove("dragging"));
      timelineDraggedSegmentId = "";
    }

    function toggleTimelineDelete(button) {
      const card = button.closest(".timeline-segment");
      if (!card) return;
      const deleted = card.dataset.deleted === "true";
      card.dataset.deleted = deleted ? "false" : "true";
      card.classList.toggle("deleted", !deleted);
      button.textContent = deleted ? "删除" : "恢复";
      markTimelineDirty(deleted ? "已恢复片段，尚未应用" : "有未应用删除操作");
    }

    function moveTimelineSegment(button, delta) {
      const card = button.closest(".timeline-segment");
      const track = $("timelineTrack");
      if (!card || !track) return;
      const cards = [...track.querySelectorAll(".timeline-segment")];
      const index = cards.indexOf(card);
      const nextIndex = index + delta;
      if (index < 0 || nextIndex < 0 || nextIndex >= cards.length) return;
      card.classList.add("moving");
      if (delta < 0) {
        track.insertBefore(card, cards[nextIndex]);
      } else {
        track.insertBefore(cards[nextIndex], card);
      }
      renumberTimelineCards();
      markTimelineDirty("有未应用排序调整");
      setTimeout(() => card.classList.remove("moving"), 450);
    }

    function renumberTimelineCards() {
      [...document.querySelectorAll(".timeline-segment")].forEach((card, index) => {
        const segmentId = card.dataset.segmentId;
        const segment = (timelineBase?.segments || []).find((item) => item.segment_id === segmentId) || {};
        const indexBox = card.querySelector(".timeline-index");
        if (indexBox) {
          indexBox.innerHTML = `#${index + 1}<br>${escapeHtml(Number(segment.timeline_start_seconds || 0).toFixed(1))}s`;
        }
      });
    }

    async function applyTimelineEdits(button = null) {
      if (!timelineBase) {
        status.textContent = "请先生成时间线预览";
        return null;
      }
      const result = await withButtonState(button, "应用中", async () => {
        const edits = collectTimelineEdits();
        const outputDir = $("outputDir").value.trim();
        if (!edits.length && !outputDir) {
          timelineOverride = timelineBase;
          renderTimeline(timelineOverride, timelineOverride.validation_errors || []);
          renderTimelineState("ok", "已应用当前时间线", [`${timelineOverride.segments.length} 个片段`]);
          $("applyTimelineButton").disabled = true;
          status.textContent = "已应用当前时间线";
          return timelineOverride;
        }
        const payload = await requestJson("/api/timeline/edit", {
          base_timeline: timelineBase,
          edits,
          output_dir: outputDir,
          user_feedback: timelineEditSummary(edits)
        }, {silent: true});
        if (payload && payload.timeline) {
          timelineBase = payload.timeline;
          timelineOverride = payload.timeline;
          renderTimeline(payload.timeline, payload.validation_errors || []);
          $("applyTimelineButton").disabled = true;
          resultDetails.textContent = JSON.stringify(payload, null, 2);
          if (payload.saved_version) {
            renderTimelineState("ok", "已应用并保存时间线", [`v${payload.saved_version.version}`, `${payload.timeline.segments.length} 个片段`]);
            await loadTimelineVersions(null);
          }
          status.textContent = payload.ok ? "时间线编辑已应用" : "时间线编辑后仍需调整";
        } else {
          renderTimelineState("warn", payload?.error || "时间线编辑失败");
          resultDetails.textContent = JSON.stringify(payload, null, 2);
        }
        return payload;
      });
      if (timelineOverride) $("applyTimelineButton").disabled = true;
      return result;
    }

    function timelineEditSummary(edits) {
      if (!edits.length) return "应用当前时间线";
      const counts = edits.reduce((acc, edit) => {
        const op = edit.op || "unknown";
        acc[op] = (acc[op] || 0) + 1;
        return acc;
      }, {});
      const labels = {
        move: "排序",
        resize: "时长",
        replace_source: "替换素材",
        update_caption: "说明",
        delete: "删除",
        insert: "新增"
      };
      return Object.entries(counts)
        .map(([op, count]) => `${labels[op] || op} ${count}`)
        .join("，");
    }

    async function loadTimelineVersions(button = null) {
      const outputDir = $("outputDir").value.trim();
      if (!outputDir) {
        renderTimelineVersions(null, "请先填写输出目录，时间线版本会保存在该目录下。");
        return null;
      }
      return withButtonState(button, "刷新中", async () => {
        const payload = await requestJson(`/api/versions?output_dir=${encodeURIComponent(outputDir)}`, null, {silent: true});
        renderTimelineVersions(payload);
        return payload;
      });
    }

    function renderTimelineVersions(payload, emptyText = "还没有时间线版本。") {
      const box = $("timelineVersions");
      if (!box) return;
      if (!payload || payload.ok === false) {
        box.innerHTML = `<div class="summary-item"><span class="hint">${escapeHtml(payload?.error || emptyText)}</span></div>`;
        return;
      }
      timelineVersions = Array.isArray(payload.versions) ? payload.versions : [];
      if (!timelineVersions.length) {
        box.innerHTML = `<div class="summary-item"><span class="hint">${escapeHtml(emptyText)}</span></div>`;
        return;
      }
      box.innerHTML = [...timelineVersions].reverse().map((entry) => {
        const ops = Array.isArray(entry.edit_operations) ? entry.edit_operations : [];
        const opSummary = ops.length ? timelineEditSummary(ops) : "应用当前时间线";
        return `
          <div class="summary-item">
            <strong>v${escapeHtml(entry.version)} · ${escapeHtml(versionStatusLabel(entry.status))}</strong>
            <span class="mini">${escapeHtml(formatTimestamp(entry.created_at))}</span>
            <div class="chip-row">
              <span class="chip">${escapeHtml(opSummary)}</span>
              <span class="chip">${escapeHtml(entry.user_feedback || "timeline_workbench_edit")}</span>
            </div>
            <div class="actions">
              <button class="neutral" onclick="loadTimelineVersion(${Number(entry.version)}, this)">载入时间线</button>
              <button class="danger" onclick="revertTimelineVersion(${Number(entry.version)}, this)">回退到此版本</button>
            </div>
          </div>
        `;
      }).join("");
    }

    function versionStatusLabel(statusValue) {
      const statusMap = {
        completed: "已渲染",
        timeline_edit: "时间线编辑",
        pending_re_render: "待复剪",
        reverted: "已回退"
      };
      return statusMap[statusValue] || statusValue || "未知状态";
    }

    function formatTimestamp(seconds) {
      const value = Number(seconds || 0);
      if (!Number.isFinite(value) || value <= 0) return "未知时间";
      return new Date(value * 1000).toLocaleString();
    }

    async function loadTimelineVersion(version, button = null) {
      const outputDir = $("outputDir").value.trim();
      if (!outputDir) {
        status.textContent = "请先填写输出目录";
        return null;
      }
      return withButtonState(button, "载入中", async () => {
        const payload = await requestJson(`/api/versions/${version}?output_dir=${encodeURIComponent(outputDir)}`, null, {silent: true});
        if (!payload || !payload.timeline) {
          status.textContent = "该版本没有时间线快照";
          resultDetails.textContent = JSON.stringify(payload, null, 2);
          return payload;
        }
        timelineBase = payload.timeline;
        timelineOverride = payload.timeline;
        renderTimeline(timelineBase, []);
        $("applyTimelineButton").disabled = true;
        renderTimelineState("ok", `已载入时间线版本 v${version}`, [`${timelineBase.segments.length} 个片段`]);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = `已载入时间线版本 v${version}`;
        switchPanel("cut");
        return payload;
      });
    }

    async function revertTimelineVersion(version, button = null) {
      const outputDir = $("outputDir").value.trim();
      if (!outputDir) {
        status.textContent = "请先填写输出目录";
        return null;
      }
      if (!confirm(`回退到时间线版本 v${version}？系统会创建一个新的回退版本，原版本记录会保留。`)) {
        return null;
      }
      return withButtonState(button, "回退中", async () => {
        const payload = await requestJson(
          `/api/versions/revert?output_dir=${encodeURIComponent(outputDir)}&version=${encodeURIComponent(version)}`,
          {},
          {silent: true}
        );
        if (payload && payload.ok && payload.timeline) {
          timelineBase = payload.timeline;
          timelineOverride = payload.timeline;
          renderTimeline(timelineBase, []);
          $("applyTimelineButton").disabled = true;
          renderTimelineState("ok", `已回退到 v${version}`, [`新版本 v${payload.new_version}`]);
          await loadTimelineVersions(null);
          resultDetails.textContent = JSON.stringify(payload, null, 2);
          status.textContent = `已回退到时间线版本 v${version}`;
        } else {
          status.textContent = payload?.error || "版本回退失败";
          resultDetails.textContent = JSON.stringify(payload, null, 2);
        }
        return payload;
      });
    }

    async function loadProjectVersionCenter(outputDir = null, button = null) {
      const selectedOutputDir = String(outputDir || activeProjectOutputDir || $("outputDir").value || "").trim();
      if (!selectedOutputDir) {
        renderProjectVersionCenter(null, null, "先选择一个历史任务，或在剪辑页填写输出目录。");
        return null;
      }
      activeProjectOutputDir = selectedOutputDir;
      return withButtonState(button, "刷新中", async () => {
        const manifestPayload = await requestJson(`/api/project-manifest?output_dir=${encodeURIComponent(selectedOutputDir)}`, null, {silent: true});
        const versionsPayload = await requestJson(`/api/versions?output_dir=${encodeURIComponent(selectedOutputDir)}`, null, {silent: true});
        activeProjectManifest = manifestPayload?.manifest || null;
        renderProjectVersionCenter(manifestPayload, versionsPayload);
        return {manifest: manifestPayload, versions: versionsPayload};
      });
    }

    function renderProjectVersionCenter(manifestPayload, versionsPayload, emptyText = "暂无项目版本信息。") {
      const box = $("projectVersionCenter");
      if (!box) return;
      const manifest = manifestPayload?.manifest || activeProjectManifest;
      const versions = Array.isArray(versionsPayload?.versions) ? versionsPayload.versions : [];
      if (!manifest && !versions.length) {
        box.innerHTML = `<div class="summary-item"><span class="hint">${escapeHtml(manifestPayload?.error || versionsPayload?.error || emptyText)}</span></div>`;
        return;
      }
      const versionHistory = manifest?.version_history || {};
      const stylePackage = manifest?.style_package || {};
      const outputDir = manifest?.output_dir || activeProjectOutputDir || "";
      const versionCards = versions.length
        ? [...versions].reverse().map((entry) => projectVersionCard(entry, outputDir)).join("")
        : `<div class="summary-item"><span class="hint">版本历史为空。应用时间线编辑或完成剪辑后会生成版本。</span></div>`;
      box.innerHTML = `
        <div class="summary-item">
          <strong>${escapeHtml(stylePackage.name || "本地项目")}</strong>
          <span class="path-text">${escapeHtml(outputDir)}</span>
          <div class="chip-row">
            <span class="chip">当前 v${escapeHtml(versionHistory.current_version || 0)}</span>
            <span class="chip">${escapeHtml(versionHistory.version_count || versions.length || 0)} 个版本</span>
            <span class="chip">${escapeHtml(projectEventLabel(manifest?.last_event))}</span>
            <span class="chip">${manifest?.execute_real_render ? "真实渲染" : "计划模式"}</span>
          </div>
          <div class="path-text">清单：${escapeHtml(outputDir ? `${outputDir}\\project_manifest.json` : "未绑定输出目录")}</div>
        </div>
        ${versionCards}
      `;
    }

    function projectVersionCard(entry, outputDir) {
      const ops = Array.isArray(entry.edit_operations) ? entry.edit_operations : [];
      const opSummary = ops.length ? timelineEditSummary(ops) : "应用当前时间线";
      return `
        <div class="summary-item">
          <strong>v${escapeHtml(entry.version)} · ${escapeHtml(versionStatusLabel(entry.status))}</strong>
          <span class="mini">${escapeHtml(formatTimestamp(entry.created_at))}</span>
          <div class="chip-row">
            <span class="chip">${escapeHtml(opSummary)}</span>
            <span class="chip">${escapeHtml(entry.user_feedback || "无反馈说明")}</span>
          </div>
          <div class="actions">
            <button class="neutral" onclick="loadProjectTimelineVersion(${Number(entry.version)}, '${escapeJs(outputDir)}', this)">载入时间线</button>
            <button class="secondary" onclick="startVersionReEdit(${Number(entry.version)}, '${escapeJs(outputDir)}', this)">基于版本复剪</button>
            <button class="danger" onclick="revertProjectVersion(${Number(entry.version)}, '${escapeJs(outputDir)}', this)">回退到此版本</button>
          </div>
        </div>
      `;
    }

    function projectEventLabel(eventName) {
      const labels = {
        render_completed: "剪辑完成",
        render_failed: "剪辑失败",
        timeline_edit: "时间线编辑",
        version_reverted: "版本回退",
        version_re_edit: "版本复剪",
        updated: "已更新"
      };
      return labels[eventName] || eventName || "未记录事件";
    }

    async function loadProjectTimelineVersion(version, outputDir, button = null) {
      const selectedOutputDir = String(outputDir || activeProjectOutputDir || "").trim();
      if (!selectedOutputDir) return null;
      return withButtonState(button, "载入中", async () => {
        const payload = await requestJson(`/api/versions/${version}?output_dir=${encodeURIComponent(selectedOutputDir)}`, null, {silent: true});
        if (!payload || !payload.timeline) {
          status.textContent = "该版本没有时间线快照";
          resultDetails.textContent = JSON.stringify(payload, null, 2);
          return payload;
        }
        setValue("outputDir", selectedOutputDir);
        timelineBase = payload.timeline;
        timelineOverride = payload.timeline;
        renderTimeline(timelineBase, []);
        $("applyTimelineButton").disabled = true;
        renderTimelineState("ok", `已从项目中心载入 v${version}`, [`${timelineBase.segments.length} 个片段`]);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = `已载入项目版本 v${version}`;
        switchPanel("cut");
        return payload;
      });
    }

    async function revertProjectVersion(version, outputDir, button = null) {
      const selectedOutputDir = String(outputDir || activeProjectOutputDir || "").trim();
      if (!selectedOutputDir) return null;
      if (!confirm(`回退项目到版本 v${version}？系统会创建一个新的回退版本，旧版本不会被删除。`)) {
        return null;
      }
      return withButtonState(button, "回退中", async () => {
        const payload = await requestJson(
          `/api/versions/revert?output_dir=${encodeURIComponent(selectedOutputDir)}&version=${encodeURIComponent(version)}`,
          {},
          {silent: true}
        );
        if (payload?.ok) {
          await loadProjectVersionCenter(selectedOutputDir, null);
          if (payload.timeline) {
            timelineBase = payload.timeline;
            timelineOverride = payload.timeline;
          }
          status.textContent = `项目已回退到 v${version}`;
        } else {
          status.textContent = payload?.error || "项目版本回退失败";
        }
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        return payload;
      });
    }

    async function startVersionReEdit(version, outputDir, button = null) {
      const selectedOutputDir = String(outputDir || activeProjectOutputDir || "").trim();
      if (!selectedOutputDir) return null;
      const defaultFeedback = $("recutRequest").value.trim() || "基于该版本继续复剪";
      const feedback = prompt(`基于 v${version} 创建复剪版本，填写本次修改要求：`, defaultFeedback);
      if (feedback === null) return null;
      return withButtonState(button, "创建中", async () => {
        const payload = await requestJson("/api/versions/re-edit", {
          output_dir: selectedOutputDir,
          base_version: version,
          user_feedback: feedback,
          timeline_edits: [],
          execute_real_render: false
        }, {silent: true});
        if (payload?.ok && payload.timeline) {
          applyProjectManifestToCutForm(selectedOutputDir, feedback, payload.new_version);
          timelineBase = payload.timeline;
          timelineOverride = payload.timeline;
          renderTimeline(timelineBase, []);
          $("applyTimelineButton").disabled = true;
          renderTimelineState("ok", `已创建复剪版本 v${payload.new_version}`, [`源版本 v${version}`]);
          await loadProjectVersionCenter(selectedOutputDir, null);
          switchPanel("cut");
          status.textContent = `已基于 v${version} 创建复剪版本 v${payload.new_version}`;
        } else {
          status.textContent = payload?.error || "创建复剪版本失败";
        }
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        return payload;
      });
    }

    function applyProjectManifestToCutForm(outputDir, feedback, newVersion) {
      const manifest = activeProjectManifest || {};
      const result = manifest.latest_result || {};
      const stylePackage = manifest.style_package || {};
      if (stylePackage.path) setValue("stylePackage", stylePackage.path);
      inputVideos = Array.isArray(manifest.input_videos) && manifest.input_videos.length
        ? manifest.input_videos
        : (Array.isArray(result.input_videos) ? result.input_videos : [result.input_video].filter(Boolean));
      if (inputVideos.length) setValue("inputVideo", inputVideos[0]);
      renderInputVideos();
      setValue("outputDir", outputDir ? `${outputDir}_recut_v${newVersion || "next"}` : "");
      const baseRequest = String(result.user_request || $("userRequest").value || "").trim();
      setValue("userRequest", `${baseRequest}${baseRequest ? "\n" : ""}复剪要求：${feedback || "继续优化"}`);
      setValue("briefText", result.confirmed_brief || "");
      $("recutRequest").value = feedback || "";
      markBriefStale();
    }

    function collectTimelineEdits() {
      const originalSegments = Array.isArray(timelineBase?.segments) ? timelineBase.segments : [];
      const cards = [...document.querySelectorAll(".timeline-segment")];
      const edits = [];
      const orderedCards = cards.filter((card) => card.dataset.segmentId);
      orderedCards.forEach((card, position) => {
        const originalPosition = Number(card.dataset.originalPosition);
        if (Number.isFinite(originalPosition) && originalPosition !== position) {
          edits.push({op: "move", segment_id: card.dataset.segmentId, new_position: position});
        }
      });
      for (const segment of originalSegments) {
        const card = cards.find((item) => item.dataset.segmentId === segment.segment_id);
        if (!card) continue;
        if (card.dataset.deleted === "true") {
          edits.push({op: "delete", segment_id: segment.segment_id});
          continue;
        }
        const duration = Number(card.querySelector('[data-field="duration"]')?.value || segment.duration_seconds);
        if (Number.isFinite(duration) && Math.abs(duration - Number(segment.duration_seconds || 0)) > 0.01) {
          edits.push({op: "resize", segment_id: segment.segment_id, duration_seconds: duration});
        }
        const caption = String(card.querySelector('[data-field="caption"]')?.value || "");
        if (caption !== String(segment.caption || "")) {
          edits.push({op: "update_caption", segment_id: segment.segment_id, caption});
        }
        const selectedSource = card.querySelector('[data-field="sourceIndex"]')?.value;
        if (selectedSource !== undefined && selectedSource !== "" && Number(selectedSource) !== Number(segment.source_material_index)) {
          const videos = normalizeInputVideos();
          const selectedOption = card.querySelector('[data-field="sourceIndex"]')?.selectedOptions?.[0];
          edits.push({
            op: "replace_source",
            segment_id: segment.segment_id,
            source_material_index: Number(selectedSource),
            source_file: videos[Number(selectedSource)] || "",
            thumbnail_path: selectedOption?.dataset?.thumbnail || ""
          });
        }
      }
      return edits;
    }

    function clearTimelineOverride() {
      timelineBase = null;
      timelineOverride = null;
      $("applyTimelineButton").disabled = true;
      renderTimelineState("", "未生成时间线");
      $("timelineTrack").innerHTML = `<div class="timeline-empty"><span class="hint">生成预览后会显示片段卡片。</span></div>`;
      status.textContent = "已清除编辑时间线";
    }

    function updateSubtitleControls() {
      const enabled = $("subtitleMode").value !== "none";
      ["subtitlePrompt", "subtitleLocation", "subtitleSize", "subtitleColor", "outlineColor", "outlineWidth"].forEach((id) => {
        $(id).disabled = !enabled;
      });
      markBriefStale();
    }

    async function previewSubtitleHandoff(button = null) {
      const path = $("subtitleHandoffPath").value.trim();
      if (!path) {
        status.textContent = "请先填写 subtitle_handoff.json 路径";
        return null;
      }
      return withButtonState(button, "校验中", async () => {
        const payload = await requestJson("/api/filmgen/subtitle-handoff/preview", {
          handoff_path: path
        }, {silent: true});
        const validation = payload.validation || {};
        const errors = validation.errors || [];
        const warnings = validation.warnings || [];
        $("subtitleHandoffPreview").innerHTML = `
          <div class="summary-item">
            <strong>${payload.ok ? "字幕交接可用" : "字幕交接需修复"}</strong>
            <span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(payload.reason || "")}</span>
            <span class="chip">${escapeHtml(String(payload.subtitle_text_count || 0))} 条字幕文本</span>
          </div>
          ${errors.map((item) => `<div class="summary-item"><span class="chip warn">${escapeHtml(item.code || "error")}</span><span>${escapeHtml(item.message || "")}</span></div>`).join("")}
          ${warnings.map((item) => `<div class="summary-item"><span class="chip warn">${escapeHtml(item.code || "warning")}</span><span>${escapeHtml(item.message || "")}</span></div>`).join("")}
        `;
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "字幕交接校验通过" : "字幕交接校验有问题";
        return payload;
      });
    }

    async function calibrateMaterialAnalysis(button = null) {
      return withButtonState(button, "校准中", async () => {
        const payload = await requestJson("/api/material/calibration", {
          sample_set: $("materialSampleSet").value,
          sample_set_path: $("materialSampleSetPath").value,
          baseline_threshold: Number($("materialRoleThreshold").value) || 0.5,
          samples: []
        }, {silent: true});
        latestMaterialCalibration = payload;
        renderMaterialCalibration(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "素材分析校准完成，可应用推荐阈值" : "素材分析校准无可用样本";
        return payload;
      });
    }

    function applyMaterialCalibration(button = null) {
      void button;
      const payload = latestMaterialCalibration;
      const tuning = payload?.recommended_tuning || {};
      const recommendedThreshold = Number(tuning.role_confidence_threshold);
      if (!payload || !Number.isFinite(recommendedThreshold)) {
        status.textContent = "请先运行素材校准";
        return;
      }
      $("materialVisualAnalysis").value = "true";
      $("materialVisualPreset").value = tuning.visual_quality_preset || "calibrated";
      $("materialRoleThreshold").value = recommendedThreshold.toFixed(2);
      if (payload.sample_set && !["inline_samples", "custom_path"].includes(payload.sample_set)) {
        $("materialSampleSet").value = payload.sample_set;
      }
      markBriefStale();
      status.textContent = `已应用素材校准：角色阈值 ${recommendedThreshold.toFixed(2)}`;
    }

    function renderMaterialCalibration(payload) {
      const tuning = payload.recommended_tuning || {};
      const roleMetrics = payload.role_metrics || {};
      const lowConfidence = payload.low_confidence_samples || [];
      const score = (value) => {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed.toFixed(2) : "0.00";
      };
      const roleNames = {
        opening_hero: "开场主视觉",
        product_body_and_detail: "主体与细节",
        site_context: "现场/环境"
      };
      const roleCards = Object.entries(roleMetrics).map(([role, item]) => `
        <div class="summary-item">
          <strong>${escapeHtml(roleNames[role] || role)}</strong>
          <div class="chip-row">
            <span class="chip">${escapeHtml(item.sample_count || 0)} 个样本</span>
            <span class="chip ${Number(item.accuracy || 0) >= 0.8 ? "ok" : "warn"}">准确率 ${score(item.accuracy)}</span>
            <span class="chip">均分 ${score(item.avg_expected_score)}</span>
            <span class="chip">边际 ${score(item.avg_margin)}</span>
          </div>
        </div>
      `).join("");
      const lowCards = lowConfidence.slice(0, 4).map((item) => `
        <div class="summary-item">
          <span class="chip warn">低置信</span>
          <strong>${escapeHtml(item.sample_id || "sample")}</strong>
          <span class="hint">期望 ${escapeHtml(roleNames[item.expected_role] || item.expected_role || "")}，预测 ${escapeHtml(roleNames[item.predicted_role] || item.predicted_role || "")}，分数 ${score(item.expected_score)}，边际 ${score(item.margin)}</span>
        </div>
      `).join("");
      $("materialCalibrationResult").innerHTML = `
        <div class="summary-item">
          <strong>${payload.ok ? "校准结果可用" : "校准结果不可用"}</strong>
          <div class="chip-row">
            <span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(payload.source || "")}</span>
            <span class="chip">${escapeHtml(payload.sample_set_label || payload.sample_set || "样本集")}</span>
            <span class="chip">样本 ${escapeHtml(payload.usable_sample_count || 0)}/${escapeHtml(payload.sample_count || 0)}</span>
            <span class="chip">推荐阈值 ${score(tuning.role_confidence_threshold)}</span>
          </div>
        </div>
        ${roleCards}
        ${lowCards || `<div class="summary-item"><span class="hint">没有明显低置信样本。</span></div>`}
      `;
    }

    function updateVoiceControls() {
      const provider = $("voiceProvider").value;
      const enabled = provider !== "none";
      const systemTts = provider === "system_tts";
      const fixture = provider === "fixture";
      $("voiceoverText").disabled = !enabled;
      $("voiceVolume").disabled = !enabled;
      $("allowEdge").disabled = !enabled || provider !== "edge_tts";
      $("systemTtsControls").style.display = systemTts ? "block" : "none";
      ["systemVoice", "systemRate", "systemVolume"].forEach((id) => {
        $(id).disabled = !systemTts;
      });
      $("fixtureVoiceControls").style.display = fixture ? "block" : "none";
      ["fixtureDuration", "fixtureSampleRate"].forEach((id) => {
        $(id).disabled = !fixture;
      });
      if (systemTts && !systemTtsVoicesLoaded && !systemTtsVoicesLoading) {
        loadSystemTtsVoices(null, {silent: true});
      }
      if (!enabled) {
        $("voiceoverText").value = "";
        $("allowEdge").checked = false;
      }
      markBriefStale();
    }

    function updateBgmControls() {
      const local = $("bgmStyle").value === "local_audio";
      const library = $("bgmStyle").value === "library";
      $("bgmAudioPath").disabled = !local;
      $("bgmLibraryControls").style.display = library ? "block" : "none";
      $("bgmLibraryDir").disabled = !library;
      $("bgmLibraryQuery").disabled = !library;
      $("bgmStart").disabled = !(local || library);
      $("bgmPreview").style.display = local ? "block" : "none";
      if (!local) $("bgmPreview").removeAttribute("src");
      markBriefStale();
    }

    async function scanBgmLibrary(button = null) {
      if (!$("bgmLibraryDir").value.trim()) {
        status.textContent = "请先选择 BGM 素材库目录";
        return null;
      }
      $("bgmStyle").value = "library";
      updateBgmControls();
      return withButtonState(button, "扫描中", async () => {
        const payload = await requestJson("/api/bgm/library/playlist", {
          library_dir: $("bgmLibraryDir").value,
          query: $("bgmLibraryQuery").value,
          style: $("bgmStyle").value,
          limit: 8
        }, {silent: true});
        const recommended = payload.recommended || null;
        renderBgmLibraryPlaylist(payload);
        if (recommended && recommended.path) {
          $("bgmAudioPath").value = recommended.path;
          $("bgmPreview").src = `/api/media-preview?path=${encodeURIComponent(recommended.path)}`;
          $("bgmPreview").style.display = "block";
        }
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = recommended ? "已推荐 BGM 素材" : "BGM 素材库无匹配";
        markBriefStale();
        return payload;
      });
    }

    function renderBgmLibraryPlaylist(payload) {
      const items = payload.items || [];
      const recommended = payload.recommended || null;
      $("bgmLibraryResult").innerHTML = recommended
        ? `<div class="summary-item"><strong>推荐：${escapeHtml(recommended.name)}</strong><span class="hint">${escapeHtml(recommended.match_reason || "")}</span></div>`
        : `<div class="summary-item"><span class="hint">未找到可用 BGM：${escapeHtml(payload.reason || "empty_library")}</span></div>`;
      if (!items.length) return;
      $("bgmLibraryResult").innerHTML += items.map((item, index) => `
        <div class="summary-item">
          <strong>${escapeHtml(index + 1)}. ${escapeHtml(item.name || "BGM")}</strong>
          <span class="path-text">${escapeHtml(item.path || "")}</span>
          <div class="chip-row">
            <span class="chip ${index === 0 ? "ok" : ""}">score ${escapeHtml(item.score || 0)}</span>
            <span class="chip">${escapeHtml(item.match_reason || "")}</span>
          </div>
          <audio class="audio-preview" controls src="/api/media-preview?path=${encodeURIComponent(item.path || "")}"></audio>
          <div class="actions"><button class="neutral" onclick="useBgmLibraryItem('${escapeJs(item.path || "")}')">选用这首</button></div>
        </div>
      `).join("");
    }

    function useBgmLibraryItem(path) {
      if (!path) return;
      $("bgmAudioPath").value = path;
      $("bgmStyle").value = "library";
      $("bgmPreview").src = `/api/media-preview?path=${encodeURIComponent(path)}`;
      $("bgmPreview").style.display = "block";
      status.textContent = "已选用素材库 BGM";
      markBriefStale();
    }

    function previewBgm() {
      if (!$("bgmAudioPath").value.trim()) {
        status.textContent = "请先选择本地音乐";
        return;
      }
      $("bgmStyle").value = "local_audio";
      updateBgmControls();
      const audio = $("bgmPreview");
      audio.src = `/api/media-preview?path=${encodeURIComponent($("bgmAudioPath").value)}`;
      audio.onloadedmetadata = () => {
        const start = Math.max(0, Number($("bgmStart").value) || 0);
        if (Number.isFinite(audio.duration) && start < audio.duration) audio.currentTime = start;
      };
      audio.play().catch(() => {
        status.textContent = "已载入音乐，可点击播放器播放";
      });
      markBriefStale();
    }

    function clearBgmAudio() {
      $("bgmAudioPath").value = "";
      $("bgmStart").value = "0";
      $("bgmStyle").value = "upbeat_instrumental";
      $("bgmPreview").removeAttribute("src");
      updateBgmControls();
      markBriefStale();
    }

    async function generateBrief(button = null) {
      return withButtonState(button, "生成中", async () => {
        status.textContent = "正在生成剪辑标准";
        const payload = await requestJson("/api/edit-brief", collectEditPayload(), {silent: true});
        $("briefText").value = payload.brief_text || "";
        const checklistCards = (payload.checklist || []).map((item) => `
          <div class="summary-item"><span>${escapeHtml(item)}</span></div>
        `);
        const materialCards = (((payload.material_plan || {}).materials) || []).map((item) => `
          <div class="summary-item">
            <strong>素材分工 ${escapeHtml(String((item.index || 0) + 1))}</strong>
            <span class="path-text">${escapeHtml(item.label || item.path || "")}</span>
            <div class="chip-row">
              <span class="chip ok">${escapeHtml(item.display_role || item.primary_role || "补充镜头")}</span>
              <span class="chip">${escapeHtml(assignmentSourceLabel(item.assignment_source))}</span>
            </div>
            ${item.assignment_reason ? `<span class="hint">${escapeHtml(item.assignment_reason)}</span>` : ""}
          </div>
        `);
        $("briefChecklist").innerHTML = [...materialCards, ...checklistCards].join("");
        briefReady = payload.ready_for_confirmation === true;
        $("startCutButton").disabled = !briefReady;
        latestResult = null;
        refreshGuidedFeedbacks();
        renderPayload(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = briefReady ? "请确认剪辑标准" : "剪辑标准生成失败";
        return payload;
      });
    }

    async function cutVideo(button = null) {
      if (!briefReady || !$("briefText").value.trim()) {
        status.textContent = "请先生成并确认剪辑标准";
        switchPanel("cut");
        return;
      }
      const result = await withButtonState(button, "剪辑中", async () => {
        status.textContent = "剪辑任务运行中，请等待渲染完成";
        const payload = collectEditPayload();
        payload.confirmed_brief = $("briefText").value;
        const nextResult = await requestJson("/api/cut", payload, {silent: true});
        latestResult = nextResult;
        renderEditResult(nextResult);
        resultDetails.textContent = JSON.stringify(nextResult, null, 2);
        status.textContent = nextResult.ok ? "剪辑完成" : "剪辑失败";
        return nextResult;
      });
      latestResult = result;
      briefReady = false;
      $("startCutButton").disabled = true;
      await loadRecentRuns();
      switchPanel("review");
    }

    function buildEditResultGuidance(payload) {
      const output = payload?.output_dir || "";
      const hasVideo = Boolean(payload?.copied_output_video);
      const rawProblem = payloadProblemText(payload);
      const friendlyProblem = humanizeProblemText(rawProblem);
      const normalized = rawProblem.toLowerCase();
      if (payload?.ok) {
        return {
          headline: "第一版已经出来了",
          summary: "建议先完整播放一遍，确认整体节奏、字幕和配音，再决定要不要继续修改。",
          tips: [
            "先看开头几秒是否够抓人，再看结尾有没有把重点收住。",
            "如果只是小改字幕、节奏或配音，可以直接点“继续修改”。",
            output ? "想回到旧版本时，直接点“查看版本”即可。" : "如果后面还要反复修改，建议保留当前输出目录。"
          ],
          actions: [
            {label: "查看结果", code: "switchPanel('review')", tone: "secondary"},
            {label: "回到剪辑页继续调整", code: "switchPanel('cut')", tone: "neutral"}
          ]
        };
      }

      const tips = [];
      const actions = [{label: "回到开始剪辑", code: "switchPanel('cut')", tone: "secondary"}];
      if (!output) {
        tips.push("先回到步骤 1，重新填写一个成片保存目录。");
      }
      if (!normalizeInputVideos().length) {
        tips.push("确认至少加入了 1 个原视频素材。");
      }
      if (!$("briefText")?.value?.trim()) {
        tips.push("重新生成一次剪辑标准，再开始出片。");
      }
      if (normalized.includes("missing_model") || normalized.includes("missing_api_key") || normalized.includes("missing_base_url") || normalized.includes("urlerror") || normalized.includes("runtimeerror")) {
        tips.push("去“高级设置”检查模型连接、本地 Ollama 或 API Key。");
        actions.push({label: "去模型与声音设置", code: "switchPanel('settings')", tone: "neutral"});
      } else if (normalized.includes("output_dir") || normalized.includes("permission")) {
        tips.push("换一个你确定有写入权限的保存目录，再试一次。");
        actions.push({label: "去检查保存位置", code: "scrollToStep('setupStep')", tone: "neutral"});
      } else if (normalized.includes("input_video") || normalized.includes("no such file") || normalized.includes("not found")) {
        tips.push("回到步骤 1，重新选择素材，避免引用了已经移动的文件。");
        actions.push({label: "去检查素材", code: "scrollToStep('setupStep')", tone: "neutral"});
      } else if (normalized.includes("style_package")) {
        tips.push("重新选择样板目录，确认样板路径仍然存在。");
        actions.push({label: "去检查样板", code: "scrollToStep('setupStep')", tone: "neutral"});
      } else if (normalized.includes("brief")) {
        tips.push("这次更像是剪辑标准已经过期，建议重新生成一次。");
        actions.push({label: "去重新生成标准", code: "scrollToStep('confirmStep')", tone: "neutral"});
      } else if (!hasVideo) {
        tips.push("这次没有拿到可播放成片，先看下方技术详情和输出目录，再决定是补参数还是重试。");
      }
      if (!tips.length) {
        tips.push("先检查样板、素材、保存位置和剪辑标准这四项是否都还是最新的。");
        tips.push("如果你刚改过目标或素材，最好重新生成剪辑标准再试。");
      }
      return {
        headline: "这次没能顺利出片",
        summary: friendlyProblem ? `系统当前卡在：${friendlyProblem}。` : "系统这次没有拿到可播放的成片。",
        tips,
        actions
      };
    }

    function renderEditResult(payload) {
      const videoPath = payload.copied_output_video;
      const output = payload.output_dir || "";
      const voice = payload.voice_provider || "未设置";
      const mode = payload.execute_real_render ? "真实渲染" : "计划模式";
      const subtitleAdapter = payload.subtitle_adapter_result || {};
      const bgmAdapter = payload.bgm_adapter_result || {};
      const exportAdapters = (payload.export_adapter_result && payload.export_adapter_result.exports) || {};
      const externalExport = exportAdapters.filmgen_handoff || exportAdapters.external_handoff || {};
      const subtitleHandoff = subtitleAdapter.handoff_path || "";
      const exportHandoff = externalExport.handoff_path || "";
      const bgmAudio = bgmAdapter.renderer_bgm_audio_input || bgmAdapter.local_bgm_audio_path || "";
      const protocolPath = payload.local_toolkit_protocol_path || "";
      const guidance = buildEditResultGuidance(payload);
      const reasonText = humanizeProblemText(payloadProblemText(payload));
      const reasonChip = !payload.ok && reasonText
        ? `<span class="chip warn">${escapeHtml(reasonText)}</span>`
        : "";
      const guidanceBlock = `
        <div class="summary-item">
          <strong>${escapeHtml(guidance.headline || "")}</strong>
          <span class="hint">${escapeHtml(guidance.summary || "")}</span>
          ${renderHintListHtml(guidance.tips || [])}
          ${renderActionButtonsHtml(guidance.actions || [])}
        </div>
      `;
      resultCards.innerHTML = `
        <div class="summary-item"><strong>${payload.ok ? "第一版任务已经完成" : "第一版任务还没完成"}</strong><div class="chip-row"><span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(mode)}</span>${reasonChip}</div></div>
        ${guidanceBlock}
        <div class="summary-item"><strong>输出目录</strong><span class="path-text">${escapeHtml(output)}</span></div>
        <div class="summary-item"><strong>成片文件</strong><span class="path-text">${escapeHtml(videoPath || "未生成视频文件")}</span></div>
        <div class="summary-item"><strong>人声方案</strong><span>${escapeHtml(voice)}</span></div>
        <div class="summary-item"><strong>字幕适配器</strong><span class="chip">${escapeHtml(subtitleAdapter.adapter_id || "未记录")}</span></div>
        <div class="summary-item"><strong>BGM 适配器</strong><span class="chip">${escapeHtml(bgmAdapter.adapter_id || "未记录")}</span></div>
        <div class="summary-item"><strong>外部字幕交接</strong><span class="path-text">${escapeHtml(subtitleHandoff || "未生成 subtitle_handoff.json")}</span></div>
        <div class="summary-item"><strong>外部导出交接</strong><span class="path-text">${escapeHtml(exportHandoff || "尚未生成外部导出交接 JSON")}</span></div>
        <div class="summary-item"><strong>本地协议清单</strong><span class="path-text">${escapeHtml(protocolPath || "未生成 local_toolkit_protocol.json")}</span></div>
        <div class="summary-item"><strong>BGM 音频输入</strong><span class="path-text">${escapeHtml(bgmAudio || "未使用本地音频")}</span></div>
      `;
      $("currentResult").innerHTML = `
        <div class="summary-item"><strong>${payload.ok ? "第一版已经生成" : "这次出片没有完成"}</strong><span class="path-text">${escapeHtml(output || "未写入输出目录")}</span><span class="hint">${escapeHtml(guidance.summary || "")}</span>${reviewActionButtons({videoPath, outputDir: output, editLabel: "回到剪辑页继续调整"})}</div>
        ${guidanceBlock}
        <div class="summary-item"><strong>成片文件</strong><span class="path-text">${escapeHtml(videoPath || "未生成视频文件")}</span></div>
        <div class="summary-item"><strong>人声方案</strong><span>${escapeHtml(voice)}</span></div>
        <div class="summary-item"><strong>版本中心</strong><span>${escapeHtml(output ? "可刷新查看当前项目版本" : "生成输出目录后可查看版本")}</span></div>
      `;
      if (exportHandoff) $("filmgenExportHandoffPath").value = exportHandoff;
      if (output) $("protocolOutputDir").value = output;
      if (protocolPath) $("protocolInspectPath").value = protocolPath;
      if (output) loadProjectVersionCenter(output, null);
      if (videoPath) {
        playReviewVideo(videoPath);
      } else {
        $("videoPreview").removeAttribute("src");
        $("videoPreview").style.display = "none";
      }
      refreshGuidedFeedbacks();
    }

    async function validateFilmgenExportHandoff(path = null, button = null) {
      const selectedPath = String(path || $("filmgenExportHandoffPath").value || "").trim();
      if (!selectedPath) {
        status.textContent = "请先填写外部导出交接 JSON 路径";
        return null;
      }
      $("filmgenExportHandoffPath").value = selectedPath;
      return withButtonState(button, "验收中", async () => {
        const payload = await requestJson("/api/filmgen/export-handoff/validate", {
          handoff_path: selectedPath
        }, {silent: true});
        renderFilmgenExportHandoffValidation(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "外部导出交接验收通过" : "外部导出交接需要修复";
        return payload;
      });
    }

    function renderFilmgenExportHandoffValidation(payload) {
      const validation = payload.validation || {};
      const errors = validation.errors || [];
      const warnings = validation.warnings || [];
      const handoff = payload.filmgen_handoff || payload.external_handoff || {};
      const candidates = handoff.input_video_candidates || [];
      $("filmgenExportHandoffPreview").innerHTML = `
        <div class="summary-item">
          <strong>${payload.ok ? "可导入外部流程" : "暂不可导入外部流程"}</strong>
          <div class="chip-row">
            <span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(payload.reason || "")}</span>
            <span class="chip">${escapeHtml(payload.source_schema || "unknown schema")}</span>
            <span class="chip">候选视频 ${escapeHtml(payload.input_video_candidate_count || 0)}</span>
          </div>
          <span class="path-text">${escapeHtml(payload.handoff_path || "")}</span>
        </div>
        ${candidates.map((item, index) => `<div class="summary-item"><strong>候选视频 ${escapeHtml(index + 1)}</strong><span class="path-text">${escapeHtml(item)}</span></div>`).join("")}
        ${errors.map((item) => `<div class="summary-item"><span class="chip warn">${escapeHtml(item.code || "error")}</span><span>${escapeHtml(item.message || "")}</span></div>`).join("")}
        ${warnings.map((item) => `<div class="summary-item"><span class="chip warn">${escapeHtml(item.code || "warning")}</span><span>${escapeHtml(item.message || "")}</span></div>`).join("")}
      `;
    }

    async function loadRecentRuns(button = null) {
      return withButtonState(button, "刷新中", async () => {
        const payload = await requestJson("/api/recent-runs", null, {silent: true});
        recentRuns = payload.runs || [];
        const box = $("recentRuns");
        if (!recentRuns.length) {
          renderRecentRunsEmpty();
          return recentRuns;
        }
        box.innerHTML = recentRuns.map((run, index) => `
          <details class="history-item">
            <summary>
              <span>
                <span class="history-title">${escapeHtml(run.style_package_name || "未命名任务")}</span>
                <span class="mini">${escapeHtml(shortPath(run.output_dir || ""))}</span>
              </span>
              <span class="chip ${run.ok ? "ok" : "warn"}">${run.ok ? "完成" : "异常"}</span>
            </summary>
            <div class="history-body">
              <div class="path-text">${escapeHtml(run.output_dir || "")}</div>
              <div class="chip-row">
                <span class="chip">${run.execute_real_render ? "真实渲染" : "计划模式"}</span>
                <span class="chip">${escapeHtml(run.input_video_count || 1)} 个素材</span>
                <span class="chip">${escapeHtml(run.voice_provider || "无新配音")}</span>
                <span class="chip">v${escapeHtml(run.current_version || 0)} / ${escapeHtml(run.version_count || 0)} 版</span>
              </div>
              <span class="mini">常用：先看成片，再决定是否继续修改。</span>
              <div class="actions">
                <button onclick="loadRunForReview(${index})">查看成片</button>
                <button class="neutral" onclick="prepareRecut(${index})">继续修改</button>
                <button class="neutral" onclick="loadProjectVersionCenter('${escapeJs(run.output_dir || "")}', null)">查看版本</button>
              </div>
              <details class="inline-more">
                <summary>更多操作</summary>
                <div class="actions">
                  <button class="danger" onclick="deleteRecentRun(${index}, this)">删除这条记录</button>
                </div>
              </details>
            </div>
          </details>
        `).join("");
        return recentRuns;
      });
    }

    function shortPath(value) {
      const text = String(value || "");
      if (text.length <= 42) return text;
      return `...${text.slice(-39)}`;
    }

    async function deleteRecentRun(index, button = null) {
      const run = recentRuns[index];
      if (!run || !run.result_json) return;
      if (!confirm("删除这个历史任务及其输出目录？")) return;
      await withButtonState(button, "删除中", async () => {
        status.textContent = "删除历史任务";
        const response = await fetch(`/api/recent-runs?result_json=${encodeURIComponent(run.result_json)}`, {method: "DELETE"});
        const payload = await response.json().catch(() => ({}));
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "历史任务已删除" : "删除失败";
        await loadRecentRuns();
      });
    }

    function loadRunForReview(index) {
      const run = recentRuns[index];
      if (!run) return;
      activeProjectOutputDir = run.output_dir || "";
      activeProjectManifest = run.project_manifest || null;
      $("currentResult").innerHTML = `
        <div class="summary-item"><strong>${escapeHtml(run.style_package_name || "历史任务")}</strong><span class="path-text">${escapeHtml(run.output_dir || "")}</span><span class="hint">建议先播放成片确认结果，再决定是否继续修改这版。</span>${reviewActionButtons({videoPath: run.copied_output_video || "", outputDir: run.output_dir || "", editLabel: "回到剪辑页继续调整"})}</div>
        <div class="summary-item"><strong>输入素材</strong><span class="path-text">${escapeHtml((run.input_videos || [run.input_video]).filter(Boolean).join("\\n"))}</span></div>
        <div class="summary-item"><strong>成片文件</strong><span class="path-text">${escapeHtml(run.copied_output_video || "无")}</span></div>
        <div class="summary-item"><strong>时间线</strong><span>${escapeHtml((run.timeline_plan?.segments || []).length || 0)} 个片段</span></div>
        <div class="summary-item"><strong>版本中心</strong><span>当前 v${escapeHtml(run.current_version || 0)}，共 ${escapeHtml(run.version_count || 0)} 个版本</span></div>
        <div class="summary-item"><strong>项目清单</strong><span class="path-text">${escapeHtml(run.project_manifest_path || "尚未生成 project_manifest.json")}</span></div>
      `;
      if (run.copied_output_video) {
        playReviewVideo(run.copied_output_video);
      }
      loadProjectVersionCenter(run.output_dir, null);
      refreshGuidedFeedbacks();
    }

    function prepareRecut(index) {
      const run = recentRuns[index];
      if (!run) return;
      activeProjectOutputDir = run.output_dir || "";
      activeProjectManifest = run.project_manifest || null;
      setValue("stylePackage", run.style_package_path);
      inputVideos = (run.input_videos && run.input_videos.length) ? run.input_videos : [run.input_video].filter(Boolean);
      setValue("inputVideo", inputVideos[0]);
      renderInputVideos();
      setValue("outputDir", run.output_dir ? `${run.output_dir}_recut` : "");
      setValue("userRequest", run.user_request);
      setValue("briefText", run.confirmed_brief);
      $("recutRequest").value = "";
      markBriefStale();
      if (run.timeline_plan && Array.isArray(run.timeline_plan.segments) && run.timeline_plan.segments.length) {
        timelineBase = run.timeline_plan;
        timelineOverride = run.timeline_plan;
        renderTimeline(timelineBase, []);
        $("applyTimelineButton").disabled = false;
        renderTimelineState("ok", "已载入历史时间线", [`${timelineBase.segments.length} 个片段`]);
      }
      refreshGuidedFeedbacks();
      switchPanel("cut");
      status.textContent = "已载入复剪任务，请调整要求后重新生成剪辑标准";
    }

    async function appendRecutRequest(button = null) {
      const text = $("recutRequest").value.trim();
      if (!text) return;
      $("userRequest").value = `${$("userRequest").value.trim()}\n复剪要求：${text}`;
      markBriefStale();
      const outputDir = String(activeProjectOutputDir || $("outputDir").value || "").trim();
      const baseVersion = Number(activeProjectManifest?.version_history?.current_version || 0);
      if (outputDir && baseVersion > 0) {
        await withButtonState(button, "创建中", async () => {
          const payload = await requestJson("/api/repair-dialogue", {
            output_dir: outputDir,
            base_version: baseVersion,
            user_feedback: text,
            timeline_edits: [],
            execute_real_render: false
          }, {silent: true});
          resultDetails.textContent = JSON.stringify(payload, null, 2);
          if (payload.ok) {
            status.textContent = `返修版本 v${payload.new_version} 已创建`;
            await loadProjectVersionCenter(outputDir, null);
            await loadProjectLibrary(null);
          } else {
            status.textContent = payload.error || "返修版本创建失败，已先加入剪辑目标";
          }
          return payload;
        });
      }
      switchPanel("cut");
    }

    async function analyzeTemplateVideo(button = null) {
      const templateVideo = $("templateVideo").value.trim();
      if (!templateVideo) {
        status.textContent = "请先选择参考视频";
        return null;
      }
      return withButtonState(button, "分析中", async () => {
        const outputDir = $("packageDir").value.trim()
          ? `${$("packageDir").value.trim()}\\assets\\reference_analysis`
          : "";
        const payload = await requestJson("/api/template/analyze", {
          template_video: templateVideo,
          output_dir: outputDir
        }, {silent: true});
        latestTemplateAnalysis = payload;
        renderTemplateAnalysis(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "样板视频分析完成" : "样板视频分析失败";
        return payload;
      });
    }

    function applyTemplateAnalysisSuggestions() {
      const analysis = latestTemplateAnalysis;
      const suggestions = analysis?.style_suggestions || {};
      if (!analysis || !analysis.ok) {
        status.textContent = "请先分析参考视频";
        return;
      }
      if (suggestions.video?.target_duration_seconds) setValue("pkgDuration", suggestions.video.target_duration_seconds);
      if (suggestions.video?.aspect_ratio) setValue("pkgAspect", suggestions.video.aspect_ratio);
      if (suggestions.video?.resolution) setValue("pkgResolution", suggestions.video.resolution);
      if (suggestions.subtitle?.font_size) setValue("pkgSubtitleSize", suggestions.subtitle.font_size);
      if (suggestions.audio?.bgm_volume_db !== undefined) setValue("pkgBgmVolume", suggestions.audio.bgm_volume_db);
      status.textContent = "已应用样板视频分析建议";
    }

    function renderTemplateAnalysis(payload) {
      const box = $("templateAnalysisResult");
      if (!box) return;
      if (!payload || !payload.ok) {
        box.innerHTML = `<div class="summary-item"><span class="chip warn">${escapeHtml(payload?.reason || "analysis_failed")}</span><span class="hint">参考视频暂不可分析。</span></div>`;
        return;
      }
      const video = payload.video || {};
      const rhythm = payload.rhythm || {};
      const subtitles = payload.subtitles || {};
      const cover = payload.cover || {};
      const bgm = payload.bgm || {};
      const warnings = payload.warnings || [];
      box.innerHTML = `
        <div class="summary-item">
          <strong>样板分析完成</strong>
          <div class="chip-row">
            <span class="chip ok">${escapeHtml(video.aspect_ratio || "比例未知")}</span>
            <span class="chip">${escapeHtml(video.resolution || `${video.width || 0}x${video.height || 0}`)}</span>
            <span class="chip">${escapeHtml(video.duration_seconds || 0)} 秒</span>
            <span class="chip">${escapeHtml(rhythm.tempo_label || "medium")} / ${escapeHtml(rhythm.estimated_bpm || 0)} BPM</span>
          </div>
        </div>
        <div class="summary-item"><strong>字幕建议</strong><span>${escapeHtml(subtitles.mode || "auto")}，字号 ${escapeHtml(subtitles.style?.font_size || "")}，描边 ${escapeHtml(subtitles.style?.outline_width || "")}</span></div>
        <div class="summary-item"><strong>封面建议</strong><span>${escapeHtml(cover.title_suggestion || "参考视频")} @ ${escapeHtml(cover.suggested_timestamp_seconds || 0)}s</span><span class="path-text">${escapeHtml(cover.extracted_frame_path || "未抽取封面帧")}</span></div>
        <div class="summary-item"><strong>BGM 建议</strong><span>${escapeHtml(bgm.bgm_style || "clean_vlog")}，音量 ${escapeHtml(bgm.bgm_volume_db || -18)} dB，${bgm.has_audio ? "检测到参考音轨" : "未检测到音轨"}</span></div>
        <div class="summary-item"><strong>节奏模板</strong><span>${escapeHtml(rhythm.suggested_segment_count || 0)} 个片段，建议切点间隔 ${escapeHtml(rhythm.cut_interval_seconds || 0)} 秒</span></div>
        ${warnings.map((item) => `<div class="summary-item"><span class="chip warn">${escapeHtml(item.code || "warning")}</span><span>${escapeHtml(item.message || "")}</span></div>`).join("")}
      `;
    }

    async function createPackage(button = null) {
      return withButtonState(button, "提取中", async () => {
        status.textContent = "正在提取风格包";
        const payload = await requestJson("/api/style-packages", {
          name: $("pkgName").value,
          template_video: $("templateVideo").value,
          package_dir: $("packageDir").value,
          description: $("packageDescription").value,
          duration: Number($("pkgDuration").value),
          aspect_ratio: $("pkgAspect").value,
          resolution: $("pkgResolution").value,
          quality: $("pkgQuality").value,
          subtitle_size: Number($("pkgSubtitleSize").value),
          bgm_volume_db: Number($("pkgBgmVolume").value),
          voice_provider: $("voiceProvider").value
        });
        status.textContent = payload.ok ? "风格包已保存" : "风格包保存失败";
        if (payload.package?.reference_analysis) {
          latestTemplateAnalysis = payload.package.reference_analysis;
          renderTemplateAnalysis(latestTemplateAnalysis);
        }
        await loadPackages();
        return payload;
      });
    }

    async function exportProjectPack(button = null) {
      return withButtonState(button, "导出中", async () => {
        const outputDir = $("projectPackOutputDir").value.trim() || activeProjectOutputDir || $("outputDir").value.trim();
        const packageDir = $("projectPackDir").value.trim();
        if (!outputDir || !packageDir) {
          status.textContent = "请填写来源输出目录和项目包目录";
          return null;
        }
        const payload = await requestJson("/api/packs/project/export", {
          name: $("projectPackName").value.trim(),
          output_dir: outputDir,
          package_dir: packageDir
        }, {silent: true});
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        if (payload?.ok) {
          $("projectPackPath").value = packageDir;
          loadedProjectPack = payload.pack;
          resolvedProjectPack = null;
          renderProjectPackPreview(payload.pack, null);
          await loadPackages();
        }
        status.textContent = payload?.ok ? "项目包已导出" : "项目包导出失败";
        return payload;
      });
    }

    async function loadProjectPack(button = null) {
      return withButtonState(button, "载入中", async () => {
        const path = $("projectPackPath").value.trim();
        if (!path) {
          status.textContent = "请填写项目包路径";
          return null;
        }
        const payload = await requestJson(`/api/packs/load?path=${encodeURIComponent(path)}`, null, {silent: true});
        if (!payload?.pack) {
          renderProjectPackPreview(null, null, payload?.error || "项目包载入失败");
          resultDetails.textContent = JSON.stringify(payload, null, 2);
          return payload;
        }
        loadedProjectPack = payload.pack;
        const resolved = await requestJson("/api/packs/resolve", {project_pack: loadedProjectPack}, {silent: true});
        resolvedProjectPack = resolved?.resolved || null;
        renderProjectPackPreview(loadedProjectPack, resolvedProjectPack);
        resultDetails.textContent = JSON.stringify({loaded: payload, resolved}, null, 2);
        status.textContent = "项目包已载入";
        return {loaded: payload, resolved};
      });
    }

    function renderProjectPackPreview(pack, resolved, emptyText = "未载入项目包。") {
      const box = $("projectPackPreview");
      if (!box) return;
      if (!pack) {
        box.innerHTML = `<div class="summary-item"><span class="hint">${escapeHtml(emptyText)}</span></div>`;
        return;
      }
      const versionHistory = pack.version_history || resolved?.version_history || {};
      const manifest = pack.project_manifest || resolved?.project_manifest || {};
      const artifactRefs = pack.artifact_refs || resolved?.artifact_refs || {};
      const timeline = pack.timeline_plan || resolved?.timeline_plan || {};
      box.innerHTML = `
        <div class="summary-item">
          <strong>${escapeHtml(pack.name || "项目包")}</strong>
          <span class="path-text">${escapeHtml(pack.source_output_dir || pack.output_dir || "")}</span>
          <div class="chip-row">
            <span class="chip">${escapeHtml((pack.input_videos || []).length)} 个素材</span>
            <span class="chip">v${escapeHtml(versionHistory.current_version || 0)}</span>
            <span class="chip">${escapeHtml(versionHistory.versions?.length || versionHistory.version_count || 0)} 个版本</span>
            <span class="chip">${escapeHtml((timeline.segments || []).length || 0)} 个片段</span>
          </div>
        </div>
        <div class="summary-item"><strong>风格包引用</strong><span class="path-text">${escapeHtml(pack.style_pack_ref || manifest.style_package?.path || "未记录")}</span></div>
        <div class="summary-item"><strong>成片引用</strong><span class="path-text">${escapeHtml(artifactRefs.copied_output_video || "未记录")}</span></div>
      `;
    }

    async function applyLoadedProjectPack(button = null) {
      if (!loadedProjectPack) {
        status.textContent = "请先载入项目包";
        return null;
      }
      return withButtonState(button, "应用中", async () => {
        if (!resolvedProjectPack) {
          const payload = await requestJson("/api/packs/resolve", {project_pack: loadedProjectPack}, {silent: true});
          resolvedProjectPack = payload?.resolved || null;
        }
        const resolved = resolvedProjectPack || {};
        const manifest = resolved.project_manifest || loadedProjectPack.project_manifest || {};
        const styleRef = loadedProjectPack.style_pack_ref || manifest.style_package?.path || "";
        if (styleRef) setValue("stylePackage", styleRef);
        inputVideos = Array.isArray(resolved.input_videos) && resolved.input_videos.length
          ? resolved.input_videos
          : (loadedProjectPack.input_videos || []);
        if (inputVideos.length) setValue("inputVideo", inputVideos[0]);
        renderInputVideos();
        const outputDir = resolved.output_dir || loadedProjectPack.output_dir || "";
        setValue("outputDir", outputDir ? `${outputDir}_imported` : "");
        const latestResult = manifest.latest_result || {};
        if (latestResult.user_request) setValue("userRequest", latestResult.user_request);
        if (latestResult.confirmed_brief) setValue("briefText", latestResult.confirmed_brief);
        markBriefStale();
        const timeline = resolved.timeline_plan || loadedProjectPack.timeline_plan || {};
        if (timeline.segments && timeline.segments.length) {
          timelineBase = timeline;
          timelineOverride = timeline;
          renderTimeline(timelineBase, []);
          $("applyTimelineButton").disabled = true;
          renderTimelineState("ok", "已载入项目包时间线", [`${timelineBase.segments.length} 个片段`]);
        }
        activeProjectOutputDir = outputDir;
        activeProjectManifest = manifest;
        switchPanel("cut");
        status.textContent = "项目包已用于剪辑";
        return resolved;
      });
    }

    async function createWorkerTaskPackage(button = null) {
      return withButtonState(button, "生成中", async () => {
        const packageDir = $("workerPackageDir").value.trim();
        if (!packageDir) {
          status.textContent = "请先填写 Worker 任务包目录";
          return null;
        }
        const payload = collectEditPayload();
        status.textContent = "生成 Worker 任务包";
        const result = await requestJson("/api/worker/package", {
          package_dir: packageDir,
          package_name: $("workerPackageName").value,
          style_package: payload.style_package,
          input_video: payload.input_video,
          input_videos: payload.input_videos,
          output_dir: payload.output_dir,
          user_request: payload.user_request,
          project_id: payload.project_id,
          execute_real_render: payload.execute_real_render,
          allow_edge_tts: payload.allow_edge_tts,
          voiceover_text: payload.voiceover_text,
          use_memory: payload.use_memory,
          confirmed_brief: payload.confirmed_brief,
          settings_overrides: payload.settings_overrides,
          timeline_override: payload.timeline_override,
          task_id: payload.task_id
        });
        if (result?.package_path) $("workerPackagePath").value = result.package_path;
        latestWorkerTaskPackage = result?.task_package || null;
        renderWorkerTaskPreview(result);
        status.textContent = result?.ok ? "Worker 任务包已生成" : "生成 Worker 任务包失败";
        return result;
      });
    }

    async function loadWorkerTaskPackage(button = null) {
      return withButtonState(button, "载入中", async () => {
        const packagePath = $("workerPackagePath").value.trim();
        if (!packagePath) {
          status.textContent = "请先填写 Worker 任务包路径";
          return null;
        }
        const payload = await requestJson("/api/worker/package/load", {package_path: packagePath}, {silent: true});
        latestWorkerTaskPackage = payload?.task_package || null;
        latestWorkerCompletion = payload?.completion || null;
        renderWorkerTaskPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "Worker 任务包已载入" : "Worker 任务包载入失败";
        return payload;
      });
    }

    async function runWorkerTaskPackage(button = null) {
      return withButtonState(button, "执行中", async () => {
        const packagePath = $("workerPackagePath").value.trim();
        if (!packagePath) {
          status.textContent = "请先填写 Worker 任务包路径";
          return null;
        }
        status.textContent = "执行 Worker 任务包";
        const payload = await requestJson("/api/worker/run", {package_path: packagePath}, {silent: true});
        latestWorkerCompletion = payload;
        renderWorkerTaskPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "Worker 任务包执行完成" : "Worker 任务包执行失败";
        return payload;
      });
    }

    function renderWorkerTaskPreview(payload) {
      const box = $("workerTaskPreview");
      if (!box) return;
      const packagePayload = payload?.task_package || latestWorkerTaskPackage || {};
      const completion = payload?.schema === "smart_video_cut.local.worker_completion.v0"
        ? payload
        : (payload?.completion || latestWorkerCompletion || {});
      if (!packagePayload || !Object.keys(packagePayload).length) {
        box.innerHTML = `<div class="summary-item"><span class="hint">还没有 Worker 任务包。</span></div>`;
        return;
      }
      const task = packagePayload.task || {};
      const inputVideos = task.input_videos || [];
      box.innerHTML = `
        <div class="summary-item">
          <strong>${escapeHtml(packagePayload.package_id || "Worker 任务包")}</strong>
          <span class="path-text">${escapeHtml(payload?.package_path || $("workerPackagePath").value || "")}</span>
          <div class="chip-row">
            <span class="chip">${escapeHtml(task.execute_real_render ? "真实渲染" : "计划模式")}</span>
            <span class="chip">${escapeHtml(inputVideos.length || 0)} 个素材</span>
            <span class="chip">${escapeHtml(task.project_id || "local_project")}</span>
          </div>
        </div>
        <div class="summary-item"><strong>风格包</strong><span class="path-text">${escapeHtml(task.style_package || "")}</span></div>
        <div class="summary-item"><strong>输出目录</strong><span class="path-text">${escapeHtml(task.output_dir || "")}</span></div>
        <div class="summary-item"><strong>任务要求</strong><span class="hint">${escapeHtml(task.user_request || "")}</span></div>
        <div class="summary-item">
          <strong>completion</strong>
          <span class="chip ${completion.ok ? "ok" : completion.status ? "warn" : ""}">${escapeHtml(completion.status || "未执行")}</span>
          <span class="path-text">${escapeHtml(completion.completion_path || "")}</span>
          ${completion.copied_output_video ? `<div class="path-text">${escapeHtml(completion.copied_output_video)}</div>` : ""}
          ${completion.error ? `<span class="hint">${escapeHtml(completion.error)}</span>` : ""}
        </div>
      `;
      if (task.output_dir) $("protocolOutputDir").value = task.output_dir;
      if (completion.output_dir && !$("protocolOutputDir").value) $("protocolOutputDir").value = completion.output_dir;
    }

    async function buildLocalToolkitProtocol(button = null) {
      return withButtonState(button, "生成中", async () => {
        const outputDir = $("protocolOutputDir").value.trim() || activeProjectOutputDir || $("outputDir").value.trim();
        if (!outputDir) {
          status.textContent = "请先填写输出目录";
          return null;
        }
        $("protocolOutputDir").value = outputDir;
        const payload = await requestJson("/api/protocol/build", {output_dir: outputDir}, {silent: true});
        latestProtocolInspection = payload;
        if (payload?.protocol_path) $("protocolInspectPath").value = payload.protocol_path;
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "本地协议清单已生成" : "本地协议清单已生成，但仍有缺项";
        return payload;
      });
    }

    async function inspectLocalToolkitProtocol(button = null) {
      return withButtonState(button, "检查中", async () => {
        const path = $("protocolInspectPath").value.trim();
        if (!path) {
          status.textContent = "请先填写协议文件或目录路径";
          return null;
        }
        const payload = await requestJson("/api/protocol/inspect", {path}, {silent: true});
        latestProtocolInspection = payload;
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "本地协议检查完成" : "本地协议检查失败";
        return payload;
      });
    }

    async function runLocalProtocol(button = null) {
      return withButtonState(button, "执行中", async () => {
        const path = $("protocolInspectPath").value.trim();
        if (!path) {
          status.textContent = "请先填写协议文件或目录路径";
          return null;
        }
        const outputDir = $("protocolOutputDir").value.trim();
        const payload = await requestJson("/api/protocol/run", {
          path,
          output_dir: outputDir,
          style_package: $("stylePackage").value,
          user_request: $("userRequest").value,
          voiceover_text: $("voiceProvider").value === "none" ? null : $("voiceoverText").value || null,
          confirmed_brief: $("briefText").value || null,
          execute_real_render: $("executeReal").checked,
          allow_edge_tts: $("allowEdge").checked,
          use_memory: $("useMemory").checked
        }, {silent: true});
        if (payload?.output_dir) $("protocolOutputDir").value = payload.output_dir;
        if (payload?.local_toolkit_protocol_path) $("protocolInspectPath").value = payload.local_toolkit_protocol_path;
        latestResult = payload?.schema === "smart_video_cut.local.edit_result.v0" ? payload : latestResult;
        latestWorkerCompletion = payload?.schema === "smart_video_cut.local.worker_completion.v0" ? payload : latestWorkerCompletion;
        renderPayload(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "协议执行完成" : "协议执行失败";
        return payload;
      });
    }

    async function initProtocolDropbox(button = null) {
      return withButtonState(button, "初始化中", async () => {
        const dropboxDir = $("protocolDropboxDir").value.trim();
        const payload = await requestJson("/api/protocol/dropbox/init", {
          dropbox_dir: dropboxDir
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        if (payload?.manifest_path) $("protocolInspectPath").value = payload.manifest_path;
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "标准协议投递箱已初始化" : "标准协议投递箱初始化失败";
        return payload;
      });
    }

    async function importProtocolDropboxItem(button = null) {
      return withButtonState(button, "投递中", async () => {
        const sourcePath = $("protocolDropboxSourcePath").value.trim();
        if (!sourcePath) {
          status.textContent = "请先选择来源协议文件或目录";
          return null;
        }
        const payload = await requestJson("/api/protocol/dropbox/import", {
          dropbox_dir: $("protocolDropboxDir").value.trim(),
          source_path: sourcePath,
          label: $("protocolDropboxLabel").value.trim()
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        if (payload?.imported_path) $("protocolInspectPath").value = payload.imported_path;
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "协议已投递到标准队列" : "协议投递失败";
        return payload;
      });
    }

    async function runProtocolDropbox(button = null) {
      return withButtonState(button, "执行中", async () => {
        const payload = await requestJson("/api/protocol/dropbox/run", {
          dropbox_dir: $("protocolDropboxDir").value.trim(),
          default_execute_real_render: $("executeReal").checked,
          max_retries: 0,
          stop_on_error: false,
          dry_run: false
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.ok ? "标准协议投递箱执行完成" : "标准协议投递箱执行有异常";
        return payload;
      });
    }

    function syncProtocolDropboxFieldsFromPayload(payload) {
      if (payload?.dropbox_dir) $("protocolDropboxDir").value = payload.dropbox_dir;
      if (payload?.manifest_path && !$("protocolInspectPath").value.trim()) $("protocolInspectPath").value = payload.manifest_path;
      if (payload?.monitor_path && payload.running) $("protocolInspectPath").value = payload.monitor_path;
      if (payload?.status_path && !payload.running) $("protocolInspectPath").value = payload.status_path;
      if (payload?.interval_seconds !== undefined && payload?.interval_seconds !== null) $("protocolDropboxInterval").value = Number(payload.interval_seconds);
      if (payload?.max_cycles !== undefined && payload?.max_cycles !== null) $("protocolDropboxMaxCycles").value = Number(payload.max_cycles);
    }

    function setProtocolDropboxMonitorPolling(enabled) {
      if (protocolDropboxMonitorPoller) {
        clearInterval(protocolDropboxMonitorPoller);
        protocolDropboxMonitorPoller = null;
      }
      if (!enabled) return;
      protocolDropboxMonitorPoller = setInterval(() => {
        refreshProtocolDropboxMonitor(null, true).catch(() => {});
      }, 5000);
    }

    async function startProtocolDropboxMonitor(button = null) {
      return withButtonState(button, "启动中", async () => {
        const payload = await requestJson("/api/protocol/dropbox/monitor/start", {
          dropbox_dir: $("protocolDropboxDir").value.trim(),
          interval_seconds: Number($("protocolDropboxInterval").value || 15),
          max_cycles: Number($("protocolDropboxMaxCycles").value || 0),
          default_execute_real_render: $("executeReal").checked,
          stop_on_error: false,
          max_retries: 0,
          dry_run: false
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        setProtocolDropboxMonitorPolling(Boolean(payload?.running));
        status.textContent = payload.running ? "标准协议投递箱已启动自动轮询" : "标准协议投递箱未进入轮询状态";
        return payload;
      });
    }

    async function stopProtocolDropboxMonitor(button = null) {
      return withButtonState(button, "停止中", async () => {
        const payload = await requestJson("/api/protocol/dropbox/monitor/stop", {
          dropbox_dir: $("protocolDropboxDir").value.trim()
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        setProtocolDropboxMonitorPolling(Boolean(payload?.running));
        status.textContent = payload.running ? "停止请求已发送，轮询仍在收尾" : "标准协议投递箱自动轮询已停止";
        return payload;
      });
    }

    async function refreshProtocolDropboxMonitor(button = null, silent = false) {
      const run = async () => {
        const payload = await requestJson("/api/protocol/dropbox/monitor/status", {
          dropbox_dir: $("protocolDropboxDir").value.trim()
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        setProtocolDropboxMonitorPolling(Boolean(payload?.running));
        if (!silent) {
          status.textContent = payload.running ? "标准协议投递箱正在自动轮询" : "标准协议投递箱看板已刷新";
        }
        return payload;
      };
      if (!button) return run();
      return withButtonState(button, "刷新中", run);
    }

    async function loadProtocolDropboxHistory(button = null) {
      return withButtonState(button, "加载中", async () => {
        const payload = await requestJson("/api/protocol/dropbox/history", {
          dropbox_dir: $("protocolDropboxDir").value.trim(),
          limit: Number($("protocolDropboxHistoryLimit").value || 10),
          queue_id: normalizeDropboxQueueId($("protocolDropboxRequeueQueue").value),
          alerts_only: $("protocolDropboxAlertsOnly").checked
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        if (payload?.history_path) $("protocolInspectPath").value = payload.history_path;
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = "标准协议投递箱历史已加载";
        return payload;
      });
    }

    async function requeueProtocolDropboxFailed(button = null) {
      return withButtonState(button, "回投中", async () => {
        const payload = await requestJson("/api/protocol/dropbox/requeue-failed", {
          dropbox_dir: $("protocolDropboxDir").value.trim(),
          queue_id: normalizeDropboxQueueId($("protocolDropboxRequeueQueue").value),
          max_files: Number($("protocolDropboxRequeueMaxFiles").value || 20)
        }, {silent: true});
        latestProtocolInspection = payload;
        syncProtocolDropboxFieldsFromPayload(payload);
        renderProtocolPreview(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        status.textContent = payload.moved_count > 0 ? "失败文件已回投到标准队列" : "没有可回投的失败文件";
        return payload;
      });
    }

    function renderProtocolPreview(payload) {
      const box = $("protocolPreview");
      if (!box) return;
      if (!payload) {
        box.innerHTML = `<div class="summary-item"><span class="hint">还没有协议检查结果。</span></div>`;
        return;
      }
      if (payload.schema === "smart_video_cut.local.toolkit_protocol.v0") {
        const artifacts = payload.artifacts || [];
        const warnings = payload.warnings || [];
        box.innerHTML = `
          <div class="summary-item">
            <strong>${escapeHtml(payload.project_id || "local_project")}</strong>
            <span class="path-text">${escapeHtml(payload.protocol_path || payload.output_dir || "")}</span>
            <div class="chip-row">
              <span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(payload.status || "unknown")}</span>
              <span class="chip">${escapeHtml(payload.execution_mode || "plan_only")}</span>
              <span class="chip">${escapeHtml(artifacts.length || 0)} 个引用</span>
            </div>
          </div>
          <div class="summary-item"><strong>输出目录</strong><span class="path-text">${escapeHtml(payload.output_dir || "")}</span></div>
          <div class="summary-item"><strong>协议能力</strong><span class="hint">Worker、ProjectPack 导出、外部导入、协议检查统一入口已写入 contracts。</span></div>
          <div class="summary-item"><strong>告警</strong><span class="path-text">${escapeHtml(warnings.length ? warnings.map((item) => item.message || item.code).join("；") : "无")}</span></div>
        `;
        return;
      }
      if (payload.schema === "smart_video_cut.local.protocol_dropbox.v0") {
        const queues = Object.values(payload.queues || {});
        const templates = Object.values(payload.templates || {});
        box.innerHTML = `
          <div class="summary-item">
            <strong>标准协议投递箱</strong>
            <span class="path-text">${escapeHtml(payload.dropbox_dir || "")}</span>
            <div class="chip-row">
              <span class="chip ok">${escapeHtml(payload.queue_count || queues.length || 0)} 个队列</span>
              <span class="chip">${escapeHtml(templates.length || 0)} 个模板</span>
            </div>
          </div>
          <div class="summary-item"><strong>清单文件</strong><span class="path-text">${escapeHtml(payload.manifest_path || "")}</span></div>
          <div class="summary-item"><strong>命名规则</strong><span class="hint">${escapeHtml(payload.naming_rule || "")}</span></div>
        `;
        return;
      }
      if (payload.schema === "smart_video_cut.local.protocol_dropbox_import.v0") {
        box.innerHTML = `
          <div class="summary-item">
            <strong>${escapeHtml(payload.queue_label || payload.queue_id || "标准协议队列")}</strong>
            <span class="path-text">${escapeHtml(payload.imported_path || "")}</span>
            <div class="chip-row">
              <span class="chip ok">${escapeHtml(payload.protocol_kind || "protocol")}</span>
              <span class="chip">${escapeHtml(payload.normalized ? "已标准化" : "原样复制")}</span>
            </div>
          </div>
          <div class="summary-item"><strong>来源</strong><span class="path-text">${escapeHtml(payload.resolved_source_path || payload.source_path || "")}</span></div>
          ${payload.normalized_reason ? `<div class="summary-item"><strong>标准化原因</strong><span class="hint">${escapeHtml(payload.normalized_reason)}</span></div>` : ""}
        `;
        return;
      }
      if (payload.schema === "smart_video_cut.local.protocol_dropbox_run.v0") {
        const queues = payload.queues || [];
        const alerts = payload.alerts || [];
        const queueHtml = queues.map((queue) => `
          <div class="summary-item">
            <strong>${escapeHtml(queue.label || queue.queue_id || "队列")}</strong>
            <span class="path-text">${escapeHtml(queue.watch_dir || "")}</span>
            <div class="chip-row">
              <span class="chip ${queue.ok ? "ok" : "warn"}">${escapeHtml(queue.protocol_kind || queue.queue_id || "queue")}</span>
              <span class="chip">file ${escapeHtml(queue.file_count || 0)}</span>
              <span class="chip">done ${escapeHtml(queue.processed_count || 0)}</span>
              <span class="chip">fail ${escapeHtml(queue.failed_count || 0)}</span>
            </div>
          </div>
        `).join("");
        box.innerHTML = `
          <div class="summary-item">
            <strong>标准协议投递箱运行</strong>
            <span class="path-text">${escapeHtml(payload.dropbox_dir || "")}</span>
            <div class="chip-row">
              <span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(payload.status || "unknown")}</span>
              <span class="chip">queue ${escapeHtml(payload.queue_count || queues.length || 0)}</span>
              <span class="chip">done ${escapeHtml(payload.processed_count || 0)}</span>
              <span class="chip">fail ${escapeHtml(payload.failed_count || 0)}</span>
              <span class="chip ${payload.alert_level === "warn" ? "warn" : ""}">alert ${escapeHtml(payload.alert_count || alerts.length || 0)}</span>
            </div>
          </div>
          <div class="summary-item"><strong>状态文件</strong><span class="path-text">${escapeHtml(payload.status_path || "")}</span></div>
          ${payload.history_path ? `<div class="summary-item"><strong>历史文件</strong><span class="path-text">${escapeHtml(payload.history_path)}</span></div>` : ""}
          <div class="summary-item"><strong>告警摘要</strong><span class="hint">${escapeHtml(alerts.length ? alerts.map((item) => item.message || item.code || "alert").join("；") : "无")}</span></div>
          ${queueHtml || `<div class="summary-item"><span class="hint">当前没有队列结果。</span></div>`}
        `;
        return;
      }
      if (payload.schema === "smart_video_cut.local.protocol_dropbox_monitor.v0") {
        const totals = payload.totals || {};
        const lastRun = payload.last_run || {};
        const recentRuns = payload.recent_runs || [];
        const activeAlerts = payload.active_alerts || [];
        const recentHtml = recentRuns.slice(-3).reverse().map((run) => `
          <div class="summary-item">
            <strong>第 ${escapeHtml(run.cycle_index || 0)} 轮</strong>
            <span class="path-text">${escapeHtml(run.status_path || "")}</span>
            <div class="chip-row">
              <span class="chip ${run.ok ? "ok" : "warn"}">${escapeHtml(run.status || (run.ok ? "completed" : "failed"))}</span>
              <span class="chip">done ${escapeHtml(run.processed_count || 0)}</span>
              <span class="chip">fail ${escapeHtml(run.failed_count || 0)}</span>
              <span class="chip ${run.alert_level === "warn" ? "warn" : ""}">alert ${escapeHtml(run.alert_count || 0)}</span>
            </div>
          </div>
        `).join("");
        box.innerHTML = `
          <div class="summary-item">
            <strong>标准协议投递箱自动轮询</strong>
            <span class="path-text">${escapeHtml(payload.monitor_path || payload.dropbox_dir || "")}</span>
            <div class="chip-row">
              <span class="chip ${payload.running ? "ok" : payload.ok ? "" : "warn"}">${escapeHtml(payload.status || "idle")}</span>
              <span class="chip">interval ${escapeHtml(payload.interval_seconds || 0)}s</span>
              <span class="chip">cycle ${escapeHtml(payload.completed_cycles || 0)}</span>
              <span class="chip ${payload.last_alert_level === "warn" ? "warn" : ""}">alert ${escapeHtml(payload.alert_count || activeAlerts.length || 0)}</span>
            </div>
          </div>
          <div class="summary-item"><strong>累计处理</strong><span class="hint">file ${escapeHtml(totals.file_count || 0)} | queued ${escapeHtml(totals.queued_count || 0)} | done ${escapeHtml(totals.processed_count || 0)} | fail ${escapeHtml(totals.failed_count || 0)}</span></div>
          ${payload.history_path ? `<div class="summary-item"><strong>历史文件</strong><span class="path-text">${escapeHtml(payload.history_path)}</span></div>` : ""}
          <div class="summary-item"><strong>当前告警</strong><span class="hint">${escapeHtml(activeAlerts.length ? activeAlerts.map((item) => item.message || item.code || "alert").join("；") : "无")}</span></div>
          ${lastRun?.status ? `<div class="summary-item"><strong>最近一轮</strong><span class="hint">第 ${escapeHtml(lastRun.cycle_index || 0)} 轮，状态 ${escapeHtml(lastRun.status || "")}，输出 done ${escapeHtml(lastRun.processed_count || 0)} / fail ${escapeHtml(lastRun.failed_count || 0)}</span></div>` : ""}
          ${recentHtml || `<div class="summary-item"><span class="hint">还没有轮询记录。</span></div>`}
        `;
        return;
      }
      if (payload.schema === "smart_video_cut.local.protocol_dropbox_history.v0") {
        const entries = payload.entries || [];
        const entryHtml = entries.slice(0, 5).map((entry) => `
          <div class="summary-item">
            <strong>${escapeHtml(entry.run_id || "dropbox_run")}</strong>
            <span class="path-text">${escapeHtml(entry.status_path || payload.history_path || "")}</span>
            <div class="chip-row">
              <span class="chip ${entry.ok ? "ok" : "warn"}">${escapeHtml(entry.status || (entry.ok ? "completed" : "completed_with_errors"))}</span>
              <span class="chip">done ${escapeHtml(entry.processed_count || 0)}</span>
              <span class="chip">fail ${escapeHtml(entry.failed_count || 0)}</span>
              <span class="chip ${entry.alert_level === "warn" ? "warn" : ""}">alert ${escapeHtml(entry.alert_count || 0)}</span>
            </div>
          </div>
        `).join("");
        box.innerHTML = `
          <div class="summary-item">
            <strong>标准协议投递箱运行历史</strong>
            <span class="path-text">${escapeHtml(payload.history_path || payload.dropbox_dir || "")}</span>
            <div class="chip-row">
              <span class="chip">run ${escapeHtml(payload.run_count || entries.length || 0)}</span>
              <span class="chip ${payload.last_alert_level === "warn" ? "warn" : ""}">alert entry ${escapeHtml(payload.alert_entry_count || 0)}</span>
              <span class="chip">${escapeHtml(payload.queue_id || "all")}</span>
            </div>
          </div>
          <div class="summary-item"><strong>筛选</strong><span class="hint">${escapeHtml(payload.alerts_only ? "仅告警历史" : "全部历史")}</span></div>
          ${entryHtml || `<div class="summary-item"><span class="hint">还没有运行历史。</span></div>`}
        `;
        return;
      }
      if (payload.schema === "smart_video_cut.local.protocol_dropbox_requeue.v0") {
        const entries = payload.entries || [];
        const queueHtml = (payload.queues || []).map((queue) => `
          <div class="summary-item">
            <strong>${escapeHtml(queue.label || queue.queue_id || "队列")}</strong>
            <span class="path-text">${escapeHtml(queue.watch_dir || "")}</span>
            <div class="chip-row">
              <span class="chip">${escapeHtml(queue.queue_id || "queue")}</span>
              <span class="chip">moved ${escapeHtml(queue.moved_count || 0)}</span>
            </div>
          </div>
        `).join("");
        const movedHtml = entries.slice(0, 5).map((entry) => `
          <div class="summary-item">
            <strong>${escapeHtml(entry.filename || entry.queue_id || "requeued")}</strong>
            <span class="path-text">${escapeHtml(entry.requeued_path || "")}</span>
          </div>
        `).join("");
        box.innerHTML = `
          <div class="summary-item">
            <strong>协议投递箱失败回投</strong>
            <span class="path-text">${escapeHtml(payload.dropbox_dir || "")}</span>
            <div class="chip-row">
              <span class="chip ${payload.moved_count > 0 ? "ok" : ""}">moved ${escapeHtml(payload.moved_count || 0)}</span>
              <span class="chip">${escapeHtml(payload.queue_id || "all")}</span>
              <span class="chip">limit ${escapeHtml(payload.max_files || 0)}</span>
            </div>
          </div>
          ${queueHtml || `<div class="summary-item"><span class="hint">没有队列摘要。</span></div>`}
          ${movedHtml || `<div class="summary-item"><span class="hint">当前没有回投文件。</span></div>`}
        `;
        return;
      }
      if (payload.schema === "smart_video_cut.local.toolkit_protocol_inspection.v0") {
        const summary = payload.summary || {};
        const validation = payload.validation || {};
        const warnings = validation.warnings || [];
        const errors = validation.errors || [];
        const entries = payload.entries || [];
        const summaryText = Object.entries(summary).slice(0, 5).map(([key, value]) => `${key}: ${value}`).join(" | ");
        const entryHtml = entries.length ? entries.map((entry) => `
          <div class="summary-item">
            <strong>${escapeHtml(entry.label || entry.protocol_kind || "协议条目")}</strong>
            <span class="path-text">${escapeHtml(entry.path || "")}</span>
            <div class="chip-row">
              <span class="chip ${entry.ok ? "ok" : "warn"}">${escapeHtml(entry.protocol_kind || "entry")}</span>
              <span class="chip">warn ${escapeHtml(entry.warning_count || 0)}</span>
              <span class="chip">err ${escapeHtml(entry.error_count || 0)}</span>
            </div>
          </div>
        `).join("") : "";
        box.innerHTML = `
          <div class="summary-item">
            <strong>${escapeHtml(payload.label || payload.protocol_kind || "协议检查结果")}</strong>
            <span class="path-text">${escapeHtml(payload.path || "")}</span>
            <div class="chip-row">
              <span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(payload.protocol_kind || "inspect")}</span>
              <span class="chip">warn ${escapeHtml(warnings.length || 0)}</span>
              <span class="chip">err ${escapeHtml(errors.length || 0)}</span>
            </div>
          </div>
          ${summaryText ? `<div class="summary-item"><strong>摘要</strong><span class="hint">${escapeHtml(summaryText)}</span></div>` : ""}
          ${entries.length ? `<div class="summary-item"><strong>目录识别</strong><span class="hint">识别到 ${escapeHtml(entries.length)} 个协议条目</span></div>${entryHtml}` : ""}
          ${errors.length ? `<div class="summary-item"><strong>错误</strong><span class="path-text">${escapeHtml(errors.map((item) => item.message || item.code).join("；"))}</span></div>` : ""}
          ${warnings.length ? `<div class="summary-item"><strong>提示</strong><span class="path-text">${escapeHtml(warnings.map((item) => item.message || item.code).join("；"))}</span></div>` : ""}
        `;
        return;
      }
      box.innerHTML = `<div class="summary-item"><span class="hint">当前结果不是协议清单或协议检查结果。</span></div>`;
    }

    function collectMemory() {
      const tags = $("memoryTags").value.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean);
      return {
        memory_type: $("memoryType").value,
        title: $("memoryTitle").value,
        content: $("memoryContent").value,
        tags,
        source: "manual_ui",
        importance: Number($("memoryImportance").value),
        enabled: $("memoryEnabled").checked
      };
    }

    async function saveMemory(button = null) {
      return withButtonState(button, "保存中", async () => {
        status.textContent = "保存本地记忆";
        const payload = await requestJson("/api/memory", collectMemory());
        status.textContent = payload.ok ? "本地记忆已保存" : "保存失败";
        if (payload.ok) {
          $("memoryTitle").value = "";
          $("memoryContent").value = "";
          $("memoryTags").value = "";
          await loadMemory();
        }
        return payload;
      });
    }

    async function saveFeedbackMemory(button = null) {
      return withButtonState(button, "保存中", async () => {
        status.textContent = "保存反馈记忆";
        const payload = await requestJson("/api/memory/feedback", {
          project_id: $("feedbackProjectId").value,
          output_dir: $("feedbackOutputDir").value,
          feedback: $("feedbackText").value,
          rating: Number($("feedbackRating").value)
        });
        status.textContent = payload.ok ? "反馈记忆已保存" : "保存失败";
        if (payload.ok) {
          $("feedbackText").value = "";
          await loadMemory();
        }
        return payload;
      });
    }

    function applyModelPreset() {
      const profile = $("llmProfile").value;
      if (profile === "visual_review_recommended") {
        $("llmCapability").value = "multimodal_text_image";
        $("llmProvider").value = "openai_compatible";
        $("llmBaseUrl").value = "https://api.openai.com/v1";
        $("allowCloudText").checked = true;
        $("allowMediaUpload").checked = true;
        $("llmModel").placeholder = "填入支持图像/视觉输入的多模态模型";
      }
      if (profile === "text_only_budget") {
        $("llmCapability").value = "text_only";
        $("allowCloudText").checked = true;
        $("allowMediaUpload").checked = false;
        $("llmModel").placeholder = "填入文本模型，不能直接看画面";
      }
      if (profile === "local_first") {
        $("llmCapability").value = "local_text_or_vision";
        $("llmProvider").value = "local_ollama";
        $("llmBaseUrl").value = "http://127.0.0.1:11434/v1";
        $("allowCloudText").checked = false;
        $("allowMediaUpload").checked = false;
        $("llmModel").placeholder = "填入本地模型名称";
      }
    }

    function collectLlmConfig() {
      return {
        provider: $("llmProvider").value,
        base_url: $("llmBaseUrl").value,
        model: $("llmModel").value,
        recommendation_profile: $("llmProfile").value,
        model_capability: $("llmCapability").value,
        api_key: $("llmApiKey").value,
        timeout_seconds: Number($("llmTimeout").value),
        temperature: Number($("llmTemperature").value),
        allow_cloud_llm_for_text_only: $("allowCloudText").checked,
        allow_media_upload_to_llm: $("allowMediaUpload").checked
      };
    }

    async function saveLlmConfig(button = null) {
      return withButtonState(button, "保存中", async () => {
        status.textContent = "保存大模型配置";
        const payload = await requestJson("/api/llm-config", collectLlmConfig());
        if (payload.ok) {
          $("llmApiKey").value = "";
          $("llmApiKey").placeholder = payload.config.api_key_set ? "已保存，留空则继续使用" : "请输入 API Key";
        }
        status.textContent = payload.ok ? "大模型配置已保存" : "保存失败";
        return payload;
      });
    }

    async function testLlmConfig(button = null) {
      return withButtonState(button, "测试中", async () => {
        status.textContent = "测试大模型连接";
        const payload = await requestJson("/api/llm-test", collectLlmConfig());
        renderMessage(
          payload.ok ? "模型连接成功" : "模型连接还没通过",
          payload.ok
            ? {
                summary: `已拿到 ${payload.model || "当前模型"} 的回复，可以继续用这套配置剪辑。`,
                chips: [
                  {label: payload.provider || "provider", tone: "ok"},
                  {label: payload.stage || "chat_completions", tone: "ok"},
                ],
                tips: [
                  "如果后面仍然想做本地优先，可以再去检测 Ollama 和读取本地模型。",
                ],
                detail: payload,
              }
            : {
                summary: humanizeProblemText(payloadProblemText(payload)) || "当前模型连接还没通过。",
                tips: [
                  "先检查模型名称、Base URL 和 API Key 是否匹配。",
                  "如果你使用本地模型，先确认本地服务已经启动。",
                ],
                actions: [
                  {label: "继续留在高级设置", code: "switchPanel('settings')", tone: "secondary"},
                ],
                detail: payload,
              },
          payload.ok ? "ok" : "warn"
        );
        status.textContent = payload.ok ? "大模型连接成功" : "大模型连接失败";
        return payload;
      });
    }

    function ollamaBaseUrl() {
      return $("llmBaseUrl").value || "http://127.0.0.1:11434";
    }

    async function checkOllamaStatus(button = null) {
      return withButtonState(button, "检测中", async () => {
        status.textContent = "检测 Ollama 本地服务";
        const params = new URLSearchParams({base_url: ollamaBaseUrl(), timeout_seconds: "3"});
        const payload = await requestJson(`/api/ollama/status?${params.toString()}`, null, {silent: true});
        renderOllamaStatus(payload);
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        renderMessage(
          payload.ok ? "Ollama 已就绪" : "Ollama 还没就绪",
          payload.ok
            ? {
                summary: `本地地址 ${payload.openai_base_url || payload.base_url || "http://127.0.0.1:11434/v1"} 可以正常访问。`,
                chips: [
                  {label: payload.version || "running", tone: "ok"},
                ],
                tips: [
                  "下一步可以直接点“读取本地模型”，确认有哪些可用模型。",
                ],
                detail: payload,
              }
            : {
                summary: humanizeProblemText(payloadProblemText(payload)) || "当前还连不上本地 Ollama 服务。",
                tips: [
                  "先启动 Ollama，再确认 11434 端口可以访问。",
                  "如果你暂时不用本地模型，也可以继续使用当前云端模型。",
                ],
                actions: [
                  {label: "继续留在高级设置", code: "switchPanel('settings')", tone: "secondary"},
                ],
                detail: payload,
              },
          payload.ok ? "ok" : "warn"
        );
        status.textContent = payload.ok ? "Ollama 已就绪" : "Ollama 未启动";
        return payload;
      });
    }

    async function loadOllamaModels(button = null) {
      return withButtonState(button, "读取中", async () => {
        status.textContent = "读取 Ollama 本地模型";
        const params = new URLSearchParams({base_url: ollamaBaseUrl(), timeout_seconds: "5"});
        const payload = await requestJson(`/api/ollama/models?${params.toString()}`, null, {silent: true});
        renderOllamaStatus(payload);
        renderOllamaModels(payload.models || [], payload.selected_model || "");
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        renderMessage(
          payload.ok ? "本地模型列表已刷新" : "还没读到本地模型",
          payload.ok
            ? {
                summary: `已读取 ${payload.model_count || 0} 个本地模型，建议先选一个再应用。`,
                chips: [
                  {label: `${payload.model_count || 0} 个模型`, tone: "ok"},
                  ...(payload.selected_model ? [{label: payload.selected_model, tone: "ok"}] : []),
                ],
                tips: [
                  payload.selected_model ? "如果这个模型就是你要用的，直接点“使用所选模型”。" : "如果没有默认选中项，先从下拉框里挑一个模型。",
                ],
                detail: payload,
              }
            : {
                summary: humanizeProblemText(payloadProblemText(payload)) || "当前还没有读到本地模型列表。",
                tips: [
                  "先确认 Ollama 本地服务已经启动。",
                  "如果还没有拉取模型，可以先在命令行执行 `ollama pull qwen2.5:7b` 这类命令。",
                ],
                actions: [
                  {label: "先检测 Ollama", code: "checkOllamaStatus()", tone: "secondary"},
                ],
                detail: payload,
              },
          payload.ok ? "ok" : "warn"
        );
        status.textContent = payload.ok ? `已读取 ${payload.model_count || 0} 个 Ollama 模型` : "读取 Ollama 模型失败";
        return payload;
      });
    }

    function renderOllamaModels(models, selectedModel = "") {
      const select = $("ollamaModelSelect");
      if (!models.length) {
        select.innerHTML = `<option value="">未发现本地模型</option>`;
        return;
      }
      select.innerHTML = models.map((model) => {
        const label = `${model.name}${model.parameter_size ? ` · ${model.parameter_size}` : ""}${model.is_vision_model ? " · vision" : ""}`;
        return `<option value="${escapeHtml(model.name)}" data-capability="${escapeHtml(model.model_capability || "text_only")}">${escapeHtml(label)}</option>`;
      }).join("");
      if (selectedModel) select.value = selectedModel;
      if (!$("llmModel").value && select.value) $("llmModel").value = select.value;
    }

    function renderOllamaStatus(payload) {
      const box = $("ollamaStatus");
      if (!box) return;
      const suggestions = (payload.pull_suggestions || []).map((item) =>
        `<div class="path-text">${escapeHtml(item.command || "")} · ${escapeHtml(item.purpose || "")}</div>`
      ).join("");
      const models = (payload.models || []).slice(0, 5).map((model) =>
        `<span class="chip">${escapeHtml(model.name || "")}</span>`
      ).join("");
      box.innerHTML = `
        <div class="summary-item">
          <strong>Ollama ${payload.ready || payload.ok ? "已就绪" : "未就绪"}</strong>
          <div class="chip-row">
            <span class="chip ${payload.ok ? "ok" : "warn"}">${escapeHtml(payload.reason || payload.stage || "status")}</span>
            ${payload.version ? `<span class="chip">版本 ${escapeHtml(payload.version)}</span>` : ""}
            ${payload.model_count !== undefined ? `<span class="chip">模型 ${escapeHtml(payload.model_count)}</span>` : ""}
          </div>
          <div class="path-text">${escapeHtml(payload.openai_base_url || payload.base_url || "")}</div>
          ${models ? `<div class="chip-row">${models}</div>` : ""}
          ${payload.ok ? "" : `<span class="hint">${escapeHtml(payload.install_hint || payload.detail || "请确认 Ollama 已启动。")}</span>`}
          ${suggestions ? `<details><summary>推荐 pull 命令</summary>${suggestions}</details>` : ""}
        </div>
      `;
    }

    async function applySelectedOllamaModel(button = null) {
      return withButtonState(button, "应用中", async () => {
        const select = $("ollamaModelSelect");
        const selectedOption = select.options[select.selectedIndex];
        const model = select.value || $("llmModel").value;
        if (!model) {
          status.textContent = "请先读取并选择 Ollama 模型";
          return null;
        }
        status.textContent = "保存 Ollama 离线模型配置";
        const payload = await requestJson("/api/ollama/apply", {
          model,
          base_url: ollamaBaseUrl(),
          model_capability: selectedOption?.dataset?.capability || "text_only"
        });
        const config = payload.config || payload.recommendation || {};
        if (payload.ok && config) {
          $("llmProfile").value = "local_first";
          $("llmProvider").value = "local_ollama";
          $("llmBaseUrl").value = config.base_url || payload.recommendation?.base_url || "http://127.0.0.1:11434/v1";
          $("llmModel").value = config.model || model;
          $("llmCapability").value = config.model_capability || payload.recommendation?.model_capability || "text_only";
          $("allowCloudText").checked = false;
          $("allowMediaUpload").checked = payload.recommendation?.allow_media_upload_to_llm === true;
          $("llmApiKey").value = "";
          $("llmApiKey").placeholder = "Ollama 本地模式不需要 API Key";
          $("directorMode").value = "hybrid";
        }
        renderOllamaStatus(payload.recommendation || payload);
        status.textContent = payload.ok ? "已切换到 Ollama 离线模型" : "Ollama 配置失败";
        return payload;
      });
    }

    function collectVoiceModelConfig() {
      return {
        provider_id: "moss_tts_nano",
        display_name: $("voiceModelName").value,
        repo_url: $("voiceModelRepo").value,
        install_dir: $("voiceModelDir").value,
        enabled: $("voiceModelEnabled").checked
      };
    }

    async function saveVoiceModelConfig(button = null) {
      return withButtonState(button, "保存中", async () => {
        status.textContent = "保存人声模型配置";
        const payload = await requestJson("/api/voice-model-config", collectVoiceModelConfig());
        status.textContent = payload.ok ? "人声模型配置已保存" : "保存失败";
        return payload;
      });
    }

    async function checkVoiceModel(button = null) {
      return withButtonState(button, "检测中", async () => {
        status.textContent = "检测人声模型";
        const payload = await requestJson("/api/moss-tts/status");
        status.textContent = payload.ready ? "MOSS 可直接使用" : "MOSS 需要配置";
        return payload;
      });
    }

    async function setupMossTts(button = null) {
      return withButtonState(button, "配置中", async () => {
        status.textContent = "配置 MOSS 依赖，可能需要几分钟";
        const payload = await requestJson("/api/moss-tts/setup");
        status.textContent = payload.ok ? "MOSS 依赖已配置" : "MOSS 配置失败";
        return payload;
      });
    }

    function previewPromptAudio() {
      const path = $("mossPromptAudioPath").value.trim();
      const audio = $("mossPromptPreview");
      if (!path) {
        audio.removeAttribute("src");
        $("voiceCaptureStatus").textContent = "等待录音或选择参考音频。";
        return;
      }
      audio.src = `/api/media-preview?path=${encodeURIComponent(path)}`;
      $("voiceCaptureStatus").textContent = "已选择参考音频，MOSS 测试和后续剪辑会把它作为 prompt-speech。";
      markBriefStale();
    }

    function clearPromptAudio() {
      $("mossPromptAudioPath").value = "";
      clearAudioElement($("mossPromptPreview"));
      $("voiceCaptureStatus").textContent = "已清除参考音频。";
      markBriefStale();
    }

    function clearAudioElement(audio) {
      if (!audio) return;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }

    function mossGenerationParams() {
      const profile = $("mossProfile").value;
      if (profile === "greedy_plain") {
        return {sample_mode: "greedy", text_temperature: 0.7, audio_temperature: 0.5, seed: 2026};
      }
      if (profile === "expressive") {
        return {sample_mode: "full", text_temperature: 1.0, audio_temperature: 0.85, seed: null};
      }
      return {sample_mode: "fixed", text_temperature: 0.8, audio_temperature: 0.6, seed: 2026};
    }

    function mossProfileLabel(value) {
      return {
        stable_clear: "清晰稳妥",
        greedy_plain: "更固定",
        expressive: "更有表现力"
      }[value] || value || "默认";
    }

    async function loadSystemTtsVoices(button = null, options = {}) {
      if (systemTtsVoicesLoading) return null;
      systemTtsVoicesLoading = true;
      const selected = $("systemVoice").value;
      const run = async () => {
        const payload = await requestJson("/api/voice/system-tts/voices", null, {silent: true});
        const voices = Array.isArray(payload.voices) ? payload.voices : [];
        systemTtsVoiceOptions = voices;
        systemTtsDefaultVoice = payload.default_voice || "";
        systemTtsPlatform = payload.platform || "";
        renderSystemTtsVoiceOptions(selected);
        systemTtsVoicesLoaded = payload.ok === true;
        $("systemTtsStatus").textContent = payload.ok
          ? `已读取 ${voices.length} 个系统 TTS 语音${systemTtsPlatform ? `（${systemTtsPlatform}）` : ""}。`
          : `系统 TTS 语音读取失败：${payload.reason || "unknown"}。可继续使用系统默认语音。`;
        return payload;
      };
      try {
        return button ? await withButtonState(button, "读取中", run) : await run();
      } finally {
        systemTtsVoicesLoading = false;
      }
    }

    function renderSystemTtsVoiceOptions(preferredValue = "") {
      const selected = preferredValue || $("systemVoice").value;
      const filter = ($("systemVoiceFilter")?.value || "").trim().toLowerCase();
      const voices = systemTtsVoiceOptions.filter((voice) => {
        if (!filter) return true;
        return [voice.name, voice.culture, voice.gender, voice.age, voice.description]
          .some((value) => String(value || "").toLowerCase().includes(filter));
      });
      $("systemVoice").innerHTML = [
        `<option value="">系统默认语音${systemTtsDefaultVoice ? `：${escapeHtml(systemTtsDefaultVoice)}` : ""}</option>`,
        ...voices.map((voice) => {
          const name = voice.name || "";
          const meta = [voice.culture, voice.gender, voice.age].filter(Boolean).join(" · ");
          return `<option value="${escapeHtml(name)}">${escapeHtml(name || "未命名语音")}${meta ? ` (${escapeHtml(meta)})` : ""}</option>`;
        })
      ].join("");
      if (selected && voices.some((voice) => voice.name === selected)) $("systemVoice").value = selected;
      if (systemTtsVoiceOptions.length) {
        $("systemTtsStatus").textContent = filter
          ? `语音筛选：${voices.length}/${systemTtsVoiceOptions.length} 个匹配。`
          : `已读取 ${systemTtsVoiceOptions.length} 个系统 TTS 语音${systemTtsPlatform ? `（${systemTtsPlatform}）` : ""}。`;
      }
    }

    async function testSystemTts(button = null) {
      return withButtonState(button, "生成试听中", async () => {
        status.textContent = "正在生成系统 TTS 试听";
        const payload = await requestJson("/api/voice/system-tts/test", {
          text: $("voiceoverText").value || $("userRequest").value || "这是一段系统 TTS 试听语音。",
          output_dir: $("outputDir").value,
          voice_name: $("systemVoice").value,
          rate: Number($("systemRate").value) || 0,
          volume: Number($("systemVolume").value) || 100
        }, {silent: true});
        if (payload.ok && payload.audio_path) {
          $("systemTtsPreview").src = `/api/media-preview?path=${encodeURIComponent(payload.audio_path)}`;
          $("systemTtsPreview").style.display = "block";
          $("systemTtsStatus").textContent = `试听已生成：${payload.voice_name || "系统默认语音"}`;
          status.textContent = "系统 TTS 试听已生成";
        } else {
          $("systemTtsStatus").textContent = `试听失败：${payload.reason || "unknown"}`;
          status.textContent = "系统 TTS 试听失败";
        }
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        return payload;
      });
    }

    function formatSampleTime(value) {
      const date = new Date(Number(value || 0) * 1000);
      if (Number.isNaN(date.getTime())) return "";
      return date.toLocaleString();
    }

    function friendlyMossError(payload) {
      if (!payload || typeof payload !== "object") return "生成失败，请查看技术详情。";
      if (payload.reason === "RuntimeError") {
        return "生成失败：模型本次合成异常。已保留历史样音，可换音色/特征后重试。";
      }
      if (payload.reason === "moss_tts_runtime_not_ready") return "MOSS 运行环境还未配置完成。";
      return payload.reason || "生成失败，请查看技术详情。";
    }

    async function loadMossSampleHistory(button = null) {
      return withButtonState(button, "刷新中", async () => {
        const params = new URLSearchParams({output_dir: $("mossTestOutputDir").value || ""});
        const payload = await requestJson(`/api/moss-tts/history?${params.toString()}`, null, {silent: true});
        renderMossSampleHistory(payload.samples || []);
        return payload;
      });
    }

    function renderMossSampleHistory(samples) {
      const box = $("mossSampleHistory");
      if (!box) return;
      if (!samples.length) {
        box.innerHTML = `<div class="summary-item"><span class="hint">还没有生成过样音。生成成功后会在这里保留列表。</span></div>`;
        return;
      }
      box.innerHTML = samples.map((sample) => {
        const audioUrl = `/api/media-preview?path=${encodeURIComponent(sample.audio_path || "")}`;
        return `
          <div class="summary-item">
            <strong>${escapeHtml(sample.voice || "MOSS 样音")} · ${escapeHtml(mossProfileLabel(sample.profile))}</strong>
            <span class="mini">${escapeHtml(formatSampleTime(sample.created_at))}</span>
            <audio class="audio-preview" controls src="${audioUrl}"></audio>
            <div class="path-text">${escapeHtml(sample.audio_path || "")}</div>
            ${sample.text_preview ? `<span class="hint">${escapeHtml(sample.text_preview)}</span>` : ""}
          </div>
        `;
      }).join("");
    }

    async function startVoiceRecording(button = null) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === "undefined") {
        $("voiceCaptureStatus").textContent = "当前浏览器不支持麦克风录音，请选择本地音频文件。";
        return;
      }
      if (voiceRecorder && voiceRecorder.state !== "inactive") {
        $("voiceCaptureStatus").textContent = "正在录音，可以开始说话；录完请点“停止并保存”。";
        return;
      }
      voiceRecordingStartButton = button || $("startRecordingButton");
      voiceRecordingStopButton = $("stopRecordingButton");
      setButtonBusy(voiceRecordingStartButton, "请求麦克风");
      if (voiceRecordingStopButton) voiceRecordingStopButton.disabled = true;
      $("voiceCaptureStatus").textContent = "正在请求浏览器麦克风权限...";
      status.textContent = "请求麦克风权限";
      try {
        voiceRecordStream = await navigator.mediaDevices.getUserMedia({audio: true});
        voiceRecordChunks = [];
        voiceRecorder = new MediaRecorder(voiceRecordStream);
        voiceRecorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) voiceRecordChunks.push(event.data);
        };
        voiceRecorder.onstop = async () => {
          const blob = new Blob(voiceRecordChunks, {type: voiceRecorder.mimeType || "audio/webm"});
          if (voiceRecordStream) voiceRecordStream.getTracks().forEach((track) => track.stop());
          voiceRecordStream = null;
          await uploadVoiceSample(blob);
        };
        voiceRecorder.start();
        setButtonBusy(voiceRecordingStartButton, "正在录音");
        if (voiceRecordingStopButton) voiceRecordingStopButton.disabled = false;
        $("voiceCaptureStatus").textContent = "麦克风已开启，可以开始说话；建议朗读 5-15 秒，录完点“停止并保存”。";
        status.textContent = "正在录音";
      } catch (error) {
        restoreButton(voiceRecordingStartButton);
        if (voiceRecordingStopButton) voiceRecordingStopButton.disabled = true;
        $("voiceCaptureStatus").textContent = "未获得麦克风权限，或麦克风不可用。可以改为选择本地参考音频。";
        status.textContent = "麦克风不可用";
      }
    }

    function stopVoiceRecording(button = null) {
      if (!voiceRecorder || voiceRecorder.state === "inactive") {
        $("voiceCaptureStatus").textContent = "当前没有正在进行的录音。";
        return;
      }
      voiceRecordingStopButton = button || $("stopRecordingButton");
      setButtonBusy(voiceRecordingStopButton, "保存中");
      setButtonBusy(voiceRecordingStartButton, "保存中");
      $("voiceCaptureStatus").textContent = "已停止录音，正在保存参考音频...";
      status.textContent = "保存参考人声";
      voiceRecorder.stop();
    }

    async function uploadVoiceSample(blob) {
      try {
        const response = await fetch("/api/voice-samples?filename=recorded-voice.webm", {
          method: "POST",
          headers: {"Content-Type": blob.type || "application/octet-stream"},
          body: blob
        });
        const payload = await response.json();
        resultDetails.textContent = JSON.stringify(payload, null, 2);
        if (payload.ok) {
          $("mossPromptAudioPath").value = payload.prompt_audio_path || payload.raw_audio_path || "";
          previewPromptAudio();
          $("voiceCaptureStatus").textContent = "参考人声已保存，可试听后用于 MOSS 模仿。";
          status.textContent = "参考人声已保存";
        } else {
          $("voiceCaptureStatus").textContent = payload.reason || "录音保存失败";
          status.textContent = "参考人声保存失败";
        }
      } catch (error) {
        $("voiceCaptureStatus").textContent = "录音上传失败，请重试或选择本地参考音频。";
        status.textContent = "参考人声保存失败";
      } finally {
        restoreButton(voiceRecordingStartButton);
        restoreButton(voiceRecordingStopButton);
        if ($("stopRecordingButton")) $("stopRecordingButton").disabled = true;
        voiceRecordingStartButton = null;
        voiceRecordingStopButton = null;
      }
    }

    async function testMossTts(button = null) {
      return withButtonState(button, "生成中", async () => {
        status.textContent = "生成 MOSS 样音";
        clearAudioElement($("mossTestPreview"));
        $("mossTestAudioPath").textContent = "正在生成，请稍候...";
        const mossParams = mossGenerationParams();
        const payload = await requestJson("/api/moss-tts/test", {
          text: $("mossTestText").value,
          output_dir: $("mossTestOutputDir").value,
          voice: $("mossVoice").value,
          profile: $("mossProfile").value,
          prompt_audio_path: $("mossPromptAudioPath").value || null,
          cpu_threads: 4,
          max_new_frames: 375,
          sample_mode: mossParams.sample_mode,
          text_temperature: mossParams.text_temperature,
          audio_temperature: mossParams.audio_temperature,
          seed: mossParams.seed
        });
        status.textContent = payload.ok ? "MOSS 样音已生成" : "MOSS 样音失败";
        if (payload.ok && payload.audio_path) {
          $("mossTestPreview").src = `/api/media-preview?path=${encodeURIComponent(payload.audio_path)}`;
          $("mossTestAudioPath").textContent = payload.audio_path;
          renderMossSampleHistory(payload.history || (payload.sample ? [payload.sample] : []));
        } else {
          $("mossTestAudioPath").textContent = friendlyMossError(payload);
          if (payload.history) renderMossSampleHistory(payload.history);
        }
        return payload;
      });
    }

    async function createVoiceProfile(button = null) {
      return withButtonState(button, "生成中", async () => {
        status.textContent = "生成人声配置";
        const payload = await requestJson("/api/voice-profile", {
          output_dir: $("voiceOutputDir").value,
          provider_id: $("voiceProviderProfile").value,
          sample_text: $("sampleText").value,
          sample_outcome: $("sampleOutcome").value
        });
        latestVoiceProfileResult = payload;
        if (payload.result_json_path) $("voiceProfileResultPath").value = payload.result_json_path;
        updateVoiceProfilePreview(payload);
        status.textContent = "人声配置完成，请先试听再确认";
        return payload;
      });
    }

    function voiceProfileAudioPath(payload) {
      if (!payload || typeof payload !== "object") return "";
      return payload.audio_path
        || payload.sample_audio_path
        || payload?.generated_voiceover?.audio_path
        || payload?.moss_tts_sample_generation?.audio_path
        || payload?.moss_tts_sample_generation?.output_audio_path
        || "";
    }

    function updateVoiceProfilePreview(payload) {
      const audioPath = voiceProfileAudioPath(payload);
      const preview = $("voiceProfilePreview");
      if (audioPath) {
        preview.src = `/api/media-preview?path=${encodeURIComponent(audioPath)}`;
        $("voiceProfileStatus").textContent = `已生成可试听样音：${audioPath}`;
      } else {
        clearAudioElement(preview);
        $("voiceProfileStatus").textContent = "当前 profile 合约没有本地可播放音频；仍可确认 artifact ref，或先生成 MOSS 测试样音。";
      }
    }

    async function confirmVoiceProfileRef(button = null) {
      return withButtonState(button, "确认中", async () => {
        status.textContent = "确认 voice_profile_ref";
        const payload = await requestJson("/api/voice-profile/confirm", {
          output_dir: $("voiceOutputDir").value || $("outputDir").value || $("mossTestOutputDir").value,
          profile_result_path: $("voiceProfileResultPath").value,
          profile_result: latestVoiceProfileResult,
          outcome: $("voiceProfileOutcome").value,
          rating: Number($("voiceProfileRating").value) || null,
          notes: $("voiceProfileNotes").value,
          prompt_audio_path: $("mossPromptAudioPath").value,
          sample_audio_path: voiceProfileAudioPath(latestVoiceProfileResult)
        });
        if (payload.voice_profile_ref) {
          latestVoiceProfileRef = payload.voice_profile_ref;
          applyVoiceProfileRefToSettings(payload);
          status.textContent = "voice_profile_ref 已批准并加入剪辑设置";
          markBriefStale();
        } else {
          status.textContent = payload.outcome === "rejected" ? "此声音已拒绝" : "已记录，需要重新生成或继续调整";
        }
        renderVoiceProfileReview(payload);
        return payload;
      });
    }

    function applyVoiceProfileRefToSettings(payload) {
      const ref = payload.voice_profile_ref || {};
      const provider = voiceProviderFromProfile(payload.provider_id || ref.provider_id || "");
      if (provider && $("voiceProvider")) {
        $("voiceProvider").value = provider;
        updateVoiceControls();
      }
      const promptAudioPath = payload.prompt_audio_path || ref.prompt_audio_path || payload?.settings_overrides?.voice?.prompt_audio_path || "";
      if (promptAudioPath && $("mossPromptAudioPath")) {
        $("mossPromptAudioPath").value = promptAudioPath;
        previewPromptAudio();
      }
    }

    function voiceProviderFromProfile(providerId) {
      if (providerId === "fixture_voice") return "fixture";
      if (["moss_tts_nano", "edge_tts", "system_tts", "fixture"].includes(providerId)) return providerId;
      return "";
    }

    function renderVoiceProfileReview(payload) {
      const box = $("voiceProfileReviewResult");
      if (!box) return;
      const ref = payload.voice_profile_ref || {};
      const warnings = (payload.warnings || []).map((item) => item.message || item.code).filter(Boolean);
      box.innerHTML = `
        <div class="summary-item">
          <strong>${payload.voice_profile_ref ? "已批准 voice_profile_ref" : "已记录试听结论"}</strong>
          <span class="chip ${payload.voice_profile_ref ? "ok" : "warn"}">${escapeHtml(payload.outcome || "unknown")}</span>
          <span class="mini">Provider：${escapeHtml(payload.provider_id || ref.provider_id || "unknown")}</span>
          ${ref.ref_id ? `<span class="mini">ref_id：${escapeHtml(ref.ref_id)}</span>` : ""}
          ${payload.review_record_path ? `<div class="path-text">${escapeHtml(payload.review_record_path)}</div>` : ""}
          ${warnings.length ? `<span class="hint">${escapeHtml(warnings.join("；"))}</span>` : ""}
        </div>
      `;
    }

    async function loadVoiceProfileRefs(button = null) {
      return withButtonState(button, "刷新中", async () => {
        const params = new URLSearchParams({output_dir: $("voiceOutputDir").value || $("outputDir").value || ""});
        const payload = await requestJson(`/api/voice-profile/refs?${params.toString()}`, null, {silent: true});
        latestVoiceProfileRefs = payload.refs || [];
        renderVoiceProfileRefs(latestVoiceProfileRefs);
        return payload;
      });
    }

    function renderVoiceProfileRefs(refs) {
      const box = $("voiceProfileReviewResult");
      if (!box) return;
      if (!refs.length) {
        box.innerHTML = `<div class="summary-item"><span class="hint">还没有已确认的 voice_profile_ref。</span></div>`;
        return;
      }
      box.innerHTML = refs.map((item, index) => `
        <div class="summary-item">
          <strong>${escapeHtml(item.provider_id || "voice_profile_ref")}</strong>
          <span class="chip ${item.can_apply_to_video_task ? "ok" : "warn"}">${escapeHtml(item.outcome || "unknown")}</span>
          <span class="mini">${escapeHtml(formatSampleTime(item.created_at))}</span>
          ${item.rating ? `<span class="mini">评分：${escapeHtml(item.rating)}</span>` : ""}
          ${item.notes ? `<span class="hint">${escapeHtml(item.notes)}</span>` : ""}
          <div class="path-text">${escapeHtml(item.review_record_path || "")}</div>
          <button class="secondary" onclick="useVoiceProfileRef(${index})">使用这个声音</button>
        </div>
      `).join("");
    }

    function useVoiceProfileRef(index) {
      const item = latestVoiceProfileRefs[index];
      if (!item || !item.voice_profile_ref) return;
      latestVoiceProfileRef = item.voice_profile_ref;
      applyVoiceProfileRefToSettings(item);
      renderVoiceProfileReview(item);
      status.textContent = "已切换 voice_profile_ref";
      markBriefStale();
    }

    function openPicker(targetId, mode, extensions = "") {
      pickerState = { targetId, mode, extensions };
      $("pickerTitle").textContent = mode === "directory" ? "选择文件夹" : "选择文件";
      $("selectCurrentDir").style.display = mode === "directory" ? "inline-block" : "none";
      $("pickerModal").classList.remove("hidden");
      const start = $(targetId).value || "";
      loadPicker(start);
    }

    function closePicker() {
      $("pickerModal").classList.add("hidden");
    }

    async function loadPicker(path, button = null) {
      return withButtonState(button, "打开中", async () => {
        const params = new URLSearchParams({
          path: path || "",
          mode: pickerState.mode,
          extensions: pickerState.extensions || ""
        });
        const payload = await requestJson(`/api/files?${params.toString()}`, null, {silent: true});
        $("pickerPath").value = payload.cwd || "";
        $("pickerShortcuts").innerHTML = [
          ...(payload.parent ? [{label: "上一级", path: payload.parent}] : []),
          ...(payload.drives || []).map((drive) => ({label: drive, path: drive})),
          ...(payload.shortcuts || [])
        ].map((item) => `<button class="neutral" onclick="loadPicker('${escapeJs(item.path)}', this)">${escapeHtml(item.label)}</button>`).join("");
        $("pickerItems").innerHTML = (payload.items || []).map((item) => {
          const action = item.is_dir
            ? `<button class="secondary" onclick="loadPicker('${escapeJs(item.path)}', this)">打开</button>${pickerState.mode === "directory" ? `<button class="neutral" onclick="choosePath('${escapeJs(item.path)}')">选择</button>` : ""}`
            : `<button class="secondary" onclick="choosePath('${escapeJs(item.path)}')">选择</button>`;
          return `<div class="picker-row"><span>${item.is_dir ? "D" : "F"}</span><span class="path-text">${escapeHtml(item.name)}</span><span class="actions">${action}</span></div>`;
        }).join("") || `<div class="picker-row"><span></span><span class="hint">没有可选项目</span><span></span></div>`;
        return payload;
      });
    }

    function escapeJs(value) {
      return String(value || "").replaceAll("\\", "\\\\").replaceAll("'", "\\'");
    }

    function choosePath(path) {
      $(pickerState.targetId).value = path;
      if (path) {
        recordRecentPath(path);
        const recentContainerId = pickerState.targetId + "RecentPaths";
        if ($(recentContainerId)) renderRecentPaths(pickerState.targetId, recentContainerId);
      }
      if (pickerState.targetId === "bgmAudioPath") {
        $("bgmStyle").value = "local_audio";
        updateBgmControls();
        previewBgm();
      }
      if (pickerState.targetId === "mossPromptAudioPath") {
        previewPromptAudio();
      }
      if (pickerState.targetId === "inputVideo") {
        addInputVideo(path);
      }
      closePicker();
      markBriefStale();
    }

    function selectPickerCurrentDir() {
      choosePath($("pickerPath").value);
    }

    [
      ...LOCAL_DRAFT_FIELD_IDS
    ].forEach((id) => {
      setTimeout(() => {
        const el = $(id);
        if (el) {
          el.addEventListener("change", markBriefStale);
          if (["INPUT", "TEXTAREA"].includes(el.tagName)) {
            el.addEventListener("input", markBriefStale);
          }
        }
      }, 0);
    });

    setTimeout(() => {
      if ($("originalAudioMode")) {
        $("originalAudioMode").addEventListener("change", () => {
          $("removeOriginalVoice").checked = $("originalAudioMode").value !== "keep";
        });
      }
      if ($("removeOriginalVoice")) {
        $("removeOriginalVoice").addEventListener("change", () => {
          $("originalAudioMode").value = $("removeOriginalVoice").checked ? "remove" : "keep";
        });
      }
      updateBgmControls();
      updateSubtitleControls();
      updateVoiceControls();
      registerBeginnerFieldListeners();
    }, 0);

    async function initializeApp() {
      restoreUiMode();
      renderCurrentResultEmpty();
      refreshGuidedFeedbacks();
      await checkRuntime();
      await loadPackages();
      await loadLocalConfig();
      restoreLocalDraft();
      suggestOutputDir();
      await loadMemory();
      await loadRecentRuns();
      await loadMossSampleHistory();
      refreshGuidedFeedbacks();
    }

    initializeApp().catch((error) => {
        status.textContent = "服务未就绪";
        status.classList.add("error");
        renderMessage("初始化失败", String(error), "warn");
      });
