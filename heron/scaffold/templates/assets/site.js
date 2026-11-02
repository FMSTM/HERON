(function () {
  var data = (document.currentScript && document.currentScript.dataset) || {};

  try {
    var v = localStorage.getItem("theme");
    if (v === "light" || v === "dark") document.documentElement.dataset.theme = v;
  } catch (e) {}

  function themeToggle() {
    var button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    function current() {
      var set = document.documentElement.dataset.theme;
      if (set) return set;
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    button.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
    });
  }

  function consent() {
    if (!data.gtm && !data.ga4 && !data.metrika) return;
    var KEY = "heron-consent";
    var box = document.querySelector("[data-consent]");
    function read() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
    function write(value) { try { localStorage.setItem(KEY, value); } catch (e) {} }
    function script(src) {
      var s = document.createElement("script");
      s.async = true; s.src = src;
      document.head.appendChild(s);
    }
    var loaded = false;
    function load() {
      if (loaded) return;
      loaded = true;
      if (data.gtm) {
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push({ "gtm.start": new Date().getTime(), event: "gtm.js" });
        script("https://www.googletagmanager.com/gtm.js?id=" + encodeURIComponent(data.gtm));
      }
      if (data.ga4) {
        window.dataLayer = window.dataLayer || [];
        window.gtag = function () { window.dataLayer.push(arguments); };
        window.gtag("js", new Date());
        window.gtag("config", data.ga4);
        script("https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(data.ga4));
      }
      if (data.metrika) {
        window.ym = window.ym || function () { (window.ym.a = window.ym.a || []).push(arguments); };
        window.ym.l = 1 * new Date();
        window.ym(Number(data.metrika), "init", { clickmap: true, trackLinks: true, accurateTrackBounce: true });
        script("https://mc.yandex.ru/metrika/tag.js");
      }
    }
    function show() { if (box) box.hidden = false; }
    function hide() { if (box) box.hidden = true; }
    var choice = read();
    if (choice === "yes") load();
    else if (choice !== "no") show();
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest("[data-consent-accept]")) { write("yes"); hide(); load(); }
      else if (target.closest("[data-consent-decline]")) { write("no"); hide(); }
      else if (target.closest("[data-consent-open]")) { show(); }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    themeToggle();
    consent();
  });
})();
