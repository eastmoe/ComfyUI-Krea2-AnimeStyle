const { app } = window.comfyAPI.app;

const NODE_NAMES = new Set(["Krea2AnimeStyleCLIPTextEncode", "Krea2AnimeStylePromptText"]);
const STYLE_URL = "/comfy-krea2-animestyle/styles.json";
const LOCALE_URL = "/comfy-krea2-animestyle/locale/zh-sn/nodes.json";

let styleDataPromise = null;
let localeTextPromise = null;

function chainCallback(target, name, callback) {
  const original = target[name];
  target[name] = function (...args) {
    const result = original?.apply(this, args);
    callback.apply(this, args);
    return result;
  };
}

function currentLocale() {
  const configured =
    app.ui?.settings?.getSettingValue?.("Comfy.Locale") ??
    app.ui?.settings?.getSettingValue?.("ComfyUI.Locale") ??
    navigator.language;
  return String(configured || "en").toLowerCase();
}

async function loadStyleData() {
  if (!styleDataPromise) {
    styleDataPromise = fetch(STYLE_URL).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    });
  }
  return styleDataPromise;
}

async function loadLocaleText() {
  if (!currentLocale().startsWith("zh")) return null;
  if (!localeTextPromise) {
    localeTextPromise = fetch(LOCALE_URL)
      .then((response) => (response.ok ? response.json() : null))
      .catch(() => null);
  }
  return localeTextPromise;
}

function injectStyle() {
  if (document.getElementById("krea2-animestyle-css")) return;
  const style = document.createElement("style");
  style.id = "krea2-animestyle-css";
  style.textContent = `
    .krea2-style-panel {
      color: #ddd;
      font: 12px/1.35 sans-serif;
      padding: 8px;
      box-sizing: border-box;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      gap: 6px;
      background: rgba(20, 20, 20, 0.72);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 6px;
    }
    .krea2-style-toolbar,
    .krea2-style-pagebar {
      display: flex;
      align-items: center;
      gap: 6px;
      flex: 0 0 auto;
    }
    .krea2-style-search,
    .krea2-style-stage-select {
      min-width: 0;
      height: 24px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      background: #1d1d1d;
      color: #eee;
      border-radius: 4px;
      padding: 0 7px;
      box-sizing: border-box;
    }
    .krea2-style-search {
      flex: 1 1 auto;
    }
    .krea2-style-stage-select {
      flex: 0 0 142px;
    }
    .krea2-style-btn {
      height: 24px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      background: #2b2b2b;
      color: #ddd;
      border-radius: 4px;
      padding: 0 8px;
      cursor: pointer;
      white-space: nowrap;
    }
    .krea2-style-btn:disabled {
      color: #777;
      cursor: default;
      opacity: 0.72;
    }
    .krea2-style-count,
    .krea2-style-page {
      color: #aaa;
      white-space: nowrap;
    }
    .krea2-style-list {
      flex: 1 1 auto;
      min-height: 0;
      display: grid;
      align-content: start;
      gap: 4px;
    }
    .krea2-style-row {
      display: grid;
      grid-template-columns: 16px 1fr;
      gap: 6px;
      align-items: start;
      min-height: 42px;
      padding: 4px 5px;
      border: 1px solid rgba(255, 255, 255, 0.07);
      border-radius: 4px;
      cursor: pointer;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.025);
    }
    .krea2-style-row:hover {
      background: rgba(255, 255, 255, 0.07);
    }
    .krea2-style-row input {
      margin: 2px 0 0;
    }
    .krea2-style-title {
      color: #f5f5f5;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .krea2-style-desc {
      margin-top: 1px;
      color: #aaa;
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .krea2-style-stage-tag {
      color: #f1d8ad;
      margin-right: 4px;
    }
    .krea2-style-empty {
      color: #999;
      padding: 14px 4px;
      text-align: center;
    }
  `;
  document.head.appendChild(style);
}

function splitSelection(value) {
  return String(value || "")
    .split(/[\n,;，；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function commitSelection(node, widget, selected) {
  widget.value = Array.from(selected).join("\n");
  widget.callback?.(widget.value);
  node.graph?.setDirtyCanvas(true, true);
}

function hideWidget(widget) {
  widget.hidden = true;
  widget.computeSize = () => [0, -4];
}

function stopCanvasEvents(element) {
  for (const eventName of [
    "pointerdown",
    "pointermove",
    "pointerup",
    "mousedown",
    "mousemove",
    "mouseup",
    "dblclick",
    "wheel",
    "keydown",
  ]) {
    element.addEventListener(eventName, (event) => {
      event.stopPropagation();
      if (eventName === "wheel") event.preventDefault();
    }, { passive: false });
  }
}

function nodeTextFor(node, text) {
  const name = node.constructor?.comfyClass ?? node.type;
  return text?.nodes?.[name];
}

function applyLabels(node, text) {
  const nodeText = nodeTextFor(node, text);
  if (!nodeText) return;
  node.title = nodeText.title ?? node.title;

  for (const widget of node.widgets ?? []) {
    const item = nodeText.inputs?.[widget.name];
    if (!item) continue;
    widget.label = item.label;
    widget.localized_name = item.label;
    widget.options = widget.options ?? {};
    widget.options.tooltip = item.tooltip ?? widget.options.tooltip;
  }

  for (const input of node.inputs ?? []) {
    const item = nodeText.inputs?.[input.name] ?? nodeText.inputs?.[input.label];
    if (!item) continue;
    input.label = item.label;
    input.localized_name = item.label;
  }

  for (const output of node.outputs ?? []) {
    const item = nodeText.outputs?.[output.name] ?? nodeText.outputs?.[output.label];
    if (!item) continue;
    output.label = item.label;
    output.localized_name = item.label;
  }
}

function patchNodeData(nodeData, nodeText) {
  if (!nodeText) return;
  nodeData.display_name = nodeText.title ?? nodeData.display_name;
  nodeData.description = nodeText.description ?? nodeData.description;

  for (const section of ["required", "optional"]) {
    const inputs = nodeData.input?.[section];
    if (!inputs) continue;
    for (const [name, spec] of Object.entries(inputs)) {
      const item = nodeText.inputs?.[name];
      if (!item || !Array.isArray(spec)) continue;
      const options = spec[1] ?? {};
      options.display_name = item.label;
      options.label = item.label;
      options.localized_name = item.label;
      options.tooltip = item.tooltip ?? options.tooltip;
      spec[1] = options;
    }
  }
}

function panelHeightForNode(node) {
  const height = Number(node.size?.[1] || 520);
  return Math.max(260, Math.min(520, Math.floor(height - 150)));
}

function pageSizeForHeight(panelHeight) {
  return Math.max(4, Math.floor((panelHeight - 78) / 52));
}

function buildRow(item, selected, onChange) {
  const label = document.createElement("label");
  label.className = "krea2-style-row";
  label.title = item.prompt_en || "";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = selected.has(item.id);

  const text = document.createElement("span");
  const title = document.createElement("div");
  title.className = "krea2-style-title";
  const stage = document.createElement("span");
  stage.className = "krea2-style-stage-tag";
  stage.textContent = item.stage_label;
  title.append(stage, document.createTextNode(`${item.zh} / ${item.ja} / ${item.romaji}`));

  const desc = document.createElement("div");
  desc.className = "krea2-style-desc";
  desc.textContent = item.prompt_en;
  text.append(title, desc);
  label.append(checkbox, text);

  checkbox.addEventListener("change", () => onChange(item.id, checkbox.checked));
  return label;
}

async function buildStyleSelector(node) {
  if (node._krea2StyleSelectorBuilt || typeof node.addDOMWidget !== "function") return;
  const widget = node.widgets?.find((item) => item.name === "style_selection");
  if (!widget) return;

  node._krea2StyleSelectorBuilt = true;
  hideWidget(widget);
  injectStyle();

  const root = document.createElement("div");
  root.className = "krea2-style-panel";
  root.textContent = "Loading styles...";
  stopCanvasEvents(root);

  node._krea2PanelHeight = panelHeightForNode(node);
  const domWidget = node.addDOMWidget("style_selector_ui", "Krea2AnimeStyleSelector", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => node._krea2PanelHeight,
  });
  domWidget.computeSize = (width) => [width, node._krea2PanelHeight + 8];

  const data = await loadStyleData();
  const stages = data.stages || [];
  const stageById = new Map(stages.map((stage) => [stage.id, stage]));
  const styles = (data.styles || []).map((item) => ({
    ...item,
    stage_label: stageById.get(item.stage)?.short ?? item.stage,
    search_text: `${item.zh} ${item.ja} ${item.romaji} ${item.prompt_en}`.toLowerCase(),
  }));

  const selected = new Set(splitSelection(widget.value));
  let page = 0;
  let filtered = styles;
  let pageSize = pageSizeForHeight(node._krea2PanelHeight);

  root.textContent = "";
  root.style.height = `${node._krea2PanelHeight}px`;

  const toolbar = document.createElement("div");
  toolbar.className = "krea2-style-toolbar";

  const stageSelect = document.createElement("select");
  stageSelect.className = "krea2-style-stage-select";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = "全部分类";
  stageSelect.append(allOption);
  for (const stage of stages) {
    const option = document.createElement("option");
    option.value = stage.id;
    option.textContent = `${stage.order} ${stage.short}`;
    stageSelect.append(option);
  }

  const search = document.createElement("input");
  search.className = "krea2-style-search";
  search.placeholder = "搜索风格";
  const clear = document.createElement("button");
  clear.className = "krea2-style-btn";
  clear.textContent = "清空";
  toolbar.append(stageSelect, search, clear);

  const list = document.createElement("div");
  list.className = "krea2-style-list";

  const pagebar = document.createElement("div");
  pagebar.className = "krea2-style-pagebar";
  const prev = document.createElement("button");
  prev.className = "krea2-style-btn";
  prev.textContent = "上一页";
  const next = document.createElement("button");
  next.className = "krea2-style-btn";
  next.textContent = "下一页";
  const pageLabel = document.createElement("span");
  pageLabel.className = "krea2-style-page";
  const count = document.createElement("span");
  count.className = "krea2-style-count";
  count.style.marginLeft = "auto";
  pagebar.append(prev, next, pageLabel, count);

  root.append(toolbar, list, pagebar);

  function refilter() {
    const needle = search.value.trim().toLowerCase();
    const stage = stageSelect.value;
    filtered = styles.filter((item) => {
      if (stage && item.stage !== stage) return false;
      return !needle || item.search_text.includes(needle);
    });
    page = 0;
    render();
  }

  function render() {
    node._krea2PanelHeight = panelHeightForNode(node);
    pageSize = pageSizeForHeight(node._krea2PanelHeight);
    root.style.height = `${node._krea2PanelHeight}px`;

    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    page = Math.min(page, totalPages - 1);
    list.replaceChildren();

    const start = page * pageSize;
    const pageItems = filtered.slice(start, start + pageSize);
    if (pageItems.length === 0) {
      const empty = document.createElement("div");
      empty.className = "krea2-style-empty";
      empty.textContent = "没有匹配的风格";
      list.append(empty);
    } else {
      for (const item of pageItems) {
        list.append(buildRow(item, selected, (id, checked) => {
          if (checked) selected.add(id);
          else selected.delete(id);
          commitSelection(node, widget, selected);
          updateFooter();
        }));
      }
    }

    prev.disabled = page <= 0;
    next.disabled = page >= totalPages - 1;
    updateFooter();
    node.graph?.setDirtyCanvas(true, true);
  }

  function updateFooter() {
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    pageLabel.textContent = `${page + 1} / ${totalPages} (${filtered.length})`;
    count.textContent = `${selected.size} 已选`;
  }

  search.addEventListener("input", refilter);
  stageSelect.addEventListener("change", refilter);
  clear.addEventListener("click", () => {
    selected.clear();
    commitSelection(node, widget, selected);
    render();
  });
  prev.addEventListener("click", () => {
    page = Math.max(0, page - 1);
    render();
  });
  next.addEventListener("click", () => {
    page += 1;
    render();
  });

  chainCallback(node, "onResize", render);
  const minWidth = Math.max(620, node.size?.[0] || 0);
  node.setSize?.([minWidth, Math.max(node.size?.[1] || 0, node.computeSize?.()[1] || 0)]);
  render();
}

app.registerExtension({
  name: "eastmoe.ComfyKrea2AnimeStyle",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_NAMES.has(nodeData?.name)) return;

    const locale = await loadLocaleText();
    patchNodeData(nodeData, locale?.nodes?.[nodeData?.name]);

    chainCallback(nodeType.prototype, "onNodeCreated", function () {
      const node = this;
      loadLocaleText().then((text) => applyLabels(node, text));
      buildStyleSelector(node).catch((error) => {
        console.warn("[Comfy-Krea2-AnimeStyle] Failed to build style selector:", error);
      });
    });

    chainCallback(nodeType.prototype, "onConfigure", function () {
      const node = this;
      loadLocaleText().then((text) => applyLabels(node, text));
    });
  },
});
