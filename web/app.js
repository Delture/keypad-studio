/* Keypad Studio front-end */
(function () {
  "use strict";

  const S = {
    api: null,
    demo: false,
    ready: false,
    config: null,
    device: null,
    runtime: null,
    meta: null,
    view: "overview",
    polling: false,
    saveTimer: null,
    recent: [],
    triggerCount: 0,
    pressed: {},
    editing: null,
    libraryFilter: "",
    pickerFilter: "",
    deviceLog: [],
    hub: null,
    hubBusy: false,
    hubTimer: null,
    gamepad: null,
    gamepadTimer: null,
    gamepadBusy: false,
    gamepadMetaKey: "",
    modalScroll: 0,
    recording: false,
  };

  const TYPE_COLOR = {
    key: "#8b5cf6",
    text: "#38bdf8",
    open: "#fbbf24",
    command: "#34d399",
    macro: "#f472b6",
    media: "#fb923c",
    app_volume: "#d97757",
    network_toggle: "#4f9d8a",
    mouse: "#a78bfa",
    system: "#60a5fa",
    clipboard: "#2dd4bf",
    window: "#c084fc",
    layer: "#f59e0b",
    profile: "#818cf8",
    delay: "#94a3b8",
    none: "#64748b",
  };

  const TOP_ICON = { actions: "grid", profiles: "layers", settings: "settings" };
  const VIEW_TITLE = {
    overview: "设备中枢",
    keypad: "小键盘",
    keyboard: "新盟 M75 键盘",
    mouse: "AUSDOM G04 Ultra 鼠标",
    gamepad: "BIGBIG WON Rainbow 2 SE",
    device: "设备诊断",
    actions: "动作库",
    profiles: "配置",
    settings: "设置",
  };
  const HUB_VIEWS = new Set(["overview", "keyboard", "mouse"]);

  const GAMEPAD_BUTTON_LABELS = {
    up: "十字上",
    down: "十字下",
    left: "十字左",
    right: "十字右",
    start: "菜单",
    back: "视图",
    l3: "L3",
    r3: "R3",
    lb: "LB",
    rb: "RB",
    a: "A",
    b: "B",
    x: "X",
    y: "Y",
  };

  function emptyGamepadButtons() {
    return Object.fromEntries(Object.keys(GAMEPAD_BUTTON_LABELS).map((key) => [key, false]));
  }

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function ico(name, size = 18, cls = "") {
    return window.icon(name, size, cls);
  }

  function typeInfo(type) {
    return (S.meta?.actionTypes || []).find((t) => t.id === type) || { id: type, name: type, icon: "bolt", desc: "" };
  }

  function typeColor(type) {
    return TYPE_COLOR[type] || "#8b5cf6";
  }

  function actionById(id) {
    if (!id) return null;
    return (S.config?.actions || []).find((a) => a.id === id) || null;
  }

  function actionIcon(action) {
    return action?.icon || typeInfo(action?.type).icon || "bolt";
  }

  function actionDisplayName(action) {
    return action?.name || "未绑定";
  }

  function currentProfile() {
    if (!S.config) return null;
    return S.config.profiles.find((p) => p.id === S.config.settings.activeProfile) || S.config.profiles[0] || null;
  }

  function currentLayers() {
    return currentProfile()?.layers || [];
  }

  function currentLayerIndex() {
    const layers = currentLayers();
    return Math.max(0, Math.min(Number(S.config?.settings.activeLayer || 0), Math.max(0, layers.length - 1)));
  }

  function currentLayer() {
    return currentLayers()[currentLayerIndex()] || null;
  }

  function bindingFor(slot) {
    return currentLayer()?.keys?.[String(slot)] || { action: null, double: null };
  }

  function actionForSlot(slot) {
    return actionById(bindingFor(slot).action);
  }

  function usageCount(actionId) {
    let count = 0;
    for (const profile of S.config?.profiles || []) {
      for (const layer of profile.layers || []) {
        for (const binding of Object.values(layer.keys || {})) {
          if (binding?.action === actionId) count += 1;
          if (binding?.double === actionId) count += 1;
        }
      }
    }
    return count;
  }

  function parseCombo(value) {
    return String(value || "")
      .replace(/＋/g, "+")
      .split("+")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function comboText(keys) {
    return (keys || []).join(" + ");
  }

  function actionPreview(action) {
    if (!action) return "未绑定动作";
    const p = action.params || {};
    switch (action.type) {
      case "key": return comboText(p.keys) + (p.mode === "down" ? "（按下）" : p.mode === "up" ? "（抬起）" : "");
      case "text": return (p.text || "").replace(/\s+/g, " ").slice(0, 48) || "空文本";
      case "open": return p.target || "未选择目标";
      case "command": return (p.command || "").replace(/\s+/g, " ").slice(0, 48) || "空命令";
      case "macro": return `${(p.steps || []).length} 个步骤` + (Number(p.repeat || 1) > 1 ? ` × ${p.repeat}` : "");
      case "media": return (S.meta?.mediaActions || {})[p.action] || p.action || "";
      case "app_volume": return `${p.process || "cs2.exe"} · ${p.mode === "mute" ? "静音" : p.mode === "full" ? "100%" : "静音 / 100% 切换"}`;
      case "network_toggle": return "Tailscale ↔ TUN（代理常开）";
      case "mouse": return (S.meta?.mouseActions || {})[p.action] || p.action || "";
      case "system": return (S.meta?.systemActions || {})[p.action] || p.action || "";
      case "clipboard": return (S.meta?.clipboardActions || {})[p.action] || p.action || "";
      case "window": return (S.meta?.windowActions || {})[p.action] || p.action || "";
      case "layer": return p.mode === "set" ? `切换到 ${currentLayers()[p.index || 0]?.name || "图层"}` : p.mode === "toggle" ? "切换图层" : p.mode === "next" ? "下一图层" : "上一图层";
      case "profile": return p.mode === "set" ? `切换到 ${S.config.profiles.find((x) => x.id === p.profileId)?.name || "配置"}` : p.mode === "next" ? "下一个配置" : "上一个配置";
      case "delay": return `${p.ms || 0} 毫秒`;
      case "none": return "无动作";
      default: return action.type;
    }
  }

  function shortTime(ts) {
    const d = new Date((ts || Date.now() / 1000) * 1000);
    return d.toLocaleTimeString("zh-CN", { hour12: false });
  }

  function deviceLabel() {
    if (!S.device?.connected) return "未连接";
    const model = S.device.model || "6 键小键盘";
    return `${model} · v${S.device.firmware || "?"}`;
  }

  function uuid(prefix) {
    return prefix + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4);
  }

  // ------------------------------------------------------------------
  // Demo state (for browser preview only)
  // ------------------------------------------------------------------

  function demoState() {
    const meta = {
      actionTypes: [
        { id: "key", name: "键盘按键", desc: "发送按键或组合键", icon: "keyboard" },
        { id: "text", name: "文本输入", desc: "输入一段文字", icon: "text" },
        { id: "open", name: "打开 / 运行", desc: "程序、文件、网址", icon: "folder" },
        { id: "command", name: "运行命令", desc: "PowerShell / CMD", icon: "terminal" },
        { id: "macro", name: "宏序列", desc: "多步骤键鼠脚本", icon: "macro" },
        { id: "media", name: "多媒体", desc: "播放与音量", icon: "music" },
        { id: "app_volume", name: "应用音量", desc: "音量合成器单程序音量", icon: "volume" },
        { id: "network_toggle", name: "网络切换", desc: "Tailscale 与 Clash Party 组合切换", icon: "network" },
        { id: "mouse", name: "鼠标动作", desc: "点击、滚轮、移动", icon: "mouse" },
        { id: "system", name: "系统功能", desc: "锁屏、睡眠等", icon: "power" },
        { id: "clipboard", name: "剪贴板", desc: "复制、粘贴", icon: "clipboard" },
        { id: "window", name: "窗口操作", desc: "最小化、关闭", icon: "window" },
        { id: "layer", name: "切换图层", desc: "切换按键图层", icon: "layers" },
        { id: "profile", name: "切换配置", desc: "切换整套配置", icon: "grid" },
        { id: "delay", name: "延时", desc: "等待一段时间", icon: "clock" },
        { id: "none", name: "无动作", desc: "不做任何事", icon: "ban" },
      ],
      mediaActions: { play_pause: "播放 / 暂停", next: "下一曲", prev: "上一曲", stop: "停止", volume_up: "音量 +", volume_down: "音量 −", mute: "静音" },
      systemActions: { lock: "锁定电脑", sleep: "睡眠", shutdown: "关机", restart: "重启", taskmgr: "任务管理器", explorer: "文件资源管理器", settings: "Windows 设置", terminal: "终端 / PowerShell", show_desktop: "显示桌面", screenshot: "截屏到图片", empty_recycle: "清空回收站" },
      clipboardActions: { copy: "复制 (Ctrl+C)", paste: "粘贴 (Ctrl+V)", cut: "剪切 (Ctrl+X)", select_all: "全选 (Ctrl+A)", undo: "撤销 (Ctrl+Z)", set: "写入剪贴板", clear: "清空剪贴板" },
      windowActions: { minimize: "最小化当前窗口", maximize: "最大化当前窗口", restore: "还原当前窗口", close: "关闭当前窗口", switch: "切换窗口 (Alt+Tab)" },
      mouseActions: { left: "左键单击", right: "右键单击", middle: "中键单击", double: "左键双击", wheel_up: "滚轮向上", wheel_down: "滚轮向下", move_rel: "相对移动", move_abs: "移动到屏幕坐标" },
    };
    const actions = [
      { id: "act_cs2", name: "CS2 音量", type: "app_volume", icon: "volume", params: { process: "cs2.exe", mode: "toggle" } },
      { id: "act_network", name: "网络切换", type: "network_toggle", icon: "network", params: {} },
      { id: "act_copy", name: "复制", type: "key", icon: "copy", params: { keys: ["Ctrl", "C"], mode: "press" } },
      { id: "act_paste", name: "粘贴", type: "key", icon: "paste", params: { keys: ["Ctrl", "V"], mode: "press" } },
      { id: "act_newtab", name: "新建标签页", type: "key", icon: "plus", params: { keys: ["Ctrl", "T"], mode: "press" } },
      { id: "act_close", name: "关闭标签页", type: "key", icon: "x", params: { keys: ["Ctrl", "W"], mode: "press" } },
      { id: "act_desktop", name: "显示桌面", type: "system", icon: "monitor", params: { action: "show_desktop" } },
      { id: "act_browser", name: "打开浏览器", type: "open", icon: "globe", params: { target: "https://www.bing.com" } },
      { id: "act_play", name: "播放 / 暂停", type: "media", icon: "play", params: { action: "play_pause" } },
      { id: "act_rename", name: "重命名", type: "macro", icon: "macro", params: { steps: [{ type: "key", keys: ["F2"], mode: "press" }, { type: "delay", ms: 120 }], repeat: 1, interval: 0 } },
    ];
    const mkKeys = (ids) => {
      const keys = {};
      ids.forEach((id, i) => { keys[String(i + 1)] = { action: id, double: null }; });
      return keys;
    };
    const profiles = [
      { id: "profile_default", name: "默认配置", color: "#8B5CF6", match: [], layers: [
        { name: "主层", keys: mkKeys(["act_cs2", "act_paste", "act_desktop", "act_browser", "act_play", "act_network"]) },
        { name: "编辑层", keys: mkKeys(["act_copy", "act_paste", "act_rename", "act_close", "act_newtab", "act_desktop"]) },
      ] },
      { id: "profile_browser", name: "浏览器", color: "#38BDF8", match: ["chrome.exe", "msedge.exe"], layers: [
        { name: "主层", keys: mkKeys(["act_newtab", "act_close", "act_paste", "act_copy", "act_play", "act_browser"]) },
      ] },
    ];
    return {
      config: {
        version: 1,
        settings: { theme: "dark", language: "zh", autostart: false, minimizeToTray: true, startMinimized: false, doublePressMs: 320, syncBindingsOnStart: true, deviceInitialized: true, activeProfile: "profile_default", activeLayer: 0, autoProfileSwitch: true, revertToDefault: true },
        triggerMap: { 6: 1, 5: 2, 4: 3, 3: 4, 2: 5, 1: 6 },
        actions,
        profiles,
      },
      device: { connected: true, model: "Single6VerticalAdvanced", modelCode: 153, firmware: "1.002", path: "\\\\?\\HID#VID_5A5A&PID_2023&MI_00", initialized: true, error: "" },
      runtime: { version: "1.0.0", dataDir: "%APPDATA%\\KeypadStudio", calibration: { active: false, index: 0, order: [] }, autostart: false, update: { phase: "idle", current: "1.0.0", canInstall: false } },
      meta,
    };
  }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------

  function boot() {
    // topbar icons
    $$(".top-nav-btn[data-nav]").forEach((btn) => {
      btn.innerHTML = ico(TOP_ICON[btn.dataset.nav] || "bolt", 18);
    });
    $("#back-btn").innerHTML = ico("arrowLeft", 18);
    $("#theme-toggle").innerHTML = ico("sun", 18);
    const loading = $("#loading-icon");
    if (loading) loading.innerHTML = ico("sparkles", 26);
    bindGlobalEvents();
    if (window.pywebview?.api) {
      initApi();
    } else {
      window.addEventListener("pywebviewready", initApi, { once: true });
      setTimeout(() => { if (!S.ready) initDemo(); }, 1600);
    }
  }

  async function initApi() {
    if (S.ready && !S.demo) return;
    try {
      S.api = window.pywebview.api;
      const data = await S.api.get_state();
      applyState(data);
      S.demo = false;
      S.ready = true;
      startPolling();
    } catch (err) {
      console.error(err);
      initDemo();
    }
  }

  function demoGamepad() {
    return {
      connected: true,
      available: true,
      model: "BIGBIG WON Rainbow 2 SE",
      xinput: true,
      slot: 0,
      packet: 20841,
      link: "2.4G 接收器",
      wireless: true,
      receiver: true,
      battery: null,
      battery_type: 1,
      battery_level: 3,
      battery_type_label: "有线供电",
      battery_level_label: "充足",
      battery_label: "接收器供电",
      battery_note: "2.4G 接收器由 USB 供电，XInput 不提供手柄电量百分比",
      charging: true,
      buttons: emptyGamepadButtons(),
      buttons_down: [],
      triggers: { left: 0, right: 0 },
      sticks: { left: { x: 0, y: 0 }, right: { x: 0, y: 0 } },
      product: "XBOX 360 For Windows",
    };
  }

  function demoHub() {
    return {
      keyboard: { connected: true, model: "新盟 M75", link: "2.4G", battery: 82, charging: false },
      mouse: {
        connected: true,
        model: "AUSDOM G04 Ultra",
        link: "2.4G",
        wireless: true,
        battery: 64,
        charging: false,
        report_rate_code: 1,
        rates: [
          { label: "8000", code: 64 }, { label: "4000", code: 32 }, { label: "2000", code: 16 },
          { label: "1000", code: 1 }, { label: "500", code: 2 }, { label: "250", code: 4 },
        ],
        stages: [
          { index: 0, dpi: 800, color: "#38bdf8" },
          { index: 1, dpi: 1600, color: "#a78bfa" },
          { index: 2, dpi: 3200, color: "#fbbf24" },
        ],
        current_stage: 1,
        dpi_min: 50,
        dpi_max: 42000,
        dpi_step: 50,
        config: {
          silent_height: 1,
          key_debounce_time: 0,
          motion_sync_enable: false,
          linear_correction_enable: false,
          ripple_control_option: 0,
          sensor_power_saving_enable: false,
          sleep_time: 90,
        },
        options: {
          lod: [
            { value: 0, label: "0.7 / 1 mm（玻璃）" },
            { value: 1, label: "1 mm" },
            { value: 2, label: "2 mm" },
          ],
          sleep: [
            { value: 1, label: "10 秒" }, { value: 3, label: "30 秒" }, { value: 6, label: "1 分钟" },
            { value: 12, label: "2 分钟" }, { value: 18, label: "3 分钟" }, { value: 30, label: "5 分钟" },
            { value: 60, label: "10 分钟" }, { value: 90, label: "15 分钟" },
          ],
          ripple: [
            { value: 0, label: "自动（默认）" },
            { value: 1, label: "开启" },
            { value: 2, label: "关闭" },
          ],
          debounce_max: 15,
        },
      },
      gamepad: demoGamepad(),
    };
  }

  function initDemo() {
    if (S.ready) return;
    S.demo = true;
    S.hub = demoHub();
    S.api = {
      async get_state() { return demoState(); },
      async save_config(config) { return { ok: true, config }; },
      async set_settings(patch) { S.config.settings = { ...S.config.settings, ...patch }; return { ok: true, config: S.config }; },
      async set_active_profile(id) { S.config.settings.activeProfile = id; S.config.settings.activeLayer = 0; return { ok: true }; },
      async set_active_layer(i) { S.config.settings.activeLayer = i; return { ok: true }; },
      async device_action() { return { ok: true }; },
      async hub_state() { return { ok: true, hub: demoHub() }; },
      async hub_action() { return { ok: true, hub: demoHub() }; },
      async gamepad_state() { return { ok: true, gamepad: demoGamepad() }; },
      async gamepad_action() { return { ok: true, gamepad: demoGamepad() }; },
      async test_action() { return { ok: true }; },
      async poll_events() { return []; },
      async set_autostart(v) { S.config.settings.autostart = v; return { ok: true }; },
      async export_config() { return { ok: false }; },
      async import_config() { return { ok: false }; },
      async open_data_dir() { return { ok: true }; },
      async choose_path() { return { ok: false }; },
      async window_control() { return { ok: true }; },
      async quit_app() { return { ok: true }; },
      async update_state() { return { ok: true, update: S.runtime.update }; },
      async update_check() { return { ok: true }; },
      async update_download() { return { ok: false, error: "演示模式不支持更新" }; },
      async update_apply() { return { ok: false, error: "演示模式不支持更新" }; },
      async open_url() { return { ok: true }; },
    };
    applyState(demoState());
    S.ready = true;
  }

  function applyState(data) {
    S.config = data.config;
    S.device = data.device;
    S.runtime = data.runtime || {};
    S.meta = data.meta;
    if (!S.booted) {
      S.view = "overview";
      S.booted = true;
    }
    document.documentElement.dataset.theme = S.config.settings.theme || "dark";
    updateThemeIcon();
    renderAll();
    if (!S.demo) {
      ensureHubPolling();
      ensureGamepadPolling();
    }
  }

  function startPolling() {
    setInterval(async () => {
      if (S.polling || !S.api) return;
      S.polling = true;
      try {
        const events = await S.api.poll_events();
        for (const event of events || []) handleEvent(event);
      } catch (err) {
        // ignore transient bridge errors
      } finally {
        S.polling = false;
      }
    }, 140);
  }

  function handleEvent(event) {
    if (!event || !event.type) return;
    switch (event.type) {
      case "toast":
        showToast(event.message, event.kind || "info");
        break;
      case "key":
        flashKey(event.slot);
        S.triggerCount += 1;
        S.recent.unshift({ slot: event.slot, name: event.actionName || "动作", ts: event.ts || Date.now() / 1000, double: event.doubleFired, type: event.actionType, icon: event.actionIcon });
        S.recent = S.recent.slice(0, 8);
        if (!S.editing && S.view === "keypad") renderView();
        break;
      case "device":
        S.device = event.device || S.device;
        updateTopbar();
        if (!S.editing && (S.view === "keypad" || S.view === "overview" || S.view === "device")) renderView();
        break;
      case "layer":
        S.config.settings.activeLayer = event.layer;
        if (!S.editing) renderView();
        break;
      case "profile":
        S.config.settings.activeProfile = event.profileId;
        S.config.settings.activeLayer = event.layer || 0;
        if (!S.editing) renderAll();
        break;
      case "calibration":
        S.runtime.calibration = event.calibration;
        if (!S.editing && S.view === "device") renderView();
        break;
      case "config":
        S.config = event.config;
        if (!S.editing) renderAll();
        break;
      case "update":
        if (S.runtime) S.runtime.update = event.update || S.runtime.update;
        if (!S.editing && S.view === "settings") renderView();
        break;
      case "raw_trigger":
        break;
      default:
        break;
    }
  }

  // ------------------------------------------------------------------
  // Global events
  // ------------------------------------------------------------------

  function bindGlobalEvents() {
    document.addEventListener("click", onClick);
    document.addEventListener("input", onInput);
    document.addEventListener("change", onChange);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (S.recording) return;
        if ($("#modal-root").children.length) closeModal();
      }
    });
  }

  async function onClick(e) {
    if (e.target.classList?.contains("modal-overlay") && e.target.dataset.overlay === "true") {
      closeModal();
      return;
    }
    const nav = e.target.closest("[data-nav]");
    if (nav) {
      setView(nav.dataset.nav);
      return;
    }
    const trigger = e.target.closest("[data-action]");
    if (!trigger) return;
    const action = trigger.dataset.action;
    const ds = trigger.dataset;

    switch (action) {
      case "modal-backdrop":
        closeModal();
        break;
      case "go-back":
        setView(S.view === "device" ? "keypad" : "overview");
        break;
      case "toggle-theme":
        toggleTheme();
        break;
      case "set-layer":
        await setLayer(Number(ds.index));
        break;
      case "edit-key":
        openKeyEditor(Number(ds.slot));
        break;
      case "open-profile-menu":
        openProfileMenu();
        break;
      case "set-profile":
        await apiCall("set_active_profile", ds.id);
        S.config.settings.activeProfile = ds.id;
        S.config.settings.activeLayer = 0;
        closeModal();
        renderAll();
        break;
      case "init-device":
        await runDeviceAction("initialize");
        break;
      case "reconnect":
        await runDeviceAction("reconnect");
        break;
      case "calibrate":
        await runDeviceAction("start_calibration");
        break;
      case "cancel-calibration":
        await runDeviceAction("cancel_calibration");
        break;
      case "simulate-key":
        await apiCall("device_action", "simulate", { slot: Number(ds.slot) });
        break;
      case "refresh-log":
        await fetchDeviceLog();
        renderView();
        break;
      case "new-action":
        openActionEditor(null, {});
        break;
      case "edit-action":
        openActionEditor(ds.id, {});
        break;
      case "duplicate-action":
        duplicateAction(ds.id);
        break;
      case "delete-action":
        confirmDeleteAction(ds.id);
        break;
      case "test-action":
        await testActionById(ds.id);
        break;
      case "test-draft":
        if (S.editing?.action) {
          const res = await apiCall("test_action", S.editing.action);
          showToast(res?.ok ? `正在测试：${S.editing.action.name}` : (res?.error || "测试失败"), res?.ok ? "info" : "error");
        }
        break;
      case "close-modal":
        closeModal();
        break;
      case "change-action-type":
        changeActionType(ds.type);
        break;
      case "select-icon":
        S.editing.action.icon = ds.icon;
        renderModal();
        break;
      case "save-action":
        await saveActionEditor();
        break;
      case "add-step":
        addMacroStep(ds.type);
        break;
      case "remove-step":
        removeMacroStep(Number(ds.index));
        break;
      case "move-step":
        moveMacroStep(Number(ds.index), Number(ds.dir));
        break;
      case "record-combo":
        startComboRecorder(ds.target);
        break;
      case "browse":
        await browsePath(ds.kind, ds.target);
        break;
      case "select-action":
        S.editing.selected = ds.id || null;
        renderModal();
        break;
      case "clear-binding":
        S.editing.selected = null;
        S.editing.double = null;
        renderModal();
        break;
      case "save-binding":
        await saveKeyBinding();
        break;
      case "edit-selected-action":
        if (S.editing?.selected) openActionEditor(S.editing.selected, {});
        break;
      case "test-selected-action":
        if (S.editing?.selected) await testActionById(S.editing.selected);
        break;
      case "new-action-for-key":
        openActionEditor(null, { slot: S.editing?.slot });
        break;
      case "new-profile":
        openProfileEditor(null);
        break;
      case "edit-profile":
        openProfileEditor(ds.id);
        break;
      case "duplicate-profile":
        duplicateProfile(ds.id);
        break;
      case "delete-profile":
        confirmDeleteProfile(ds.id);
        break;
      case "save-profile":
        await saveProfileEditor();
        break;
      case "add-layer":
        addProfileLayer();
        break;
      case "remove-layer":
        removeProfileLayer(Number(ds.index));
        break;
      case "export-config":
        await exportConfig();
        break;
      case "import-config":
        await importConfig();
        break;
      case "open-data-dir":
        await apiCall("open_data_dir");
        break;
      case "set-theme":
        await updateSetting("theme", ds.theme);
        break;
      case "confirm-delete":
        await performDelete(trigger.dataset);
        break;
      case "refresh-state":
        await refreshState();
        break;
      case "hub-refresh":
        await loadHub();
        renderView();
        break;
      case "hub-rate":
        await hubAction("report_rate", { code: Number(ds.code) });
        break;
      case "hub-stage":
        await hubAction("stage", { stage: Number(ds.stage) });
        break;
      case "hub-apply-dpi": {
        const input = $(`[data-role="hub-dpi-input"][data-stage="${ds.stage}"]`);
        const value = input ? Number(input.value) : 0;
        if (!value) { showToast("请输入有效的 DPI 数值", "error"); break; }
        await hubAction("dpi", { stage: Number(ds.stage), dpi: value });
        break;
      }
      case "gp-refresh":
        S.gamepad = null;
        await loadGamepad();
        renderView();
        break;
      case "gp-vibrate": {
        const strength = ds.strength === "strong"
          ? { left: 90, right: 90, duration_ms: 600 }
          : { left: 35, right: 30, duration_ms: 220 };
        await gamepadAction("vibrate", strength);
        break;
      }
      case "gp-stop":
        await gamepadAction("stop");
        break;
      case "update-check":
        S.runtime.update = { ...(S.runtime.update || {}), phase: "checking", error: null };
        renderView();
        await apiCall("update_check");
        break;
      case "update-download": {
        const res = await apiCall("update_download");
        if (!res?.ok) showToast(res?.error || "下载失败", "error");
        else showToast("开始下载更新…", "info");
        break;
      }
      case "update-apply": {
        const res = await apiCall("update_apply");
        if (!res?.ok) showToast(res?.error || "无法开始安装", "error");
        else showToast("正在关闭应用并安装更新…", "info");
        break;
      }
      case "open-release":
        await apiCall("open_url", S.runtime?.update?.page || "https://github.com/Delture/keypad-studio/releases");
        break;
      case "open-repo":
        await apiCall("open_url", "https://github.com/Delture/keypad-studio");
        break;
      default:
        break;
    }
  }

  function onInput(e) {
    const el = e.target;
    if (el.matches('[data-role="hub-dpi"]')) {
      const out = $("#hub-dpi-value");
      if (out) out.textContent = `${el.value} DPI`;
      return;
    }
    if (el.matches('[data-role="library-search"]')) {
      S.libraryFilter = el.value;
      renderView();
      const next = $('[data-role="library-search"]');
      if (next) { next.focus(); next.setSelectionRange(next.value.length, next.value.length); }
      return;
    }
    if (el.matches('[data-role="picker-search"]')) {
      S.pickerFilter = el.value;
      filterPicker(el.value);
      return;
    }
    if (el.hasAttribute("data-field")) updateField(el);
    if (el.hasAttribute("data-profile-field")) updateProfileField(el);
  }

  function onChange(e) {
    const el = e.target;
    if (el.matches('[data-role="hub-dpi"]')) {
      hubAction("dpi", { stage: Number(el.dataset.stage), dpi: Number(el.value) });
      return;
    }
    if (el.hasAttribute("data-mouse-setting")) {
      if (S.hubBusy) return;
      const name = el.dataset.mouseSetting;
      const value = el.type === "checkbox" ? el.checked : Number(el.value);
      hubAction("mouse_setting", { name, value });
      return;
    }
    if (el.hasAttribute("data-setting")) {
      updateSetting(el.dataset.setting, el.type === "checkbox" ? el.checked : el.value);
      return;
    }
    if (el.hasAttribute("data-setting-number")) {
      updateSetting(el.dataset.settingNumber, Number(el.value));
      return;
    }
    if (el.hasAttribute("data-profile-select")) {
      S.editing.profile.match = String(el.value || "").split(",").map((x) => x.trim()).filter(Boolean);
      return;
    }
    if (el.matches('[data-role="macro-step-type"]')) {
      changeMacroStepType(Number(el.dataset.index), el.value);
      return;
    }
    if (el.hasAttribute("data-field")) {
      updateField(el);
      if (el.dataset.rerender === "true") renderModal();
    }
    if (el.hasAttribute("data-profile-field")) updateProfileField(el);
  }

  // ------------------------------------------------------------------
  // API wrappers
  // ------------------------------------------------------------------

  async function apiCall(method, ...args) {
    if (!S.api) return { ok: false };
    try {
      return await S.api[method](...args);
    } catch (err) {
      console.error(method, err);
      showToast("操作失败：" + err.message, "error");
      return { ok: false, error: String(err) };
    }
  }

  async function refreshState() {
    if (S.demo) { renderAll(); return; }
    const data = await apiCall("get_state");
    if (data && data.config) {
      applyState(data);
    }
  }

  async function runDeviceAction(action) {
    const res = await apiCall("device_action", action);
    if (res?.device) S.device = res.device;
    if (!res?.ok && res?.error) showToast(res.error, "error");
    if (action === "initialize" && res?.ok) {
      S.config.settings.deviceInitialized = true;
      showToast("6 个按键已初始化", "success");
    }
    if (!S.demo) await refreshState();
    else renderAll();
  }

  async function setLayer(index) {
    S.config.settings.activeLayer = index;
    if (!S.demo) await apiCall("set_active_layer", index);
    renderAll();
  }

  async function updateSetting(key, value) {
    S.config.settings[key] = value;
    if (key === "theme") {
      document.documentElement.dataset.theme = value;
      updateThemeIcon();
    }
    if (S.demo) {
      if (key === "autostart") S.config.settings.autostart = value;
      renderAll();
      return;
    }
    let res;
    if (key === "autostart") res = await apiCall("set_autostart", value);
    else res = await apiCall("set_settings", { [key]: value });
    if (res?.ok && res.config) S.config = res.config;
    showToast(key === "theme" ? "主题已切换" : "设置已保存", "success");
    renderAll();
  }

  async function toggleTheme() {
    const next = (S.config?.settings.theme || "dark") === "dark" ? "light" : "dark";
    await updateSetting("theme", next);
  }

  function updateThemeIcon() {
    const el = $("#theme-toggle");
    if (el) el.innerHTML = ico((S.config?.settings.theme || "dark") === "dark" ? "sun" : "moon", 19);
  }

  async function saveNow() {
    if (S.demo) return { ok: true };
    const res = await apiCall("save_config", S.config);
    if (res?.ok && res.config) S.config = res.config;
    return res;
  }

  // ------------------------------------------------------------------
  // Rendering: shell
  // ------------------------------------------------------------------

  function renderAll() {
    if (!S.config) return;
    updateTopbar();
    updateThemeIcon();
    document.documentElement.dataset.theme = S.config.settings.theme || "dark";
    renderView();
  }

  function updateTopbar() {
    const profile = currentProfile();
    $("#profile-name").textContent = profile?.name || "未选择配置";
    $("#profile-dot").style.background = profile?.color || "#8b5cf6";
    $("#profile-dot").style.color = profile?.color || "#8b5cf6";
    $$(".top-nav-btn[data-nav]").forEach((btn) => btn.classList.toggle("active", btn.dataset.nav === S.view));
    $("#back-btn").classList.toggle("hidden", S.view === "overview");
    $("#crumb-title").textContent = VIEW_TITLE[S.view] || "";
  }

  function setView(view) {
    S.view = view;
    renderView();
    const viewEl = $(".view");
    if (viewEl) viewEl.scrollTop = 0;
    ensureHubPolling();
    ensureGamepadPolling();
  }

  function ensureHubPolling() {
    if (S.hubTimer) { clearInterval(S.hubTimer); S.hubTimer = null; }
    if (S.demo || !HUB_VIEWS.has(S.view)) return;
    loadHub();
    S.hubTimer = setInterval(() => {
      if (HUB_VIEWS.has(S.view) && !S.hubBusy) loadHub(true);
    }, 12000);
  }

  async function loadHub(silent = false) {
    if (S.demo || !S.api) return;
    const res = await apiCall("hub_state");
    if (res?.ok && res.hub) {
      S.hub = res.hub;
      const active = document.activeElement;
      const interacting = !!(active && active.matches && active.matches('[data-role="hub-dpi"], [data-role="hub-dpi-input"], [data-mouse-setting]'));
      if (HUB_VIEWS.has(S.view) && !interacting) renderView();
    } else if (!silent) {
      showToast(res?.error || "读取外设状态失败", "error");
    }
  }

  async function hubAction(action, payload) {
    S.hubBusy = true;
    try {
      const res = await apiCall("hub_action", action, payload);
      if (res?.ok && res.hub) S.hub = res.hub;
      if (!res?.ok) showToast(res?.error || "操作失败", "error");
    } finally {
      S.hubBusy = false;
    }
    if (HUB_VIEWS.has(S.view)) renderView();
  }

  function gamepadMetaKey(gp) {
    if (!gp) return "";
    return [gp.connected, gp.link, gp.battery, gp.battery_label, gp.battery_note, gp.slot, gp.available].join("|");
  }

  function ensureGamepadPolling() {
    if (S.gamepadTimer) { clearInterval(S.gamepadTimer); S.gamepadTimer = null; }
    if (S.demo || !S.api || S.view !== "gamepad") return;
    if (!S.gamepad && S.hub?.gamepad) S.gamepad = S.hub.gamepad;
    loadGamepad();
    S.gamepadTimer = setInterval(() => {
      if (S.view === "gamepad" && !S.gamepadBusy) loadGamepad(true);
    }, 60);
  }

  async function loadGamepad(silent = false) {
    if (S.demo || !S.api) return;
    S.gamepadBusy = true;
    try {
      const res = await apiCall("gamepad_state");
      if (res?.ok && res.gamepad) {
        const previous = S.gamepad;
        S.gamepad = res.gamepad;
        if (S.view === "gamepad") {
          const changed = !previous || gamepadMetaKey(previous) !== gamepadMetaKey(res.gamepad);
          if (changed) renderView();
          else updateGamepadLive();
        }
      } else if (!silent) {
        showToast(res?.error || "读取手柄状态失败", "error");
      }
    } catch (err) {
      if (!silent) showToast("读取手柄状态失败", "error");
    } finally {
      S.gamepadBusy = false;
    }
  }

  async function gamepadAction(action, payload) {
    S.gamepadBusy = true;
    try {
      const res = await apiCall("gamepad_action", action, payload);
      if (res?.ok && res.gamepad) {
        S.gamepad = res.gamepad;
        S.gamepadMetaKey = gamepadMetaKey(res.gamepad);
      }
      if (!res?.ok) showToast(res?.error || "手柄操作失败", "error");
    } catch (err) {
      showToast("手柄操作失败", "error");
    } finally {
      S.gamepadBusy = false;
    }
    if (S.view === "gamepad") updateGamepadLive();
  }

  function updateStickDot(selector, stick) {
    const dot = $(selector);
    if (!dot) return;
    const x = Number(stick?.x || 0);
    const y = Number(stick?.y || 0);
    const max = 43;
    dot.style.transform = `translate(${(x / 32767) * max}px, ${(-y / 32767) * max}px)`;
    dot.classList.toggle("active", Math.abs(x) > 3500 || Math.abs(y) > 3500);
  }

  function updateGamepadLive() {
    const gp = S.gamepad;
    if (!gp) return;
    const chip = $("#gp-status");
    if (chip) {
      chip.textContent = gp.connected ? "已连接" : "未连接";
      chip.classList.toggle("accent", !!gp.connected);
    }
    const buttons = gp.buttons || {};
    $$("[data-gp-btn]").forEach((el) => {
      el.classList.toggle("active", !!buttons[el.dataset.gpBtn]);
    });
    const triggers = gp.triggers || {};
    const lt = Number(triggers.left || 0);
    const rt = Number(triggers.right || 0);
    const ltBar = $("#gp-lt-bar");
    const rtBar = $("#gp-rt-bar");
    const ltVal = $("#gp-lt-val");
    const rtVal = $("#gp-rt-val");
    if (ltBar) ltBar.style.width = `${Math.max(2, Math.round((lt / 255) * 100))}%`;
    if (rtBar) rtBar.style.width = `${Math.max(2, Math.round((rt / 255) * 100))}%`;
    if (ltVal) ltVal.textContent = String(lt);
    if (rtVal) rtVal.textContent = String(rt);
    updateStickDot("#gp-dot-l", gp.sticks?.left);
    updateStickDot("#gp-dot-r", gp.sticks?.right);
    const leftVal = $("#gp-stick-l-val");
    const rightVal = $("#gp-stick-r-val");
    if (leftVal) leftVal.textContent = `${gp.sticks?.left?.x ?? 0}, ${gp.sticks?.left?.y ?? 0}`;
    if (rightVal) rightVal.textContent = `${gp.sticks?.right?.x ?? 0}, ${gp.sticks?.right?.y ?? 0}`;
    const packet = $("#gp-packet");
    if (packet) packet.textContent = gp.connected ? String(gp.packet ?? "—") : "—";
    const active = $("#gp-active");
    if (active) {
      const labels = (gp.buttons_down || []).map((name) => GAMEPAD_BUTTON_LABELS[name] || name);
      active.textContent = labels.length ? labels.join(" · ") : "无按键按下";
    }
  }

  function renderView() {
    if (!S.config) return;
    const host = $("#view-inner");
    const scroll = $(".view")?.scrollTop || 0;
    let html = "";
    if (S.view === "overview") html = renderOverview();
    else if (S.view === "keypad") html = renderKeypad();
    else if (S.view === "keyboard") html = renderKeyboard();
    else if (S.view === "mouse") html = renderMouse();
    else if (S.view === "gamepad") html = renderGamepad();
    else if (S.view === "actions") html = renderActions();
    else if (S.view === "profiles") html = renderProfiles();
    else if (S.view === "device") html = renderDevice();
    else if (S.view === "settings") html = renderSettings();
    host.innerHTML = html;
    updateTopbar();
    const view = $(".view");
    if (view) view.scrollTop = scroll;
    if (S.view === "device" && !S.demo) fetchDeviceLog().then(() => {
      const box = $("#device-log");
      if (box) box.innerHTML = renderLogLines();
    });
  }

  // ------------------------------------------------------------------
  // Rendering: overview
  // ------------------------------------------------------------------

  function renderOverview() {
    const profile = currentProfile();
    const layers = currentLayers();
    const layerIndex = currentLayerIndex();
    const bound = Object.values(currentLayer()?.keys || {}).filter((b) => b?.action).length;
    const connected = !!S.device?.connected;
    const kb = S.hub?.keyboard || {};
    const ms = S.hub?.mouse || {};
    const gp = S.hub?.gamepad || S.gamepad || {};
    const kbOnline = !!kb.connected;
    const kbOk = kbOnline && kb.battery != null;
    const msOnline = !!ms.connected;
    const msOk = msOnline && ms.battery != null;
    const gpOnline = !!gp.connected;
    const rate = (ms.rates || []).find((r) => r.code === ms.report_rate_code);
    const stage = (ms.stages || []).find((s) => s.index === ms.current_stage) || (ms.stages || [])[0];
    const reading = !S.hub;
    const online = [connected, kbOnline, msOnline, gpOnline].filter(Boolean).length;
    const gpBattery = gp.battery != null ? `${gp.battery}<small>%</small>` : gpOnline ? "在线" : "—";
    const gpNote = gp.battery != null
      ? (gp.charging ? "正在充电" : "XInput 电量")
      : (gp.battery_label || "XInput 状态");
    const gpInput = gpOnline ? `XInput · slot ${gp.slot ?? "—"}` : "等待连接";

    const keypadCard = `<button class="overview-card" data-nav="keypad" style="--card-accent:#8b5cf6;--card-index:0">
      <div class="overview-top">
        <div class="overview-orb">${ico("usb", 26)}</div>
        <span class="chip ${connected ? "accent" : ""}">${connected ? "已连接" : "未连接"}</span>
      </div>
      <div class="overview-name">6 键小键盘</div>
      <div class="overview-model">${esc(S.device?.model || "Single6VerticalAdvanced")}</div>
      <div class="overview-value">${connected ? "在线" : "离线"} <small>${connected ? `固件 ${esc(S.device?.firmware || "—")}` : "请检查数据线"}</small></div>
      <div class="overview-rows">
        <div class="overview-row"><span>当前配置</span><strong>${esc(profile?.name || "—")} · ${esc(layers[layerIndex]?.name || "—")}</strong></div>
        <div class="overview-row"><span>按键绑定</span><strong>${bound} / 6</strong></div>
        <div class="overview-row"><span>本次触发</span><strong>${S.triggerCount} 次</strong></div>
      </div>
      <div class="overview-foot"><span>按键与图层设置</span>${ico("arrowRight", 15)}</div>
    </button>`;

    const keyboardCard = `<button class="overview-card" data-nav="keyboard" style="--card-accent:#38bdf8;--card-index:1">
      <div class="overview-top">
        <div class="overview-orb">${ico("keyboard", 26)}</div>
        <span class="chip ${kbOk ? "accent" : ""}">${reading ? "读取中" : kbOk ? "已连接" : kbOnline ? "读取失败" : "离线"}</span>
      </div>
      <div class="overview-name">${esc(kb.model || "新盟 M75")}</div>
      <div class="overview-model">2.4G 无线键盘</div>
      <div class="overview-value">${kbOk ? `${kb.battery}<small>%</small>` : "—"} <small>${kb.charging ? "正在充电" : "剩余电量"}</small></div>
      ${kbOk ? `<div class="overview-meter"><i style="width:${Math.max(2, Math.min(100, Number(kb.battery)))}%;background:${batteryTone(Number(kb.battery))}"></i></div>` : `<div class="overview-idle">${reading ? "正在读取电量…" : "未读取到电量"}</div>`}
      <div class="overview-rows">
        <div class="overview-row"><span>连接方式</span><strong>2.4G 接收器</strong></div>
        <div class="overview-row"><span>状态</span><strong>${reading ? "正在读取…" : kbOk ? esc(kb.link || "2.4G") + " 已连接" : kbOnline ? "接收器在线" : "未找到接收器"}</strong></div>
      </div>
      <div class="overview-foot"><span>查看电量</span>${ico("arrowRight", 15)}</div>
    </button>`;

    const mouseCard = `<button class="overview-card" data-nav="mouse" style="--card-accent:#a78bfa;--card-index:2">
      <div class="overview-top">
        <div class="overview-orb">${ico("mouse", 26)}</div>
        <span class="chip ${msOk ? "accent" : ""}">${reading ? "读取中" : msOk ? "已连接" : msOnline ? "读取失败" : "离线"}</span>
      </div>
      <div class="overview-name">${esc(ms.model || "AUSDOM G04 Ultra")}</div>
      <div class="overview-model">${ms.wireless === false ? "有线鼠标" : "2.4G 无线鼠标"}</div>
      <div class="overview-value">${msOk ? `${ms.battery}<small>%</small>` : "—"} <small>${ms.charging ? "正在充电" : "剩余电量"}</small></div>
      ${msOk ? `<div class="overview-meter"><i style="width:${Math.max(2, Math.min(100, Number(ms.battery)))}%;background:${batteryTone(Number(ms.battery))}"></i></div>` : `<div class="overview-idle">${reading ? "正在读取配置…" : "未读取到鼠标"}</div>`}
      <div class="overview-rows">
        <div class="overview-row"><span>回报率</span><strong>${msOk && rate ? `${esc(rate.label)} Hz` : "—"}</strong></div>
        <div class="overview-row"><span>当前 DPI</span><strong>${msOk && stage ? `${stage.dpi} · 第 ${Number(ms.current_stage) + 1} 档` : "—"}</strong></div>
      </div>
      <div class="overview-foot"><span>DPI 与回报率</span>${ico("arrowRight", 15)}</div>
    </button>`;

    const gamepadCard = `<button class="overview-card" data-nav="gamepad" style="--card-accent:#fb923c;--card-index:3">
      <div class="overview-top">
        <div class="overview-orb">${ico("gamepad", 26)}</div>
        <span class="chip ${gpOnline ? "accent" : ""}">${reading ? "读取中" : gpOnline ? "已连接" : "离线"}</span>
      </div>
      <div class="overview-name">BIGBIG WON Rainbow 2 SE</div>
      <div class="overview-model">XInput 无线手柄</div>
      <div class="overview-value">${gpBattery} <small>${gpNote}</small></div>
      ${gp.battery != null ? `<div class="overview-meter"><i style="width:${Math.max(2, Math.min(100, Number(gp.battery)))}%;background:${batteryTone(Number(gp.battery))}"></i></div>` : `<div class="overview-idle">${reading ? "正在查询手柄…" : gpOnline ? "实时输入与震动可用" : "打开手柄电源后重试"}</div>`}
      <div class="overview-rows">
        <div class="overview-row"><span>连接方式</span><strong>${esc(gp.link || "—")}</strong></div>
        <div class="overview-row"><span>电量状态</span><strong>${esc(gp.battery_label || gp.battery_note || "—")}</strong></div>
        <div class="overview-row"><span>输入通道</span><strong>${esc(gpInput)}</strong></div>
      </div>
      <div class="overview-foot"><span>实时测试与震动</span>${ico("arrowRight", 15)}</div>
    </button>`;

    return `
      <div class="overview-head">
        <div>
          <div class="eyebrow">设备中枢 · KEYPAD STUDIO</div>
          <h1>所有外设，一屏掌握</h1>
          <p>点击设备卡片进入控制页面${S.hub ? ` · <strong>${online} / 4</strong> 台设备在线` : " · 正在读取外设…"}</p>
        </div>
        <button class="btn" data-action="hub-refresh">${ico("refresh", 15)} 重新扫描</button>
      </div>
      <div class="overview-summary">
        <div class="summary-cell"><div class="summary-icon">${ico("devices", 18)}</div><div><strong>${online}<span> / 4</span></strong><small>在线设备</small></div></div>
        <div class="summary-cell"><div class="summary-icon">${ico("layers", 18)}</div><div><strong>${esc(profile?.name || "—")}</strong><small>当前配置 · ${esc(layers[layerIndex]?.name || "—")}</small></div></div>
        <div class="summary-cell"><div class="summary-icon">${ico("bolt", 18)}</div><div><strong>${S.triggerCount}<span> 次</span></strong><small>本次运行触发</small></div></div>
        <div class="summary-cell"><div class="summary-icon">${ico("activity", 18)}</div><div><strong>${gpOnline ? "手柄在线" : "等待手柄"}</strong><small>${gpOnline ? "实时输入已就绪" : "XInput 未检测到设备"}</small></div></div>
      </div>
      <div class="overview-grid">${keypadCard}${keyboardCard}${mouseCard}${gamepadCard}</div>
    `;
  }

  // ------------------------------------------------------------------
  // Rendering: keypad
  // ------------------------------------------------------------------

  function renderKeypad() {
    const profile = currentProfile();
    const layers = currentLayers();
    const layerIndex = currentLayerIndex();
    const settings = S.config.settings;
    const connected = !!S.device?.connected;
    let banner = "";
    if (!connected) {
      banner = `<div class="banner">
        <div class="banner-icon">${ico("plug", 22)}</div>
        <div class="banner-body"><strong>还没有连接小键盘</strong><p>请用数据线把 6 键小键盘接到电脑，然后重新连接。大键盘的 2.4GHz 连接不会被影响。</p></div>
        <button class="btn primary" data-action="reconnect">${ico("refresh", 16)} 重新连接</button>
      </div>`;
    } else if (!settings.deviceInitialized) {
      banner = `<div class="banner">
        <div class="banner-icon">${ico("sparkles", 22)}</div>
        <div class="banner-body"><strong>最后一步：初始化 6 个按键</strong><p>把 6 个按键切换为软件触发模式。之后所有自定义动作都由 Keypad Studio 执行，功能不再受键盘固件限制。</p></div>
        <button class="btn primary" data-action="init-device">${ico("bolt", 16)} 初始化按键</button>
      </div>`;
    }

    const slots = [1, 2, 3, 4, 5, 6];
    const keyCards = slots.map((slot) => {
      const binding = bindingFor(slot);
      const action = actionById(binding.action);
      const doubleAction = actionById(binding.double);
      const color = action ? typeColor(action.type) : "#64748b";
      return `<button class="key-card ${action ? "" : "key-empty"}" data-action="edit-key" data-slot="${slot}" style="--key-color:${color}">
        <div class="key-top"><span class="key-slot">键 ${String(slot).padStart(2, "0")}</span><span class="key-dot"></span></div>
        <div class="key-icon">${ico(action ? actionIcon(action) : "plus", 23)}</div>
        <div class="key-name">${esc(action ? action.name : "未绑定动作")}</div>
        <div class="key-type">${action ? esc(typeInfo(action.type).name) : "点击设置"}</div>
        <div class="key-hint">${esc(action ? actionPreview(action) : "—")}${doubleAction ? " · 双击" : ""}</div>
      </button>`;
    }).join("");

    const recent = S.recent.length
      ? S.recent.slice(0, 5).map((item) => {
          const action = actionById(bindingFor(item.slot).action);
          const itemType = item.type || action?.type;
          const itemIcon = item.icon || actionIcon(action);
          return `<div class="recent-row">
            <div class="recent-icon" style="color:${typeColor(itemType)}">${ico(itemIcon, 17)}</div>
            <div class="recent-main"><div class="recent-name">${esc(item.name)}</div><div class="recent-meta">按键 ${item.slot}${item.double ? " · 双击" : ""}</div></div>
            <div class="recent-time">${shortTime(item.ts)}</div>
          </div>`;
        }).join("")
      : `<div class="empty" style="padding:28px 10px"><div class="empty-icon" style="width:48px;height:48px">${ico("bolt", 20)}</div><h3>还没有触发记录</h3><p>按下小键盘上的任意按键，动作会显示在这里。</p></div>`;

    const bindCount = Object.values(currentLayer()?.keys || {}).filter((b) => b?.action).length;
    const appMatches = (profile?.match || []).length
      ? profile.match.map((m) => `<span class="chip">${ico("window", 12)} ${esc(m)}</span>`).join("")
      : `<span class="chip">${ico("grid", 12)} 所有程序</span>`;

    return `
      ${banner}
      <div class="layout-bar">
        <div class="tabs">
          ${layers.map((layer, i) => `<button class="tab ${i === layerIndex ? "active" : ""}" data-action="set-layer" data-index="${i}">${esc(layer.name)}</button>`).join("")}
        </div>
        <div class="chips">
          <span class="chip">${ico("layers", 12)} ${layers.length} 个图层</span>
          <span class="chip">${ico("keyboard", 12)} ${bindCount} / 6 已绑定</span>
        </div>
      </div>

      <div class="key-grid">${keyCards}</div>

      <div class="stats-grid">
        <div class="stat"><div class="stat-label">${ico("grid", 14)} 当前配置</div><div class="stat-value">${esc(profile?.name || "—")}</div></div>
        <div class="stat"><div class="stat-label">${ico("layers", 14)} 当前图层</div><div class="stat-value">${esc(layers[layerIndex]?.name || "—")} <small>${layerIndex + 1} / ${layers.length}</small></div></div>
        <div class="stat"><div class="stat-label">${ico("usb", 14)} 设备状态</div><div class="stat-value" style="font-size:15px">${connected ? `<span style="color:var(--success)">在线</span> <small>${esc(S.device.model || "")}</small>` : `<span style="color:var(--danger)">离线</span>`}</div></div>
        <div class="stat"><div class="stat-label">${ico("bolt", 14)} 本次触发</div><div class="stat-value">${S.triggerCount} <small>次</small></div></div>
      </div>

      <div class="split">
        <div class="panel">
          <div class="panel-head"><div><div class="panel-title">最近动作</div><div class="panel-sub">本次运行中按下的按键</div></div><button class="btn small ghost" data-action="refresh-state">${ico("refresh", 14)} 刷新</button></div>
          <div class="recent-list">${recent}</div>
        </div>
        <div class="panel">
          <div class="panel-head"><div><div class="panel-title">当前配置</div><div class="panel-sub">${esc(profile?.name || "")}</div></div><button class="btn small" data-nav="profiles">${ico("settings", 14)} 管理</button></div>
          <div class="setting-row"><div class="setting-main"><div class="setting-name">自动切换程序</div><div class="setting-desc">前台程序匹配时自动切换配置</div></div><span class="chip ${settings.autoProfileSwitch ? "accent" : ""}">${settings.autoProfileSwitch ? "已开启" : "已关闭"}</span></div>
          <div class="setting-row"><div class="setting-main"><div class="setting-name">双击动作</div><div class="setting-desc">双击检测窗口 ${settings.doublePressMs || 320} ms</div></div><span class="chip">${ico("clock", 12)} ${settings.doublePressMs || 320} ms</span></div>
          <div class="setting-row"><div class="setting-main"><div class="setting-name">匹配程序</div><div class="setting-desc">当前配置关联的程序</div></div><div class="chips">${appMatches}</div></div>
          <div class="divider"></div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn small" data-nav="actions">${ico("grid", 14)} 动作库</button>
            <button class="btn small" data-nav="device">${ico("usb", 14)} 设备诊断</button>
            <button class="btn small" data-nav="settings">${ico("settings", 14)} 设置</button>
          </div>
        </div>
      </div>
    `;
  }

  // ------------------------------------------------------------------
  // Rendering: actions
  // ------------------------------------------------------------------

  function renderActions() {
    const q = S.libraryFilter.trim().toLowerCase();
    const actions = (S.config.actions || []).filter((a) => {
      if (!q) return true;
      return (a.name || "").toLowerCase().includes(q) || (typeInfo(a.type).name || "").toLowerCase().includes(q) || (a.type || "").includes(q);
    });
    const cards = actions.map((action) => {
      const t = typeInfo(action.type);
      const color = typeColor(action.type);
      const used = usageCount(action.id);
      return `<div class="action-card">
        <div class="action-head">
          <div class="action-icon" style="--action-color:${color}">${ico(actionIcon(action), 21)}</div>
          <div class="action-main"><div class="action-name">${esc(action.name)}</div><div class="action-type">${esc(t.name)}</div></div>
        </div>
        <div class="action-preview">${esc(actionPreview(action))}</div>
        <div class="action-foot">
          <button class="btn small ghost icon-only" title="编辑" data-action="edit-action" data-id="${action.id}">${ico("edit", 14)}</button>
          <button class="btn small ghost icon-only" title="测试" data-action="test-action" data-id="${action.id}">${ico("play", 14)}</button>
          <button class="btn small ghost icon-only" title="复制" data-action="duplicate-action" data-id="${action.id}">${ico("duplicate", 14)}</button>
          <button class="btn small ghost icon-only danger" title="删除" data-action="delete-action" data-id="${action.id}">${ico("trash", 14)}</button>
          <span class="action-use">${used ? `被 ${used} 个按键使用` : "未使用"}</span>
        </div>
      </div>`;
    }).join("");

    return `
      <div class="toolbar">
        <div class="search">${ico("search", 16)}<input class="input" data-role="library-search" value="${esc(S.libraryFilter)}" placeholder="搜索动作名称或类型…"></div>
        <span class="chip">${actions.length} 个动作</span>
        <div class="spacer"></div>
        <button class="btn primary" data-action="new-action">${ico("plus", 16)} 新建动作</button>
      </div>
      ${actions.length ? `<div class="library-grid">${cards}</div>` : `<div class="empty"><div class="empty-icon">${ico("search", 24)}</div><h3>没有匹配的动作</h3><p>换个关键词，或者新建一个动作。</p><button class="btn primary" data-action="new-action">${ico("plus", 16)} 新建动作</button></div>`}
    `;
  }

  // ------------------------------------------------------------------
  // Rendering: profiles
  // ------------------------------------------------------------------

  function renderProfiles() {
    const profiles = S.config.profiles || [];
    const cards = profiles.map((profile) => {
      const active = profile.id === S.config.settings.activeProfile;
      const keys = profile.layers?.[0]?.keys || {};
      const bound = Object.values(keys).filter((b) => b?.action).length;
      const apps = (profile.match || []).length
        ? profile.match.map((m) => `<span class="chip">${ico("window", 11)} ${esc(m)}</span>`).join("")
        : `<span class="chip">${ico("grid", 11)} 所有程序</span>`;
      return `<div class="profile-card ${active ? "active" : ""}">
        <div class="profile-top">
          <div class="profile-swatch" style="background:${profile.color || "#8B5CF6"}">${esc((profile.name || "?").slice(0, 1))}</div>
          <div style="min-width:0"><div class="profile-name">${esc(profile.name)} ${active ? `<span class="chip accent" style="margin-left:6px">当前</span>` : ""}</div><div class="profile-meta">${profile.layers?.length || 1} 个图层 · 主层已绑定 ${bound} / 6</div></div>
        </div>
        <div class="profile-apps"><div class="chips">${apps}</div></div>
        <div class="profile-foot">
          ${active ? "" : `<button class="btn small" data-action="set-profile" data-id="${profile.id}">${ico("check", 13)} 设为当前</button>`}
          <button class="btn small ghost" data-action="edit-profile" data-id="${profile.id}">${ico("edit", 13)} 编辑</button>
          <button class="btn small ghost icon-only" title="复制" data-action="duplicate-profile" data-id="${profile.id}">${ico("duplicate", 13)}</button>
          <button class="btn small ghost icon-only danger" title="删除" data-action="delete-profile" data-id="${profile.id}">${ico("trash", 13)}</button>
        </div>
      </div>`;
    }).join("");

    return `
      <div class="toolbar">
        <span class="chip">${profiles.length} 个配置</span>
        <div class="spacer"></div>
        <button class="btn primary" data-action="new-profile">${ico("plus", 16)} 新建配置</button>
      </div>
      <div class="profile-grid">${cards}</div>
      <div class="panel" style="margin-top:18px">
        <div class="panel-head"><div><div class="panel-title">配置切换</div><div class="panel-sub">在前台程序匹配时自动切换</div></div><span class="chip ${S.config.settings.autoProfileSwitch ? "accent" : ""}">${S.config.settings.autoProfileSwitch ? "自动切换已开启" : "自动切换已关闭"}</span></div>
        <div class="setting-row"><div class="setting-main"><div class="setting-name">未匹配时恢复默认</div><div class="setting-desc">离开已匹配的程序后回到第一个配置</div></div><label class="switch"><input type="checkbox" data-setting="revertToDefault" ${S.config.settings.revertToDefault ? "checked" : ""}><span></span></label></div>
        <div class="setting-row"><div class="setting-main"><div class="setting-name">自动切换</div><div class="setting-desc">根据前台程序名（如 chrome.exe）切换配置</div></div><label class="switch"><input type="checkbox" data-setting="autoProfileSwitch" ${S.config.settings.autoProfileSwitch ? "checked" : ""}><span></span></label></div>
      </div>
    `;
  }

  // ------------------------------------------------------------------
  // Rendering: device
  // ------------------------------------------------------------------

  function renderDevice() {
    const d = S.device || {};
    const cal = S.runtime?.calibration || { active: false, index: 0 };
    const calPanel = cal.active ? `<div class="panel" style="margin-top:16px">
      <div class="panel-head"><div><div class="panel-title">校准按键顺序</div><div class="panel-sub">请从左到右依次按下 6 个按键</div></div><button class="btn small" data-action="cancel-calibration">取消</button></div>
      <div class="calibrate-steps">${[0,1,2,3,4,5].map((i) => `<div class="cal-step ${i < cal.index ? "done" : i === cal.index ? "current" : ""}"></div>`).join("")}</div>
      <div style="font-size:12px;color:var(--text-secondary);margin-top:8px">${cal.index < 6 ? `请按第 <strong style="color:var(--text-primary)">${cal.index + 1}</strong> 个键（从左往右）` : "校准完成"}</div>
    </div>` : "";

    return `
      <div class="toolbar">
        <span class="chip ${d.connected ? "accent" : ""}">${d.connected ? "已连接" : "未连接"}</span>
        <div class="spacer"></div>
        <button class="btn" data-action="refresh-state">${ico("refresh", 15)} 刷新状态</button>
      </div>
      <div class="panel">
        <div class="device-hero">
          <div class="device-orb">${ico("usb", 24)}</div>
          <div style="min-width:0;flex:1"><div class="device-title">${esc(d.model || "6 键小键盘")}</div><div class="device-sub">${d.connected ? `<span style="color:var(--success)">已连接</span> · 固件 v${esc(d.firmware || "?")}` : `<span style="color:var(--danger)">未连接</span> · 请检查数据线`}</div></div>
        </div>
        <div class="device-meta">
          <div class="meta-cell"><div class="meta-label">型号代码</div><div class="meta-value">0x${(d.modelCode || 0).toString(16).toUpperCase().padStart(2, "0")}</div></div>
          <div class="meta-cell"><div class="meta-label">固件版本</div><div class="meta-value">${esc(d.firmware || "—")}</div></div>
          <div class="meta-cell"><div class="meta-label">软件触发</div><div class="meta-value">${S.config.settings.deviceInitialized ? "已初始化" : "未初始化"}</div></div>
        </div>
        <div class="divider"></div>
        <div class="action-row">
          <button class="btn" data-action="reconnect">${ico("plug", 15)} 重新连接</button>
          <button class="btn primary" data-action="init-device">${ico("bolt", 15)} 初始化 6 个按键</button>
          <button class="btn" data-action="calibrate">${ico("crosshair", 15)} 校准按键顺序</button>
          <button class="btn" data-action="refresh-log">${ico("list", 15)} 刷新日志</button>
        </div>
        <div class="help" style="margin-top:12px;font-size:12px;color:var(--text-secondary);line-height:1.6">
          初始化会把 6 个按键的固件绑定写成软件触发器。键盘只负责把“按了第几个键”告诉电脑，具体动作由本应用执行；因此可以在不刷固件的情况下随时修改功能。
        </div>
      </div>
      ${calPanel}
      <div class="panel" style="margin-top:16px">
        <div class="panel-head"><div><div class="panel-title">按键测试</div><div class="panel-sub">确认每个物理按键都能被识别</div></div></div>
        <div class="action-row">${[1,2,3,4,5,6].map((slot) => `<button class="btn small" data-action="simulate-key" data-slot="${slot}">${ico("bolt", 13)} 模拟键 ${slot}</button>`).join("")}</div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="panel-head"><div><div class="panel-title">原始 HID 日志</div><div class="panel-sub">最近 60 条收发记录（用于排查）</div></div></div>
        <div class="log-box" id="device-log">${renderLogLines()}</div>
      </div>
    `;
  }

  function batteryTone(level) {
    if (level <= 15) return "var(--danger)";
    if (level <= 35) return "var(--warning)";
    return "var(--success)";
  }

  function renderBattery(device, label) {
    const level = Number(device.battery ?? 0);
    const tone = batteryTone(level);
    const note = device.charging ? "正在充电" : label || "剩余电量";
    return `<div class="hub-battery">
        <strong style="color:${tone}">${level}<span>%</span></strong>
        <span class="hub-battery-note">${device.charging ? ico("charging", 13) : ico("battery", 13)} ${note}</span>
      </div>
      <div class="hub-bar"><i style="width:${Math.max(2, Math.min(100, level))}%;background:${tone}"></i></div>`;
  }

  function hubReading(title, text) {
    return `<div class="empty"><div class="empty-icon">${ico("refresh", 20)}</div><h3>${esc(title)}</h3><p>${esc(text)}</p></div>`;
  }

  function renderKeyboard() {
    if (!S.hub) return hubReading("正在读取键盘", "正在查询新盟 M75 的 2.4G 接收器…");
    const kb = S.hub.keyboard || {};
    const kbOk = kb.connected && kb.battery != null;
    const kbOnline = !!kb.connected;
    return `
      <div class="toolbar">
        <span class="chip ${kbOk ? "accent" : ""}">${kbOk ? "已连接" : kbOnline ? "读取失败" : "未连接"}</span>
        <div class="spacer"></div>
        <button class="btn" data-action="hub-refresh">${ico("refresh", 15)} 重新读取</button>
      </div>
      <div class="panel device-page">
        <div class="hub-head">
          <div class="hub-orb">${ico("keyboard", 24)}</div>
          <div class="hub-main">
            <div class="hub-name">${esc(kb.model || "新盟 M75")}</div>
            <div class="hub-sub">${kbOk ? esc(kb.link || "2.4G") + " 已连接" : kbOnline ? "接收器在线 · 读取失败" : "未找到 2.4G 接收器"}</div>
          </div>
        </div>
        ${kbOk ? `<div class="page-battery">${renderBattery(kb, "剩余电量")}</div>` : `<div class="hub-note">${esc(kb.error || "请确认键盘的 2.4G 接收器已插入电脑，并打开键盘电源。")}</div>`}
        <div class="divider"></div>
        <div class="device-meta">
          <div class="meta-cell"><div class="meta-label">连接方式</div><div class="meta-value">2.4G 接收器</div></div>
          <div class="meta-cell"><div class="meta-label">读取内容</div><div class="meta-value">电量</div></div>
          <div class="meta-cell"><div class="meta-label">按键设置</div><div class="meta-value">不修改</div></div>
        </div>
        <div class="hub-note">键盘只读取电量，不会修改任何按键设置。读取失败时请先按一下键盘再重试。</div>
      </div>`;
  }

  function renderMouse() {
    if (!S.hub) return hubReading("正在读取鼠标", "正在查询 AUSDOM G04 Ultra 的 2.4G 接收器…");
    const ms = S.hub.mouse || {};
    const msOk = ms.connected && ms.battery != null;
    const msOnline = !!ms.connected;
    const rateButtons = (ms.rates || []).map((rate) => `<button class="hub-chip ${ms.report_rate_code === rate.code ? "active" : ""}" data-action="hub-rate" data-code="${rate.code}">${esc(rate.label)} Hz</button>`).join("");
    const stageButtons = (ms.stages || []).map((stage) => `<button class="hub-chip ${ms.current_stage === stage.index ? "active" : ""}" data-action="hub-stage" data-stage="${stage.index}">
        <i class="hub-dot" style="background:${esc(stage.color)}"></i>${stage.dpi}
      </button>`).join("");
    const activeStage = (ms.stages || []).find((s) => s.index === ms.current_stage) || (ms.stages || [])[0];
    const dpiValue = activeStage ? activeStage.dpi : ms.dpi_min || 50;
    const cfg = ms.config || {};
    const opts = ms.options || {};
    const choose = (items, current) => (items || []).map((item) => `<option value="${item.value}" ${Number(current) === Number(item.value) ? "selected" : ""}>${esc(item.label)}</option>`).join("");
    const debounceOptions = Array.from({ length: (opts.debounce_max || 15) + 1 }, (_, msDelay) => `<option value="${msDelay}" ${Number(cfg.key_debounce_time) === msDelay ? "selected" : ""}>${msDelay} ms</option>`).join("");
    const sensorPanel = msOk && ms.config ? `
      <div class="page-section mouse-settings">
        <div class="hub-section-title">传感器与按键</div>
        <div class="setting-row">
          <div class="setting-main"><div class="setting-name">静默高度 LOD</div><div class="setting-desc">抬起鼠标时的有效高度，越低越早停止追踪。</div></div>
          <select class="select" data-mouse-setting="silent_height">${choose(opts.lod, cfg.silent_height)}</select>
        </div>
        <div class="setting-row">
          <div class="setting-main"><div class="setting-name">轨迹同步</div><div class="setting-desc">让传感器采样与移动轨迹对齐，提升移动准确性。</div></div>
          <label class="switch"><input type="checkbox" data-mouse-setting="motion_sync_enable" ${cfg.motion_sync_enable ? "checked" : ""}><span></span></label>
        </div>
        <div class="setting-row">
          <div class="setting-main"><div class="setting-name">直线修正</div><div class="setting-desc">修正直线移动时的横向抖动，适合办公与绘图。</div></div>
          <label class="switch"><input type="checkbox" data-mouse-setting="linear_correction_enable" ${cfg.linear_correction_enable ? "checked" : ""}><span></span></label>
        </div>
        <div class="setting-row">
          <div class="setting-main"><div class="setting-name">波纹控制</div><div class="setting-desc">高速移动时的算法修正，消除波浪状抖动。</div></div>
          <select class="select" data-mouse-setting="ripple_control_option">${choose(opts.ripple, cfg.ripple_control_option)}</select>
        </div>
        <div class="setting-row">
          <div class="setting-main"><div class="setting-name">传感器省电</div><div class="setting-desc">开启后降低传感器功耗；关闭可保持更高性能。</div></div>
          <label class="switch"><input type="checkbox" data-mouse-setting="sensor_power_saving_enable" ${cfg.sensor_power_saving_enable ? "checked" : ""}><span></span></label>
        </div>
        <div class="setting-row">
          <div class="setting-main"><div class="setting-name">休眠时间</div><div class="setting-desc">鼠标静止一段时间后进入休眠，降低耗电。</div></div>
          <select class="select" data-mouse-setting="sleep_time">${choose(opts.sleep, cfg.sleep_time)}</select>
        </div>
        <div class="setting-row">
          <div class="setting-main"><div class="setting-name">按键去抖</div><div class="setting-desc">提高防抖延迟可增强按键稳定性，0 - ${opts.debounce_max || 15} ms。</div></div>
          <select class="select" data-mouse-setting="key_debounce_time">${debounceOptions}</select>
        </div>
      </div>` : "";
    const dpiPanel = msOk && activeStage ? `
      <div class="page-section">
        <div class="hub-section-title">DPI 档位 · 点击切换当前档位</div>
        <div class="hub-chips">${stageButtons}</div>
      </div>
      <div class="page-section">
        <div class="hub-section-title">当前档位 DPI · 松开滑块后写入鼠标</div>
        <div class="hub-dpi-row"><span class="hub-dpi-value" id="hub-dpi-value">${dpiValue} DPI</span></div>
        <input class="hub-range" type="range" data-role="hub-dpi" data-stage="${activeStage.index}" min="${ms.dpi_min || 50}" max="${ms.dpi_max || 42000}" step="${ms.dpi_step || 50}" value="${dpiValue}">
        <div class="row tight hub-dpi-apply">
          <input class="input" type="number" data-role="hub-dpi-input" data-stage="${activeStage.index}" min="${ms.dpi_min || 50}" max="${ms.dpi_max || 42000}" step="${ms.dpi_step || 50}" value="${dpiValue}">
          <button class="btn primary" data-action="hub-apply-dpi" data-stage="${activeStage.index}">${ico("check", 14)} 应用</button>
        </div>
      </div>` : "";

    return `
      <div class="toolbar">
        <span class="chip ${msOk ? "accent" : ""}">${msOk ? "已连接" : msOnline ? "读取失败" : "未连接"}</span>
        <div class="spacer"></div>
        <button class="btn" data-action="hub-refresh">${ico("refresh", 15)} 重新读取</button>
      </div>
      <div class="panel device-page">
        <div class="hub-head">
          <div class="hub-orb">${ico("mouse", 24)}</div>
          <div class="hub-main">
            <div class="hub-name">${esc(ms.model || "AUSDOM G04 Ultra")}</div>
            <div class="hub-sub">${msOk ? esc(ms.link || "2.4G") + " 已连接" : msOnline ? "接收器在线 · 读取失败" : "未找到 2.4G 接收器"}</div>
          </div>
        </div>
        ${msOk ? `<div class="page-battery">${renderBattery(ms, "剩余电量")}</div>` : `<div class="hub-note">${esc(ms.error || "请确认鼠标的 2.4G 接收器已插入电脑，并打开鼠标电源。")}</div>`}
        ${msOk ? `<div class="page-section">
          <div class="hub-section-title">回报率 · ${ms.wireless ? "2.4G 无线" : "有线"}</div>
          <div class="hub-chips">${rateButtons}</div>
        </div>` : ""}
        ${dpiPanel}
        ${sensorPanel}
        <div class="hub-note">回报率、DPI 与传感器设置会立即写入鼠标，保存在接收器中。切换设置后请稍等片刻再继续操作。</div>
      </div>`;
  }

  function renderGamepad() {
    const gp = S.gamepad || S.hub?.gamepad || null;
    if (!gp) return hubReading("正在连接手柄", "正在查询 XInput 手柄状态…");
    const connected = !!gp.connected;
    const battery = gp.battery;
    const batteryKnown = battery != null;
    const buttons = gp.buttons || {};
    const down = (name) => (buttons[name] ? " active" : "");
    const lt = Number(gp.triggers?.left || 0);
    const rt = Number(gp.triggers?.right || 0);
    const lx = Number(gp.sticks?.left?.x || 0);
    const ly = Number(gp.sticks?.left?.y || 0);
    const rx = Number(gp.sticks?.right?.x || 0);
    const ry = Number(gp.sticks?.right?.y || 0);
    const dotStyle = (x, y) => `transform:translate(${(x / 32767) * 43}px, ${(-y / 32767) * 43}px)`;
    const disabled = connected ? "" : " disabled";
    const batteryBlock = batteryKnown ? `
      <div class="gp-power">
        <div class="gp-power-value" style="color:${batteryTone(Number(battery))}">${battery}<span>%</span></div>
        <div class="gp-power-main">
          <div class="gp-power-title">${gp.charging ? "正在充电" : "手柄电量"}</div>
          <div class="gp-power-note">${esc(gp.battery_note || "XInput 电量等级换算，仅供参考")}</div>
        </div>
        <div class="gp-bar"><i style="width:${Math.max(2, Math.min(100, Number(battery)))}%;background:${batteryTone(Number(battery))}"></i></div>
      </div>` : `
      <div class="gp-power gp-power--unknown">
        <div class="gp-power-icon">${ico(connected ? "charging" : "battery", 24)}</div>
        <div class="gp-power-main">
          <div class="gp-power-title">${esc(gp.battery_label || (connected ? "手柄已连接" : "未检测到手柄"))}</div>
          <div class="gp-power-note">${esc(gp.battery_note || gp.error || "XInput 未提供电量百分比")}</div>
        </div>
        <span class="chip ${connected ? "accent" : ""}">${connected ? "实时在线" : "离线"}</span>
      </div>`;

    return `
      <div class="toolbar">
        <span class="chip ${connected ? "accent" : ""}" id="gp-status">${connected ? "已连接" : "未连接"}</span>
        <div class="spacer"></div>
        <button class="btn" data-action="gp-refresh">${ico("refresh", 15)} 重新检测</button>
      </div>
      <div class="panel device-page gp-page">
        <div class="hub-head gp-head">
          <div class="hub-orb gp-orb">${ico("gamepad", 26)}</div>
          <div class="hub-main">
            <div class="hub-name">BIGBIG WON Rainbow 2 SE</div>
            <div class="hub-sub">${connected ? `${esc(gp.link || "XInput")} · 实时输入已就绪` : "未检测到 XInput 手柄，请打开手柄电源"}</div>
          </div>
          <div class="gp-slot ${connected ? "on" : ""}">${connected ? `SLOT ${gp.slot ?? "—"}` : "OFFLINE"}</div>
        </div>
        ${batteryBlock}
        <div class="gp-facts">
          <div class="gp-fact"><span>连接方式</span><strong>${esc(gp.link || "—")}</strong></div>
          <div class="gp-fact"><span>输入通道</span><strong>${connected ? `XInput · slot ${gp.slot ?? "—"}` : "—"}</strong></div>
          <div class="gp-fact"><span>电量来源</span><strong>${esc(gp.battery_label || (connected ? "XInput" : "—"))}</strong></div>
          <div class="gp-fact"><span>数据包</span><strong class="mono" id="gp-packet">${connected ? (gp.packet ?? "—") : "—"}</strong></div>
        </div>
        <div class="divider"></div>
        <div class="gp-tester">
          <div class="gp-tester-head">
            <span class="hub-section-title">实时输入测试</span>
            <span class="gp-active" id="gp-active">${(gp.buttons_down || []).length ? esc((gp.buttons_down || []).map((name) => GAMEPAD_BUTTON_LABELS[name] || name).join(" · ")) : "无按键按下"}</span>
          </div>
          <div class="gp-layout">
            <div class="gp-side">
              <div class="gp-stick-wrap">
                <div class="gp-stick">
                  <span class="gp-stick-ring"></span>
                  <i class="gp-stick-dot" id="gp-dot-l" style="${dotStyle(lx, ly)}"></i>
                  <span class="gp-stick-tag">L</span>
                </div>
                <div class="gp-axis mono" id="gp-stick-l-val">${lx}, ${ly}</div>
              </div>
              <div class="gp-cross">
                <span class="gp-btn gp-dpad gp-up${down("up")}" data-gp-btn="up">${ico("chevronUp", 15)}</span>
                <span class="gp-btn gp-dpad gp-left${down("left")}" data-gp-btn="left">${ico("chevronRight", 15, "flip")}</span>
                <span class="gp-cross-center"></span>
                <span class="gp-btn gp-dpad gp-right${down("right")}" data-gp-btn="right">${ico("chevronRight", 15)}</span>
                <span class="gp-btn gp-dpad gp-down${down("down")}" data-gp-btn="down">${ico("chevronDown", 15)}</span>
              </div>
            </div>
            <div class="gp-center">
              <div class="gp-triggers">
                <div class="gp-trigger">
                  <div class="gp-trigger-head"><span>LT</span><strong class="mono" id="gp-lt-val">${lt}</strong></div>
                  <div class="gp-trigger-track"><i id="gp-lt-bar" style="width:${Math.max(2, Math.round((lt / 255) * 100))}%"></i></div>
                </div>
                <div class="gp-trigger">
                  <div class="gp-trigger-head"><span>RT</span><strong class="mono" id="gp-rt-val">${rt}</strong></div>
                  <div class="gp-trigger-track"><i id="gp-rt-bar" style="width:${Math.max(2, Math.round((rt / 255) * 100))}%"></i></div>
                </div>
              </div>
              <div class="gp-bumpers">
                <span class="gp-btn gp-bumper${down("lb")}" data-gp-btn="lb">LB</span>
                <span class="gp-btn gp-bumper${down("rb")}" data-gp-btn="rb">RB</span>
              </div>
              <div class="gp-face">
                <span class="gp-btn gp-face-btn gp-face-y${down("y")}" data-gp-btn="y">Y</span>
                <span class="gp-btn gp-face-btn gp-face-x${down("x")}" data-gp-btn="x">X</span>
                <span class="gp-btn gp-face-btn gp-face-b${down("b")}" data-gp-btn="b">B</span>
                <span class="gp-btn gp-face-btn gp-face-a${down("a")}" data-gp-btn="a">A</span>
              </div>
              <div class="gp-system">
                <span class="gp-btn gp-pill${down("back")}" data-gp-btn="back">${ico("window", 13)} 视图</span>
                <span class="gp-btn gp-pill${down("start")}" data-gp-btn="start">${ico("list", 13)} 菜单</span>
              </div>
            </div>
            <div class="gp-side">
              <div class="gp-stick-wrap">
                <div class="gp-stick">
                  <span class="gp-stick-ring"></span>
                  <i class="gp-stick-dot" id="gp-dot-r" style="${dotStyle(rx, ry)}"></i>
                  <span class="gp-stick-tag">R</span>
                </div>
                <div class="gp-axis mono" id="gp-stick-r-val">${rx}, ${ry}</div>
              </div>
              <div class="gp-stick-extra">
                <span class="gp-btn gp-pill${down("l3")}" data-gp-btn="l3">L3 按下</span>
                <span class="gp-btn gp-pill${down("r3")}" data-gp-btn="r3">R3 按下</span>
              </div>
            </div>
          </div>
        </div>
        <div class="gp-vibrate-panel">
          <div class="gp-vibrate-copy">
            <div class="hub-section-title">震动测试</div>
            <p>通过 XInput 直接驱动手柄的左右马达，用来确认连接正常。震动会在设定时间后自动停止。</p>
          </div>
          <div class="gp-vibrate-actions">
            <button class="btn" data-action="gp-vibrate" data-strength="light"${disabled}>${ico("vibrate", 15)} 轻震</button>
            <button class="btn primary" data-action="gp-vibrate" data-strength="strong"${disabled}>${ico("vibrate", 15)} 强震</button>
            <button class="btn" data-action="gp-stop"${disabled}>停止</button>
          </div>
        </div>
        <div class="hub-note">XInput 提供实时按键、摇杆、扳机、震动和粗粒度电量。按键重映射、体感、宏、灯效与固件升级依赖厂商私有协议，本版本尚未接入，也不会修改手柄固件。</div>
      </div>`;
  }

  function renderLogLines() {
    const logs = (S.deviceLog || []).slice(-60).reverse();
    if (!logs.length) return `<div class="muted">暂无日志。点击「刷新日志」读取。</div>`;
    return logs.map((row) => `<div class="log-line"><span class="log-dir ${row.dir === "IN" ? "in" : ""}">${esc(row.dir)}</span><span>${esc(row.ts)}</span><span>${esc(row.hex)}</span></div>`).join("");
  }

  async function fetchDeviceLog() {
    if (S.demo) return;
    const res = await apiCall("device_action", "log");
    if (res?.ok) S.deviceLog = res.log || [];
  }

  // ------------------------------------------------------------------
  // Rendering: settings
  // ------------------------------------------------------------------

  function updatePanelHTML() {
    const u = S.runtime?.update || { phase: "idle", current: S.runtime?.version };
    const phase = u.phase || "idle";
    const current = esc(u.current || S.runtime?.version || "");
    const latest = esc(u.latest || "");
    const canInstall = !!u.canInstall;
    let status = "";
    let action = "";

    if (phase === "checking") {
      status = "正在连接 GitHub 检查新版本…";
    } else if (phase === "available") {
      if (!canInstall) {
        status = `发现新版本 ${latest}。当前是源码运行，请到发布页下载。`;
        action = `<button class="btn small" data-action="open-release">${ico("external", 13)} 打开发布页</button>`;
      } else if (!u.asset) {
        status = `发现新版本 ${latest}，安装包还在 GitHub 上编译，请稍后再试。`;
        action = `<button class="btn small" data-action="update-check">${ico("refresh", 13)} 重新检查</button>`;
      } else {
        status = `发现新版本 ${latest}（当前 ${current}）。`;
        action = `<button class="btn small primary" data-action="update-download">${ico("download", 13)} 下载并安装</button>`;
      }
    } else if (phase === "uptodate") {
      status = `已是最新版本 ${current}。`;
      action = `<button class="btn small" data-action="update-check">${ico("refresh", 13)} 重新检查</button>`;
    } else if (phase === "downloading") {
      status = "正在下载安装包…";
    } else if (phase === "extracting") {
      status = "正在解压安装包…";
    } else if (phase === "ready") {
      status = `新版本 ${latest} 已下载。安装会关闭应用、替换文件并自动重启。`;
      action = `<button class="btn small primary" data-action="update-apply">${ico("refresh", 13)} 重启并安装</button>`;
    } else if (phase === "installing") {
      status = "正在重启并安装，请稍候…";
    } else if (phase === "error") {
      status = `检查失败：${esc(u.error || "未知错误")}`;
      action = `<button class="btn small" data-action="update-check">${ico("refresh", 13)} 重试</button>`;
    } else {
      const auto = S.config.settings.autoCheckUpdate !== false;
      status = !canInstall
        ? "源码运行模式，只能检查版本，不能自动安装。"
        : auto ? "启动时会自动检查更新，也可以手动检查。" : "自动检查已关闭，可以手动检查。";
      action = `<button class="btn small" data-action="update-check">${ico("refresh", 13)} 检查更新</button>`;
    }

    const percent = Math.max(0, Math.min(100, Number(u.progress || 0)));
    const progress = phase === "downloading"
      ? `<div class="update-progress"><div class="hub-bar"><i style="width:${Math.max(2, percent)}%"></i></div><span>${percent}%</span></div>`
      : "";
    const notes = phase === "available" && u.notes ? `<div class="update-notes">${esc(u.notes)}</div>` : "";

    return `
      <div class="setting-row" style="align-items:flex-start">
        <div class="setting-main"><div class="setting-name">当前版本 ${current}</div><div class="setting-desc">${status}</div>${progress}${notes}</div>
        ${action ? `<div style="flex:0 0 auto">${action}</div>` : ""}
      </div>
      <div class="setting-row"><div class="setting-main"><div class="setting-name">启动时检查更新</div><div class="setting-desc">从 GitHub Releases 获取新版本</div></div><label class="switch"><input type="checkbox" data-setting="autoCheckUpdate" ${S.config.settings.autoCheckUpdate !== false ? "checked" : ""}><span></span></label></div>
    `;
  }

  function renderSettings() {
    const s = S.config.settings;
    return `
      <div class="split">
        <div>
          <div class="panel">
            <div class="panel-title" style="margin-bottom:6px">启动与运行</div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">开机自启动</div><div class="setting-desc">登录 Windows 后自动在托盘运行</div></div><label class="switch"><input type="checkbox" data-setting="autostart" ${s.autostart ? "checked" : ""}><span></span></label></div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">关闭窗口时最小化到托盘</div><div class="setting-desc">关闭窗口不退出，按键动作继续工作</div></div><label class="switch"><input type="checkbox" data-setting="minimizeToTray" ${s.minimizeToTray ? "checked" : ""}><span></span></label></div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">启动时同步按键绑定</div><div class="setting-desc">每次连接设备后自动写入软件触发绑定</div></div><label class="switch"><input type="checkbox" data-setting="syncBindingsOnStart" ${s.syncBindingsOnStart ? "checked" : ""}><span></span></label></div>
          </div>
          <div class="panel" style="margin-top:16px">
            <div class="panel-title" style="margin-bottom:6px">按键行为</div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">双击判定窗口</div><div class="setting-desc">两次触发间隔小于该值时执行双击动作</div></div><div class="row" style="max-width:190px;align-items:center"><input class="input" type="number" min="80" max="1500" step="10" value="${s.doublePressMs || 320}" data-setting-number="doublePressMs"><span class="muted" style="font-size:11px">ms</span></div></div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">自动切换配置</div><div class="setting-desc">根据前台程序匹配切换配置</div></div><label class="switch"><input type="checkbox" data-setting="autoProfileSwitch" ${s.autoProfileSwitch ? "checked" : ""}><span></span></label></div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">未匹配时恢复默认</div><div class="setting-desc">离开匹配程序后回到第一个配置</div></div><label class="switch"><input type="checkbox" data-setting="revertToDefault" ${s.revertToDefault ? "checked" : ""}><span></span></label></div>
          </div>
        </div>
        <div>
          <div class="panel">
            <div class="panel-title" style="margin-bottom:12px">外观</div>
            <div class="action-row">
              <button class="btn ${s.theme === "dark" ? "primary" : ""}" data-action="set-theme" data-theme="dark">${ico("moon", 15)} 深色</button>
              <button class="btn ${s.theme === "light" ? "primary" : ""}" data-action="set-theme" data-theme="light">${ico("sun", 15)} 浅色</button>
            </div>
          </div>
          <div class="panel" style="margin-top:16px">
            <div class="panel-title" style="margin-bottom:12px">数据</div>
            <div class="action-row">
              <button class="btn" data-action="export-config">${ico("download", 15)} 导出配置</button>
              <button class="btn" data-action="import-config">${ico("upload", 15)} 导入配置</button>
            </div>
            <div class="divider"></div>
            <div class="setting-main"><div class="setting-name">数据目录</div><div class="setting-desc mono" style="word-break:break-all">${esc(S.runtime?.dataDir || "")}</div></div>
            <button class="btn small" style="margin-top:10px" data-action="open-data-dir">${ico("folder-open", 13)} 打开目录</button>
          </div>
          <div class="panel" style="margin-top:16px">
            <div class="panel-title" style="margin-bottom:4px">软件更新</div>
            ${updatePanelHTML()}
          </div>
          <div class="panel" style="margin-top:16px">
            <div class="panel-title" style="margin-bottom:8px">关于</div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">Keypad Studio</div><div class="setting-desc">版本 ${esc(S.runtime?.version || "1.0.0")} · WebView2</div></div></div>
            <div class="setting-row"><div class="setting-main"><div class="setting-name">GitHub</div><div class="setting-desc mono">Delture/keypad-studio</div></div><button class="btn small" data-action="open-repo">${ico("external", 13)} 打开</button></div>
          </div>
        </div>
      </div>
    `;
  }

  // ------------------------------------------------------------------
  // Modals
  // ------------------------------------------------------------------

  function renderModal() {
    const root = $("#modal-root");
    if (!S.editing) { root.innerHTML = ""; return; }
    if (S.editing.kind === "key") root.innerHTML = keyEditorHTML();
    else if (S.editing.kind === "action") root.innerHTML = actionEditorHTML();
    else if (S.editing.kind === "profile") root.innerHTML = profileEditorHTML();
    else if (S.editing.kind === "profile-menu") root.innerHTML = profileMenuHTML();
    else if (S.editing.kind === "confirm") root.innerHTML = confirmHTML();
    else root.innerHTML = "";
    const body = $(".modal-body");
    if (body) body.scrollTop = S.modalScroll || 0;
    const search = $('[data-role="picker-search"]');
    if (search) {
      search.value = S.pickerFilter;
      filterPicker(S.pickerFilter);
    }
  }

  function openModal(editing) {
    S.editing = editing;
    S.modalScroll = 0;
    S.pickerFilter = "";
    renderModal();
  }

  function closeModal() {
    S.editing = null;
    $("#modal-root").innerHTML = "";
  }

  function modalShell({ title, sub, body, footer, wide = true }) {
    return `<div class="modal-overlay" data-overlay="true">
      <div class="modal ${wide ? "wide" : ""}">
        <div class="modal-header"><div><div class="modal-title">${title}</div>${sub ? `<div class="modal-sub">${sub}</div>` : ""}</div><button class="btn small ghost icon-only" data-action="close-modal">${ico("x", 16)}</button></div>
        <div class="modal-body" onscroll="this.closest('.modal').dataset.scroll=this.scrollTop">${body}</div>
        <div class="modal-footer">${footer}</div>
      </div>
    </div>`;
  }

  // ------------------------------------------------------------------
  // Key editor
  // ------------------------------------------------------------------

  function openKeyEditor(slot) {
    const binding = bindingFor(slot);
    openModal({ kind: "key", slot, selected: binding.action || null, double: binding.double || null });
  }

  function keyEditorHTML() {
    const { slot, selected, double } = S.editing;
    const action = actionById(selected);
    const doubleAction = actionById(double);
    const layer = currentLayer();
    const q = (S.pickerFilter || "").toLowerCase();
    const actions = (S.config.actions || []).filter((a) => !q || (a.name || "").toLowerCase().includes(q) || typeInfo(a.type).name.includes(q));
    const current = action
      ? `<div class="current-action">
          <div class="action-icon" style="--action-color:${typeColor(action.type)};color:${typeColor(action.type)}">${ico(actionIcon(action), 22)}</div>
          <div><div class="current-name">${esc(action.name)}</div><div class="current-sub">${esc(typeInfo(action.type).name)} · ${esc(actionPreview(action))}</div></div>
          <div class="actions"><button class="btn small" data-action="test-selected-action">${ico("play", 13)} 测试</button><button class="btn small" data-action="edit-selected-action">${ico("edit", 13)} 编辑</button></div>
        </div>`
      : `<div class="current-action"><div class="action-icon">${ico("plus", 22)}</div><div><div class="current-name">未绑定动作</div><div class="current-sub">从下面选择一个动作，或新建一个</div></div></div>`;

    const picker = actions.length
      ? actions.map((a) => `<button class="picker-item ${a.id === selected ? "selected" : ""}" data-action="select-action" data-id="${a.id}">
          <span class="picker-icon" style="color:${typeColor(a.type)}">${ico(actionIcon(a), 16)}</span>
          <span style="min-width:0"><span class="picker-name">${esc(a.name)}</span><span class="picker-type">${esc(typeInfo(a.type).name)}</span></span>
        </button>`).join("")
      : `<div class="empty" style="grid-column:1/-1;padding:26px"><div class="empty-icon" style="width:48px;height:48px">${ico("search", 20)}</div><h3>没有匹配的动作</h3><p>换个关键词，或新建动作。</p></div>`;

    const options = (S.config.actions || []).map((a) => `<option value="${a.id}" ${double === a.id ? "selected" : ""}>${esc(a.name)}（${esc(typeInfo(a.type).name)}）</option>`).join("");

    return modalShell({
      title: `按键 ${slot} · ${esc(layer?.name || "图层")}`,
      sub: `当前配置：${esc(currentProfile()?.name || "")}`,
      body: `
        ${current}
        <div class="row" style="align-items:center;margin-bottom:14px">
          <div class="search">${ico("search", 15)}<input class="input" data-role="picker-search" value="${esc(S.pickerFilter)}" placeholder="搜索动作…"></div>
          <button class="btn" data-action="new-action-for-key">${ico("plus", 14)} 新建动作</button>
        </div>
        <div class="picker" id="action-picker">${picker}</div>
        <div class="divider"></div>
        <div class="field" style="margin-bottom:0"><label>双击动作（可选）</label>
          <select class="select" data-role="double-select" onchange="window.__ks_set_double(this.value)">
            <option value="">无</option>${options}
          </select>
          <div class="help">双击该按键时执行另一个动作。设置后单次点击会等待 ${S.config.settings.doublePressMs || 320} ms 再执行。</div>
        </div>
      `,
      footer: `<div class="left"><button class="btn ghost danger" data-action="clear-binding">${ico("trash", 14)} 清除</button></div>
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn primary" data-action="save-binding">${ico("check", 15)} 保存绑定</button>`,
    });
  }

  async function saveKeyBinding() {
    const { slot, selected, double } = S.editing;
    const layer = currentLayer();
    if (!layer) return;
    if (!layer.keys) layer.keys = {};
    layer.keys[String(slot)] = { action: selected || null, double: double || null };
    await saveNow();
    closeModal();
    renderAll();
    showToast("按键绑定已保存", "success");
  }

  // used by the double-action select
  window.__ks_set_double = function (value) {
    if (S.editing?.kind === "key") S.editing.double = value || null;
  };

  function filterPicker(query) {
    const q = String(query || "").toLowerCase();
    $$("#action-picker .picker-item").forEach((item) => {
      item.style.display = item.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  }

  // ------------------------------------------------------------------
  // Action editor
  // ------------------------------------------------------------------

  function defaultParams(type) {
    switch (type) {
      case "key": return { keys: ["Ctrl", "C"], mode: "press", hold: 0 };
      case "text": return { text: "", mode: "type", interval: 0 };
      case "open": return { target: "", args: "", cwd: "", runAsAdmin: false };
      case "command": return { command: "", shell: "powershell", hidden: true, cwd: "" };
      case "macro": return { steps: [{ type: "delay", ms: 100 }], repeat: 1, interval: 0 };
      case "media": return { action: "play_pause" };
      case "app_volume": return { process: "cs2.exe", mode: "toggle" };
      case "network_toggle": return {};
      case "mouse": return { action: "left", count: 1, dx: 0, dy: 0, x: 0, y: 0, delta: 120 };
      case "system": return { action: "lock" };
      case "clipboard": return { action: "paste", text: "" };
      case "window": return { action: "minimize" };
      case "layer": return { mode: "toggle", index: 1 };
      case "profile": return { mode: "next", profileId: S.config.profiles[0]?.id || "" };
      case "delay": return { ms: 100 };
      default: return {};
    }
  }

  function openActionEditor(id, opts = {}) {
    let action;
    let isNew = false;
    if (id) {
      const original = actionById(id);
      if (!original) return;
      action = JSON.parse(JSON.stringify(original));
    } else {
      isNew = true;
      action = { id: uuid("act_"), name: "新动作", type: "key", icon: "keyboard", params: defaultParams("key") };
    }
    openModal({ kind: "action", action, isNew, slot: opts.slot || null });
  }

  function actionEditorHTML() {
    const e = S.editing;
    const a = e.action;
    const t = typeInfo(a.type);
    const types = S.meta.actionTypes.map((item) => `<button class="type-option ${item.id === a.type ? "selected" : ""}" data-action="change-action-type" data-type="${item.id}">
      <span class="type-icon">${ico(item.icon, 17)}</span><span>${esc(item.name)}</span>
    </button>`).join("");
    const icons = ["bolt", "keyboard", "text", "folder", "terminal", "macro", "music", "mouse", "power", "clipboard", "window", "layers", "grid", "clock", "globe", "play", "copy", "paste", "monitor", "lock", "sparkles", "command", "user", "bell"].map((name) =>
      `<button class="icon-choice ${a.icon === name ? "selected" : ""}" data-action="select-icon" data-icon="${name}" title="${name}">${ico(name, 17)}</button>`).join("");

    return modalShell({
      title: e.isNew ? "新建动作" : "编辑动作",
      sub: `${esc(t.name)} · ${esc(t.desc || "")}`,
      body: `
        <div class="field"><label>动作名称</label><input class="input" data-field="name" value="${esc(a.name)}" placeholder="例如：打开浏览器"></div>
        <div class="field"><label>图标</label><div class="icon-picker">${icons}</div></div>
        <div class="field"><label>动作类型</label><div class="type-grid">${types}</div></div>
        <div class="divider"></div>
        <div id="action-form">${actionFormHTML(a)}</div>
      `,
      footer: `${e.isNew ? "" : `<div class="left"><button class="btn ghost danger" data-action="delete-action" data-id="${a.id}">${ico("trash", 14)} 删除</button></div>`}
        <button class="btn" data-action="test-draft">${ico("play", 14)} 测试</button>
        <button class="btn" data-action="close-modal">取消</button>
        <button class="btn primary" data-action="save-action">${ico("check", 15)} 保存动作</button>`,
    });
  }

  function actionFormHTML(a) {
    const p = a.params || {};
    switch (a.type) {
      case "key":
        return `<div class="row">
          <div class="field" style="flex:1.6"><label>按键 / 组合键</label>
            <div class="combo-wrap"><input class="input" id="combo-main" data-field="keys" data-kind="combo" value="${esc(comboText(p.keys))}" placeholder="例如 Ctrl + C"><button class="btn" data-action="record-combo" data-target="#combo-main">${ico("keyboard", 14)} 录制</button></div>
            <div class="help">点击「录制」后直接按下想要的组合键，按 Esc 取消。</div>
          </div>
          <div class="field" style="flex:0 0 150px"><label>触发方式</label><select class="select" data-field="mode">
            <option value="press" ${p.mode === "press" ? "selected" : ""}>按下并抬起</option>
            <option value="down" ${p.mode === "down" ? "selected" : ""}>只按下</option>
            <option value="up" ${p.mode === "up" ? "selected" : ""}>只抬起</option>
          </select></div>
        </div>
        <div class="field" style="max-width:200px"><label>按住时长（毫秒，可选）</label><input class="input" type="number" min="0" step="10" data-field="hold" value="${Number(p.hold || 0)}"></div>`;
      case "text":
        return `<div class="field"><label>文本内容</label><textarea class="textarea" data-field="text" placeholder="输入要发送的文字，支持中文">${esc(p.text || "")}</textarea></div>
          <div class="row"><div class="field"><label>输入方式</label><select class="select" data-field="mode"><option value="type" ${p.mode === "type" ? "selected" : ""}>逐字输入（Unicode）</option><option value="paste" ${p.mode === "paste" ? "selected" : ""}>剪贴板粘贴</option></select></div>
          <div class="field"><label>字符间隔（毫秒）</label><input class="input" type="number" min="0" data-field="interval" value="${Number(p.interval || 0)}"></div></div>
          <div class="help">如果目标程序不接受 Unicode 输入，请改用「剪贴板粘贴」。</div>`;
      case "open":
        return `<div class="field"><label>目标（程序 / 文件 / 文件夹 / 网址）</label>
          <div class="combo-wrap"><input class="input" id="open-target" data-field="target" value="${esc(p.target || "")}" placeholder="C:\\Windows\\notepad.exe 或 https://example.com"><button class="btn" data-action="browse" data-kind="file" data-target="#open-target">${ico("file", 14)} 文件</button><button class="btn" data-action="browse" data-kind="folder" data-target="#open-target">${ico("folder-open", 14)} 文件夹</button></div></div>
          <div class="row"><div class="field"><label>参数（可选）</label><input class="input" data-field="args" value="${esc(p.args || "")}" placeholder="命令行参数"></div><div class="field"><label>工作目录（可选）</label><input class="input" data-field="cwd" value="${esc(p.cwd || "")}" placeholder="留空为默认"></div></div>
          <label class="check"><input type="checkbox" data-field="runAsAdmin" ${p.runAsAdmin ? "checked" : ""}> 以管理员身份运行</label>`;
      case "command":
        return `<div class="field"><label>命令内容</label><textarea class="textarea" data-field="command" placeholder="例如：Get-Process | Sort-Object CPU -Descending | Select-Object -First 5">${esc(p.command || "")}</textarea></div>
          <div class="row"><div class="field"><label>Shell</label><select class="select" data-field="shell"><option value="powershell" ${p.shell === "powershell" ? "selected" : ""}>PowerShell</option><option value="cmd" ${p.shell === "cmd" ? "selected" : ""}>CMD</option><option value="bat" ${p.shell === "bat" ? "selected" : ""}>bat 文件</option></select></div>
          <div class="field"><label>工作目录</label><input class="input" data-field="cwd" value="${esc(p.cwd || "")}"></div></div>
          <label class="check"><input type="checkbox" data-field="hidden" ${p.hidden !== false ? "checked" : ""}> 隐藏命令行窗口</label>`;
      case "macro":
        return `<div class="row"><div class="field"><label>循环次数</label><input class="input" type="number" min="1" max="999" data-field="repeat" value="${Number(p.repeat || 1)}"></div><div class="field"><label>每轮间隔（毫秒）</label><input class="input" type="number" min="0" data-field="interval" value="${Number(p.interval || 0)}"></div></div>
          <div class="field"><label>步骤</label><div id="macro-steps">${(p.steps || []).map((step, i) => macroStepHTML(step, i)).join("")}</div>
          <div class="add-step-row">
            ${["key", "text", "delay", "mouse", "media", "app_volume", "clipboard", "window", "open", "command"].map((type) => `<button class="btn" data-action="add-step" data-type="${type}">${ico(typeIcon(type), 13)} ${typeStepName(type)}</button>`).join("")}
          </div></div>`;
      case "media":
        return selectField("media", "媒体动作", S.meta.mediaActions, p.action);
      case "app_volume":
        return `<div class="row"><div class="field" style="flex:1.5"><label>程序名</label><input class="input" data-field="process" value="${esc(p.process || "cs2.exe")}" placeholder="cs2.exe"><div class="help">匹配音量合成器中的程序名，例如 cs2.exe、chrome.exe。不影响系统音量。</div></div>
          <div class="field"><label>操作</label><select class="select" data-field="mode">
            <option value="toggle" ${p.mode === "toggle" ? "selected" : ""}>静音 ↔ 100%</option>
            <option value="mute" ${p.mode === "mute" ? "selected" : ""}>静音</option>
            <option value="full" ${p.mode === "full" ? "selected" : ""}>设为 100%</option>
          </select></div></div>`;
      case "network_toggle":
        return `<div class="help" style="font-size:12px;line-height:1.75">
          当前为「Tailscale 已连接 + Clash Party 普通代理 + TUN 关闭」时，切换到「Tailscale 断开 + Clash Party TUN 模式」；其他状态则恢复为前者。<br>
          Clash Party 需要配置 TUN 与系统代理的全局快捷键，应用会读取其配置；切换 TUN 需要 Clash Party 具备管理员权限。
        </div>`;
      case "mouse":
        return `<div class="field"><label>鼠标动作</label><select class="select" data-field="action" data-rerender="true">${options(S.meta.mouseActions, p.action)}</select></div>${mouseParamsHTML(p)}`;
      case "system":
        return selectField("system", "系统动作", S.meta.systemActions, p.action);
      case "clipboard":
        return `<div class="field"><label>剪贴板动作</label><select class="select" data-field="action" data-rerender="true">${options(S.meta.clipboardActions, p.action)}</select></div>
          ${p.action === "set" ? `<div class="field"><label>写入的文本</label><textarea class="textarea" data-field="text">${esc(p.text || "")}</textarea></div>` : ""}`;
      case "window":
        return selectField("window", "窗口动作", S.meta.windowActions, p.action);
      case "layer":
        return `<div class="row"><div class="field"><label>切换方式</label><select class="select" data-field="mode" data-rerender="true"><option value="toggle" ${p.mode === "toggle" ? "selected" : ""}>切换（再按回主层）</option><option value="set" ${p.mode === "set" ? "selected" : ""}>切换到指定图层</option><option value="next" ${p.mode === "next" ? "selected" : ""}>下一图层</option><option value="prev" ${p.mode === "prev" ? "selected" : ""}>上一图层</option></select></div>
          <div class="field"><label>目标图层</label><select class="select" data-field="index">${currentLayers().map((layer, i) => `<option value="${i}" ${Number(p.index || 0) === i ? "selected" : ""}>${esc(layer.name)}</option>`).join("")}</select></div></div>`;
      case "profile":
        return `<div class="row"><div class="field"><label>切换方式</label><select class="select" data-field="mode" data-rerender="true"><option value="next" ${p.mode === "next" ? "selected" : ""}>下一个配置</option><option value="prev" ${p.mode === "prev" ? "selected" : ""}>上一个配置</option><option value="set" ${p.mode === "set" ? "selected" : ""}>切换到指定配置</option></select></div>
          <div class="field"><label>目标配置</label><select class="select" data-field="profileId">${S.config.profiles.map((profile) => `<option value="${profile.id}" ${p.profileId === profile.id ? "selected" : ""}>${esc(profile.name)}</option>`).join("")}</select></div></div>`;
      case "delay":
        return `<div class="field" style="max-width:240px"><label>等待时长（毫秒）</label><input class="input" type="number" min="0" step="10" data-field="ms" value="${Number(p.ms || 0)}"></div>`;
      case "none":
        return `<div class="empty" style="padding:26px"><div class="empty-icon" style="width:48px;height:48px">${ico("ban", 20)}</div><h3>无动作</h3><p>按下这个按键不会执行任何操作。</p></div>`;
      default:
        return "";
    }
  }

  function selectField(field, label, map, selected) {
    return `<div class="field"><label>${label}</label><select class="select" data-field="${field}">${options(map, selected)}</select></div>`;
  }

  function options(map, selected) {
    return Object.entries(map || {}).map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${esc(label)}</option>`).join("");
  }

  function mouseParamsHTML(p, stepIndex = null) {
    const step = stepIndex == null ? "" : ` data-step="${stepIndex}"`;
    if (p.action === "move_rel") {
      return `<div class="row"><div class="field"><label>X 位移</label><input class="input" type="number" data-field="dx"${step} value="${Number(p.dx || 0)}"></div><div class="field"><label>Y 位移</label><input class="input" type="number" data-field="dy"${step} value="${Number(p.dy || 0)}"></div></div>`;
    }
    if (p.action === "move_abs") {
      return `<div class="row"><div class="field"><label>X 坐标</label><input class="input" type="number" data-field="x"${step} value="${Number(p.x || 0)}"></div><div class="field"><label>Y 坐标</label><input class="input" type="number" data-field="y"${step} value="${Number(p.y || 0)}"></div></div>`;
    }
    if (p.action.startsWith("wheel")) {
      return `<div class="field" style="max-width:220px"><label>滚动量</label><input class="input" type="number" step="120" data-field="delta"${step} value="${Number(p.delta || 120)}"></div>`;
    }
    return `<div class="field" style="max-width:220px"><label>点击次数</label><input class="input" type="number" min="1" max="5" data-field="count"${step} value="${Number(p.count || 1)}"></div>`;
  }

  function typeIcon(type) {
    return { key: "keyboard", text: "text", delay: "clock", mouse: "mouse", media: "music", app_volume: "volume", clipboard: "clipboard", window: "window", open: "folder", command: "terminal" }[type] || "bolt";
  }

  function typeStepName(type) {
    return { key: "按键", text: "文本", delay: "延时", mouse: "鼠标", media: "多媒体", app_volume: "应用音量", clipboard: "剪贴板", window: "窗口", open: "打开", command: "命令" }[type] || type;
  }

  function macroStepHTML(step, index) {
    const type = step.type || "delay";
    let fields = "";
    if (type === "key") {
      fields = `<div class="row"><div class="field" style="flex:1.6"><label>组合键</label><div class="combo-wrap"><input class="input" id="combo-step-${index}" data-step="${index}" data-field="keys" data-kind="combo" value="${esc(comboText(step.keys))}" placeholder="例如 A"><button class="btn small" data-action="record-combo" data-target="#combo-step-${index}">${ico("keyboard", 13)} 录制</button></div></div><div class="field" style="flex:0 0 140px"><label>方式</label><select class="select" data-step="${index}" data-field="mode"><option value="press" ${step.mode === "press" ? "selected" : ""}>按下并抬起</option><option value="down" ${step.mode === "down" ? "selected" : ""}>按下</option><option value="up" ${step.mode === "up" ? "selected" : ""}>抬起</option></select></div></div>`;
    } else if (type === "text") {
      fields = `<div class="field"><label>文本</label><textarea class="textarea" data-step="${index}" data-field="text" style="min-height:62px">${esc(step.text || "")}</textarea></div>`;
    } else if (type === "delay") {
      fields = `<div class="field" style="max-width:220px"><label>等待（毫秒）</label><input class="input" type="number" min="0" step="10" data-step="${index}" data-field="ms" value="${Number(step.ms || 0)}"></div>`;
    } else if (type === "mouse") {
      fields = `<div class="field"><label>鼠标动作</label><select class="select" data-step="${index}" data-field="action" data-rerender="true">${options(S.meta.mouseActions, step.action)}</select></div>${mouseParamsHTML(step, index)}`;
    } else if (type === "media") {
      fields = `<div class="field"><label>媒体动作</label><select class="select" data-step="${index}" data-field="action">${options(S.meta.mediaActions, step.action)}</select></div>`;
    } else if (type === "app_volume") {
      fields = `<div class="row"><div class="field" style="flex:1.5"><label>程序名</label><input class="input" data-step="${index}" data-field="process" value="${esc(step.process || "cs2.exe")}"></div><div class="field"><label>操作</label><select class="select" data-step="${index}" data-field="mode"><option value="toggle" ${step.mode === "toggle" ? "selected" : ""}>静音 ↔ 100%</option><option value="mute" ${step.mode === "mute" ? "selected" : ""}>静音</option><option value="full" ${step.mode === "full" ? "selected" : ""}>100%</option></select></div></div>`;
    } else if (type === "clipboard") {
      fields = `<div class="field"><label>剪贴板动作</label><select class="select" data-step="${index}" data-field="action" data-rerender="true">${options(S.meta.clipboardActions, step.action)}</select></div>${step.action === "set" ? `<div class="field"><label>写入文本</label><textarea class="textarea" data-step="${index}" data-field="text" style="min-height:62px">${esc(step.text || "")}</textarea></div>` : ""}`;
    } else if (type === "window") {
      fields = `<div class="field"><label>窗口动作</label><select class="select" data-step="${index}" data-field="action">${options(S.meta.windowActions, step.action)}</select></div>`;
    } else if (type === "open") {
      fields = `<div class="field"><label>目标</label><input class="input" data-step="${index}" data-field="target" value="${esc(step.target || "")}" placeholder="程序、文件或网址"></div>`;
    } else if (type === "command") {
      fields = `<div class="field"><label>命令</label><textarea class="textarea" data-step="${index}" data-field="command" style="min-height:62px">${esc(step.command || "")}</textarea></div>`;
    }
    return `<div class="step-card">
      <div class="step-head"><span class="step-index">${index + 1}</span><span class="step-type">${typeStepName(type)}</span>
        <span class="step-actions">
          <button class="btn small ghost icon-only" data-action="move-step" data-index="${index}" data-dir="-1" ${index === 0 ? "disabled" : ""} title="上移">${ico("arrowUp", 13)}</button>
          <button class="btn small ghost icon-only" data-action="move-step" data-index="${index}" data-dir="1" title="下移">${ico("arrowDown", 13)}</button>
          <button class="btn small ghost icon-only danger" data-action="remove-step" data-index="${index}" title="删除">${ico("trash", 13)}</button>
        </span>
      </div>
      <div class="step-body">${fields}</div>
    </div>`;
  }

  function changeActionType(type) {
    if (!S.editing?.action) return;
    S.editing.action.type = type;
    S.editing.action.icon = typeInfo(type).icon || "bolt";
    S.editing.action.params = defaultParams(type);
    renderModal();
  }

  function updateField(el) {
    if (!S.editing) return;
    const field = el.dataset.field;
    const value = el.type === "checkbox" ? el.checked : el.value;
    if (S.editing.kind === "action") {
      const action = S.editing.action;
      if (el.dataset.step != null) {
        const index = Number(el.dataset.step);
        const step = action.params.steps?.[index];
        if (!step) return;
        if (field === "keys") step.keys = parseCombo(value);
        else if (["ms", "count", "dx", "dy", "x", "y", "delta"].includes(field)) step[field] = Number(value);
        else step[field] = value;
        return;
      }
      if (field === "name") action.name = value;
      else if (field === "icon") action.icon = value;
      else {
        action.params = action.params || {};
        if (field === "keys") action.params.keys = parseCombo(value);
        else if (["hold", "interval", "repeat", "count", "dx", "dy", "x", "y", "delta", "ms", "index"].includes(field)) action.params[field] = Number(value);
        else if (field === "hidden" || field === "runAsAdmin") action.params[field] = !!value;
        else action.params[field] = value;
      }
    } else if (S.editing.kind === "profile") {
      updateProfileField(el);
    }
  }

  function updateProfileField(el) {
    if (S.editing?.kind !== "profile") return;
    const field = el.dataset.profileField;
    const value = el.type === "checkbox" ? el.checked : el.value;
    if (field === "name") S.editing.profile.name = value;
    else if (field === "color") S.editing.profile.color = value;
    else if (field === "match") S.editing.profile.match = String(value || "").split(",").map((x) => x.trim()).filter(Boolean);
    else if (field?.startsWith("layer-name:")) {
      const i = Number(field.split(":")[1]);
      if (S.editing.profile.layers?.[i]) S.editing.profile.layers[i].name = value;
    }
  }

  function changeMacroStepType(index, type) {
    if (!S.editing?.action?.params?.steps) return;
    const current = S.editing.action.params.steps[index] || {};
    const step = { type };
    if (type === "key") Object.assign(step, { keys: ["A"], mode: "press" });
    if (type === "text") Object.assign(step, { text: "", mode: "type" });
    if (type === "delay") Object.assign(step, { ms: 100 });
    if (type === "mouse") Object.assign(step, { action: "left", count: 1 });
    if (type === "media") Object.assign(step, { action: "play_pause" });
    if (type === "app_volume") Object.assign(step, { process: "cs2.exe", mode: "toggle" });
    if (type === "clipboard") Object.assign(step, { action: "paste", text: "" });
    if (type === "window") Object.assign(step, { action: "minimize" });
    if (type === "open") Object.assign(step, { target: "" });
    if (type === "command") Object.assign(step, { command: "", shell: "powershell", hidden: true });
    S.editing.action.params.steps[index] = step;
    renderModal();
  }

  function addMacroStep(type) {
    if (!S.editing?.action) return;
    S.editing.action.params = S.editing.action.params || {};
    S.editing.action.params.steps = S.editing.action.params.steps || [];
    const step = { type };
    if (type === "key") Object.assign(step, { keys: ["A"], mode: "press" });
    if (type === "text") Object.assign(step, { text: "", mode: "type" });
    if (type === "delay") Object.assign(step, { ms: 100 });
    if (type === "mouse") Object.assign(step, { action: "left", count: 1, dx: 0, dy: 0, x: 0, y: 0, delta: 120 });
    if (type === "media") Object.assign(step, { action: "play_pause" });
    if (type === "app_volume") Object.assign(step, { process: "cs2.exe", mode: "toggle" });
    if (type === "clipboard") Object.assign(step, { action: "paste", text: "" });
    if (type === "window") Object.assign(step, { action: "minimize" });
    if (type === "open") Object.assign(step, { target: "" });
    if (type === "command") Object.assign(step, { command: "", shell: "powershell", hidden: true });
    S.editing.action.params.steps.push(step);
    renderModal();
  }

  function removeMacroStep(index) {
    if (!S.editing?.action?.params?.steps) return;
    S.editing.action.params.steps.splice(index, 1);
    renderModal();
  }

  function moveMacroStep(index, dir) {
    const steps = S.editing?.action?.params?.steps;
    if (!steps) return;
    const target = index + dir;
    if (target < 0 || target >= steps.length) return;
    const [item] = steps.splice(index, 1);
    steps.splice(target, 0, item);
    renderModal();
  }

  async function saveActionEditor() {
    const e = S.editing;
    if (!e?.action) return;
    const action = e.action;
    if (!String(action.name || "").trim()) action.name = "未命名动作";
    if (e.isNew) {
      S.config.actions.push(action);
    } else {
      const i = S.config.actions.findIndex((x) => x.id === action.id);
      if (i >= 0) S.config.actions[i] = action;
    }
    if (e.slot) {
      const layer = currentLayer();
      if (layer) {
        layer.keys = layer.keys || {};
        layer.keys[String(e.slot)] = { action: action.id, double: layer.keys[String(e.slot)]?.double || null };
      }
    }
    await saveNow();
    const slot = e.slot;
    closeModal();
    renderAll();
    showToast(e.isNew ? "动作已创建" : "动作已保存", "success");
    if (slot) openKeyEditor(slot);
  }

  async function testActionById(id) {
    const action = actionById(id);
    if (!action) return;
    const res = await apiCall("test_action", action);
    showToast(res?.ok ? `正在测试：${action.name}` : (res?.error || "测试失败"), res?.ok ? "info" : "error");
  }

  function duplicateAction(id) {
    const original = actionById(id);
    if (!original) return;
    const copy = JSON.parse(JSON.stringify(original));
    copy.id = uuid("act_");
    copy.name = original.name + " 副本";
    S.config.actions.push(copy);
    saveNow();
    renderView();
    showToast("动作已复制", "success");
  }

  function confirmDeleteAction(id) {
    const action = actionById(id);
    if (!action) return;
    openModal({ kind: "confirm", title: "删除动作", message: `确定删除「${esc(action.name)}」吗？所有引用它的按键绑定也会被清除。`, confirmLabel: "删除", confirmAction: "delete-action-confirm", id, type: "action" });
  }

  function confirmDeleteProfile(id) {
    const profile = S.config.profiles.find((p) => p.id === id);
    if (!profile) return;
    if (S.config.profiles.length <= 1) { showToast("至少保留一个配置", "warning"); return; }
    openModal({ kind: "confirm", title: "删除配置", message: `确定删除「${esc(profile.name)}」吗？其中的图层和按键绑定会一起删除。`, confirmLabel: "删除", confirmAction: "delete-profile-confirm", id, type: "profile" });
  }

  async function performDelete(ds) {
    if (ds.confirmAction === "delete-action-confirm") {
      const id = ds.id;
      S.config.actions = S.config.actions.filter((a) => a.id !== id);
      for (const profile of S.config.profiles) {
        for (const layer of profile.layers) {
          for (const slot of Object.keys(layer.keys || {})) {
            if (layer.keys[slot]?.action === id) layer.keys[slot].action = null;
            if (layer.keys[slot]?.double === id) layer.keys[slot].double = null;
          }
        }
      }
      await saveNow();
      closeModal();
      renderAll();
      showToast("动作已删除", "success");
    } else if (ds.confirmAction === "delete-profile-confirm") {
      const id = ds.id;
      S.config.profiles = S.config.profiles.filter((p) => p.id !== id);
      if (S.config.settings.activeProfile === id) {
        S.config.settings.activeProfile = S.config.profiles[0].id;
        S.config.settings.activeLayer = 0;
      }
      await saveNow();
      closeModal();
      renderAll();
      showToast("配置已删除", "success");
    }
  }

  // ------------------------------------------------------------------
  // Confirm / profile menu modals
  // ------------------------------------------------------------------

  function confirmHTML() {
    const e = S.editing;
    return `<div class="modal-overlay" data-overlay="true"><div class="modal" style="width:min(440px,100%)">
      <div class="modal-header"><div><div class="modal-title">${e.title}</div></div><button class="btn small ghost icon-only" data-action="close-modal">${ico("x", 16)}</button></div>
      <div class="modal-body"><div style="font-size:13px;line-height:1.7;color:var(--text-secondary)">${e.message}</div></div>
      <div class="modal-footer"><button class="btn" data-action="close-modal">取消</button><button class="btn danger" data-action="confirm-delete" data-confirm-action="${e.confirmAction}" data-id="${e.id}">${ico("trash", 14)} ${e.confirmLabel}</button></div>
    </div></div>`;
  }

  function openProfileMenu() {
    openModal({ kind: "profile-menu" });
  }

  function profileMenuHTML() {
    const rows = S.config.profiles.map((profile) => `<button class="picker-item ${profile.id === S.config.settings.activeProfile ? "selected" : ""}" data-action="set-profile" data-id="${profile.id}">
      <span class="picker-icon" style="color:${profile.color || "#8b5cf6"}">${ico("grid", 16)}</span>
      <span style="min-width:0"><span class="picker-name">${esc(profile.name)}</span><span class="picker-type">${(profile.match || []).join(" · ") || "所有程序"}</span></span>
    </button>`).join("");
    return `<div class="modal-overlay" data-overlay="true"><div class="modal" style="width:min(460px,100%)">
      <div class="modal-header"><div><div class="modal-title">切换配置</div><div class="modal-sub">当前配置会立即生效</div></div><button class="btn small ghost icon-only" data-action="close-modal">${ico("x", 16)}</button></div>
      <div class="modal-body"><div class="picker" style="grid-template-columns:1fr">${rows}</div></div>
      <div class="modal-footer"><button class="btn" data-action="close-modal">取消</button><button class="btn primary" data-action="new-profile">${ico("plus", 14)} 新建配置</button></div>
    </div></div>`;
  }

  // ------------------------------------------------------------------
  // Profile editor
  // ------------------------------------------------------------------

  function openProfileEditor(id) {
    let profile;
    let isNew = false;
    if (id) {
      const original = S.config.profiles.find((p) => p.id === id);
      if (!original) return;
      profile = JSON.parse(JSON.stringify(original));
    } else {
      isNew = true;
      profile = { id: uuid("profile_"), name: "新配置", color: "#8B5CF6", match: [], layers: [{ name: "主层", keys: { "1": { action: null, double: null }, "2": { action: null, double: null }, "3": { action: null, double: null }, "4": { action: null, double: null }, "5": { action: null, double: null }, "6": { action: null, double: null } } }] };
    }
    openModal({ kind: "profile", profile, isNew });
  }

  function profileEditorHTML() {
    const e = S.editing;
    const p = e.profile;
    const layerRows = (p.layers || []).map((layer, i) => `<div class="step-card">
      <div class="step-head"><span class="step-index">${i + 1}</span><span class="step-type">${esc(layer.name)}</span><span class="step-actions">${p.layers.length > 1 ? `<button class="btn small ghost icon-only danger" data-action="remove-layer" data-index="${i}" title="删除图层">${ico("trash", 13)}</button>` : ""}</span></div>
      <div class="step-body"><div class="field" style="margin:0"><label>图层名称</label><input class="input" data-profile-field="layer-name:${i}" value="${esc(layer.name)}"></div></div>
    </div>`).join("");
    const colors = ["#8B5CF6", "#38BDF8", "#34D399", "#FBBF24", "#FB7185", "#F472B6", "#818CF8", "#2DD4BF"];
    return modalShell({
      title: e.isNew ? "新建配置" : "编辑配置",
      sub: "配置可以绑定到前台程序，实现自动切换",
      body: `
        <div class="row">
          <div class="field" style="flex:1.5"><label>配置名称</label><input class="input" data-profile-field="name" value="${esc(p.name)}" placeholder="例如：浏览器、Photoshop"></div>
          <div class="field" style="flex:0 0 auto"><label>颜色</label><div class="icon-picker">${colors.map((c) => `<button class="icon-choice ${p.color === c ? "selected" : ""}" style="color:${c}" data-action="select-profile-color" data-color="${c}">${ico("grid", 15)}</button>`).join("")}</div></div>
        </div>
        <div class="field"><label>匹配程序（可选）</label><input class="input" data-profile-field="match" value="${esc((p.match || []).join(", "))}" placeholder="chrome.exe, msedge.exe"><div class="help">前台程序匹配时自动切换到此配置。多个程序用英文逗号分隔；留空表示不自动切换。</div></div>
        <div class="section-title">图层</div>
        <div id="profile-layers">${layerRows}</div>
        <button class="btn" data-action="add-layer">${ico("plus", 14)} 添加图层</button>
      `,
      footer: `<button class="btn" data-action="close-modal">取消</button><button class="btn primary" data-action="save-profile">${ico("check", 15)} 保存配置</button>`,
    });
  }

  function addProfileLayer() {
    if (S.editing?.kind !== "profile") return;
    const p = S.editing.profile;
    p.layers = p.layers || [];
    const keys = {};
    for (let i = 1; i <= 6; i++) keys[String(i)] = { action: null, double: null };
    p.layers.push({ name: `第 ${p.layers.length + 1} 层`, keys });
    renderModal();
  }

  function removeProfileLayer(index) {
    if (S.editing?.kind !== "profile") return;
    const p = S.editing.profile;
    if (p.layers.length <= 1) return;
    p.layers.splice(index, 1);
    renderModal();
  }

  async function saveProfileEditor() {
    const e = S.editing;
    if (!e?.profile) return;
    const p = e.profile;
    if (!p.name.trim()) p.name = "未命名配置";
    if (e.isNew) S.config.profiles.push(p);
    else {
      const i = S.config.profiles.findIndex((x) => x.id === p.id);
      if (i >= 0) S.config.profiles[i] = p;
    }
    await saveNow();
    closeModal();
    renderAll();
    showToast(e.isNew ? "配置已创建" : "配置已保存", "success");
  }

  // color picker in profile editor
  document.addEventListener("click", (e) => {
    const el = e.target.closest('[data-action="select-profile-color"]');
    if (!el) return;
    if (S.editing?.kind === "profile") {
      S.editing.profile.color = el.dataset.color;
      renderModal();
    }
  });

  function duplicateProfile(id) {
    const original = S.config.profiles.find((p) => p.id === id);
    if (!original) return;
    const copy = JSON.parse(JSON.stringify(original));
    copy.id = uuid("profile_");
    copy.name = original.name + " 副本";
    S.config.profiles.push(copy);
    saveNow();
    renderView();
    showToast("配置已复制", "success");
  }

  // ------------------------------------------------------------------
  // Combo recorder
  // ------------------------------------------------------------------

  function startComboRecorder(selector) {
    const input = document.querySelector(selector);
    if (!input) return;
    S.recording = true;
    const overlay = document.createElement("div");
    overlay.className = "record-overlay";
    overlay.innerHTML = `<div class="record-box"><div class="record-title">请按下组合键</div><div class="record-preview" id="record-preview">等待按键…</div><div class="record-help">按 Esc 取消 · 修饰键可以按住</div></div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", () => cleanup());

    const modifiers = [];
    let preview = [];
    const keyNameFromEvent = (event) => {
      const code = event.code || "";
      if (/^Key[A-Z]$/.test(code)) return code.slice(3);
      if (/^Digit[0-9]$/.test(code)) return code.slice(5);
      if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) return code;
      if (/^Numpad[0-9]$/.test(code)) return code;
      const map = {
        Escape: "Esc", Enter: "Enter", Space: "Space", Tab: "Tab", Backspace: "Backspace",
        Delete: "Delete", Insert: "Insert", Home: "Home", End: "End", PageUp: "PageUp", PageDown: "PageDown",
        ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right",
        Semicolon: "Semicolon", Equal: "Equals", Comma: "Comma", Minus: "Minus", Period: "Period",
        Slash: "Slash", Backquote: "Backtick", BracketLeft: "LeftBracket", Backslash: "Backslash",
        BracketRight: "RightBracket", Quote: "Quote", CapsLock: "CapsLock", NumLock: "NumLock",
        PrintScreen: "PrintScreen", Pause: "Pause",
      };
      return map[code] || event.key;
    };
    const updatePreview = () => {
      const el = document.getElementById("record-preview");
      if (el) el.textContent = preview.length ? preview.join("  +  ") : "等待按键…";
    };
    const handler = (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape") {
        cleanup();
        return;
      }
      const mods = [];
      if (event.ctrlKey) mods.push("Ctrl");
      if (event.shiftKey) mods.push("Shift");
      if (event.altKey) mods.push("Alt");
      if (event.metaKey) mods.push("Win");
      const key = keyNameFromEvent(event);
      if (["Control", "Shift", "Alt", "Meta", "LCtrl", "RCtrl", "LShift", "RShift", "LAlt", "RAlt", "LWin", "RWin"].includes(key)) {
        preview = [...mods];
        if (!preview.length) preview = [key];
        updatePreview();
        return;
      }
      const combo = [...mods, key];
      input.value = combo.join(" + ");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      cleanup();
    };
    const cleanup = () => {
      S.recording = false;
      window.removeEventListener("keydown", handler, true);
      overlay.remove();
    };
    window.addEventListener("keydown", handler, true);
  }

  // ------------------------------------------------------------------
  // File dialogs
  // ------------------------------------------------------------------

  async function browsePath(kind, selector) {
    const res = await apiCall("choose_path", kind);
    if (res?.ok && res.path) {
      const input = document.querySelector(selector);
      if (input) {
        input.value = res.path;
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }
  }

  // ------------------------------------------------------------------
  // Import / export
  // ------------------------------------------------------------------

  async function exportConfig() {
    const res = await apiCall("export_config");
    if (res?.ok) showToast("配置已导出", "success");
    else if (res?.error) showToast(res.error, "error");
  }

  async function importConfig() {
    const res = await apiCall("import_config");
    if (res?.ok && res.config) {
      S.config = res.config;
      renderAll();
      showToast("配置已导入", "success");
    } else if (res?.error) showToast(res.error, "error");
  }

  // ------------------------------------------------------------------
  // Toasts
  // ------------------------------------------------------------------

  function showToast(message, kind = "info") {
    const root = $("#toast-root");
    if (!root) return;
    while (root.children.length >= 4) root.firstElementChild.remove();
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    const iconName = kind === "success" ? "check" : kind === "error" ? "x" : kind === "warning" ? "info" : "info";
    el.innerHTML = `${ico(iconName, 17)}<span>${esc(message)}</span>`;
    root.appendChild(el);
    setTimeout(() => {
      el.classList.add("leaving");
      setTimeout(() => el.remove(), 220);
    }, 2800);
  }

  // ------------------------------------------------------------------
  // Start
  // ------------------------------------------------------------------

  boot();
})();
