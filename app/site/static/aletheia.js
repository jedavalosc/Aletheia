/* Aletheia News — progressive enhancement. Pages read fully without JS. */
(function () {
  "use strict";
  var doc = document.documentElement;
  doc.classList.add("js");
  var L = window.ALETHEIA || {};
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  // --- Pure Factual Mode (a per-reader convenience; never sent anywhere except as a chat flag)
  function setFactual(on) {
    doc.classList.toggle("factual", on);
    document.querySelectorAll("[data-factual-toggle]").forEach(function (b) { b.setAttribute("aria-pressed", on ? "true" : "false"); });
    store("aletheia-factual", on ? "1" : "0");
  }
  document.querySelectorAll("[data-factual-toggle]").forEach(function (b) {
    b.addEventListener("click", function () { setFactual(!doc.classList.contains("factual")); });
  });
  setFactual(store("aletheia-factual") === "1");
  document.querySelectorAll("[data-leave-factual]").forEach(function (a) {
    a.addEventListener("click", function () { setFactual(false); });
  });

  // --- Sentence -> sources
  document.querySelectorAll("details.src").forEach(function (d) { d.open = false; });
  document.querySelectorAll(".sent").forEach(function (s) {
    function go(ev) {
      if (ev.type === "keydown" && ev.key !== "Enter" && ev.key !== " ") return;
      ev.preventDefault();
      var det = document.getElementById(s.getAttribute("aria-controls"));
      var open = s.getAttribute("aria-expanded") === "true";
      document.querySelectorAll(".sent[aria-expanded=true]").forEach(function (x) { x.setAttribute("aria-expanded", "false"); });
      det.querySelectorAll(".claim").forEach(function (c) { c.classList.remove("hit"); });
      if (open) { det.open = false; return; }
      s.setAttribute("aria-expanded", "true");
      det.open = true;
      var first = null;
      (s.dataset.claims || "").split(" ").forEach(function (id) {
        var c = det.querySelector('[data-claim="' + id + '"]');
        if (c) { c.classList.add("hit"); first = first || c; }
      });
      if (first) first.scrollIntoView({ block: "nearest" });
    }
    s.addEventListener("click", go); s.addEventListener("keydown", go);
  });

  // --- Axis switch (triptych + coverage) and measure switch
  function show(group, attr, value) {
    document.querySelectorAll("[data-" + group + "]").forEach(function (el) { el.hidden = el.getAttribute("data-" + group) !== value; });
  }
  var state = { axis: null, measure: "medios" };
  function applyCoverage() {
    document.querySelectorAll("figure[data-variants]").forEach(function (f) {
      f.querySelectorAll(".variant").forEach(function (v) {
        v.hidden = !(v.dataset.axis === state.axis && v.dataset.measure === state.measure);
      });
    });
  }
  document.querySelectorAll("[data-axis-btn]").forEach(function (b) {
    if (b.getAttribute("aria-pressed") === "true") state.axis = b.dataset.axisBtn;
    b.addEventListener("click", function () {
      state.axis = b.dataset.axisBtn;
      document.querySelectorAll("[data-axis-btn]").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      show("axis-view", "axis-view", state.axis); applyCoverage();
    });
  });
  document.querySelectorAll("[data-measure-btn]").forEach(function (b) {
    b.addEventListener("click", function () {
      state.measure = b.dataset.measureBtn;
      document.querySelectorAll("[data-measure-btn]").forEach(function (x) { x.setAttribute("aria-pressed", x.dataset.measureBtn === state.measure ? "true" : "false"); });
      applyCoverage();
    });
  });

  // --- Mobile tabs for the triptych (chronicle open by default)
  document.querySelectorAll(".tabs").forEach(function (tabs) {
    var root = tabs.nextElementSibling;
    tabs.querySelectorAll("[role=tab]").forEach(function (t) {
      t.addEventListener("click", function () {
        tabs.querySelectorAll("[role=tab]").forEach(function (x) { x.setAttribute("aria-selected", x === t ? "true" : "false"); });
        root.querySelectorAll("[data-pane]").forEach(function (p) { p.classList.toggle("active", p.dataset.pane === t.dataset.pane); });
      });
    });
  });

  // --- Chat
  var openBtn = document.getElementById("chat-open"), panel = document.getElementById("chat");
  if (!openBtn || !panel) return;
  var log = panel.querySelector(".log"), form = panel.querySelector("form"), ta = panel.querySelector("textarea");
  var sessionId = null, claims = null;
  function loadClaims() {
    if (claims) return Promise.resolve(claims);
    return fetch(L.claimsUrl).then(function (r) { return r.json(); }).then(function (j) { claims = j; return j; }).catch(function () { claims = {}; return claims; });
  }
  openBtn.addEventListener("click", function () { panel.hidden = false; openBtn.hidden = true; ta.focus(); });
  panel.querySelector("[data-close]").addEventListener("click", function () { panel.hidden = true; openBtn.hidden = false; openBtn.focus(); });
  panel.addEventListener("keydown", function (e) { if (e.key === "Escape") panel.querySelector("[data-close]").click(); });
  ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  function renderSegment(box, seg) {
    var lbl = L.segLabels[seg.tipo];
    if (lbl) box.appendChild(el("span", "seg-lbl", lbl + (seg.meta ? " · " + seg.meta : "")));
    var p = el("p", null, seg.texto);
    p.style.margin = "2px 0 6px";
    (seg.claim_ids || []).forEach(function (cid) {
      var b = el("button", "cite", cid); b.type = "button"; b.setAttribute("aria-expanded", "false");
      b.addEventListener("click", function () {
        var nxt = b.nextSibling;
        if (nxt && nxt.classList && nxt.classList.contains("cite-body")) { nxt.remove(); b.setAttribute("aria-expanded", "false"); return; }
        loadClaims().then(function (c) {
          var info = c[cid]; var body = el("span", "cite-body");
          if (info) {
            body.appendChild(el("span", null, info.texto + " "));
            var a = el("a", null, info.evento); a.href = info.url + "#" + cid; body.appendChild(a);
            body.appendChild(el("span", null, " · " + info.modo));
          } else { body.textContent = cid; }
          b.after(body); b.setAttribute("aria-expanded", "true");
        });
      });
      p.appendChild(b);
    });
    box.appendChild(p);
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = ta.value.trim(); if (!q) return;
    ta.value = "";
    log.appendChild(el("div", "msg q", q));
    var ans = el("div", "msg a"); ans.setAttribute("aria-live", "polite");
    var wait = el("p", "muted small", L.verifying); ans.appendChild(wait); log.appendChild(ans);
    log.scrollTop = log.scrollHeight;
    fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
      body: JSON.stringify({ pergunta: q, idioma: L.lang, edicao: L.edition, evento: L.event || null,
                             modo_factual: doc.classList.contains("factual"), sessao: sessionId })
    }).then(function (r) {
      if (!r.ok || !r.body) throw new Error(r.status);
      var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
      function pump() {
        return reader.read().then(function (res) {
          if (res.done) return;
          buf += dec.decode(res.value, { stream: true });
          var parts = buf.split("\n\n"); buf = parts.pop();
          parts.forEach(function (chunk) {
            var ev = "message", data = "";
            chunk.split("\n").forEach(function (line) {
              if (line.indexOf("event:") === 0) ev = line.slice(6).trim();
              if (line.indexOf("data:") === 0) data += line.slice(5).trim();
            });
            if (!data) return;
            var obj = JSON.parse(data);
            if (ev === "session") sessionId = obj.sessao;
            if (ev === "segment") { if (wait.parentNode) wait.remove(); renderSegment(ans, obj); }
            if (ev === "error") { wait.textContent = obj.mensagem || L.unavailable; }
            log.scrollTop = log.scrollHeight;
          });
          return pump();
        });
      }
      return pump();
    }).catch(function () { wait.textContent = L.unavailable; });
  });
})();
