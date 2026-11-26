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
 *
 * Na konci lišty jsou A− / A+ — velikost písma, pamatuje si ji každé
 * zařízení zvlášť (localStorage["fractal-termfont"]).
 *
 * Vedle ⌨ je ✎ — přejmenování záložky. Název se ukládá do tmux (přes
 * /ctl/term-title), takže je stejný na všech zařízeních a zmizí s terminálem.
 * Záložka před něj dává kategorii projektu („Práce: úprava grafu"); ukládá
 * se jen samotný název.
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
    ["^C",   "c",          "KeyC",       67],  // zkratka; posílá se s ctrlKey
    ["A−",   null,         null,          0],  // velikost písma, nic neposílá
    ["A+",   null,         null,          0]
  ];

  /* ---- velikost písma ---- */
  /* A− / A+ na konci lišty. Velikost se drží v localStorage, tedy zvlášť pro
     každý prohlížeč/zařízení — na iPhonu větší, na desktopu beze změny.
     ttyd posílá při každém (re)connectu svoje preference (-t fontSize=14)
     a tím by ji přepsal, proto ji enforceFont() hlídá a vrací. Po změně
     fit() přepočítá sloupce/řádky a ttyd je pošle do pty. */
  var FONT_KEY = "fractal-termfont";
  var FONT_MIN = 9, FONT_MAX = 32;

  function wantedFont() {
    var n = 0;
    try { n = parseInt(localStorage.getItem(FONT_KEY), 10) || 0; } catch (e) {}
    return n >= FONT_MIN && n <= FONT_MAX ? n : 0;   // 0 = nechat ttyd výchozí
  }

  function enforceFont() {
    var t = window.term, want = wantedFont();
    if (!t || !t.options || !want || t.options.fontSize === want) return;
    t.options.fontSize = want;
    if (t.fit) t.fit();
  }

  function stepFont(d) {
    var t = window.term;
    var cur = wantedFont() || (t && t.options && t.options.fontSize) || 14;
    var n = Math.max(FONT_MIN, Math.min(FONT_MAX, cur + d));
    try { localStorage.setItem(FONT_KEY, String(n)); } catch (e) {}
    enforceFont();
  }

  setInterval(enforceFont, 1000);
  window.addEventListener("storage", function (e) {
    if (e.key === FONT_KEY) enforceFont();
  });

  var ctrlArmed = false;   // sticky Ctrl: platí pro následující klávesu
  var ctrlBtn = null;

  /* ---- název záložky ---- */
  /* Všechny terminály na /term jsou jedna ttyd instance, takže ttyd nemůže
     mít titulek podle projektu (-t titleFixed je pro celý proces jeden).
     Odvozuje se proto tady z URL: /term/?arg=shop → „shop — terminál",
     /brain → „brain — terminál". Bez toho má každá záložka stejný titulek
     a při víc otevřených terminálech se v nich nedá vyznat. */

  /* Vlastní název (ikonka ✎) má přednost. Drží ho tmux, server podle adresy
     terminálu pozná, ke které session/oknu patří; terminál, který server
     nezná (404), si název pamatuje aspoň v tomhle prohlížeči (localStorage).
     409 = terminál je serverový, jen ještě (nebo už) neběží: ptát se znovu,
     nikdy nesahat do localStorage. Dřív se to nerozlišovalo - stránka, která
     se zeptala dřív, než tmux session vznikla, si název uložila do prohlížeče
     pod adresou terminálu a každá další session se stejným číslem (shop:p5)
     pak převzala název té zavřené. */

  var customTitle = "";
  var titlePrefix = "";            // kategorie projektu ze serveru: „Práce: úprava grafu"
  var titleLocal = false;          // server terminál nezná → localStorage
  var arg = new URLSearchParams(location.search).get("arg");
  var seg = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean).pop();
  var termId = arg || (seg && seg !== "term" ? seg : "");
  var LOCAL_KEY = "fractal-termtitle:" + location.pathname + location.search;

  function wantedTitle() {
    if (customTitle) return titlePrefix ? titlePrefix + ": " + customTitle : customTitle;
    return (termId || "fractal") + " — terminál";
  }

  function keepTitle() {
    if (document.title !== wantedTitle()) document.title = wantedTitle();

    // ttyd si titulek přepisuje při (re)connectu; hlídáme ho, ale jen jednou
    // navěšeným observerem nad <title>
    var el = document.querySelector("title");
    if (el && !el.dataset.tkWatched) {
      el.dataset.tkWatched = "1";
      new MutationObserver(function () {
        if (document.title !== wantedTitle()) document.title = wantedTitle();
      }).observe(el, { childList: true, characterData: true, subtree: true });
    }
  }

  function saveLocal(t) {
    try { t ? localStorage.setItem(LOCAL_KEY, t) : localStorage.removeItem(LOCAL_KEY); } catch (e) {}
  }

  var retryTimer = null;

  function loadTitle(tries) {
    if (!termId) {
      try { customTitle = localStorage.getItem(LOCAL_KEY) || ""; } catch (e) {}
      keepTitle();
      return;
    }
    tries = tries || 0;
    clearTimeout(retryTimer);
    fetch("/ctl/term-title?arg=" + encodeURIComponent(termId), { cache: "no-store" })
      .then(function (r) {
        if (r.status === 404) return { local: true };
        if (r.status === 409) return { pending: true };
        return r.ok ? r.json() : null;
      })
      .catch(function () { return null; })
      .then(function (j) {
        if (!j) return;            // server nedostupný: nechat, co je
        titleLocal = !!j.local;
        if (titleLocal) {
          try { customTitle = localStorage.getItem(LOCAL_KEY) || ""; } catch (e) {}
        } else {
          saveLocal("");           // serverový terminál: nic z prohlížeče (ani staré)
          // neběží: žádný název; session se možná zrovna zakládá - zkusit znovu
          customTitle = j.pending ? "" : (j.title || "");
          titlePrefix = j.prefix || "";
          if (j.pending && tries < 10) retryTimer = setTimeout(function () { loadTitle(tries + 1); }, 1500);
        }
        keepTitle();
      });
  }

  function renameTitle() {
    var t = window.prompt("Název záložky (prázdné = výchozí)", customTitle);
    if (t === null) return;
    t = t.trim().slice(0, 60);
    customTitle = t;
    keepTitle();
    if (titleLocal || !termId) { saveLocal(t); return; }
    fetch("/ctl/term-title", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arg: termId, title: t })
    }).then(function (r) {
      // terminál server nezná - aspoň v tomhle prohlížeči; serverový, který
      // neběží, název nedostane (patřil by session, která tu ještě není)
      if (r.status === 404) { titleLocal = true; saveLocal(t); }
      else if (r.status === 409) { window.alert("Terminál neběží, název se neuložil."); loadTitle(); }
    }).catch(function () {});
  }

  // název mohl změnit někdo jinde (jiné zařízení), nebo se pod touhle adresou
  // mezitím otevřela jiná session - načíst při návratu na záložku a občas i tak
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) loadTitle();
  });
  setInterval(function () { if (!document.hidden) loadTitle(); }, 30000);

  keepTitle();
  loadTitle();

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
    "#tk-toggle{position:fixed;top:6px;right:56px;z-index:10;border:0;",
    "  background:none;color:#e7eaee;opacity:.35;font:17px system-ui;",
    "  padding:6px 8px;cursor:pointer;touch-action:manipulation}",
    "#tk-toggle:hover{opacity:1}",
    "#tk-rename{position:fixed;top:6px;right:88px;z-index:10;border:0;",
    "  background:none;color:#e7eaee;opacity:.35;font:15px system-ui;",
    "  padding:7px 8px;cursor:pointer;touch-action:manipulation}",
    "#tk-rename:hover{opacity:1}"
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
        if (k[0] === "A−" || k[0] === "A+") { stepFont(k[0] === "A+" ? 1 : -1); return; }
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

    // ✎ vedle: přejmenování záložky (viz loadTitle/renameTitle)
    var rename = document.createElement("button");
    rename.id = "tk-rename";
    rename.type = "button";
    rename.textContent = "✎";
    rename.title = "přejmenovat záložku";
    rename.addEventListener("pointerdown", function (e) { e.preventDefault(); });
    rename.addEventListener("click", renameTitle);

    document.body.appendChild(bar);
    document.body.appendChild(toggle);
    document.body.appendChild(rename);
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
    if (document.getElementById("terminal-container")) { apply(); keepTitle(); enforceFont(); return; }
    if (++tries < 50) setTimeout(wait, 200);
  })();
})();
