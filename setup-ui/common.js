// Shared helpers for the framework-free pages. ES5-friendly for captive sheets.
(function () {
  "use strict";
  var WOT = (window.WOT = {});

  WOT.api = function (method, path, body) {
    var opts = { method: method, headers: {}, credentials: "same-origin" };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      return r.text().then(function (t) {
        var data = {};
        try { data = t ? JSON.parse(t) : {}; } catch (e) { data = {}; }
        return { ok: r.ok, status: r.status, data: data };
      });
    });
  };

  WOT.$ = function (sel) { return document.querySelector(sel); };

  WOT.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  WOT.bars = function (signal) {
    var n = signal >= 75 ? 4 : signal >= 50 ? 3 : signal >= 25 ? 2 : 1;
    var h = '<span class="bars" aria-label="Signal ' + n + ' of 4">';
    for (var i = 1; i <= 4; i++) h += '<i class="' + (i <= n ? "on" : "") + '"></i>';
    return h + "</span>";
  };

  WOT.lock = '<svg width="14" height="14" viewBox="0 0 24 24" aria-label="Needs a password" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';
  WOT.alert = '<span class="ico p"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.5l9 16H3z"/><path d="M12 10v4.5M12 17.4v.1"/></svg></span>';
  WOT.ok = '<span class="ico g"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg></span>';

  // Background light (HANDOFF 4): two blurred blobs, added by script so the HTML stays plain.
  WOT.blobs = function () {
    var bg = document.createElement("div");
    bg.className = "bg";
    bg.setAttribute("aria-hidden", "true");
    bg.innerHTML = '<div class="blob p" style="width:300px;height:300px;right:-120px;top:-60px"></div>' +
      '<div class="blob g s" style="width:340px;height:340px;left:-150px;bottom:40px"></div>';
    document.body.insertBefore(bg, document.body.firstChild);
  };
  if (document.readyState !== "loading") WOT.blobs(); else document.addEventListener("DOMContentLoaded", WOT.blobs);

  WOT.banner = function (el, text, kind) {
    if (!text) { el.innerHTML = ""; return; }
    var info = kind === "info";
    el.innerHTML = '<div class="glass banner ' + (info ? "tg" : "pk") + '" role="' + (info ? "status" : "alert") + '">' +
      (info ? WOT.ok : WOT.alert) + '<div style="flex:1">' + WOT.esc(text) + "</div></div>";
  };

  WOT.showHide = function (root) {
    var btns = (root || document).querySelectorAll(".field .show");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function (ev) {
        var input = ev.currentTarget.parentNode.querySelector("input");
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        ev.currentTarget.textContent = show ? "Hide" : "Show";
        ev.currentTarget.setAttribute("aria-pressed", show ? "true" : "false");
      });
    }
  };
})();
