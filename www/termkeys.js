/* termkeys.js — lišta s ovládacími tlačítky (šipky, Esc, Ctrl…) pro terminály.
 *
 * Do stránek ttyd ji injektuje nginx (sub_filter v snippets/ttyd-proxy.conf),
 * takže platí pro všechny terminály — současné i budoucí — bez zásahu do
 * jednotlivých ttyd instancí. Soubor patří uživateli, úpravy nechtějí root.
 *
 * K čemu: na iOS nejde u hw klávesnice bez šipek (nebo úplně bez klávesnice)
 * poslat šipky, Esc, Ctrl+C… Lišta je posílá syntetickými KeyboardEventy na
 * .xterm-helper-textarea — xterm.js netestuje isTrusted, takže je zpracuje
 * jako opravdové klávesy.
 *
 * Zapínání: localStorage["fractal-termkeys"] = "on" | "off". Přepíná se na
 * rozcestníku (stejný origin ⇒ sdílené localStorage) nebo ikonkou ⌨ v rohu.
 * Posloucháme i "storage" event, takže přepnutí na dashboardu se projeví
 * živě v už otevřených terminálech.
 */
(function () {
  "use strict";

  var KEY = "fractal-termkeys";

  /* [popisek, ev.key, ev.code, keyCode] — keyCode je potřeba, protože xterm
     rozhoduje podle něj; konstruktor KeyboardEvent ho ignoruje, tak se níže
     doplňuje přes defineProperty. */
  var KEYS = [
    ["Esc",  "Escape",     "Escape",     27],
    ["Tab",  "Tab",        "Tab",         9],
    ["Ctrl", null,         null,          0],  // sticky modifikátor, nic neposílá
    ["←",    "ArrowLeft",  "ArrowLeft",  37],
    ["↓",    "ArrowDown",  "ArrowDown",  40],
    ["↑",    "ArrowUp",    "ArrowUp",    38],
    ["→",    "ArrowRight", "ArrowRight", 39],
    ["PgUp", "PageUp",     "PageUp",     33],
    ["PgDn", "PageDown",   "PageDown",   34],
    ["^C",   "c",          "KeyC",       67]   // zkratka; posílá se s ctrlKey
  ];

  var ctrlArmed = false;   // sticky Ctrl: platí pro následující klávesu
  var ctrlBtn = null;

  /* ---- název záložky ---- */
  /* Všechny terminály na /term jsou jedna ttyd instance, takže ttyd nemůže
     mít titulek podle projektu (-t titleFixed je pro celý proces jeden).
     Odvozuje se proto tady z URL: /term/?arg=shop → „shop — terminál",
     /brain → „brain — terminál". Bez toho má každá záložka stejný titulek
     a při víc otevřených terminálech se v nich nedá vyznat. */

  function wantedTitle() {
    var arg = new URLSearchParams(location.search).get("arg");
    var seg = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean).pop();
    var name = arg || (seg && seg !== "term" ? seg : "fractal");
    return name + " — terminál";
  }

  function keepTitle() {
    var want = wantedTitle();
    if (document.title !== want) document.title = want;

    // ttyd si titulek přepisuje při (re)connectu; hlídáme ho, ale jen jednou
    // navěšeným observerem nad <title>
    var el = document.querySelector("title");
    if (el && !el.dataset.tkWatched) {
      el.dataset.tkWatched = "1";
      new MutationObserver(function () {
        if (document.title !== want) document.title = want;
      }).observe(el, { childList: true, characterData: true, subtree: true });
    }
  }

  keepTitle();

  function sendKey(key, code, keyCode, ctrl) {
    var ta = document.querySelector(".xterm-helper-textarea");
    if (!ta) return;
    var ev = new KeyboardEvent("keydown", {
      key: key, code: code, ctrlKey: !!ctrl, bubbles: true, cancelable: true
    });
    // xterm čte ev.keyCode/which; v init dictu je konstruktor zahazuje
    Object.defineProperty(ev, "keyCode", { value: keyCode });
    Object.defineProperty(ev, "which",   { value: keyCode });
    ta.dispatchEvent(ev);
  }

  function disarmCtrl() {
    ctrlArmed = false;
    if (ctrlBtn) ctrlBtn.classList.remove("tk-armed");
  }

  /* ---- lišta ---- */

  var css = [
    "#tk-bar{position:fixed;left:0;right:0;bottom:0;z-index:10;display:none;",
    "  gap:6px;padding:6px 8px calc(6px + env(safe-area-inset-bottom));",
    "  overflow-x:auto;background:#161615;border-top:1px solid #2c2c2a;",
    "  -webkit-user-select:none;user-select:none}",
    "#tk-bar button{flex:1 0 auto;min-width:42px;padding:10px 12px;border:0;",
    "  border-radius:8px;background:#2c2c2a;color:#e7eaee;font:15px system-ui;",
    "  cursor:pointer;touch-action:manipulation}",
    "#tk-bar button:active{background:#3987e5}",
    "#tk-bar button.tk-armed{background:#3987e5;color:#fff}",
    "#tk-toggle{position:fixed;top:6px;right:8px;z-index:10;border:0;",
    "  background:none;color:#e7eaee;opacity:.35;font:17px system-ui;",
    "  padding:6px 8px;cursor:pointer;touch-action:manipulation}",
    "#tk-toggle:hover{opacity:1}"
  ].join("\n");

  function build() {
    var style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);

    var bar = document.createElement("div");
    bar.id = "tk-bar";

    KEYS.forEach(function (k) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = k[0];
      // preventDefault na pointerdown: tlačítko nesmí ukrást fokus terminálu
      // (a na iOS shodit klávesnici, když je zrovna vyvolaná)
      b.addEventListener("pointerdown", function (e) { e.preventDefault(); });
      b.addEventListener("click", function () {
        if (k[0] === "Ctrl") {
          ctrlArmed = !ctrlArmed;
          b.classList.toggle("tk-armed", ctrlArmed);
          return;
        }
        var ctrl = k[0] === "^C" || ctrlArmed;
        sendKey(k[1], k[2], k[3], ctrl);
        disarmCtrl();
      });
      if (k[0] === "Ctrl") ctrlBtn = b;
      bar.appendChild(b);
    });

    // ⌨ v rohu: rychlé přepnutí bez návratu na rozcestník; zapisuje do
    // localStorage, takže se s přepínačem na dashboardu drží v synchronu
    var toggle = document.createElement("button");
    toggle.id = "tk-toggle";
    toggle.type = "button";
    toggle.textContent = "⌨";
    toggle.title = "ovládací tlačítka (šipky, Esc, Ctrl…)";
    toggle.addEventListener("pointerdown", function (e) { e.preventDefault(); });
    toggle.addEventListener("click", function () {
      var on = localStorage.getItem(KEY) === "on";
      try { localStorage.setItem(KEY, on ? "off" : "on"); } catch (e) {}
      apply();
    });

    document.body.appendChild(bar);
    document.body.appendChild(toggle);
    return bar;
  }

  /* Sticky Ctrl i pro opravdovou klávesnici: Ctrl na liště + "c" z klávesnice
     = Ctrl+C. Zachytí se první obyčejný znak a přepošle se s ctrlKey. */
  document.addEventListener("keydown", function (e) {
    if (!ctrlArmed || !e.isTrusted || e.ctrlKey || e.key.length !== 1) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    sendKey(e.key.toLowerCase(), e.code, e.key.toUpperCase().charCodeAt(0), true);
    disarmCtrl();
  }, true);

  var bar = null;

  function apply() {
    if (!bar) bar = build();
    var on = localStorage.getItem(KEY) === "on";
    bar.style.display = on ? "flex" : "none";
    // Lišta si ukousne výšku z kontejneru terminálu; resize event donutí
    // ttyd (fit addon) přepočítat počet řádků, takže nic nepřekryje.
    var c = document.getElementById("terminal-container");
    if (c) c.style.height = on ? "calc(100% - " + bar.offsetHeight + "px)" : "";
    window.dispatchEvent(new Event("resize"));
    if (!on) disarmCtrl();
  }

  // přepnutí na rozcestníku se projeví hned, i v už otevřeném terminálu
  window.addEventListener("storage", function (e) {
    if (e.key === KEY) apply();
  });

  /* ttyd vykresluje do #terminal-container až po startu appky — počkáme,
     než existuje, pak teprv lišta dává smysl. */
  var tries = 0;
  (function wait() {
    if (document.getElementById("terminal-container")) { apply(); keepTitle(); return; }
    if (++tries < 50) setTimeout(wait, 200);
  })();
})();
