const state = {
  projects: [],
  project: null,
  providers: [],
  tab: "brief",
  editPack: null,
  smartDefaults: {},
  bridgePreview: null,
  modelPipeline: null,
  planning: null,
  planningCompare: { left: null, right: null },
  planningOpenOnly: false,
  images: null,
  imageCompare: { left: null, right: null },
  imageRegenerate: { assetId: "", issue: "artifact" },
  imageOpenOnly: false,
  clips: null,
  clipCompare: { left: null, right: null },
  clipRegenerate: { assetId: "", issue: "stiff_motion" },
  clipOpenOnly: false,
  clipFocusShotId: "",
  orchestrationDrag: { referenceId: "", shotId: "" },
  busy: null,
};

const $ = (selector) => document.querySelector(selector);

const IMAGE_ISSUES = [
  ["character_mismatch", "人物不像"],
  ["scene_mismatch", "场景不对"],
  ["composition_wrong", "构图不对"],
  ["style_inconsistent", "风格不统一"],
  ["artifact", "有瑕疵"],
];

const CLIP_ISSUES = [
  ["stiff_motion", "动作僵硬"],
  ["camera_wrong", "镜头运动错误"],
  ["identity_drift", "人物漂移"],
  ["duration_wrong", "时长不对"],
  ["flicker", "画面闪烁"],
];

const MODEL_SLOT_UI = {
  planning_model: {
    index: "01",
    input: "需求 Brief",
    output: "策划稿 / 分镜",
    sample: "5秒爱情单镜头策划",
  },
  text_to_image_model: {
    index: "02",
    input: "分镜文字",
    output: "人物 / 场景 / 关键帧图",
    sample: "黄昏公园情侣关键帧",
  },
  image_to_video_model: {
    index: "03",
    input: "参考图 + 镜头文字",
    output: "视频片段",
    sample: "基于关键帧生成5秒镜头",
  },
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data?.error?.message || `请求失败：${response.status}`;
    const error = new Error(message);
    error.payload = data;
    throw error;
  }
  return data;
}

function formPayload(form) {
  const payload = {};
  const data = new FormData(form);
  for (const [key, value] of data.entries()) {
    const input = form.elements[key];
    if (input?.type === "checkbox") {
      payload[key] = input.checked;
    } else if (input?.type === "number") {
      payload[key] = Number(value || 0);
    } else {
      payload[key] = String(value || "").trim();
    }
  }
  for (const input of form.querySelectorAll('input[type="checkbox"]')) {
    if (!Object.prototype.hasOwnProperty.call(payload, input.name)) payload[input.name] = false;
  }
  return payload;
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      resolve("");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("读取文件失败"));
    reader.readAsDataURL(file);
  });
}

function dragTypesInclude(event, type) {
  return Array.from(event.dataTransfer?.types || []).includes(type);
}

async function loadBootstrap() {
  const [data, smartDefaults] = await Promise.all([
    api("/api/bootstrap"),
    api("/api/smart-video-cut/defaults").catch(() => ({})),
  ]);
  state.projects = data.projects || [];
  state.providers = data.providers || [];
  state.project = data.active_project || null;
  state.smartDefaults = smartDefaults || {};
  state.modelPipeline = await api("/api/model-pipeline/config").catch(() => null);
  state.planning = state.project ? await loadPlanning(state.project.id) : null;
  state.images = state.project ? await loadImages(state.project.id) : null;
  state.clips = state.project ? await loadClips(state.project.id) : null;
  state.planningCompare = { left: null, right: null };
  state.imageCompare = { left: null, right: null };
  state.clipCompare = { left: null, right: null };
  render();
}

async function selectProject(projectId) {
  state.project = await api(`/api/projects/${projectId}`);
  state.planning = await loadPlanning(projectId);
  state.images = await loadImages(projectId);
  state.clips = await loadClips(projectId);
  state.planningCompare = { left: null, right: null };
  state.imageCompare = { left: null, right: null };
  state.clipCompare = { left: null, right: null };
  state.clipFocusShotId = "";
  render();
}

async function loadPlanning(projectId) {
  return api(`/api/projects/${projectId}/planning`).catch(() => null);
}

async function loadImages(projectId) {
  return api(`/api/projects/${projectId}/images`).catch(() => null);
}

async function loadClips(projectId) {
  return api(`/api/projects/${projectId}/clips`).catch(() => null);
}

function render() {
  renderProjects();
  renderProjectHeader();
  renderWorkflow();
  renderTabs();
  renderBrief();
  renderPlanning();
  renderReferenceAssets();
  renderOrchestration();
  renderImages();
  renderClips();
  renderShots();
  renderTasks();
  renderAssets();
  renderProviders();
  renderModelPipeline();
  renderSmartCutBridge();
}

function renderProjects() {
  const list = $("#project-list");
  if (!state.projects.length) {
    list.innerHTML = `<p class="muted">还没有项目。</p>`;
    return;
  }
  list.innerHTML = state.projects
    .map((project) => `
      <button class="project-item ${state.project?.id === project.id ? "active" : ""}" data-project-id="${project.id}" type="button">
        <strong>${escapeHtml(project.title)}</strong>
        <small>${escapeHtml(project.current_step)} · ${project.shot_count || 0} 镜头</small>
      </button>
    `)
    .join("");
}

function renderProjectHeader() {
  const project = state.project;
  $("#project-title").textContent = project?.title || "选择或新建项目";
  $("#project-logline").textContent = project?.logline || "围绕一个项目完成需求确认、三阶段生成验收、产物沉淀和剪辑装配。";
  $("#metric-shots").textContent = project?.totals?.shot_count || 0;
  $("#metric-assets").textContent = project?.totals?.asset_count || 0;
  $("#metric-cost").textContent = money(project?.totals?.actual_cost || 0);
  $("#advance-step").disabled = !project;
  $("#approve-step").disabled = !project;
}

function renderWorkflow() {
  const workflow = state.project?.workflow || [];
  $("#workflow").innerHTML = workflow
    .map((step) => `
      <div class="step ${escapeHtml(step.status)}">
        <strong>${escapeHtml(step.label)}</strong>
        <small>${statusLabel(step.status)}${step.approval_required ? " · 需审批" : ""}</small>
      </div>
    `)
    .join("");
}

function renderTabs() {
  document.querySelectorAll(".tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.tab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${state.tab}`);
  });
}

function renderBrief() {
  const project = state.project;
  const form = $("#brief-form");
  if (!form) return;
  $("#brief-current-step").textContent = project ? workflowStepLabel(project.current_step) : "未选择项目";
  $("#brief-readiness").textContent = deliveryReadinessLabel();
  $("#brief-title").value = project?.title || "";
  $("#brief-logline").value = project?.logline || "";
  $("#brief-format").value = project?.format || "short";
  $("#brief-duration").value = project?.target_duration_seconds || 60;
  form.querySelectorAll("input, textarea, select, button").forEach((node) => {
    node.disabled = !project;
  });
  $("#brief-summary").innerHTML = project ? briefSummaryHtml() : `<p class="muted">先在左侧新建或选择项目。</p>`;
  $("#brief-models").innerHTML = modelStageSummaryHtml();
}

function briefSummaryHtml() {
  const project = state.project || {};
  const draft = state.planning?.planning_draft || {};
  const shots = project.shots || [];
  const imageItems = state.images?.items || [];
  const clipItems = state.clips?.items || [];
  const approvedImages = imageItems.filter((item) => item.status === "approved").length;
  const approvedClips = clipItems.filter((item) => item.status === "approved").length;
  return `
    <div class="brief-kpis">
      <span><b>${escapeHtml(shots.length)}</b>分镜</span>
      <span><b>${escapeHtml(approvedImages)}</b>已批图片</span>
      <span><b>${escapeHtml(approvedClips)}</b>已批视频</span>
    </div>
    <article class="brief-card">
      <strong>故事方向</strong>
      <p>${escapeHtml(draft.story_outline || project.logline || "尚未生成策划稿。")}</p>
    </article>
    <article class="brief-card">
      <strong>下一步</strong>
      <p>${escapeHtml(nextActionText())}</p>
    </article>
  `;
}

function modelStageSummaryHtml() {
  const slots = state.modelPipeline?.slots || [];
  if (!slots.length) return `<p class="muted">尚未加载模型槽位。</p>`;
  return slots.map((slot) => `
    <article class="model-summary-card">
      <strong>${escapeHtml(slot.label || slot.slot_key)}</strong>
      <span>${escapeHtml(slot.provider_name || slot.provider_id || "未配置供应商")}</span>
      <small>${escapeHtml(slot.model || "未配置模型")} · ${slot.enabled ? "可用" : "停用"}</small>
    </article>
  `).join("");
}

function deliveryReadinessLabel() {
  const status = state.clips?.status || state.images?.status || state.planning?.status || "not_started";
  if (state.project?.current_step === "final_qc") return "待最终质检";
  if (state.project?.current_step === "archive") return "已归档";
  if (status === "approved") return "可交付";
  return {
    not_started: "待开始",
    draft: "待策划验收",
    waiting_for_images: "待图片",
    waiting_for_planning: "待策划",
    needs_review: "待验收",
    failed: "需处理失败",
  }[status] || "进行中";
}

function nextActionText() {
  if (!state.project) return "选择或新建项目。";
  if ((state.planning?.status || "not_started") !== "approved") return "完善需求后生成并批准策划稿。";
  if ((state.images?.status || "not_started") !== "approved") return "基于已批准策划稿生成并批准关键帧图。";
  if ((state.clips?.status || "not_started") !== "approved") return "基于已批准图片生成并批准视频片段。";
  if (state.project.current_step === "final_qc") return "检查剪辑标准和导出内容，完成最终质检后归档。";
  return "导出 edit pack 并发送到智能剪辑软件。";
}

function workflowStepLabel(stepKey) {
  const step = (state.project?.workflow || []).find((item) => item.step_key === stepKey);
  return step?.label || stepKey || "未开始";
}

function renderPlanning() {
  const draft = state.planning?.planning_draft || null;
  const busy = Boolean(state.busy);
  $("#planning-status").textContent = planningStatusLabel(state.planning?.status || "not_started");
  $("#planning-open-only").checked = state.planningOpenOnly;
  $("#generate-planning").disabled = !state.project || busy;
  $("#generate-planning").textContent = isBusy("generate-planning") ? "正在生成..." : "生成策划草案";
  $("#approve-planning").disabled = !state.project || !draft || busy;
  $("#approve-planning").textContent = isBusy("approve-planning") ? "正在批准..." : "批准并同步分镜";
  $("#planning-form").querySelectorAll("textarea, button[type='submit']").forEach((node) => {
    node.disabled = !state.project || busy;
  });
  if (!draft) {
    $("#planning-story").value = "";
    $("#planning-characters").value = "";
    $("#planning-scenes").value = "";
    $("#planning-storyboard").value = "";
    $("#planning-shot-review").innerHTML = `${busyMessage("planning")}<p class="muted">生成策划草案后开始逐镜头检查。</p>`;
    renderPlanningVersions();
    renderPlanningCompare();
    return;
  }
  $("#planning-story").value = draft.story_outline || "";
  $("#planning-characters").value = cardsToText(draft.characters || []);
  $("#planning-scenes").value = cardsToText(draft.scenes || []);
  $("#planning-storyboard").value = storyboardToText(draft.storyboard || []);
  renderPlanningShotReview(draft);
  renderPlanningVersions();
  renderPlanningCompare();
}

function renderPlanningShotReview(draft) {
  const container = $("#planning-shot-review");
  const storyboard = draft?.storyboard || [];
  const busy = Boolean(state.busy);
  const filtered = state.planningOpenOnly
    ? storyboard.filter((item) => (item.status || "draft") !== "approved")
    : storyboard;
  container.innerHTML = busyMessage("planning") + (filtered.length
    ? filtered.map((item, index) => {
      const position = Number(item.position || index + 1) || index + 1;
      return `
        <article class="planning-shot-card">
          <div class="shot-meta">
            <span>#${position}</span>
            <span>${escapeHtml(item.duration_seconds || 5)}s</span>
            <span>${planningShotStatusLabel(item.status || "draft")}</span>
          </div>
          <strong>${escapeHtml(item.title || `镜头 ${position}`)}</strong>
          <p class="muted">${escapeHtml(item.summary || "未填写镜头摘要")}</p>
          <p>${escapeHtml(item.video_prompt || item.prompt || item.image_prompt || "")}</p>
          <div class="issue-actions">
            ${planningIssueButtons(position)}
            <button data-action="approve-planning-shot" data-position="${position}" ${busy ? "disabled" : ""} type="button">${isBusy(`approve-planning-shot:${position}`) ? "正在标记..." : "标记通过"}</button>
          </div>
        </article>
      `;
    }).join("")
    : `<p class="muted">没有待处理镜头。</p>`);
}

function renderPlanningVersions() {
  const versions = state.planning?.versions || [];
  $("#planning-versions").innerHTML = versions.length
    ? versions.map((version) => {
      const assetId = version.asset_id || "";
      return `
      <div class="version-row">
        <strong>${escapeHtml(version.status)}</strong>
        <span>${escapeHtml(version.source || "unknown")}</span>
        <span>${escapeHtml(version.created_at || "")}</span>
        <small>${escapeHtml(version.storyboard_count || 0)} 镜头</small>
        <div class="version-actions">
          <button data-action="compare-planning-version" data-side="left" data-asset-id="${escapeHtml(assetId)}" ${assetId ? "" : "disabled"} type="button">左</button>
          <button data-action="compare-planning-version" data-side="right" data-asset-id="${escapeHtml(assetId)}" ${assetId ? "" : "disabled"} type="button">右</button>
          <button class="danger" data-action="delete-planning-version" data-asset-id="${escapeHtml(assetId)}" ${assetId ? "" : "disabled"} type="button">删除</button>
        </div>
      </div>
    `;
    }).join("")
    : `<p class="muted">暂无策划版本。</p>`;
}

function renderPlanningCompare() {
  const container = $("#planning-compare");
  const left = state.planningCompare.left;
  const right = state.planningCompare.right;
  if (!left && !right) {
    container.innerHTML = `<p class="muted">在策划版本列表中选择左、右两个版本进行对比。</p>`;
    return;
  }
  container.innerHTML = `
    <div class="compare-columns">
      ${planningCompareColumn("左侧版本", left)}
      ${planningCompareColumn("右侧版本", right)}
    </div>
    ${planningCompareDiff(left, right)}
  `;
}

function planningCompareColumn(label, payload) {
  if (!payload) {
    return `
      <article class="compare-column empty">
        <strong>${label}</strong>
        <p class="muted">尚未选择版本。</p>
      </article>
    `;
  }
  const draft = payload.planning_draft || {};
  const version = payload.version || {};
  const characters = draft.characters || [];
  const scenes = draft.scenes || [];
  const storyboard = draft.storyboard || [];
  return `
    <article class="compare-column">
      <div class="compare-meta">
        <strong>${label}</strong>
        <span>${escapeHtml(version.status || "draft")}</span>
        <span>${escapeHtml(version.source || "unknown")}</span>
      </div>
      <small>${escapeHtml(version.created_at || "")}</small>
      <p>${escapeHtml(draft.story_outline || "未填写故事方向")}</p>
      <div class="compare-counts">
        <span>${characters.length} 角色</span>
        <span>${scenes.length} 场景</span>
        <span>${storyboard.length} 镜头</span>
      </div>
      <div class="compare-storyboard">
        ${storyboard.length ? storyboard.map((item, index) => {
          const position = Number(item.position || index + 1) || index + 1;
          return `
            <div>
              <strong>#${position} ${escapeHtml(item.title || `镜头 ${position}`)}</strong>
              <span>${escapeHtml(planningShotStatusLabel(item.status || "draft"))}</span>
              <p class="muted">${escapeHtml(item.summary || item.video_prompt || item.image_prompt || "")}</p>
            </div>
          `;
        }).join("") : `<p class="muted">没有分镜。</p>`}
      </div>
    </article>
  `;
}

function planningCompareDiff(left, right) {
  if (!left || !right) {
    return `
      <article class="compare-diff">
        <strong>差异摘要</strong>
        <p class="muted">选择左右两个版本后显示差异。</p>
      </article>
    `;
  }
  const rows = planningDiffRows(left.planning_draft || {}, right.planning_draft || {});
  return `
    <article class="compare-diff">
      <strong>差异摘要</strong>
      ${rows.length
        ? `<ul>${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>`
        : `<p class="muted">两个版本的核心策划字段一致。</p>`}
    </article>
  `;
}

function planningDiffRows(leftDraft, rightDraft) {
  const rows = [];
  if (!samePlanningText(leftDraft.story_outline, rightDraft.story_outline)) rows.push("故事方向有变化");
  pushCountDiff(rows, "角色", leftDraft.characters, rightDraft.characters);
  pushCountDiff(rows, "场景", leftDraft.scenes, rightDraft.scenes);
  pushCountDiff(rows, "镜头", leftDraft.storyboard, rightDraft.storyboard);

  const leftStoryboard = leftDraft.storyboard || [];
  const rightStoryboard = rightDraft.storyboard || [];
  const max = Math.max(leftStoryboard.length, rightStoryboard.length);
  for (let index = 0; index < max && rows.length < 14; index += 1) {
    const leftItem = leftStoryboard[index];
    const rightItem = rightStoryboard[index];
    if (!leftItem && rightItem) {
      rows.push(`右侧新增 #${rightItem.position || index + 1} ${rightItem.title || "未命名镜头"}`);
      continue;
    }
    if (leftItem && !rightItem) {
      rows.push(`右侧缺少 #${leftItem.position || index + 1} ${leftItem.title || "未命名镜头"}`);
      continue;
    }
    if (!leftItem || !rightItem) continue;
    const changed = [];
    if (!samePlanningText(leftItem.title, rightItem.title)) changed.push("标题");
    if (!samePlanningText(leftItem.status, rightItem.status)) changed.push("状态");
    if (!samePlanningText(leftItem.summary, rightItem.summary)) changed.push("摘要");
    if (!samePlanningText(leftItem.camera, rightItem.camera)) changed.push("镜头语言");
    if (!samePlanningText(leftItem.image_prompt, rightItem.image_prompt)) changed.push("图片 prompt");
    if (!samePlanningText(leftItem.video_prompt, rightItem.video_prompt)) changed.push("视频 prompt");
    if (changed.length) rows.push(`#${rightItem.position || leftItem.position || index + 1} ${changed.join("、")} 有变化`);
  }
  return rows;
}

function pushCountDiff(rows, label, leftItems, rightItems) {
  const leftCount = (leftItems || []).length;
  const rightCount = (rightItems || []).length;
  if (leftCount !== rightCount) rows.push(`${label}数量：${leftCount} -> ${rightCount}`);
}

function samePlanningText(left, right) {
  return String(left || "").trim() === String(right || "").trim();
}

function clearDeletedPlanningCompare(assetId) {
  for (const side of ["left", "right"]) {
    if (String(state.planningCompare[side]?.version?.asset_id || "") === String(assetId)) {
      state.planningCompare[side] = null;
    }
  }
}

function referenceAssets() {
  return (state.project?.assets || []).filter((asset) => {
    const metadata = asset.metadata || {};
    return asset.type === "reference" && metadata.artifact_kind === "reference_image";
  });
}

function renderReferenceAssets() {
  const container = $("#reference-assets");
  if (!container) return;
  const refs = referenceAssets();
  const form = $("#reference-form");
  $("#reference-count").textContent = refs.length ? `${refs.length} 项` : "0";
  form.querySelectorAll("input, textarea, select, button").forEach((node) => {
    node.disabled = !state.project || Boolean(state.busy);
  });
  if (!state.project) {
    container.innerHTML = `<p class="muted">请先创建或选择项目。</p>`;
    return;
  }
  container.innerHTML = refs.length
    ? refs.map(referenceAssetCard).join("")
    : `<p class="muted">还没有锁定参考图。可上传角色或场景参考，后续关键帧会默认沿用。</p>`;
}

function referenceAssetCard(asset) {
  const metadata = asset.metadata || {};
  const kind = metadata.reference_kind === "scene" ? "场景" : "角色";
  return `
    <article class="reference-card">
      ${imagePreview(asset, "thumb")}
      <div class="reference-card-body">
        <div class="shot-meta">
          <span>${escapeHtml(kind)}</span>
          <span>${escapeHtml(asset.status || "approved")}</span>
        </div>
        <strong>${escapeHtml(metadata.reference_name || asset.title || "参考图")}</strong>
        <p class="muted">${escapeHtml(metadata.visual_prompt || asset.prompt || "未填写视觉描述")}</p>
        <small>${escapeHtml(asset.file_path || "")}</small>
        <div class="issue-actions">
          <button class="danger" data-action="delete-reference" data-asset-id="${escapeHtml(asset.id || "")}" ${state.busy ? "disabled" : ""} type="button">删除</button>
        </div>
      </div>
    </article>
  `;
}

function sortedShots() {
  return [...(state.project?.shots || [])].sort((left, right) => Number(left.position || 0) - Number(right.position || 0));
}

function referenceShotIds(asset) {
  const ids = asset?.metadata?.shot_ids || [];
  return Array.isArray(ids) ? ids.map(String).filter(Boolean) : [];
}

function referenceScope(asset) {
  const metadata = asset?.metadata || {};
  const scope = String(metadata.reference_scope || "").trim();
  if (scope) return scope;
  return referenceShotIds(asset).length ? "shots" : "project";
}

function referenceName(asset) {
  return asset?.metadata?.reference_name || asset?.title || "参考图";
}

function globalReferenceAssets() {
  return referenceAssets().filter((asset) => referenceScope(asset) === "project");
}

function effectiveReferenceAssetsForShot(shot) {
  const shotId = String(shot?.id || "");
  return referenceAssets().filter((asset) => {
    if (referenceScope(asset) === "project") return true;
    return referenceShotIds(asset).includes(shotId);
  });
}

function shotBoundReferenceAssets(shot) {
  const shotId = String(shot?.id || "");
  return referenceAssets().filter((asset) => referenceScope(asset) === "shots" && referenceShotIds(asset).includes(shotId));
}

function latestImageItemForShot(shotId) {
  return (state.images?.items || []).find((item) => String(item.shot?.id || "") === String(shotId || ""));
}

function latestClipItemForShot(shotId) {
  return (state.clips?.items || []).find((item) => String(item.shot?.id || "") === String(shotId || ""));
}

function renderOrchestration() {
  const board = $("#orchestration-board");
  const tray = $("#orchestration-reference-tray");
  if (!board || !tray) return;
  const refs = referenceAssets();
  const globalRefs = globalReferenceAssets();
  const shots = sortedShots();
  $("#orchestration-status").textContent = orchestrationStatusSummary(shots, refs);
  $("#orchestration-global-refs").innerHTML = globalRefs.length
    ? globalRefs.map((asset) => `<span>${escapeHtml(referenceName(asset))}</span>`).join("")
    : `<small class="muted">无</small>`;
  tray.innerHTML = refs.length
    ? refs.map(orchestrationReferenceCard).join("")
    : `<p class="muted">在图片验收页添加角色或场景参考图。</p>`;
  board.innerHTML = shots.length
    ? shots.map(orchestrationShotRow).join("")
    : `<p class="muted">先在策划验收中同步分镜表。</p>`;
}

function orchestrationStatusSummary(shots, refs) {
  if (!state.project) return "未开始";
  const imageItems = state.images?.items || [];
  const clipItems = state.clips?.items || [];
  const approvedImages = imageItems.filter((item) => item.status === "approved").length;
  const approvedClips = clipItems.filter((item) => item.status === "approved").length;
  return `${shots.length} 镜头 · ${refs.length} 参考 · ${approvedImages} 图 · ${approvedClips} 视频`;
}

function orchestrationReferenceCard(asset) {
  const metadata = asset.metadata || {};
  const kind = metadata.reference_kind === "scene" ? "场景" : "角色";
  const scope = referenceScope(asset);
  const ids = referenceShotIds(asset);
  const bindingText = scope === "project" ? "全片" : ids.length ? `${ids.length} 镜头` : "未绑定";
  const shotOptions = sortedShots().map((shot) => `
    <option value="${escapeHtml(shot.id || "")}">#${escapeHtml(shot.position || "-")} ${escapeHtml(shot.title || "未命名镜头")}</option>
  `).join("");
  return `
    <article class="orchestration-reference-card" draggable="true" data-reference-id="${escapeHtml(asset.id || "")}">
      ${imagePreview(asset, "thumb")}
      <div>
        <div class="shot-meta">
          <span>${escapeHtml(kind)}</span>
          <span>${escapeHtml(bindingText)}</span>
        </div>
        <strong>${escapeHtml(referenceName(asset))}</strong>
        <small>${escapeHtml(metadata.visual_prompt || asset.prompt || "")}</small>
        <div class="orchestration-bind-controls">
          <select data-reference-shot-picker="${escapeHtml(asset.id || "")}" ${shotOptions ? "" : "disabled"}>
            ${shotOptions || `<option value="">暂无分镜</option>`}
          </select>
          <button data-action="bind-reference-picker" data-reference-id="${escapeHtml(asset.id || "")}" ${shotOptions && !state.busy ? "" : "disabled"} type="button">绑定</button>
        </div>
        <div class="issue-actions">
          <button data-action="set-reference-global" data-reference-id="${escapeHtml(asset.id || "")}" ${state.busy ? "disabled" : ""} type="button">设为全片</button>
          <button data-action="clear-reference-binding" data-reference-id="${escapeHtml(asset.id || "")}" ${state.busy ? "disabled" : ""} type="button">清空绑定</button>
        </div>
      </div>
    </article>
  `;
}

function orchestrationShotRow(shot) {
  const refs = effectiveReferenceAssetsForShot(shot);
  const imageItem = latestImageItemForShot(shot.id);
  const clipItem = latestClipItemForShot(shot.id);
  return `
    <article class="orchestration-row" draggable="true" data-shot-id="${escapeHtml(shot.id || "")}">
      <section class="orchestration-shot">
        <button class="compact-button row-drag-handle" type="button" title="拖动调整顺序">拖动</button>
        <div>
          <div class="shot-meta">
            <span>#${escapeHtml(shot.position || "-")}</span>
            <span>${escapeHtml(shot.duration_seconds || 5)}s</span>
            <span>${escapeHtml(shot.status || "")}</span>
          </div>
          <strong>${escapeHtml(shot.title || "未命名镜头")}</strong>
          <p class="muted">${escapeHtml(shot.summary || shot.prompt || "")}</p>
        </div>
      </section>
      <section class="orchestration-dropzone" data-shot-drop="${escapeHtml(shot.id || "")}">
        ${refs.length ? refs.map((asset) => orchestrationReferenceBadge(asset, shot)).join("") : `<small class="muted">拖入参考图</small>`}
      </section>
      ${orchestrationStageCard("image", imageItem, shot)}
      ${orchestrationStageCard("clip", clipItem, shot)}
    </article>
  `;
}

function orchestrationReferenceBadge(asset, shot) {
  const shotScoped = referenceScope(asset) === "shots";
  return `
    <span class="reference-link ${shotScoped ? "shot-bound" : ""}">
      ${escapeHtml(referenceName(asset))}
      ${shotScoped ? `<button data-action="unbind-reference-shot" data-reference-id="${escapeHtml(asset.id || "")}" data-shot-id="${escapeHtml(shot.id || "")}" ${state.busy ? "disabled" : ""} type="button">移除</button>` : ""}
    </span>
  `;
}

function orchestrationStageCard(stage, item, shot) {
  const asset = item?.latest_asset || null;
  const isImage = stage === "image";
  const status = isImage ? imageReviewStatusLabel(item?.status || "missing") : clipReviewStatusLabel(item?.status || "missing");
  const canGenerateClip = Boolean(latestImageItemForShot(shot.id)?.latest_asset && latestImageItemForShot(shot.id)?.status === "approved");
  const refCount = effectiveReferenceAssetsForShot(shot).length;
  const action = isImage ? "orchestration-generate-image" : "orchestration-generate-clip";
  const busyKey = isImage ? `orchestration-generate-image:${shot.id || ""}` : `orchestration-generate-clip:${shot.id || ""}`;
  const preview = asset
    ? (isImage ? imagePreview(asset, "thumb") : clipPreview(asset, "thumb"))
    : `<div class="${isImage ? "image-preview" : "clip-preview"} empty orchestration-empty">${isImage ? "待生成" : "待视频"}</div>`;
  return `
    <section class="orchestration-stage-card">
      <div class="shot-meta">
        <span>${isImage ? "关键帧" : "视频"}</span>
        <span>${escapeHtml(status)}</span>
      </div>
      ${preview}
      ${isImage && !refCount ? `<small class="muted">未绑定参考图</small>` : ""}
      ${!isImage && !canGenerateClip ? `<small class="muted">需先批准关键帧</small>` : ""}
      <div class="issue-actions">
        <button data-action="${action}" data-shot-id="${escapeHtml(shot.id || "")}" ${state.busy || (!isImage && !canGenerateClip) ? "disabled" : ""} type="button">${isBusy(busyKey) ? "生成中..." : "生成"}</button>
        ${asset ? `<button data-action="${isImage ? "go-image-review" : "go-clip-review"}" data-shot-id="${escapeHtml(shot.id || "")}" type="button">查看</button>` : ""}
      </div>
    </section>
  `;
}

async function setReferenceBinding(referenceId, payload, successMessage) {
  if (!state.project || !referenceId) return;
  setBusy(`bind-reference:${referenceId}`, "正在更新参考图绑定...");
  try {
    state.project = await api(`/api/projects/${state.project.id}/references/${encodeURIComponent(referenceId)}/bindings`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    state.images = await loadImages(state.project.id);
    state.clips = await loadClips(state.project.id);
    toast(successMessage || "参考图绑定已更新");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
    state.orchestrationDrag = { referenceId: "", shotId: "" };
  }
  render();
}

async function bindReferenceToShot(referenceId, shotId) {
  const asset = referenceAssets().find((item) => String(item.id || "") === String(referenceId || ""));
  if (!asset || !shotId) return;
  const ids = referenceScope(asset) === "shots" ? referenceShotIds(asset) : [];
  if (!ids.includes(String(shotId))) ids.push(String(shotId));
  await setReferenceBinding(referenceId, { scope: "shots", shot_ids: ids }, "参考图已绑定到分镜");
}

async function unbindReferenceFromShot(referenceId, shotId) {
  const asset = referenceAssets().find((item) => String(item.id || "") === String(referenceId || ""));
  if (!asset || !shotId) return;
  const ids = referenceShotIds(asset).filter((id) => id !== String(shotId));
  await setReferenceBinding(referenceId, { scope: "shots", shot_ids: ids }, "已从该分镜移除参考图");
}

async function reorderShotBefore(movedShotId, targetShotId) {
  if (!state.project || !movedShotId || !targetShotId || movedShotId === targetShotId) return;
  const ids = sortedShots().map((shot) => String(shot.id || "")).filter(Boolean);
  const movedIndex = ids.indexOf(String(movedShotId));
  const targetIndex = ids.indexOf(String(targetShotId));
  if (movedIndex < 0 || targetIndex < 0) return;
  ids.splice(movedIndex, 1);
  ids.splice(ids.indexOf(String(targetShotId)), 0, String(movedShotId));
  setBusy("reorder-shots", "正在保存分镜顺序...");
  try {
    state.project = await api(`/api/projects/${state.project.id}/shots/reorder`, {
      method: "POST",
      body: JSON.stringify({ shot_ids: ids }),
    });
    state.images = await loadImages(state.project.id);
    state.clips = await loadClips(state.project.id);
    toast("分镜顺序已更新");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
    state.orchestrationDrag = { referenceId: "", shotId: "" };
  }
  render();
}

function renderImages() {
  const busy = Boolean(state.busy);
  $("#image-review-status").textContent = imageReviewStatusLabel(state.images?.status || "not_started");
  $("#image-open-only").checked = state.imageOpenOnly;
  $("#generate-images").disabled = !state.project || !(state.project?.shots || []).length || busy;
  $("#generate-images").textContent = isBusy("generate-images") ? "正在生成..." : "生成关键帧图";
  const container = $("#image-review");
  const items = state.images?.items || [];
  const filtered = state.imageOpenOnly
    ? items.filter((item) => item.status !== "approved")
    : items;
  if (!state.project) {
    container.innerHTML = `<p class="muted">请先创建或选择项目。</p>`;
    renderImageCompare();
    return;
  }
  if (!items.length) {
    container.innerHTML = `<p class="muted">先在策划分镜中批准策划稿，生成正式分镜后再进入图片验收。</p>`;
    renderImageCompare();
    return;
  }
  container.innerHTML = `${busyMessage("image")}` + (filtered.length
    ? filtered.map(imageReviewCard).join("")
    : `<p class="muted">没有待处理图片。</p>`);
  renderImageCompare();
}

function imageReviewCard(item) {
  const shot = item.shot || {};
  const asset = item.latest_asset || null;
  const versions = item.versions || [];
  const position = Number(shot.position || 0) || "";
  const busy = Boolean(state.busy);
  const regenerateBusy = asset && isBusy(`regenerate-image:${asset.id}`);
  const approveBusy = asset && isBusy(`approve-image:${asset.id}`);
  return `
    <article class="image-review-card">
      <div class="shot-meta">
        <span>#${escapeHtml(position || "-")}</span>
        <span>${escapeHtml(imageReviewStatusLabel(item.status || "missing"))}</span>
        <span>${escapeHtml(shot.duration_seconds || 5)}s</span>
      </div>
      <strong>${escapeHtml(shot.title || "未命名镜头")}</strong>
      ${imagePreview(asset)}
      <p class="muted">${escapeHtml(shot.summary || "")}</p>
      <p>${escapeHtml(asset?.prompt || item.planned_image_prompt || shot.image_prompt || shot.prompt || "")}</p>
      ${assetReferenceNames(asset)}
      <div class="issue-actions">
        ${asset ? `<button data-action="open-image-regenerate" data-asset-id="${escapeHtml(asset.id)}" ${busy ? "disabled" : ""} type="button">${regenerateBusy ? "正在重生成..." : "重新生图"}</button>` : `<button data-action="generate-image-shot" data-shot-id="${escapeHtml(shot.id || "")}" ${busy ? "disabled" : ""} type="button">生成本镜头</button>`}
        ${asset ? `<button class="primary" data-action="approve-image" data-asset-id="${escapeHtml(asset.id)}" ${busy || item.status === "approved" ? "disabled" : ""} type="button">${approveBusy ? "正在批准..." : item.status === "approved" ? "已批准" : "批准图片"}</button>` : ""}
        ${asset ? `<button class="danger" data-action="delete-image" data-asset-id="${escapeHtml(asset.id)}" ${busy ? "disabled" : ""} type="button">删除</button>` : ""}
      </div>
      <details class="version-history" ${versions.length ? "open" : ""}>
        <summary>历史图片（${versions.length}）</summary>
        <div class="image-version-list compact-history">
          ${versions.length ? versions.map(imageVersionCard).join("") : `<small class="muted">暂无图片版本。</small>`}
        </div>
      </details>
    </article>
  `;
}

function imageVersionCard(version) {
  const busy = Boolean(state.busy);
  const status = imageAssetStatus(version);
  return `
    <article class="image-version-card">
      ${imagePreview(version, "thumb")}
      <div class="image-version-meta">
        <strong>${escapeHtml(imageReviewStatusLabel(status))}</strong>
        <small>${escapeHtml(version.created_at || "")}</small>
      </div>
      <div class="image-version-actions">
        <button data-action="open-image-regenerate" data-asset-id="${escapeHtml(version.id)}" ${busy ? "disabled" : ""} type="button">基于此版返工</button>
        <button data-action="approve-image" data-asset-id="${escapeHtml(version.id)}" ${busy || status === "approved" ? "disabled" : ""} type="button">${status === "approved" ? "已批准" : "批准此版本"}</button>
        <button data-action="compare-image-version" data-side="left" data-asset-id="${escapeHtml(version.id)}" type="button">设为左侧对比</button>
        <button data-action="compare-image-version" data-side="right" data-asset-id="${escapeHtml(version.id)}" type="button">设为右侧对比</button>
        <button class="danger" data-action="delete-image" data-asset-id="${escapeHtml(version.id)}" ${busy ? "disabled" : ""} type="button">删除版本</button>
      </div>
    </article>
  `;
}

function imagePreview(asset, variant = "") {
  if (!asset) return `<div class="image-preview empty">待生成</div>`;
  if (!isPreviewableImage(asset.file_path || "")) {
    return `<div class="image-preview empty">无可预览文件</div>`;
  }
  const klass = variant === "thumb" ? "image-preview image-preview-thumb" : "image-preview";
  return `<img class="${klass}" src="/api/assets/${encodeURIComponent(asset.id)}/file" alt="${escapeHtml(asset.title || "关键帧图")}" loading="lazy" />`;
}

function assetReferenceNames(asset) {
  const names = asset?.metadata?.reference_names || [];
  if (!Array.isArray(names) || !names.length) return "";
  return `
    <div class="reference-badges">
      ${names.filter(Boolean).map((name) => `<span>${escapeHtml(name)}</span>`).join("")}
    </div>
  `;
}

function imageIssueReference() {
  return IMAGE_ISSUES.map(([issue, label]) => `
    <button class="${state.imageRegenerate.issue === issue ? "active" : ""}" data-image-issue="${issue}" type="button">${label}</button>
  `).join("");
}

function renderImageCompare() {
  const container = $("#image-compare");
  const left = state.imageCompare.left;
  const right = state.imageCompare.right;
  if (!left && !right) {
    container.innerHTML = `<p class="muted">在图片版本中选择左、右两个版本进行对比。</p>`;
    return;
  }
  container.innerHTML = `
    <div class="compare-columns">
      ${imageCompareColumn("左侧图片", left)}
      ${imageCompareColumn("右侧图片", right)}
    </div>
    <article class="compare-diff">
      <strong>差异摘要</strong>
      ${imageDiffRows(left, right)}
    </article>
  `;
}

function imageCompareColumn(label, asset) {
  if (!asset) {
    return `
      <article class="compare-column empty">
        <strong>${label}</strong>
        <p class="muted">尚未选择图片版本。</p>
      </article>
    `;
  }
  return `
    <article class="compare-column">
      <div class="compare-meta">
        <strong>${label}</strong>
        <span>${escapeHtml(imageReviewStatusLabel(imageAssetStatus(asset)))}</span>
        <span>${escapeHtml(asset.model || "")}</span>
      </div>
      ${imagePreview(asset)}
      <p>${escapeHtml(asset.prompt || "无 prompt")}</p>
      <small>${escapeHtml(asset.file_path || "")}</small>
    </article>
  `;
}

function imageDiffRows(left, right) {
  if (!left || !right) return `<p class="muted">选择左右两个图片版本后显示差异。</p>`;
  const rows = [];
  if (imageAssetStatus(left) !== imageAssetStatus(right)) rows.push("审核状态有变化");
  if ((left.prompt || "").trim() !== (right.prompt || "").trim()) rows.push("图片 prompt 有变化");
  if ((left.model || "").trim() !== (right.model || "").trim()) rows.push("模型有变化");
  if ((left.file_path || "").trim() !== (right.file_path || "").trim()) rows.push("输出文件有变化");
  return rows.length
    ? `<ul>${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>`
    : `<p class="muted">两个图片版本的核心字段一致。</p>`;
}

function imageAssetStatus(asset) {
  return asset?.metadata?.review_status || asset?.status || "generated";
}

function imageReviewStatusLabel(status) {
  return {
    waiting_for_planning: "等待策划",
    not_started: "未开始",
    missing: "待生成",
    generated: "待验收",
    needs_review: "待验收",
    approved: "已批准",
    failed: "失败",
  }[status] || status;
}

function isPreviewableImage(path) {
  return /\.(png|jpe?g|webp|gif)$/i.test(String(path || ""));
}

function findImageAsset(assetId) {
  for (const item of state.images?.items || []) {
    const found = (item.versions || []).find((asset) => String(asset.id) === String(assetId));
    if (found) return found;
  }
  return null;
}

function clearDeletedImageCompare(assetId) {
  for (const side of ["left", "right"]) {
    if (String(state.imageCompare[side]?.id || "") === String(assetId)) {
      state.imageCompare[side] = null;
    }
  }
}

function renderClips() {
  $("#clip-review-status").textContent = clipReviewStatusLabel(state.clips?.status || "not_started");
  $("#clip-open-only").checked = state.clipOpenOnly;
  $("#generate-clips").disabled = !state.project || !(state.project?.shots || []).length || isBusy("generate-clips");
  $("#generate-clips").textContent = isBusy("generate-clips") ? "正在生成..." : "生成视频片段";
  const container = $("#clip-review");
  const items = state.clips?.items || [];
  const filtered = state.clipOpenOnly
    ? items.filter((item) => item.status !== "approved")
    : items;
  if (!state.project) {
    container.innerHTML = `<p class="muted">请先创建或选择项目。</p>`;
    renderClipCompare();
    return;
  }
  if (!items.length) {
    container.innerHTML = `<p class="muted">先完成策划分镜，再进入图生视频验收。</p>`;
    renderClipCompare();
    return;
  }
  if (!filtered.length) {
    container.innerHTML = `<p class="muted">没有待处理视频片段。</p>`;
    renderClipCompare();
    return;
  }
  const visibleItems = filtered;
  const selected = selectedClipItem(visibleItems);
  container.innerHTML = `${busyMessage("clip")}${clipWorkbench(visibleItems, selected)}`;
  renderClipCompare();
}

function selectedClipItem(items) {
  const selected = items.find((item) => String(item.shot?.id || "") === String(state.clipFocusShotId || ""));
  const firstOpen = items.find((item) => item.status !== "approved");
  return selected || firstOpen || items[0];
}

function clipWorkbench(items, item) {
  const shot = item.shot || {};
  const asset = item.latest_asset || null;
  const task = item.latest_task || null;
  const reference = item.reference_image || null;
  const versions = item.versions || [];
  const position = Number(shot.position || 0) || "";
  const regenerateBusy = asset && isBusy(`regenerate-clip:${asset.id}`);
  const approveBusy = asset && isBusy(`approve-clip:${asset.id}`);
  const canGenerate = Boolean(reference);
  return `
    <div class="clip-workbench">
      <aside class="clip-shot-rail">
        ${items.map((candidate) => clipQueueItem(candidate, shot.id)).join("")}
      </aside>
      <article class="clip-player-panel">
        <div class="section-head">
          <div>
            <h2>#${escapeHtml(position || "-")} ${escapeHtml(shot.title || "未命名镜头")}</h2>
            <p class="muted">${escapeHtml(shot.summary || "")}</p>
          </div>
          <span class="pill">${escapeHtml(clipReviewStatusLabel(item.status || "missing"))}</span>
        </div>
        ${clipPreview(asset)}
        ${task?.error ? `<div class="risk high">生成失败：${escapeHtml(task.error)}</div>` : ""}
        <div class="task-actions">
          ${asset ? `<button data-action="open-clip-regenerate" data-asset-id="${escapeHtml(asset.id)}" ${regenerateBusy || isBusy("generate-clips") ? "disabled" : ""} type="button">${regenerateBusy ? "正在重新生成..." : "按说明返工"}</button>` : `<button data-action="generate-clip-shot" data-shot-id="${escapeHtml(shot.id || "")}" ${isBusy(`generate-clip-shot:${shot.id || ""}`) || !canGenerate ? "disabled" : ""} type="button">生成当前镜头</button>`}
          ${asset ? `<button class="primary" data-action="approve-clip" data-asset-id="${escapeHtml(asset.id)}" ${approveBusy || item.status === "approved" ? "disabled" : ""} type="button">${approveBusy ? "正在批准..." : item.status === "approved" ? "已批准" : "批准当前视频"}</button>` : ""}
          ${asset ? `<button class="danger" data-action="delete-clip" data-asset-id="${escapeHtml(asset.id)}" ${isBusy(`delete-clip:${asset.id}`) ? "disabled" : ""} type="button">删除当前视频</button>` : ""}
        </div>
      </article>
      <aside class="clip-side-panel">
        <section>
          <strong>批准参考图</strong>
          ${imagePreview(reference, "thumb")}
          ${reference ? `<small>${escapeHtml(reference.model || "")}</small>` : `<p class="muted">需要先在图片验收中批准一张参考图。</p>`}
        </section>
        <section>
          <strong>视频 Prompt</strong>
          <p>${escapeHtml(asset?.prompt || item.planned_video_prompt || shot.video_prompt || shot.prompt || "")}</p>
          ${assetReferenceNames(asset)}
        </section>
        <section class="asset-meta-list">
          ${asset ? `
            <span>模型：${escapeHtml(asset.model || "")}</span>
            <span>成本：${escapeHtml(money(asset.cost || 0))}</span>
            <span>文件：${escapeHtml(asset.file_path || "")}</span>
          ` : `<span>尚未生成视频资产</span>`}
        </section>
        <details class="version-history" ${versions.length ? "open" : ""}>
          <summary>历史视频（${versions.length}）</summary>
          <div class="clip-version-list compact-history">
            ${versions.length ? versions.map(clipVersionCard).join("") : `<small class="muted">暂无视频版本。</small>`}
          </div>
        </details>
      </aside>
    </div>
  `;
}

function clipQueueItem(item, activeShotId) {
  const shot = item.shot || {};
  const active = String(shot.id || "") === String(activeShotId || "");
  return `
    <button class="clip-queue-item ${active ? "active" : ""}" data-action="select-clip-shot" data-shot-id="${escapeHtml(shot.id || "")}" type="button">
      <span>#${escapeHtml(shot.position || "-")} ${escapeHtml(shot.title || "未命名镜头")}</span>
      <small>${escapeHtml(clipReviewStatusLabel(item.status || "missing"))} · ${escapeHtml(shot.duration_seconds || 5)}s</small>
    </button>
  `;
}

function clipVersionCard(version) {
  const status = clipAssetStatus(version);
  return `
    <article class="clip-version-card">
      ${clipPreview(version, "thumb")}
      <div class="image-version-meta">
        <strong>${escapeHtml(clipReviewStatusLabel(status))}</strong>
        <small>${escapeHtml(version.created_at || "")}</small>
      </div>
      <div class="clip-version-actions">
        <button data-action="open-clip-regenerate" data-asset-id="${escapeHtml(version.id)}" ${isBusy(`regenerate-clip:${version.id}`) ? "disabled" : ""} type="button">基于此版返工</button>
        <button data-action="approve-clip" data-asset-id="${escapeHtml(version.id)}" ${isBusy(`approve-clip:${version.id}`) || status === "approved" ? "disabled" : ""} type="button">${status === "approved" ? "已批准" : "批准此版本"}</button>
        <button data-action="compare-clip-version" data-side="left" data-asset-id="${escapeHtml(version.id)}" type="button">设为左侧对比</button>
        <button data-action="compare-clip-version" data-side="right" data-asset-id="${escapeHtml(version.id)}" type="button">设为右侧对比</button>
        <button class="danger" data-action="delete-clip" data-asset-id="${escapeHtml(version.id)}" ${isBusy(`delete-clip:${version.id}`) ? "disabled" : ""} type="button">删除版本</button>
      </div>
    </article>
  `;
}

function clipPreview(asset, variant = "") {
  if (!asset) return `<div class="clip-preview empty">待生成</div>`;
  if (!isPreviewableVideo(asset.file_path || "")) {
    return `<div class="clip-preview empty">无可播放视频</div>`;
  }
  const klass = variant === "thumb" ? "clip-preview clip-preview-thumb" : "clip-preview";
  return `<video class="${klass}" src="/api/assets/${encodeURIComponent(asset.id)}/file" controls preload="metadata"></video>`;
}

function renderClipCompare() {
  const container = $("#clip-compare");
  const left = state.clipCompare.left;
  const right = state.clipCompare.right;
  if (!left && !right) {
    container.innerHTML = `<p class="muted">在视频版本中选择左、右两个版本进行对比。</p>`;
    return;
  }
  container.innerHTML = `
    <div class="compare-columns">
      ${clipCompareColumn("左侧视频", left)}
      ${clipCompareColumn("右侧视频", right)}
    </div>
    <article class="compare-diff">
      <strong>差异摘要</strong>
      ${clipDiffRows(left, right)}
    </article>
  `;
}

function clipCompareColumn(label, asset) {
  if (!asset) {
    return `
      <article class="compare-column empty">
        <strong>${label}</strong>
        <p class="muted">尚未选择视频版本。</p>
      </article>
    `;
  }
  return `
    <article class="compare-column">
      <div class="compare-meta">
        <strong>${label}</strong>
        <span>${escapeHtml(clipReviewStatusLabel(clipAssetStatus(asset)))}</span>
        <span>${escapeHtml(asset.model || "")}</span>
      </div>
      ${clipPreview(asset)}
      <p>${escapeHtml(asset.prompt || "无 prompt")}</p>
      <small>${escapeHtml(asset.file_path || "")}</small>
    </article>
  `;
}

function clipDiffRows(left, right) {
  if (!left || !right) return `<p class="muted">选择左右两个视频版本后显示差异。</p>`;
  const rows = [];
  if (clipAssetStatus(left) !== clipAssetStatus(right)) rows.push("审核状态有变化");
  if ((left.prompt || "").trim() !== (right.prompt || "").trim()) rows.push("视频 prompt 有变化");
  if ((left.model || "").trim() !== (right.model || "").trim()) rows.push("模型有变化");
  if ((left.metadata?.reference_image_asset_id || "") !== (right.metadata?.reference_image_asset_id || "")) rows.push("参考图版本有变化");
  if ((left.file_path || "").trim() !== (right.file_path || "").trim()) rows.push("输出文件有变化");
  return rows.length
    ? `<ul>${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>`
    : `<p class="muted">两个视频版本的核心字段一致。</p>`;
}

function clipAssetStatus(asset) {
  return asset?.metadata?.review_status || asset?.status || "generated";
}

function clipReviewStatusLabel(status) {
  return {
    waiting_for_planning: "等待策划",
    waiting_for_images: "等待图片批准",
    waiting_for_image: "缺少批准图",
    not_started: "未开始",
    missing: "待生成",
    queued: "排队中",
    running: "生成中",
    generated: "待验收",
    needs_review: "待验收",
    approved: "已批准",
    failed: "失败",
  }[status] || status;
}

function clipGenerationToast(payload) {
  if ((payload?.generated_asset_ids || []).length) return "视频片段已生成，等待验收";
  if ((payload?.pending || []).length) return "视频任务已提交，等待供应商返回可播放文件";
  if ((payload?.errors || []).length) return payload.errors[0].message || "视频生成失败";
  return "视频任务已更新";
}

function isPreviewableVideo(path) {
  return /\.(mp4|webm|mov|m4v)$/i.test(String(path || ""));
}

function findClipAsset(assetId) {
  for (const item of state.clips?.items || []) {
    const found = (item.versions || []).find((asset) => String(asset.id) === String(assetId));
    if (found) return found;
  }
  return null;
}

function clearDeletedClipCompare(assetId) {
  for (const side of ["left", "right"]) {
    if (String(state.clipCompare[side]?.id || "") === String(assetId)) {
      state.clipCompare[side] = null;
    }
  }
}

function clipIssueReference() {
  return CLIP_ISSUES.map(([issue, label]) => `
    <button class="${state.clipRegenerate.issue === issue ? "active" : ""}" data-clip-issue="${issue}" type="button">${label}</button>
  `).join("");
}

function openClipRegenerateDialog(assetId) {
  state.clipRegenerate = { assetId, issue: "stiff_motion" };
  $("#clip-regenerate-reference").innerHTML = clipIssueReference();
  $("#clip-regenerate-note").value = "";
  const dialog = $("#clip-regenerate-dialog");
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
}

function closeClipRegenerateDialog() {
  setClipRegenerateDialogBusy(false);
  const dialog = $("#clip-regenerate-dialog");
  if (typeof dialog.close === "function") {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
  }
}

function setClipRegenerateDialogBusy(isBusy) {
  $("#clip-regenerate-note").disabled = isBusy;
  $("#cancel-clip-regenerate").disabled = isBusy;
  $("#close-clip-regenerate").disabled = isBusy;
  $("#clip-regenerate-submit").disabled = isBusy;
  $("#clip-regenerate-submit").textContent = isBusy ? "正在重新生成..." : "确认重新生成";
  $("#clip-regenerate-progress").hidden = !isBusy;
  $("#clip-regenerate-reference").querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
}

function openImageRegenerateDialog(assetId) {
  state.imageRegenerate = { assetId, issue: "artifact" };
  $("#image-regenerate-reference").innerHTML = imageIssueReference();
  $("#image-regenerate-note").value = "";
  const dialog = $("#image-regenerate-dialog");
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
}

function closeImageRegenerateDialog() {
  setImageRegenerateDialogBusy(false);
  const dialog = $("#image-regenerate-dialog");
  if (typeof dialog.close === "function") {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
  }
}

function setImageRegenerateDialogBusy(isBusy) {
  $("#image-regenerate-note").disabled = isBusy;
  $("#cancel-image-regenerate").disabled = isBusy;
  $("#close-image-regenerate").disabled = isBusy;
  $("#image-regenerate-submit").disabled = isBusy;
  $("#image-regenerate-submit").textContent = isBusy ? "正在重新生图..." : "确认重新生图";
  $("#image-regenerate-progress").hidden = !isBusy;
  $("#image-regenerate-reference").querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
}

function renderShots() {
  const project = state.project;
  const shots = project?.shots || [];
  $("#shot-count").textContent = shots.length;
  $("#shots").innerHTML = shots.length
    ? shots.map((shot) => `
      <article class="shot-card">
        <div class="shot-meta">
          <span>#${shot.position}</span>
          <span>${shot.duration_seconds}s</span>
          <span>${escapeHtml(shot.status)}</span>
        </div>
        <strong>${escapeHtml(shot.title)}</strong>
        <p class="muted">${escapeHtml(shot.summary || "未填写摘要")}</p>
        <p>${escapeHtml(shot.prompt || "")}</p>
      </article>
    `).join("")
    : `<p class="muted">分镜表为空，先添加一个镜头。</p>`;

  const shotSelect = $("#task-shot");
  shotSelect.innerHTML = `<option value="">全项目</option>` + shots
    .map((shot) => `<option value="${shot.id}">#${shot.position} ${escapeHtml(shot.title)}</option>`)
    .join("");
}

function renderTasks() {
  const tasks = state.project?.tasks || [];
  const busy = Boolean(state.busy);
  $("#task-count").textContent = tasks.length;
  $("#tasks").innerHTML = tasks.length
    ? tasks.map((task) => {
      const risk = task.risk_flags?.length
        ? `<div class="risk ${task.risk_level}">${task.risk_flags.map((flag) => `${escapeHtml(flag.label)}：${escapeHtml(flag.suggestion)}`).join("<br>")}</div>`
        : "";
      const actions = [
        task.status === "blocked" ? `<button data-action="approve-task" data-task-id="${task.id}" ${busy ? "disabled" : ""} type="button">✓</button>` : "",
        ["queued", "failed"].includes(task.status) ? `<button class="primary" data-action="run-task" data-task-id="${task.id}" ${busy ? "disabled" : ""} type="button">${isBusy(`run-task:${task.id}`) ? "正在运行..." : "▶"}</button>` : "",
      ].join("");
      return `
        <article class="task-card">
          <div class="task-meta">
            <span class="status ${escapeHtml(task.status)}">${statusLabel(task.status)}</span>
            <span>${escapeHtml(task.stage)}</span>
            <span>${escapeHtml(task.provider_id)}</span>
            <span>${money(task.cost_estimate || 0)}</span>
          </div>
          <strong>${escapeHtml(task.model || "未指定模型")}</strong>
          <p>${escapeHtml(task.prompt || "")}</p>
          ${risk}
          <div class="task-actions">${actions}</div>
        </article>
      `;
    }).join("")
    : `<p class="muted">没有生成任务。</p>`;

  const providerSelect = $("#task-provider");
  providerSelect.innerHTML = state.providers
    .map((provider) => `<option value="${provider.id}">${provider.enabled ? "●" : "○"} ${escapeHtml(provider.name)}</option>`)
    .join("");
}

function renderAssets() {
  const assets = state.project?.assets || [];
  $("#assets").innerHTML = assets.length
    ? `
      <table>
        <thead>
          <tr>${["类型", "标题", "镜头", "文件", "供应商", "成本", "状态", "操作"].map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${assets.map((asset) => `
            <tr>
              <td>${escapeHtml(asset.type || "")}</td>
              <td>${escapeHtml(asset.title || "")}</td>
              <td>${escapeHtml(asset.shot_id || "")}</td>
              <td>${escapeHtml(asset.file_path || "")}</td>
              <td>${escapeHtml(asset.provider || "")}</td>
              <td>${escapeHtml(money(asset.cost || 0))}</td>
              <td>${escapeHtml(asset.status || "")}</td>
              <td><button class="danger compact-button" data-action="delete-asset" data-asset-id="${escapeHtml(asset.id || "")}" type="button">删除</button></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `
    : `<p class="muted">暂无资产。</p>`;
  const ledger = state.project?.ledger || [];
  $("#ledger").innerHTML = table(
    ["时间", "供应商", "操作", "模型", "状态", "实际成本"],
    ledger.map((row) => [
      row.created_at,
      row.provider_id,
      row.operation,
      row.model,
      row.status,
      money(row.actual_cost || 0),
    ]),
    "暂无账本记录。"
  );
}

function renderProviders() {
  const container = $("#providers");
  if (!container) return;
  container.innerHTML = state.providers.map((provider) => `
    <article class="provider-row">
      <strong>${escapeHtml(provider.name)}</strong>
      <div class="provider-meta">
        <span>${escapeHtml(provider.id)}</span>
        <span>${escapeHtml(provider.kind)}</span>
        <span>${provider.enabled ? "启用" : "停用"}</span>
        <span>${escapeHtml(provider.api_key_env || "未设置密钥变量")}</span>
      </div>
      <p class="muted">${escapeHtml(provider.pricing?.note || provider.pricing?.unit || "价格由配置表维护")}</p>
      <div class="task-actions">
        <button data-action="provider-smoke-test" data-provider-id="${escapeHtml(provider.id)}" type="button">适配器探针</button>
      </div>
    </article>
  `).join("");
}

function renderModelPipeline() {
  const container = $("#model-pipeline-slots");
  if (!container) return;
  const slots = state.modelPipeline?.slots || [];
  container.innerHTML = slots.map(modelSlotCard).join("");
  for (const slot of slots) {
    const row = container.querySelector(`[data-model-slot-key="${cssEscape(slot.slot_key)}"]`);
    if (!row) continue;
    const select = row.querySelector('[data-slot-field="provider_id"]');
    if (select) select.value = slot.provider_id || "mock-local";
    refreshModelSlotHints(row);
  }
}

function modelSlotCard(slot) {
  const ui = MODEL_SLOT_UI[slot.slot_key] || { index: "--", input: slot.role || "", output: slot.stage || "", sample: "" };
  const settings = slot.settings || {};
  const providerOptions = state.providers
    .map((provider) => `<option value="${escapeHtml(provider.id)}">${provider.enabled ? "●" : "○"} ${escapeHtml(provider.name)}</option>`)
    .join("");
  const candidateOptions = modelCandidatesForSlot(slot)
    .map((model) => `<option value="${escapeHtml(model)}"></option>`)
    .join("");
  const status = modelSlotStatus(slot);
  return `
    <article class="model-slot-card model-slot-workbench" data-model-slot-key="${escapeHtml(slot.slot_key)}">
      <div class="model-slot-head">
        <span class="slot-index">${escapeHtml(ui.index)}</span>
        <div>
          <strong>${escapeHtml(slot.label)}</strong>
          <small>${escapeHtml(ui.input)} -> ${escapeHtml(ui.output)}</small>
        </div>
        <span class="status ${escapeHtml(status.kind)}">${escapeHtml(status.label)}</span>
      </div>
      <div class="model-slot-flow">
        <span>输入：${escapeHtml(ui.input)}</span>
        <span>输出：${escapeHtml(ui.output)}</span>
      </div>
      <div class="grid-two">
        <label>
          供应商
          <select data-slot-field="provider_id">
            ${providerOptions}
          </select>
        </label>
        <label>
          模型
          <input data-slot-field="model" list="model-options-${escapeHtml(slot.slot_key)}" value="${escapeHtml(slot.model || "")}" placeholder="${escapeHtml(ui.sample)}" />
          <datalist id="model-options-${escapeHtml(slot.slot_key)}">${candidateOptions}</datalist>
        </label>
      </div>
      <div class="grid-three model-key-grid">
        <label>
          Base URL
          <input data-slot-setting="base_url" value="${escapeHtml(settings.base_url || "")}" placeholder="留空使用供应商默认地址" />
        </label>
        <label>
          Key 环境变量
          <input data-slot-setting="api_key_env" value="${escapeHtml(settings.api_key_env || slot.api_key_env || "")}" placeholder="DEEPSEEK_API_KEY" />
        </label>
        <label>
          Key 文件路径
          <input data-slot-setting="api_key_file" value="${escapeHtml(settings.api_key_file || "")}" placeholder="C:\\keys\\filmgen-model-key.txt" />
        </label>
      </div>
      <div class="provider-snapshot" data-slot-provider-summary></div>
      <div class="model-candidate-list" data-slot-model-candidates></div>
      <div class="model-slot-footer">
        <label class="checkline compact">
          <input data-slot-field="enabled" type="checkbox" ${slot.enabled ? "checked" : ""} />
          启用此阶段
        </label>
        <button data-action="probe-model-slot" data-slot-key="${escapeHtml(slot.slot_key)}" type="button">测试此模型</button>
      </div>
      <div class="slot-probe-result" data-slot-result="${escapeHtml(slot.slot_key)}"></div>
    </article>
  `;
}

function providerById(providerId) {
  return state.providers.find((provider) => String(provider.id || "") === String(providerId || "")) || null;
}

function modelFamilyForSlot(slot) {
  const role = String(slot.role || "");
  if (role === "text_to_image") return "image";
  if (role === "image_to_video") return "video";
  return "text";
}

function modelCandidatesForSlot(slot, provider = null) {
  const family = modelFamilyForSlot(slot);
  const providers = provider ? [provider] : state.providers;
  const candidates = [];
  for (const item of providers) {
    const catalog = item?.model_catalog || {};
    for (const model of catalog[family] || []) {
      if (model && !candidates.includes(model)) candidates.push(model);
    }
  }
  if (slot.model && !candidates.includes(slot.model)) candidates.unshift(slot.model);
  return candidates;
}

function modelSlotStatus(slot) {
  if (!slot.enabled) return { kind: "blocked", label: "停用" };
  const provider = providerById(slot.provider_id);
  if (!slot.provider_id || !provider) return { kind: "failed", label: "缺供应商" };
  if (!provider.enabled) return { kind: "blocked", label: "供应商停用" };
  if (!slot.model) return { kind: "failed", label: "缺模型" };
  return { kind: "succeeded", label: "可测试" };
}

function collectModelSlotPayload(row) {
  const settings = {};
  row.querySelectorAll("[data-slot-setting]").forEach((field) => {
    const key = field.dataset.slotSetting || "";
    if (!key) return;
    settings[key] = field.value?.trim() || "";
  });
  return {
    slot_key: row.dataset.modelSlotKey,
    provider_id: row.querySelector('[data-slot-field="provider_id"]')?.value || "",
    model: row.querySelector('[data-slot-field="model"]')?.value?.trim() || "",
    enabled: row.querySelector('[data-slot-field="enabled"]')?.checked !== false,
    settings,
  };
}

function refreshModelSlotHints(row) {
  const slotKey = row.dataset.modelSlotKey || "";
  const baseSlot = (state.modelPipeline?.slots || []).find((slot) => slot.slot_key === slotKey) || { slot_key: slotKey };
  const payload = { ...baseSlot, ...collectModelSlotPayload(row) };
  const provider = providerById(payload.provider_id);
  const summary = row.querySelector("[data-slot-provider-summary]");
  if (summary) {
    const keyEnv = payload.settings?.api_key_env || provider?.api_key_env || "";
    const keyFile = payload.settings?.api_key_file || "";
    const baseUrl = payload.settings?.base_url || provider?.base_url || "";
    summary.innerHTML = provider
      ? `
        <span>${provider.enabled ? "已启用" : "已停用"}</span>
        <span>${escapeHtml(provider.kind || "provider")}</span>
        <span>${escapeHtml(baseUrl || "无 Base URL")}</span>
        <span>${escapeHtml(keyFile ? `Key 文件：${keyFile}` : keyEnv ? `Key 变量：${keyEnv}` : "未配置 Key")}</span>
      `
      : `<span>未选择供应商</span>`;
  }
  const candidates = row.querySelector("[data-slot-model-candidates]");
  if (candidates) {
    const models = modelCandidatesForSlot(payload, provider).slice(0, 6);
    candidates.innerHTML = models.length
      ? models.map((model) => `<button class="compact-button" data-action="use-model-candidate" data-model="${escapeHtml(model)}" type="button">${escapeHtml(model)}</button>`).join("")
      : `<small class="muted">该供应商没有模型清单，可直接填写模型名。</small>`;
  }
}

function renderSmartCutBridge() {
  const defaults = state.smartDefaults || {};
  $("#smart-cut-target").textContent = defaults.base_url || "http://127.0.0.1:8769";
  $("#bridge-manifest-path").value = state.editPack?.manifest_path || $("#bridge-manifest-path").value || "";
  if (!$("#bridge-style-package").value) $("#bridge-style-package").value = defaults.style_package || "";
  if (!$("#bridge-input-video").value) $("#bridge-input-video").value = defaults.input_video || "";
  if (!$("#bridge-output-dir").value) $("#bridge-output-dir").value = defaults.output_dir || "";
}

function table(headers, rows, emptyText) {
  if (!rows.length) return `<p class="muted">${emptyText}</p>`;
  return `
    <table>
      <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(String(cell ?? ""))}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function currentStep() {
  return (state.project?.workflow || []).find((step) => step.step_key === state.project.current_step);
}

function statusLabel(status) {
  return {
    pending: "等待",
    in_progress: "进行中",
    completed: "完成",
    blocked: "待审批",
    queued: "排队",
    running: "运行中",
    succeeded: "成功",
    failed: "失败",
    cancelled: "取消",
  }[status] || status;
}

function planningStatusLabel(status) {
  return {
    not_started: "未开始",
    draft: "待验收",
    approved: "已批准",
  }[status] || status;
}

function planningShotStatusLabel(status) {
  return {
    draft: "待检查",
    needs_review: "需复核",
    approved: "已通过",
  }[status] || status;
}

function planningIssueButtons(position) {
  const busy = Boolean(state.busy);
  return [
    ["story_off", "故事偏离"],
    ["character_unclear", "角色不清晰"],
    ["scene_unclear", "场景不清晰"],
    ["weak_camera", "镜头太弱"],
  ].map(([issue, label]) => `
    <button data-action="regenerate-planning-shot" data-position="${position}" data-issue="${issue}" ${busy ? "disabled" : ""} type="button">${isBusy(`regenerate-planning-shot:${position}`) ? "正在重写..." : label}</button>
  `).join("");
}

function money(value) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(String(value));
  return String(value).replaceAll('"', '\\"');
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2600);
}

function setBusy(key, message) {
  state.busy = key ? { key, message } : null;
  render();
  if (message) toast(message);
}

function isBusy(key) {
  return state.busy?.key === key;
}

function busyMessage(scope = "") {
  if (!state.busy) return "";
  const message = state.busy.message || "正在处理，请稍候...";
  return `<div class="busy-banner" data-busy-scope="${escapeHtml(scope)}">${escapeHtml(message)}</div>`;
}

function formatEditBrief(payload) {
  const brief = payload?.edit_brief || {};
  const lines = [];
  if (brief.brief_text) lines.push(brief.brief_text);
  if (Array.isArray(brief.checklist) && brief.checklist.length) {
    lines.push(`确认清单：\n${brief.checklist.map((item, index) => `${index + 1}. ${item}`).join("\n")}`);
  }
  if (payload?.filmgen_handoff?.input_video_candidates?.length) {
    lines.push(`可用输入视频：\n${payload.filmgen_handoff.input_video_candidates.join("\n")}`);
  }
  if (brief.output_dir) lines.push(`输出目录：${brief.output_dir}`);
  return lines.join("\n\n");
}

function formatProviderSmoke(payload) {
  const rows = (payload.results || []).map((row) => {
    const suffix = row.output_file ? `\n  输出：${row.output_file}` : row.reason ? `\n  原因：${row.reason}` : "";
    return `${row.family}: ${row.status} (${row.model || "未配置模型"})${suffix}`;
  });
  return [
    `${payload.provider_name || payload.provider_id} / ${payload.adapter}`,
    `整体：${payload.ok ? "通过" : "未通过"}`,
    ...rows,
    "",
    JSON.stringify(payload, null, 2),
  ].join("\n");
}

function collectModelPipelinePayload() {
  const slots = [];
  document.querySelectorAll("[data-model-slot-key]").forEach((row) => {
    slots.push(collectModelSlotPayload(row));
  });
  return { slots };
}

function formatModelPipelineConfig(payload) {
  const rows = (payload.slots || []).map((slot) => {
    const provider = slot.provider_name || slot.provider_id || "未配置供应商";
    return `${slot.label}: ${slot.enabled ? "启用" : "停用"} / ${provider} / ${slot.model || "未配置模型"}`;
  });
  return ["已保存模型链路", ...rows].join("\n");
}

function formatModelPipelineProbe(payload) {
  const rows = (payload.results || []).map((row) => {
    const suffix = row.output_file ? `\n  输出：${row.output_file}` : row.reason ? `\n  原因：${row.reason}` : "";
    return `${row.label}: ${row.status} / ${row.provider_id || "未配置供应商"} / ${row.model || "未配置模型"}${suffix}`;
  });
  return [
    `整体：${payload.ok ? "通过" : "未全部通过"}`,
    ...rows,
    "",
    JSON.stringify(payload, null, 2),
  ].join("\n");
}

function formatSingleModelProbe(payload, slotKey) {
  const row = (payload.results || []).find((item) => item.slot_key === slotKey) || (payload.results || [])[0] || {};
  const suffix = row.output_file ? `\n输出：${row.output_file}` : row.reason ? `\n原因：${row.reason}` : "";
  return `${row.label || slotKey}: ${row.status || "unknown"}\n供应商：${row.provider_id || "未配置"}\n模型：${row.model || "未配置"}${suffix}`;
}

function cardsToText(cards) {
  return (cards || [])
    .map((card) => [card.name, card.description, card.visual_prompt].map((part) => String(part || "").trim()).join(" | "))
    .join("\n");
}

function storyboardToText(items) {
  return (items || [])
    .map((item, index) => [
      item.position || index + 1,
      item.title,
      item.duration_seconds || 5,
      item.summary,
      item.location,
      item.camera,
      item.image_prompt || item.prompt,
      item.video_prompt || item.prompt,
    ].map((part) => String(part || "").trim()).join(" | "))
    .join("\n");
}

function parseCards(text, fallbackName) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const parts = splitPlanningLine(line);
      return {
        name: parts[0] || `${fallbackName} ${index + 1}`,
        description: parts[1] || "",
        visual_prompt: parts.slice(2).join(" | ") || "",
      };
    });
}

function parseStoryboard(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const parts = splitPlanningLine(line);
      const position = Number(parts[0] || index + 1) || index + 1;
      const duration = Number(parts[2] || 5) || 5;
      return {
        position,
        title: parts[1] || `镜头 ${position}`,
        duration_seconds: duration,
        summary: parts[3] || "",
        location: parts[4] || "",
        camera: parts[5] || "",
        image_prompt: parts[6] || "",
        video_prompt: parts[7] || parts[6] || "",
      };
    });
}

function splitPlanningLine(line) {
  return String(line || "").split(/\s*[|｜]\s*/).map((part) => part.trim());
}

function collectPlanningDraft() {
  const base = state.planning?.planning_draft || {};
  const previousByPosition = new Map((base.storyboard || []).map((item) => [Number(item.position || 0), item]));
  return {
    ...base,
    story_outline: $("#planning-story").value.trim(),
    characters: parseCards($("#planning-characters").value, "角色"),
    scenes: parseCards($("#planning-scenes").value, "场景"),
    storyboard: parseStoryboard($("#planning-storyboard").value).map((item) => ({
      ...item,
      status: previousByPosition.get(Number(item.position || 0))?.status || item.status || "draft",
      review_note: previousByPosition.get(Number(item.position || 0))?.review_note || "",
    })),
  };
}

async function loadSmartCutPreview(manifestPath) {
  if (!manifestPath) return;
  try {
    const preview = await api("/api/smart-video-cut/edit-pack/preview", {
      method: "POST",
      body: JSON.stringify({ manifest_path: manifestPath }),
    });
    state.bridgePreview = preview;
    const handoff = preview.filmgen_handoff || {};
    const candidates = handoff.input_video_candidates || [];
    const defaultInput = state.smartDefaults?.input_video || "";
    const defaultOutput = state.smartDefaults?.output_dir || "";
    if (candidates.length && (!$("#bridge-input-video").value || $("#bridge-input-video").value === defaultInput)) {
      $("#bridge-input-video").value = candidates[0];
    }
    if ((!$("#bridge-output-dir").value || $("#bridge-output-dir").value === defaultOutput) && handoff.recommended_output_dir) {
      $("#bridge-output-dir").value = handoff.recommended_output_dir;
    }
    if (!$("#bridge-user-request").value && handoff.recommended_user_request) {
      $("#bridge-user-request").value = handoff.recommended_user_request;
    }
    $("#edit-brief-result").textContent = JSON.stringify(preview, null, 2);
  } catch (error) {
    $("#edit-brief-result").textContent = `智能剪辑软件未连接或读取失败：${error.message}`;
  }
}

$("#project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const project = await api("/api/projects", {
    method: "POST",
    body: JSON.stringify(formPayload(form)),
  });
  form.reset();
  await loadBootstrap();
  await selectProject(project.id);
  toast("项目已创建");
});

$("#project-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-project-id]");
  if (!button) return;
  await selectProject(button.dataset.projectId);
});

$("#brief-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return toast("请先创建或选择项目");
  const payload = formPayload(event.currentTarget);
  state.project = await api(`/api/projects/${state.project.id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.projects = state.projects.map((project) => (project.id === state.project.id ? {
    ...project,
    title: state.project.title,
    logline: state.project.logline,
    current_step: state.project.current_step,
  } : project));
  toast("项目需求已保存");
  render();
});

document.querySelector(".tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab]");
  if (!button) return;
  state.tab = button.dataset.tab;
  renderTabs();
});

$("#orchestration-add-reference").addEventListener("click", () => {
  state.tab = "images";
  renderTabs();
  toast("可在图片验收页添加参考图");
});

$("#orchestration-reference-tray").addEventListener("dragstart", (event) => {
  const card = event.target.closest("[data-reference-id]");
  if (!card) return;
  const referenceId = card.dataset.referenceId || "";
  state.orchestrationDrag = { referenceId, shotId: "" };
  event.dataTransfer?.setData("application/x-filmgen-reference", referenceId);
  event.dataTransfer?.setData("text/plain", referenceId);
});

$("#orchestration-board").addEventListener("dragstart", (event) => {
  const row = event.target.closest(".orchestration-row");
  if (!row || event.target.closest("button")) return;
  const shotId = row.dataset.shotId || "";
  state.orchestrationDrag = { referenceId: "", shotId };
  event.dataTransfer?.setData("application/x-filmgen-shot", shotId);
  event.dataTransfer?.setData("text/plain", shotId);
});

$("#orchestration-board").addEventListener("dragover", (event) => {
  const hasReference = Boolean(state.orchestrationDrag.referenceId || dragTypesInclude(event, "application/x-filmgen-reference"));
  const hasShot = Boolean(state.orchestrationDrag.shotId || dragTypesInclude(event, "application/x-filmgen-shot"));
  if ((hasReference && event.target.closest("[data-shot-drop]")) || (hasShot && event.target.closest(".orchestration-row"))) {
    event.preventDefault();
  }
});

$("#orchestration-global-drop").addEventListener("dragover", (event) => {
  if (state.orchestrationDrag.referenceId || dragTypesInclude(event, "application/x-filmgen-reference")) {
    event.preventDefault();
  }
});

$("#orchestration-global-drop").addEventListener("drop", async (event) => {
  event.preventDefault();
  const referenceId = event.dataTransfer?.getData("application/x-filmgen-reference") || state.orchestrationDrag.referenceId;
  if (!referenceId || !state.project) return;
  await setReferenceBinding(referenceId, { scope: "project", shot_ids: [] }, "参考图已设为全片");
});

$("#orchestration-board").addEventListener("drop", async (event) => {
  event.preventDefault();
  if (!state.project) return;
  const referenceId = event.dataTransfer?.getData("application/x-filmgen-reference") || state.orchestrationDrag.referenceId;
  const droppedShot = event.target.closest("[data-shot-drop]");
  if (referenceId && droppedShot) {
    await bindReferenceToShot(referenceId, droppedShot.dataset.shotDrop || "");
    return;
  }
  const movedShotId = event.dataTransfer?.getData("application/x-filmgen-shot") || state.orchestrationDrag.shotId;
  const targetRow = event.target.closest(".orchestration-row");
  if (movedShotId && targetRow) {
    await reorderShotBefore(movedShotId, targetRow.dataset.shotId || "");
  }
});

$("#orchestration-reference-tray").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || !state.project) return;
  const referenceId = button.dataset.referenceId || "";
  if (!referenceId) return;
  if (button.dataset.action === "set-reference-global") {
    await setReferenceBinding(referenceId, { scope: "project", shot_ids: [] }, "参考图已设为全片");
  }
  if (button.dataset.action === "clear-reference-binding") {
    await setReferenceBinding(referenceId, { scope: "shots", shot_ids: [] }, "参考图绑定已清空");
  }
  if (button.dataset.action === "bind-reference-picker") {
    const picker = button.closest(".orchestration-reference-card")?.querySelector(`[data-reference-shot-picker="${cssEscape(referenceId)}"]`);
    const shotId = picker?.value || "";
    if (!shotId) return toast("请选择要绑定的分镜");
    await bindReferenceToShot(referenceId, shotId);
  }
});

$("#orchestration-board").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || !state.project) return;
  const shotId = button.dataset.shotId || "";
  try {
    if (button.dataset.action === "unbind-reference-shot") {
      await unbindReferenceFromShot(button.dataset.referenceId || "", shotId);
    }
    if (button.dataset.action === "orchestration-generate-image") {
      if (!confirm("即将调用文生图模型生成这个镜头的关键帧。确认继续？")) return;
      setBusy(`orchestration-generate-image:${shotId}`, "正在生成本镜头关键帧，请稍候...");
      state.images = await api(`/api/projects/${state.project.id}/images/generate`, {
        method: "POST",
        body: JSON.stringify({ shot_id: shotId }),
      });
      state.project = state.images.project || state.project;
      state.clips = await loadClips(state.project.id);
      toast("本镜头关键帧图已生成");
    }
    if (button.dataset.action === "orchestration-generate-clip") {
      if (!confirm("即将调用图生视频模型生成这个镜头。确认继续？")) return;
      setBusy(`orchestration-generate-clip:${shotId}`, "正在生成本镜头视频片段，请稍候...");
      state.clipFocusShotId = shotId;
      state.clips = await api(`/api/projects/${state.project.id}/clips/generate`, {
        method: "POST",
        body: JSON.stringify({ shot_id: shotId }),
      });
      state.project = state.clips.project || state.project;
      toast(clipGenerationToast(state.clips));
    }
    if (button.dataset.action === "go-image-review") {
      state.tab = "images";
      render();
      return;
    }
    if (button.dataset.action === "go-clip-review") {
      state.clipFocusShotId = shotId;
      state.tab = "clips";
      render();
      return;
    }
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#advance-step").addEventListener("click", async () => {
  if (!state.project) return;
  try {
    const data = await api(`/api/projects/${state.project.id}/workflow/advance`, { method: "POST", body: "{}" });
    state.project = data.project;
    toast("工作流已推进");
  } catch (error) {
    if (error.payload?.project) state.project = error.payload.project;
    toast(error.payload?.error?.message || error.message);
  }
  render();
});

$("#approve-step").addEventListener("click", async () => {
  if (!state.project) return;
  const step = currentStep();
  if (!step) return;
  state.project = await api(`/api/projects/${state.project.id}/workflow/${step.step_key}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved: true, note: "local approval" }),
  });
  toast("当前步骤已批准");
  render();
});

$("#shot-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return toast("请先创建项目");
  const form = event.currentTarget;
  state.project = await api(`/api/projects/${state.project.id}/shots`, {
    method: "POST",
    body: JSON.stringify(formPayload(form)),
  });
  state.images = await loadImages(state.project.id);
  state.clips = await loadClips(state.project.id);
  form.reset();
  toast("镜头已添加");
  render();
});

$("#generate-planning").addEventListener("click", async () => {
  if (!state.project) return toast("请先创建项目");
  setBusy("generate-planning", "正在调用编剧策划模型生成草案，请稍候...");
  try {
    state.planning = await api(`/api/projects/${state.project.id}/planning/generate`, {
      method: "POST",
      body: JSON.stringify({ brief: state.project.logline || "" }),
    });
    state.project = state.planning.project || state.project;
    toast("策划草案已生成");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#planning-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return toast("请先创建项目");
  state.planning = await api(`/api/projects/${state.project.id}/planning/save`, {
    method: "POST",
    body: JSON.stringify({ planning_draft: collectPlanningDraft() }),
  });
  state.project = state.planning.project || state.project;
  toast("策划修改已保存");
  render();
});

$("#approve-planning").addEventListener("click", async () => {
  if (!state.project) return toast("请先创建项目");
  setBusy("approve-planning", "正在批准策划稿并同步分镜...");
  try {
    state.planning = await api(`/api/projects/${state.project.id}/planning/approve`, {
      method: "POST",
      body: JSON.stringify({ planning_draft: collectPlanningDraft() }),
    });
    state.project = state.planning.project || state.project;
    state.images = await loadImages(state.project.id);
    state.clips = await loadClips(state.project.id);
    toast("策划稿已批准并同步分镜");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#planning-open-only").addEventListener("change", (event) => {
  state.planningOpenOnly = event.currentTarget.checked;
  renderPlanningShotReview(state.planning?.planning_draft || null);
});

$("#planning-shot-review").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || !state.project) return;
  const position = Number(button.dataset.position || 0);
  if (!position) return;
  try {
    if (button.dataset.action === "regenerate-planning-shot") {
      setBusy(`regenerate-planning-shot:${position}`, "正在重写这个镜头...");
      state.planning = await api(`/api/projects/${state.project.id}/planning/shots/${position}/regenerate`, {
        method: "POST",
        body: JSON.stringify({ planning_draft: collectPlanningDraft(), issue: button.dataset.issue || "story_off" }),
      });
      state.project = state.planning.project || state.project;
      toast("该镜头已重生成，待复核");
    }
    if (button.dataset.action === "approve-planning-shot") {
      setBusy(`approve-planning-shot:${position}`, "正在标记镜头通过...");
      state.planning = await api(`/api/projects/${state.project.id}/planning/shots/${position}/approve`, {
        method: "POST",
        body: JSON.stringify({ planning_draft: collectPlanningDraft() }),
      });
      state.project = state.planning.project || state.project;
      toast("该镜头已标记通过");
    }
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#planning-versions").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || !state.project) return;
  const assetId = button.dataset.assetId || "";
  if (!assetId) return;
  try {
    if (button.dataset.action === "compare-planning-version") {
      const side = button.dataset.side === "right" ? "right" : "left";
      state.planningCompare[side] = await api(
        `/api/projects/${state.project.id}/planning/versions/${encodeURIComponent(assetId)}`
      );
      renderPlanningCompare();
      toast(`${side === "left" ? "左侧" : "右侧"}版本已载入`);
    }
    if (button.dataset.action === "delete-planning-version") {
      if (!confirm("删除这个策划版本？如果它是当前批准版本，后续阶段会回到剩余版本或项目分镜。")) return;
      setBusy(`delete-planning:${assetId}`, "正在删除策划版本...");
      state.project = await api(`/api/projects/${state.project.id}/assets/${encodeURIComponent(assetId)}`, {
        method: "DELETE",
      });
      state.planning = await loadPlanning(state.project.id);
      state.images = await loadImages(state.project.id);
      state.clips = await loadClips(state.project.id);
      clearDeletedPlanningCompare(assetId);
      toast("策划版本已删除");
      render();
    }
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
});

$("#generate-images").addEventListener("click", async () => {
  if (!state.project) return toast("请先创建项目");
  if (!confirm("即将调用文生图模型生成关键帧图。确认继续？")) return;
  setBusy("generate-images", "正在调用文生图模型生成关键帧，通常需要十几秒，请稍候...");
  try {
    state.images = await api(`/api/projects/${state.project.id}/images/generate`, {
      method: "POST",
      body: "{}",
    });
    state.project = state.images.project || state.project;
    state.clips = await loadClips(state.project.id);
    toast("关键帧图已生成，等待验收");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#reference-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return toast("请先创建项目");
  const form = event.currentTarget;
  const payload = formPayload(form);
  delete payload.file;
  const file = $("#reference-file")?.files?.[0] || null;
  if (!file && !payload.file_path) return toast("请上传参考图片，或填写本地图片路径");
  setBusy("save-reference", "正在保存角色/场景参考图...");
  try {
    if (file) {
      payload.data_url = await fileToDataUrl(file);
      payload.file_name = file.name || "reference.png";
    }
    state.project = await api(`/api/projects/${state.project.id}/references`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.images = await loadImages(state.project.id);
    state.clips = await loadClips(state.project.id);
    form.reset();
    toast("参考图已保存，后续关键帧会沿用");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#reference-assets").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action='delete-reference']");
  if (!button || !state.project) return;
  const assetId = button.dataset.assetId || "";
  if (!assetId) return;
  if (!confirm("删除这个锁定参考图？之后新生成的关键帧不会再使用它。")) return;
  setBusy(`delete-reference:${assetId}`, "正在删除参考图...");
  try {
    state.project = await api(`/api/projects/${state.project.id}/assets/${encodeURIComponent(assetId)}`, {
      method: "DELETE",
    });
    state.images = await loadImages(state.project.id);
    state.clips = await loadClips(state.project.id);
    clearDeletedImageCompare(assetId);
    clearDeletedClipCompare(assetId);
    toast("参考图已删除");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#image-open-only").addEventListener("change", (event) => {
  state.imageOpenOnly = event.currentTarget.checked;
  renderImages();
});

$("#image-review").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || !state.project) return;
  try {
    if (button.dataset.action === "generate-image-shot") {
      if (!confirm("即将调用文生图模型生成这个镜头的关键帧。确认继续？")) return;
      setBusy(`generate-image-shot:${button.dataset.shotId || ""}`, "正在生成本镜头关键帧，请稍候...");
      state.images = await api(`/api/projects/${state.project.id}/images/generate`, {
        method: "POST",
        body: JSON.stringify({ shot_id: button.dataset.shotId || "" }),
      });
      state.project = state.images.project || state.project;
      state.clips = await loadClips(state.project.id);
      toast("本镜头关键帧图已生成");
    }
    if (button.dataset.action === "approve-image") {
      const assetId = button.dataset.assetId || "";
      setBusy(`approve-image:${assetId}`, "正在批准图片...");
      state.images = await api(`/api/projects/${state.project.id}/images/${encodeURIComponent(button.dataset.assetId || "")}/approve`, {
        method: "POST",
        body: "{}",
      });
      state.project = state.images.project || state.project;
      state.clips = await loadClips(state.project.id);
      toast("图片已批准");
    }
    if (button.dataset.action === "delete-image") {
      const assetId = button.dataset.assetId || "";
      if (!confirm("删除这张图片及其本地生成文件？已删除图片不会进入后续视频生成。")) return;
      setBusy(`delete-image:${assetId}`, "正在删除图片...");
      state.images = await api(`/api/projects/${state.project.id}/images/${encodeURIComponent(assetId)}`, {
        method: "DELETE",
      });
      state.project = state.images.project || state.project;
      state.clips = await loadClips(state.project.id);
      clearDeletedImageCompare(assetId);
      toast("图片已删除");
    }
    if (button.dataset.action === "open-image-regenerate") {
      openImageRegenerateDialog(button.dataset.assetId || "");
      return;
    }
    if (button.dataset.action === "compare-image-version") {
      const side = button.dataset.side === "right" ? "right" : "left";
      state.imageCompare[side] = findImageAsset(button.dataset.assetId || "");
      renderImageCompare();
      toast(`${side === "left" ? "左侧" : "右侧"}图片版本已载入`);
      return;
    }
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#image-regenerate-reference").addEventListener("click", (event) => {
  const button = event.target.closest("[data-image-issue]");
  if (!button) return;
  state.imageRegenerate.issue = button.dataset.imageIssue || "artifact";
  $("#image-regenerate-reference").innerHTML = imageIssueReference();
});

$("#image-regenerate-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return toast("请先创建项目");
  const assetId = state.imageRegenerate.assetId;
  const note = $("#image-regenerate-note").value.trim();
  if (!assetId) return toast("请选择要重生成的图片");
  if (!note) return toast("请先写明具体问题或修改方向");
  setImageRegenerateDialogBusy(true);
  setBusy(`regenerate-image:${assetId}`, "正在按你的说明重新生图，可能需要十几秒，请稍候...");
  try {
    state.images = await api(`/api/projects/${state.project.id}/images/${encodeURIComponent(assetId)}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ issue: state.imageRegenerate.issue || "artifact", note }),
    });
    state.project = state.images.project || state.project;
    state.clips = await loadClips(state.project.id);
    closeImageRegenerateDialog();
    toast("图片已重生成，等待验收");
    render();
  } catch (error) {
    toast(error.message);
  } finally {
    setImageRegenerateDialogBusy(false);
    state.busy = null;
    render();
  }
});

$("#close-image-regenerate").addEventListener("click", closeImageRegenerateDialog);
$("#cancel-image-regenerate").addEventListener("click", closeImageRegenerateDialog);

$("#generate-clips").addEventListener("click", async () => {
  if (!state.project) return toast("请先创建项目");
  if (!confirm("即将调用图生视频模型，基于已批准图片生成视频片段。确认继续？")) return;
  setBusy("generate-clips", "正在调用图生视频模型生成片段，可能需要更久，请稍候...");
  try {
    state.clips = await api(`/api/projects/${state.project.id}/clips/generate`, {
      method: "POST",
      body: "{}",
    });
    state.project = state.clips.project || state.project;
    toast(clipGenerationToast(state.clips));
  } catch (error) {
    state.clips = await loadClips(state.project.id);
    state.project = state.clips?.project || state.project;
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#clip-open-only").addEventListener("change", (event) => {
  state.clipOpenOnly = event.currentTarget.checked;
  renderClips();
});

$("#clip-review").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button || !state.project) return;
  try {
    if (button.dataset.action === "select-clip-shot") {
      state.clipFocusShotId = button.dataset.shotId || "";
      renderClips();
      return;
    }
    if (button.dataset.action === "generate-clip-shot") {
      if (!confirm("即将调用图生视频模型生成这个镜头。确认继续？")) return;
      state.clipFocusShotId = button.dataset.shotId || state.clipFocusShotId;
      setBusy(`generate-clip-shot:${button.dataset.shotId || ""}`, "正在生成本镜头视频片段，请稍候...");
      state.clips = await api(`/api/projects/${state.project.id}/clips/generate`, {
        method: "POST",
        body: JSON.stringify({ shot_id: button.dataset.shotId || "" }),
      });
      state.project = state.clips.project || state.project;
      toast(clipGenerationToast(state.clips));
    }
    if (button.dataset.action === "approve-clip") {
      const assetId = button.dataset.assetId || "";
      setBusy(`approve-clip:${assetId}`, "正在批准视频片段...");
      state.clips = await api(`/api/projects/${state.project.id}/clips/${encodeURIComponent(assetId)}/approve`, {
        method: "POST",
        body: "{}",
      });
      state.project = state.clips.project || state.project;
      toast("视频片段已批准");
    }
    if (button.dataset.action === "delete-clip") {
      const assetId = button.dataset.assetId || "";
      if (!confirm("删除这个视频片段及其本地生成文件？已删除视频不会进入 edit pack。")) return;
      setBusy(`delete-clip:${assetId}`, "正在删除视频片段...");
      state.clips = await api(`/api/projects/${state.project.id}/clips/${encodeURIComponent(assetId)}`, {
        method: "DELETE",
      });
      state.project = state.clips.project || state.project;
      clearDeletedClipCompare(assetId);
      toast("视频片段已删除");
    }
    if (button.dataset.action === "open-clip-regenerate") {
      openClipRegenerateDialog(button.dataset.assetId || "");
      return;
    }
    if (button.dataset.action === "compare-clip-version") {
      const side = button.dataset.side === "right" ? "right" : "left";
      state.clipCompare[side] = findClipAsset(button.dataset.assetId || "");
      renderClipCompare();
      toast(`${side === "left" ? "左侧" : "右侧"}视频版本已载入`);
      return;
    }
  } catch (error) {
    state.clips = await loadClips(state.project.id);
    state.project = state.clips?.project || state.project;
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

$("#clip-regenerate-reference").addEventListener("click", (event) => {
  const button = event.target.closest("[data-clip-issue]");
  if (!button) return;
  state.clipRegenerate.issue = button.dataset.clipIssue || "stiff_motion";
  $("#clip-regenerate-reference").innerHTML = clipIssueReference();
});

$("#clip-regenerate-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return toast("请先创建项目");
  const assetId = state.clipRegenerate.assetId;
  const note = $("#clip-regenerate-note").value.trim();
  if (!assetId) return toast("请选择要重生成的视频片段");
  if (!note) return toast("请先写明具体问题或修改方向");
  if (!confirm("即将再次调用图生视频模型。确认继续？")) return;
  setClipRegenerateDialogBusy(true);
  setBusy(`regenerate-clip:${assetId}`, "正在按你的说明重新生成视频片段，可能需要更久，请稍候...");
  try {
    state.clips = await api(`/api/projects/${state.project.id}/clips/${encodeURIComponent(assetId)}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ issue: state.clipRegenerate.issue || "stiff_motion", note }),
    });
    state.project = state.clips.project || state.project;
    closeClipRegenerateDialog();
    toast(clipGenerationToast(state.clips));
    render();
  } catch (error) {
    state.clips = await loadClips(state.project.id);
    state.project = state.clips?.project || state.project;
    toast(error.message);
  } finally {
    setClipRegenerateDialogBusy(false);
    state.busy = null;
    render();
  }
});

$("#close-clip-regenerate").addEventListener("click", closeClipRegenerateDialog);
$("#cancel-clip-regenerate").addEventListener("click", closeClipRegenerateDialog);

$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.project) return toast("请先创建项目");
  const form = event.currentTarget;
  const data = await api(`/api/projects/${state.project.id}/generation-tasks`, {
    method: "POST",
    body: JSON.stringify(formPayload(form)),
  });
  state.project = data.project;
  toast(data.risk.risk_level === "low" ? "任务已入队" : "任务已进入人工审批");
  render();
});

$("#tasks").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  if (button.dataset.action === "approve-task") {
    state.project = await api(`/api/generation-tasks/${button.dataset.taskId}/approve`, {
      method: "POST",
      body: "{}",
    });
    toast("任务已批准");
  }
  if (button.dataset.action === "run-task") {
    const data = await api(`/api/generation-tasks/${button.dataset.taskId}/run`, {
      method: "POST",
      body: "{}",
    });
    state.project = data.project;
    state.images = await loadImages(state.project.id);
    state.clips = await loadClips(state.project.id);
    toast("生成结果已回流资产库");
  }
  render();
});

$("#register-asset").addEventListener("click", async () => {
  if (!state.project) return toast("请先创建项目");
  const title = window.prompt("资产标题");
  if (!title) return;
  const filePath = window.prompt("本地文件路径") || "";
  state.project = await api(`/api/projects/${state.project.id}/assets`, {
    method: "POST",
    body: JSON.stringify({ title, file_path: filePath, type: "final", status: "registered" }),
  });
  toast("资产已登记");
  render();
});

$("#assets").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action='delete-asset']");
  if (!button || !state.project) return;
  const assetId = button.dataset.assetId || "";
  if (!assetId) return;
  if (!confirm("删除这个资产登记？若文件在 FilmGen 工作目录内，也会删除对应本地生成文件。")) return;
  setBusy(`delete-asset:${assetId}`, "正在删除资产...");
  try {
    state.project = await api(`/api/projects/${state.project.id}/assets/${encodeURIComponent(assetId)}`, {
      method: "DELETE",
    });
    state.images = await loadImages(state.project.id);
    state.clips = await loadClips(state.project.id);
    state.planning = await loadPlanning(state.project.id);
    clearDeletedPlanningCompare(assetId);
    clearDeletedImageCompare(assetId);
    clearDeletedClipCompare(assetId);
    toast("资产已删除");
  } catch (error) {
    toast(error.message);
  } finally {
    state.busy = null;
  }
  render();
});

if ($("#provider-form")) {
  $("#provider-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formPayload(form);
    const data = await api("/api/providers", { method: "POST", body: JSON.stringify(payload) });
    state.providers = data.providers || [];
    form.reset();
    toast("供应商配置已保存");
    render();
  });
}

if ($("#providers")) {
  $("#providers").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action='provider-smoke-test']");
    if (!button) return;
    const providerId = button.dataset.providerId;
    $("#provider-smoke-result").textContent = "正在检查适配器技术探针...";
    try {
      const result = await api(`/api/providers/${encodeURIComponent(providerId)}/smoke-test`, {
        method: "POST",
        body: "{}",
      });
      $("#provider-smoke-result").textContent = formatProviderSmoke(result);
      toast(result.ok ? "适配器探针通过" : "适配器探针未全部通过");
    } catch (error) {
      $("#provider-smoke-result").textContent = error.message;
      toast(error.message);
    }
  });
}

$("#model-pipeline-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    state.modelPipeline = await api("/api/model-pipeline/config", {
      method: "POST",
      body: JSON.stringify(collectModelPipelinePayload()),
    });
    $("#model-pipeline-result").textContent = formatModelPipelineConfig(state.modelPipeline);
    toast("模型槽位已保存");
    renderModelPipeline();
  } catch (error) {
    $("#model-pipeline-result").textContent = error.message;
    toast(error.message);
  }
});

$("#model-pipeline-slots").addEventListener("change", (event) => {
  const row = event.target.closest("[data-model-slot-key]");
  if (!row) return;
  refreshModelSlotHints(row);
});

$("#model-pipeline-slots").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const row = button.closest("[data-model-slot-key]");
  if (!row) return;
  if (button.dataset.action === "use-model-candidate") {
    const input = row.querySelector('[data-slot-field="model"]');
    if (input) {
      input.value = button.dataset.model || "";
      refreshModelSlotHints(row);
    }
    return;
  }
  if (button.dataset.action === "probe-model-slot") {
    const slot = collectModelSlotPayload(row);
    const slotLabel = row.querySelector(".model-slot-head strong")?.textContent?.trim() || slot.slot_key;
    if (!confirm(`即将调用${slotLabel}进行一次模型测试。确认继续？`)) return;
    const singleSlotPayload = collectModelPipelinePayload().slots.map((item) => ({
      ...item,
      enabled: item.slot_key === slot.slot_key ? item.enabled : false,
    }));
    const resultNode = row.querySelector("[data-slot-result]");
    button.disabled = true;
    button.textContent = "正在测试...";
    if (resultNode) resultNode.textContent = "正在测试...";
    try {
      const result = await api("/api/model-pipeline/probe", {
        method: "POST",
        body: JSON.stringify({ slots: singleSlotPayload }),
      });
      const selectedResult = (result.results || []).find((item) => item.slot_key === slot.slot_key) || {};
      if (resultNode) resultNode.textContent = formatSingleModelProbe(result, slot.slot_key);
      $("#model-pipeline-result").textContent = formatModelPipelineProbe(result);
      toast(selectedResult.status === "succeeded" ? `${slotLabel}测试通过` : `${slotLabel}测试未通过`);
    } catch (error) {
      if (resultNode) resultNode.textContent = error.message;
      $("#model-pipeline-result").textContent = error.message;
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "测试此模型";
    }
  }
});

$("#probe-model-pipeline").addEventListener("click", async () => {
  if (!confirm("即将依次调用三阶段模型进行链路测试。确认继续？")) return;
  $("#model-pipeline-result").textContent = "正在测试三阶段模型配置...";
  try {
    const result = await api("/api/model-pipeline/probe", {
      method: "POST",
      body: JSON.stringify(collectModelPipelinePayload()),
    });
    $("#model-pipeline-result").textContent = formatModelPipelineProbe(result);
    toast(result.ok ? "模型链路探针通过" : "模型链路探针未全部通过");
  } catch (error) {
    $("#model-pipeline-result").textContent = error.message;
    toast(error.message);
  }
});

$("#export-pack").addEventListener("click", async () => {
  if (!state.project) return toast("请先创建项目");
  const data = await api(`/api/projects/${state.project.id}/edit-pack`, { method: "POST", body: "{}" });
  state.project = data.project;
  state.editPack = data.edit_pack;
  $("#export-result").textContent = JSON.stringify(data.edit_pack, null, 2);
  $("#bridge-manifest-path").value = data.edit_pack?.manifest_path || "";
  toast("剪辑交付包已导出");
  render();
  await loadSmartCutPreview(data.edit_pack?.manifest_path);
});

$("#smart-cut-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = formPayload(event.currentTarget);
  if (!payload.manifest_path) return toast("请先导出 edit pack");
  try {
    const data = await api("/api/smart-video-cut/edit-brief", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("#edit-brief-result").textContent = formatEditBrief(data);
    toast("剪辑标准预览已生成");
  } catch (error) {
    $("#edit-brief-result").textContent = error.message;
    toast(error.message);
  }
  render();
});

loadBootstrap().catch((error) => {
  toast(error.message);
});
