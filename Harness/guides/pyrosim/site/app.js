/* PyroSim in Seven Days — page behaviour.
   i18n swaps the innerHTML of every tagged element when the language
   changes, so nothing here keeps a reference to text nodes: handlers are
   delegated from document, and state that shows in the DOM is re-applied when
   <html lang> changes. */
(function () {
  "use strict";

  var STORE_KEY = "pyrosim-guide-progress-v1";
  var DAYS = ["day1", "day2", "day3", "day4", "day5", "day6", "day7"];

  function zh() { return (document.documentElement.getAttribute("lang") || "").indexOf("zh") === 0; }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return [].slice.call((root || document).querySelectorAll(sel)); }

  /* ---------- FDS listings: text lives in <script type="text/plain"> ---------- */
  function escapeHtml(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function highlight(src) {
    // Namelist records (&NAME ... /) in copper, free text between records as comments.
    var out = [], i = 0, re = /&[A-Z]{3,4}\b[\s\S]*?\/(?=\s*(?:\n|$))/g, m;
    while ((m = re.exec(src))) {
      if (m.index > i) out.push('<span class="cm">' + escapeHtml(src.slice(i, m.index)) + "</span>");
      var rec = escapeHtml(m[0]).replace(/^&amp;([A-Z]{3,4})/, '<span class="nl">&amp;$1</span>');
      out.push(rec);
      i = m.index + m[0].length;
    }
    if (i < src.length) out.push('<span class="cm">' + escapeHtml(src.slice(i)) + "</span>");
    return out.join("");
  }
  function sourceText(name) {
    var box = document.getElementById("src-" + name);
    return box ? box.textContent.replace(/^\n/, "") : "";
  }
  $all("pre.fds[data-src]").forEach(function (pre) {
    pre.innerHTML = highlight(sourceText(pre.getAttribute("data-src")));
  });

  /* ---------- Copy and save ---------- */
  var downloads = null;
  function flash(bar, ok) {
    var s = bar && $(".listing-status", bar);
    if (!s) return;
    s.textContent = ok ? "✓" : "…";
    setTimeout(function () { s.textContent = ""; }, 1800);
  }
  function selectPre(pre) {
    var r = document.createRange(); r.selectNodeContents(pre);
    var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
  }
  document.addEventListener("click", function (e) {
    var copy = e.target.closest("[data-copy]");
    if (copy) {
      var name = copy.getAttribute("data-copy");
      var pre = $('pre.fds[data-src="' + name + '"]');
      var text = sourceText(name);
      var bar = copy.closest(".listing-bar");
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { flash(bar, true); },
          function () { if (pre) selectPre(pre); flash(bar, false); });
      } else if (pre) { selectPre(pre); flash(bar, false); }
      return;
    }
    var save = e.target.closest("[data-save]");
    if (save && downloads) {
      var file = save.getAttribute("data-save");
      downloads.save({ filename: file + ".fds", data: sourceText(file) })
        .then(function () { flash(save.closest(".listing-bar"), true); }, function () {});
    }
  });
  if (window.claude && typeof window.claude.use === "function") {
    window.claude.use("downloads").then(function (d) {
      downloads = d;
      if (d) $all("[data-save]").forEach(function (b) { b.hidden = false; });
    }, function () {});
  }

  /* ---------- Progress ---------- */
  function readProgress() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch (e) { return {}; }
  }
  function writeProgress(p) { try { localStorage.setItem(STORE_KEY, JSON.stringify(p)); } catch (e) {} }
  var progress = readProgress();
  function applyProgress() {
    var n = 0;
    DAYS.forEach(function (d) {
      var on = !!progress[d];
      if (on) n++;
      var box = document.getElementById("done-" + d);
      if (box) box.checked = on;
      $all('a[href="#' + d + '"]').forEach(function (a) { a.classList.toggle("done", on); });
    });
    $all("[data-progress-count]").forEach(function (el) { el.textContent = n + " / 7"; });
  }
  document.addEventListener("change", function (e) {
    var t = e.target;
    if (t.matches && t.matches("input[data-done]")) {
      progress[t.getAttribute("data-done")] = t.checked;
      writeProgress(progress);
      applyProgress();
    }
  });
  applyProgress();

  /* ---------- Where the reader is ---------- */
  var currentId = "start";
  var sections = $all("main section[id]");
  function markCurrent() {
    var best = null, bestTop = -Infinity;
    sections.forEach(function (s) {
      var top = s.getBoundingClientRect().top;
      if (top <= 140 && top > bestTop) { best = s; bestTop = top; }
    });
    currentId = best ? best.id : (sections[0] && sections[0].id) || "start";
    $all(".rail a").forEach(function (a) {
      a.setAttribute("aria-current", a.getAttribute("href") === "#" + currentId ? "true" : "false");
    });
    var ctx = $("[data-ask-context]");
    if (ctx) {
      var h = best && $("h2", best);
      ctx.textContent = h ? h.textContent : "";
    }
  }
  var ticking = false;
  window.addEventListener("scroll", function () {
    if (!ticking) { ticking = true; requestAnimationFrame(function () { ticking = false; markCurrent(); }); }
  }, { passive: true });
  markCurrent();

  /* ---------- Error finder ---------- */
  function filterErrors() {
    var input = document.getElementById("err-filter");
    if (!input) return;
    var q = input.value.trim().toLowerCase();
    var rows = $all("#errors tbody tr"), shown = 0;
    rows.forEach(function (tr) {
      var hit = !q || tr.textContent.toLowerCase().indexOf(q) !== -1 ||
        (tr.getAttribute("data-tags") || "").toLowerCase().indexOf(q) !== -1;
      tr.hidden = !hit;
      if (hit) shown++;
    });
    var c = $("[data-err-count]");
    if (c) c.textContent = shown + " / " + rows.length;
  }
  document.addEventListener("input", function (e) {
    if (e.target.id === "err-filter") filterErrors();
    if (e.target.closest && e.target.closest(".calc")) calc();
  });
  filterErrors();

  /* ---------- Hand calculation (Day 6) ---------- */
  var LININGS = {
    // k (kW/m·K), rho (kg/m3), c (kJ/kg·K), delta (m) — values set in page data
  };
  function num(id) { var el = document.getElementById(id); return el ? parseFloat(el.value) : NaN; }
  function out(id, v, digits) {
    var el = document.getElementById(id);
    if (el) el.value = isFinite(v) ? v.toFixed(digits) : "—";
  }
  function calc() {
    var data = document.getElementById("calc-data");
    if (!data) return;
    var linings = LININGS;
    try { linings = JSON.parse(data.textContent); } catch (e) { return; }
    var Q = num("c-q"), L = num("c-l"), W = num("c-w"), H = num("c-h");
    var wo = num("c-wo"), ho = num("c-ho"), t = num("c-t");
    var sel = document.getElementById("c-lining");
    var m = linings[sel ? sel.value : ""];
    if (!m) return;
    var Ao = wo * ho, rootH = Math.sqrt(ho);
    var AT = 2 * (L * W + L * H + W * H) - Ao;
    var tp = (m.rho * m.c / m.k) * Math.pow(m.delta / 2, 2);
    var hk = t < tp ? Math.sqrt(m.k * m.rho * m.c / t) : m.k / m.delta;
    var dT = 6.85 * Math.pow((Q * Q) / (Ao * rootH * hk * AT), 1 / 3);
    out("o-dt", dT, 0);
    out("o-tg", dT + 20, 0);
    out("o-hk", hk * 1000, 1);
    out("o-fo-mqh", 610 * Math.sqrt(hk * AT * Ao * rootH), 0);
    out("o-fo-bab", 750 * Ao * rootH, 0);
    out("o-fo-tho", 7.8 * AT + 378 * Ao * rootH, 0);
  }
  calc();

  /* ---------- Charts: crosshair + tooltip ---------- */
  function chartSetup(fig) {
    var dataEl = $("script[type='application/json']", fig);
    var svg = $("svg", fig);
    if (!dataEl || !svg) return;
    var spec;
    try { spec = JSON.parse(dataEl.textContent); } catch (e) { return; }
    var wrap = $(".chart-wrap", fig);
    var tip = $(".tip", fig);
    var cross = $(".crosshair", svg);
    function show(evt) {
      var pt = svg.createSVGPoint();
      pt.x = evt.clientX; pt.y = evt.clientY;
      var loc = pt.matrixTransform(svg.getScreenCTM().inverse());
      if (loc.x < spec.plot[0] || loc.x > spec.plot[2]) { hide(); return; }
      var xVal = spec.x0 + (loc.x - spec.plot[0]) / (spec.plot[2] - spec.plot[0]) * (spec.x1 - spec.x0);
      var xs = spec.t, lo = 0, hi = xs.length - 1;
      while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (xs[mid] < xVal) lo = mid; else hi = mid; }
      var i = Math.abs(xs[lo] - xVal) < Math.abs(xs[hi] - xVal) ? lo : hi;
      var px = spec.plot[0] + (xs[i] - spec.x0) / (spec.x1 - spec.x0) * (spec.plot[2] - spec.plot[0]);
      if (cross) { cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.removeAttribute("visibility"); }
      var lines = [spec.xlabel + " " + xs[i] + " " + spec.xunit];
      spec.series.forEach(function (s, k) {
        var name = $("[data-series='" + k + "']", fig);
        var label = name ? name.textContent : s.name;
        var v = s.v[i];
        lines.push(label + ": " + (v == null ? "—" : v.toFixed(s.digits)) + " " + spec.yunit);
      });
      tip.innerHTML = lines.map(escapeHtml).join("<br>");
      var box = wrap.getBoundingClientRect();
      tip.style.left = (evt.clientX - box.left) + "px";
      tip.style.top = (evt.clientY - box.top) + "px";
      tip.hidden = false;
    }
    function hide() { tip.hidden = true; if (cross) cross.setAttribute("visibility", "hidden"); }
    svg.addEventListener("pointermove", show);
    svg.addEventListener("pointerleave", hide);
  }
  $all("figure.chart").forEach(chartSetup);

  /* ---------- Ask Peter ---------- */
  var sample = null, controller = null;
  var panel = document.getElementById("ask-panel");
  function setAskAvailable(on) {
    $all("[data-ask-on]").forEach(function (el) { el.hidden = !on; });
    $all("[data-ask-off]").forEach(function (el) { el.hidden = on; });
  }
  setAskAvailable(false);
  if (window.claude && typeof window.claude.use === "function") {
    window.claude.use("sample").then(function (s) { sample = s; setAskAvailable(!!s); }, function () {});
  }
  function guideContext() {
    var parts = [];
    var sec = document.getElementById(currentId);
    if (sec) parts.push("SECTION THE READER IS ON:\n" + sec.innerText.slice(0, 9000));
    var ref = document.getElementById("reference");
    if (ref && ref !== sec) parts.push("REFERENCE RESULTS:\n" + ref.innerText.slice(0, 3500));
    var errs = document.getElementById("errors");
    if (errs && errs !== sec) parts.push("ERROR TABLE:\n" + errs.innerText.slice(0, 5000));
    return parts.join("\n\n");
  }
  function ask(question) {
    var answer = document.getElementById("ask-answer");
    if (!sample || !question) return;
    if (controller) controller.abort();
    controller = new AbortController();
    answer.textContent = "…";
    var lang = zh()
      ? "Answer in Hong Kong written Chinese (Traditional characters, professional register). Keep PyroSim menu names, FDS keywords, file names, numbers and units in English."
      : "Answer in English.";
    var prompt = [
      "You are Peter, a patient fire-modelling tutor. The reader is a total beginner learning PyroSim 2026.1 on a Windows computer, which writes input for NIST FDS 6.10.1, for introductory education. PyroSim does not compute the fire; FDS does.",
      lang,
      "Ground every answer in the guide text below. If the guide does not cover the question, say so plainly and name where to look (a Thunderhead PyroSim documentation page or an FDS User Guide chapter) instead of guessing. Never invent a menu path, dialog field or number. For how-to questions give short numbered steps; for why questions give one short paragraph. Keep it under 200 words.",
      guideContext(),
      "QUESTION: " + question
    ].join("\n\n");
    sample(prompt, {
      signal: controller.signal, cache: false,
      onText: function (p) { answer.textContent = p.text; }
    }).then(function (r) { answer.textContent = r.text; }, function (err) {
      if (!err || err.code === "cancelled") return;
      if (err.code === "not_granted") { setAskAvailable(false); answer.textContent = ""; return; }
      answer.textContent = err.code === "rate_limited" ? "⏳" : (err.text || "—");
    });
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-ask-open]")) {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) { markCurrent(); var ta = document.getElementById("ask-q"); if (ta) ta.focus(); }
      return;
    }
    if (e.target.closest("[data-ask-close]")) { panel.hidden = true; return; }
    if (e.target.closest("[data-ask-send]")) { ask((document.getElementById("ask-q") || {}).value || ""); return; }
    var sug = e.target.closest("[data-suggest]");
    if (sug) {
      var ta2 = document.getElementById("ask-q");
      if (ta2) ta2.value = sug.textContent.trim();
      ask(sug.textContent.trim());
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && panel && !panel.hidden) panel.hidden = true;
    if (e.target.id === "ask-q" && e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(e.target.value);
  });

  /* ---------- Re-apply DOM state after a language switch ---------- */
  new MutationObserver(function () {
    applyProgress(); filterErrors(); markCurrent();
    $all("pre.fds[data-src]").forEach(function (pre) {
      if (!$(".nl", pre)) pre.innerHTML = highlight(sourceText(pre.getAttribute("data-src")));
    });
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
})();
