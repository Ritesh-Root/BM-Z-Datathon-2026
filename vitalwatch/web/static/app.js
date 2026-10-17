/* VitalWatch ward dashboard. Vanilla JS, Server-Sent Events, inline SVG. No emoji. */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const S = {
    beds: new Map(), alerts: new Map(), notes: new Map(), policy: null, simH: 0,
    selected: null, showGT: false, speed: 1, paused: false, detail: null, snooze: 4, env: null, dataNote: "",
  };

  // ------------------------------------------------------------------ token + storage
  const store = {
    get(k) { try { return window.sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { window.sessionStorage.setItem(k, v); } catch (e) { /* private mode */ } },
    lget(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } },
    lset(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
  };
  const urlToken = new URLSearchParams(location.search).get("token");
  if (urlToken) store.set("vw-token", urlToken);
  const token = () => store.get("vw-token") || "";

  async function post(url, body) {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-VW-Token": token() }, body: JSON.stringify(body) });
    if (r.status === 401) { $("#token-dialog").hidden = false; throw new Error("token"); }
    return r.json();
  }
  $("#token-save").addEventListener("click", () => { store.set("vw-token", $("#token-input").value.trim()); $("#token-dialog").hidden = true; });

  // ------------------------------------------------------------------ formatting
  const pct = (p) => (p == null ? "--" : p * 100 < 1 ? "<1%" : (p * 100 < 10 ? (p * 100).toFixed(1) : (p * 100).toFixed(0)) + "%");
  const STATE = {
    QUIET: ["Stable", "i-checkmark--outline"], WATCH: ["Rising", "i-warning--alt"], ALERT: ["Alert", "i-warning--filled"],
    ESCALATED: ["Escalated", "i-alarm"], ACKED: ["Snoozed", "i-checkmark--filled"],
  };
  const TRIGGER = { sustained: "stayed above threshold", threshold: "crossed threshold", rise: "rose sharply",
    breakthrough: "kept rising after acknowledgement", re_alert: "still high after snooze" };
  function stateTag(b) {
    const [label, icon] = STATE[b.state] || STATE.QUIET;
    const extra = b.state === "ACKED" && b.snooze_left != null ? ` ${b.snooze_left} h` : "";
    return `<span class="state-tag s-${b.state}"><span class="i ${icon}" aria-hidden="true"></span>${label}${extra}</span>`;
  }

  // ------------------------------------------------------------------ sparkline
  function yMax() {
    let m = S.policy ? S.policy.theta_on * 2.5 : 0.2;
    for (const b of S.beds.values()) for (const v of b.spark || []) if (v > m) m = v;
    return Math.min(1, m * 1.1);
  }
  function spark(values, ymax) {
    const W = 200, H = 38, n = values.length;
    if (!n) return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"></svg>`;
    const x = (i) => (n === 1 ? W : (i / 47) * W - ((n - 1) / 47) * W + W);
    const y = (v) => H - 2 - (v / ymax) * (H - 4);
    const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const th = S.policy ? y(S.policy.theta_on).toFixed(1) : null;
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
      ${th ? `<line x1="0" x2="${W}" y1="${th}" y2="${th}" stroke="var(--threshold)" stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke" opacity=".7"/>` : ""}
      <polyline points="${pts}" fill="none" stroke="var(--spark)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    </svg>`;
  }

  // ------------------------------------------------------------------ ward grid
  function tileHTML(b, ymax) {
    const v = b.vitals || {};
    const vit = ["HR", "MAP", "RR", "SpO2", "T"].filter((k) => v[k] != null).map((k) => `<span>${k} <b>${esc(v[k])}</b></span>`).join("");
    const gt = S.showGT && b.gt_onset_in_h != null
      ? `<div class="gt">${b.gt_onset_in_h >= 0 ? `labelled onset in ${b.gt_onset_in_h.toFixed(0)} h` : `labelled onset ${(-b.gt_onset_in_h).toFixed(0)} h ago`}</div>` : "";
    return `<div class="tile-top"><span class="i i-hospital-bed" aria-hidden="true"></span><span class="bed">Bed ${b.bed}</span>
        <span class="pid">${esc(b.pid)}</span></div>
      <div class="tile-mid"><div class="risk">${pct(b.risk)}<small>risk</small></div>${stateTag(b)}</div>
      ${spark(b.spark || [], ymax)}
      <div class="vitals">${vit}</div>${gt}`;
  }
  function renderWard() {
    const ward = $("#ward");
    const ymax = yMax();
    const seen = new Set();
    [...S.beds.values()].sort((a, b) => a.bed - b.bed).forEach((b) => {
      seen.add(String(b.bed));
      let t = ward.querySelector(`[data-bed="${b.bed}"]`);
      if (!t) {
        t = el("button", "tile");
        t.dataset.bed = b.bed;
        t.addEventListener("click", () => openBed(b.bed));
        ward.appendChild(t);
      }
      t.className = `tile s-${b.state}${S.selected === b.bed ? " selected" : ""}`;
      t.setAttribute("aria-label", `Bed ${b.bed}, risk ${pct(b.risk)}, ${(STATE[b.state] || STATE.QUIET)[0]}`);
      t.innerHTML = tileHTML(b, ymax);
    });
    ward.querySelectorAll(".tile").forEach((t) => { if (!seen.has(t.dataset.bed)) t.remove(); });
  }

  // ------------------------------------------------------------------ alert strip
  function renderAlerts() {
    const strip = $("#alert-strip");
    const active = [...S.alerts.values()].sort((a, b) => b.sim_h - a.sim_h);
    if (!active.length) {
      strip.innerHTML = `<div class="quiet-strip"><span class="i i-checkmark--filled" aria-hidden="true"></span>No unacknowledged alerts</div>`;
      return;
    }
    strip.innerHTML = "";
    active.forEach((a) => {
      const c = el("div", `alert-card${a.escalated ? " escalated" : ""}`);
      c.innerHTML = `<span class="i ${a.escalated ? "i-alarm" : "i-warning--filled"}" aria-hidden="true"></span>
        <div><div class="t">Bed ${a.bed} &middot; risk ${pct(a.risk)}${a.escalated ? " &middot; escalated" : ""}</div>
        <div class="s">${esc(TRIGGER[a.trigger] || a.trigger)} &middot; ${esc(a.alert_id)} ${a.latency_ms != null ? " &middot; raised in " + a.latency_ms.toFixed(1) + " ms" : ""}</div></div>`;
      const btn = el("button", null, "Open");
      btn.addEventListener("click", () => openBed(a.bed));
      c.appendChild(btn);
      strip.appendChild(c);
    });
  }

  // ------------------------------------------------------------------ drawer
  async function openBed(bed) {
    S.selected = bed;
    $("#drawer").hidden = false;
    $("#ack-result").textContent = "";
    renderWard();
    await refreshDetail();
  }
  $("#d-close").addEventListener("click", () => { S.selected = null; $("#drawer").hidden = true; renderWard(); });

  async function refreshDetail() {
    if (S.selected == null) return;
    try {
      const r = await fetch(`/api/bed/${S.selected}`);
      S.detail = await r.json();
    } catch (e) { return; }
    renderDrawer();
  }

  function trendSVG(d) {
    const W = 420, H = 170, L = 36, R = 8, T = 8, B = 22;
    const hist = d.hist || [];
    if (!hist.length) return "";
    const now = S.simH - 1;
    const ymax = Math.min(1, Math.max(d.policy.theta_on * 2.5, ...hist.map((h) => h[1])) * 1.1);
    const x = (h) => L + ((h - (now - 47)) / 47) * (W - L - R);
    const y = (v) => T + (1 - v / ymax) * (H - T - B);
    const ticks = [0, ymax / 2, ymax].map((v) => `<g><line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--border)" stroke-width="1"/>
      <text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" font-size="10" fill="var(--text-2)">${(v * 100).toFixed(0)}%</text></g>`).join("");
    const xt = [-48, -36, -24, -12, 0].map((o) => `<text x="${x(now + o)}" y="${H - 6}" text-anchor="middle" font-size="10" fill="var(--text-2)">${o === 0 ? "now" : o + " h"}</text>`).join("");
    const pts = hist.map((h) => `${x(h[0]).toFixed(1)},${y(h[1]).toFixed(1)}`).join(" ");
    const area = `${x(hist[0][0]).toFixed(1)},${y(0)} ${pts} ${x(hist[hist.length - 1][0]).toFixed(1)},${y(0)}`;
    const marks = (d.markers || []).filter((m) => m[0] >= now - 47).map((m) => {
      const v = (hist.find((h) => h[0] === m[0]) || [0, 0])[1];
      const color = m[1] === "ack" ? "var(--blue)" : m[1] === "escalation" ? "var(--purple)" : m[1] === "resolve" ? "var(--text-3)" : "var(--red)";
      return `<circle cx="${x(m[0])}" cy="${y(v)}" r="5" fill="${color}" stroke="var(--layer)" stroke-width="2"><title>${esc(m[1])} at ward hour ${m[0]}</title></circle>`;
    }).join("");
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Risk trend for the last 48 hours">
      ${ticks}${xt}
      <line x1="${L}" x2="${W - R}" y1="${y(d.policy.theta_on)}" y2="${y(d.policy.theta_on)}" stroke="var(--threshold)" stroke-dasharray="4 3" stroke-width="1"/>
      <polygon points="${area}" fill="var(--spark)" opacity=".1"/>
      <polyline points="${pts}" fill="none" stroke="var(--spark)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      ${marks}
      <line class="xhair" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--text-3)" stroke-width="1" visibility="hidden"/>
      <rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent" class="hit"/>
    </svg><div class="tooltip" hidden></div>`;
  }
  function wireTrendHover(d) {
    const wrap = $("#d-trend"), svg = wrap.querySelector("svg"), tip = wrap.querySelector(".tooltip");
    if (!svg) return;
    const hit = svg.querySelector(".hit"), xh = svg.querySelector(".xhair");
    const hist = d.hist || [];
    const now = S.simH - 1, L = 36, R = 8, W = 420;
    hit.addEventListener("mousemove", (ev) => {
      const box = svg.getBoundingClientRect();
      const px = ((ev.clientX - box.left) / box.width) * W;
      const h = Math.round(now - 47 + ((px - L) / (W - L - R)) * 47);
      const pt = hist.reduce((best, p) => (Math.abs(p[0] - h) < Math.abs(best[0] - h) ? p : best), hist[0]);
      const sx = L + ((pt[0] - (now - 47)) / 47) * (W - L - R);
      xh.setAttribute("x1", sx); xh.setAttribute("x2", sx); xh.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.style.left = `${(sx / W) * box.width}px`;
      tip.style.top = `10px`;
      tip.textContent = `${pct(pt[1])} risk at ${now - pt[0] === 0 ? "now" : (now - pt[0]) + " h ago"}`;
    });
    hit.addEventListener("mouseleave", () => { xh.setAttribute("visibility", "hidden"); tip.hidden = true; });
  }

  function renderDrawer() {
    const d = S.detail;
    if (!d || d.error) { $("#d-title").textContent = "Empty bed"; return; }
    const bedState = S.beds.get(d.bed) || d;
    $("#d-title").textContent = `Bed ${d.bed}`;
    $("#d-sub").textContent = `${d.pid} · ${d.age} · ${d.unit} · ICU hour ${d.hour}`;
    $("#d-risk").textContent = pct(bedState.risk);
    $("#d-state").outerHTML = `<div class="state-tag-wrap" id="d-state">${stateTag(bedState)}</div>`;
    $("#d-trend").innerHTML = trendSVG(d);
    wireTrendHover(d);

    const activeAlert = d.alert && ["ALERT", "ESCALATED", "ACKED"].includes(bedState.state) ? d.alert : null;
    const drivers = activeAlert ? activeAlert.drivers : d.drivers_now || [];
    const maxL = Math.max(0.01, ...drivers.map((x) => x.logit));
    $("#d-drivers").innerHTML = drivers.length ? drivers.map((x) => `<li><span class="d-label">${esc(x.label)}</span>
        <span class="bar" aria-hidden="true"><span style="width:${Math.max(4, (x.logit / maxL) * 100).toFixed(0)}%"></span></span>
        <span class="d-text">${esc(x.text)}</span></li>`).join("")
      : `<li class="d-text">No signal is pushing the risk up right now.</li>`;

    renderNote(activeAlert);
    const canAck = ["ALERT", "ESCALATED"].includes(bedState.state);
    $("#ack-btn").disabled = !canAck;
    $("#ack-btn").textContent = canAck ? `Acknowledge ${bedState.alert_id}` : "No active alert on this bed";
  }

  function renderNote(alert) {
    const meta = $("#d-note-meta"), box = $("#d-note");
    if (!alert) { meta.innerHTML = ""; box.textContent = "A handoff note is drafted when VitalWatch raises an alert."; box.classList.remove("cursor"); return; }
    const n = S.notes.get(alert.alert_id) || { source: alert.note.source, text: alert.note.text, gen_s: alert.note.gen_s };
    if (n.streaming) {
      meta.innerHTML = `<span class="i i-ibm-granite" aria-hidden="true"></span>Drafting with IBM Granite, running locally on this machine`;
      box.textContent = n.draft || "";
      box.classList.add("cursor");
      return;
    }
    box.classList.remove("cursor");
    if (n.source === "granite") {
      meta.innerHTML = `<span class="i i-checkmark--filled" aria-hidden="true"></span>IBM Granite (local) &middot; checked against the facts &middot; ${n.gen_s != null ? n.gen_s + " s" : ""}`;
    } else if (n.rejected) {
      meta.innerHTML = `<span class="i i-information" aria-hidden="true"></span>Model draft rejected (${esc(n.rejected)}); template note kept`;
    } else {
      meta.innerHTML = `<span class="i i-information" aria-hidden="true"></span>Template note (instant)${n.pending ? " &middot; Granite draft queued" : ""}`;
    }
    box.textContent = n.text || "";
  }

  document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".seg-btn").forEach((x) => { x.classList.remove("active"); x.setAttribute("aria-checked", "false"); });
    b.classList.add("active"); b.setAttribute("aria-checked", "true"); S.snooze = Number(b.dataset.snooze);
  }));
  $("#ack-btn").addEventListener("click", async () => {
    const b = S.beds.get(S.selected);
    if (!b || !b.alert_id) return;
    try {
      const r = await post("/api/ack", { alert_id: b.alert_id, user: $("#ack-user").value, reason: $("#ack-reason").value, snooze_h: S.snooze });
      $("#ack-result").innerHTML = r.ok
        ? `<span class="i i-checkmark--filled" aria-hidden="true"></span>Logged as audit record #${r.audit_seq} (chain ${esc(r.audit_head.slice(0, 12))})`
        : esc(r.error || "Could not acknowledge");
    } catch (e) { /* token dialog shown */ }
  });

  // ------------------------------------------------------------------ header + footer
  function renderChips(env, metrics) {
    if (env) {
      const acc = env.accelerator || {};
      const onZ = acc.arch === "s390x";
      const p = $("#chip-platform");
      p.className = `chip${onZ ? " accent" : ""}`;
      p.lastElementChild.textContent = onZ ? `IBM LinuxONE s390x${acc.machine_name ? " · " + acc.machine_name.split(" (")[0] : ""}` : `${acc.arch} dev host`;
    }
    if (metrics) {
      const s = $("#chip-scorer");
      const nnpa = metrics.scorer.device === "nnpa";
      s.className = `chip${nnpa ? " accent" : ""}`;
      s.lastElementChild.textContent = nnpa ? "Telum AI accelerator (Snap ML)" : metrics.scorer.detail.replace(/ \(CPU.*\)/, " on CPU");
    }
    const dchip = $("#chip-data");
    dchip.className = `chip${/SYNTHETIC/.test(S.dataNote) ? " warn" : ""}`;
    dchip.lastElementChild.textContent = /SYNTHETIC/.test(S.dataNote) ? "Synthetic patients" : (S.dataNote ? "PhysioNet 2019 test patients" : "--");
    dchip.title = S.dataNote;
  }
  function renderMetrics(m) {
    const lat = m.latency_ms || {};
    $("#m-score").textContent = lat.score ? `${lat.score.p50.toFixed(2)} ms for ${m.beds} beds` : "--";
    $("#m-e2e").textContent = lat.alert_e2e ? `${lat.alert_e2e.p99.toFixed(1)} ms` : "--";
    $("#m-beds").textContent = m.beds;
    $("#m-alerts").textContent = m.alerts_fired;
    $("#m-shadow").textContent = m.plain_threshold_alarms;
    const llm = m.llm || {};
    $("#m-llm").textContent = llm.backend === "granite"
      ? `IBM Granite local${llm.last_tok_s ? " · " + llm.last_tok_s + " tok/s" : ""} · queue ${llm.queue}` : "template (no local model found)";
    $("#m-seq").textContent = m.audit.seq;
    $("#m-head").textContent = m.audit.head;
    S.paused = m.paused; S.speed = m.speed;
    renderControls();
    renderChips(null, m);
  }
  function renderControls() {
    $("#btn-pause").innerHTML = `<span class="i ${S.paused ? "i-play" : "i-pause"}" aria-hidden="true"></span>`;
    $("#btn-pause").setAttribute("aria-label", S.paused ? "Resume replay" : "Pause replay");
    document.querySelectorAll(".speed").forEach((b) => b.classList.toggle("active", Number(b.dataset.speed) === S.speed));
  }
  $("#btn-pause").addEventListener("click", () => post("/api/control", { action: S.paused ? "resume" : "pause" }).catch(() => {}));
  document.querySelectorAll(".speed").forEach((b) => b.addEventListener("click", () => post("/api/control", { action: "speed", value: Number(b.dataset.speed) }).catch(() => {})));
  $("#gt-toggle").addEventListener("change", (e) => { S.showGT = e.target.checked; renderWard(); });
  $("#btn-verify").addEventListener("click", async () => {
    const r = await (await fetch("/api/audit/verify")).json();
    $("#verify-result").innerHTML = r.ok
      ? `<span class="ok-text"><span class="i i-checkmark--filled" aria-hidden="true"></span>${r.records} records intact</span>`
      : `<span class="bad-text"><span class="i i-warning--filled" aria-hidden="true"></span>Broken at #${r.first_bad_seq}: ${esc(r.reason)}</span>`;
  });
  const savedTheme = store.lget("vw-theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  $("#btn-theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    store.lset("vw-theme", document.documentElement.dataset.theme);
  });

  // ------------------------------------------------------------------ data flow
  function applyTick(d) {
    S.simH = d.sim_h + 1;
    $("#clock").textContent = `Ward hour ${d.sim_h}`;
    d.beds.forEach((b) => S.beds.set(b.bed, b));
    renderWard();
    if (S.selected != null) refreshDetail();
  }
  function handlers() {
    return {
      tick: applyTick,
      metrics: renderMetrics,
      control: (d) => { S.paused = d.paused; S.speed = d.speed; renderControls(); },
      alert: (d) => {
        S.alerts.set(d.alert_id, { ...d, escalated: false });
        S.notes.set(d.alert_id, { source: "template", text: d.note.text, pending: d.llm_pending });
        renderAlerts();
        if (S.selected === d.bed) refreshDetail();
      },
      note_start: (d) => { const n = S.notes.get(d.alert_id) || {}; S.notes.set(d.alert_id, { ...n, streaming: true, draft: "" }); maybeNote(d.alert_id); },
      note_delta: (d) => { const n = S.notes.get(d.alert_id); if (n) { n.draft = (n.draft || "") + d.delta; maybeNote(d.alert_id); } },
      note_ready: (d) => {
        const n = S.notes.get(d.alert_id) || {};
        if (d.valid) S.notes.set(d.alert_id, { source: d.source, text: d.text, gen_s: d.gen_s });
        else S.notes.set(d.alert_id, { ...n, streaming: false, pending: false, rejected: d.reason });
        maybeNote(d.alert_id);
      },
      ack: (d) => { S.alerts.delete(d.alert_id); renderAlerts(); if (S.selected === d.bed) refreshDetail(); },
      escalation: (d) => { const a = S.alerts.get(d.alert_id); if (a) { a.escalated = true; renderAlerts(); } },
      resolve: (d) => { S.alerts.delete(d.alert_id); renderAlerts(); },
    };
  }
  function maybeNote(aid) {
    const d = S.detail;
    if (d && d.alert && d.alert.alert_id === aid) renderNote(d.alert);
  }

  async function loadState() {
    const s = await (await fetch("/api/state")).json();
    S.policy = s.policy; S.simH = s.sim_h; S.env = s.env; S.dataNote = s.data_note;
    s.beds.forEach((b) => {
      S.beds.set(b.bed, b);
      if (b.alert && ["ALERT", "ESCALATED"].includes(b.state)) {
        S.alerts.set(b.alert.alert_id, { ...b.alert, bed: b.bed, escalated: b.state === "ESCALATED" });
      }
    });
    $("#clock").textContent = `Ward hour ${s.sim_h - 1}`;
    renderChips(s.env, s.metrics);
    renderMetrics(s.metrics);
    renderWard();
    renderAlerts();
  }

  let failures = 0, poller = null;
  function connect() {
    const es = new EventSource("/stream");
    const h = handlers();
    Object.keys(h).forEach((k) => es.addEventListener(k, (ev) => { failures = 0; try { h[k](JSON.parse(ev.data)); } catch (e) { console.error(k, e); } }));
    es.onerror = () => {
      failures += 1;
      if (failures >= 3 && !poller) {
        es.close();
        poller = setInterval(() => loadState().catch(() => {}), 2000);
      }
    };
  }

  loadState().then(connect).catch((e) => { console.error(e); connect(); });
})();
