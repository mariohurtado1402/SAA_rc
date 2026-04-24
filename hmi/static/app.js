(() => {
  const $ = (id) => document.getElementById(id);

  // ------------- WebSocket telemetry -------------
  let ws;
  let userEditing = new Set();      // inputs the user is currently typing in
  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws/state`);
    ws.onmessage = (ev) => render(JSON.parse(ev.data));
    ws.onclose = () => setTimeout(connect, 1000);
  }
  connect();

  // ------------- Render telemetry -------------
  function render(s) {
    // mode
    document.querySelectorAll(".mode").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === s.mode);
    });

    // lights
    $("ldr-value").textContent = s.ldr.value;
    $("headlight-label").textContent = s.ldr.headlight_on ? "ON" : "OFF";
    $("ldr-dot").classList.toggle("on", s.ldr.headlight_on);
    setIfIdle("ldr-on", s.ldr.on_threshold);
    setIfIdle("ldr-off", s.ldr.off_threshold);

    // thrust + steering
    $("thr-pct").textContent = s.command.throttle_pct.toFixed(0);
    $("thr-us").textContent = s.applied.esc_us;
    $("str-deg").textContent = s.applied.servo_deg;
    setSliderIfIdle("throttle", s.command.throttle_pct);
    setSliderIfIdle("steer", s.command.steer_deg);

    // camera + LKA
    $("lane-bias").textContent = s.lane.bias === null ? "—" : s.lane.bias.toFixed(2);
    $("lane-diff").textContent = s.lane.diff === null ? "—" : s.lane.diff;
    $("lane-action").textContent = s.lane.action;
    setIfIdle("lka-gain", s.lane.gain_deg);

    // proximity
    for (const k of ["front", "rear_left", "rear_right"]) {
      const v = s.distances[k];
      const d = $(`d-${k}`);
      const bar = $(`bar-${k}`);
      if (d) d.textContent = v ? `${v.toFixed(1)} cm` : "—";
      if (bar) bar.value = Math.min(200, Math.max(0, v || 0));
    }
    setIfIdle("rcca-th", s.rcca_threshold_cm);
    $("rcca-flag").classList.toggle("hidden", !s.applied.rcca_brake);

    // calibration
    for (const k of [
      "forward_min_us", "forward_max_us", "forward_kick_us", "forward_kick_ms",
      "reverse_min_us", "reverse_max_us", "reverse_kick_us", "reverse_kick_ms",
    ]) setIfIdle(k, s.calibration[k]);

    // disable controls for absent subsystems
    document.body.classList.toggle("no-camera", !s.availability.camera);
  }

  function setIfIdle(id, value) {
    if (userEditing.has(id)) return;
    const el = $(id);
    if (!el) return;
    if (document.activeElement === el) return;
    if (el.value === String(value)) return;
    el.value = value;
  }
  function setSliderIfIdle(id, value) {
    if (userEditing.has(id)) return;
    const el = $(id);
    if (!el || document.activeElement === el) return;
    if (Number(el.value) === Number(value)) return;
    el.value = value;
  }
  document.addEventListener("focusin", (e) => {
    if (e.target.id) userEditing.add(e.target.id);
  });
  document.addEventListener("focusout", (e) => {
    userEditing.delete(e.target.id);
  });

  // ------------- Commands -------------
  async function postJSON(url, data) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  }

  document.querySelectorAll(".mode").forEach((b) => {
    b.onclick = () => postJSON("/api/mode", { mode: b.dataset.mode });
  });
  $("stop").onclick = () => postJSON("/api/stop", {});

  let cmdThrottle = 0, cmdSteer = 100;
  function pushCommand() {
    postJSON("/api/command", { throttle_pct: cmdThrottle, steer_deg: cmdSteer });
  }
  $("throttle").addEventListener("input", (e) => {
    cmdThrottle = Number(e.target.value); pushCommand();
  });
  $("steer").addEventListener("input", (e) => {
    cmdSteer = Number(e.target.value); pushCommand();
  });

  // Threshold + gain sliders persist via /api/thresholds on change.
  function pushThresholds() {
    postJSON("/api/thresholds", {
      ldr_on_threshold: Number($("ldr-on").value),
      ldr_off_threshold: Number($("ldr-off").value),
      rcca_threshold_cm: Number($("rcca-th").value),
      lka_gain_deg: Number($("lka-gain").value),
    });
  }
  ["ldr-on", "ldr-off", "rcca-th", "lka-gain"].forEach((id) =>
    $(id).addEventListener("change", pushThresholds));

  // Calibration save
  $("save-cal").onclick = () => {
    const cal = {};
    ["forward_min_us", "forward_max_us", "forward_kick_us", "forward_kick_ms",
     "reverse_min_us", "reverse_max_us", "reverse_kick_us", "reverse_kick_ms"]
      .forEach((k) => { cal[k] = Number($(k).value); });
    postJSON("/api/calibration", cal);
  };

  // ------------- Keybindings -------------
  const STEP_THR = 5, STEP_STR = 5;
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    let changed = false;
    if (k === "w") { cmdThrottle = clamp(cmdThrottle + STEP_THR, -100, 100); changed = true; }
    else if (k === "s") { cmdThrottle = clamp(cmdThrottle - STEP_THR, -100, 100); changed = true; }
    else if (k === "a") { cmdSteer = clamp(cmdSteer - STEP_STR, 60, 140); changed = true; }
    else if (k === "d") { cmdSteer = clamp(cmdSteer + STEP_STR, 60, 140); changed = true; }
    else if (k === " ") { cmdThrottle = 0; cmdSteer = 100; changed = true; e.preventDefault(); }
    if (changed) {
      $("throttle").value = cmdThrottle;
      $("steer").value = cmdSteer;
      pushCommand();
    }
  });
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
})();
