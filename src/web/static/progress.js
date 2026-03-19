(function () {
  "use strict";

  var MAX_LOG_LINES = 150;
  var ACTIVE_STATUSES = new Set(["generating", "queued", "posting"]);
  var PHASE_ORDER = ["discovery", "generation", "posting"];
  var connections = new Map();

  function getWsUrl(itemId) {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + "/ws/content/" + itemId;
  }

  function connectCard(card) {
    var itemId = card.dataset.itemId;
    var status = card.dataset.status;
    if (!itemId || !ACTIVE_STATUSES.has(status)) return;
    if (connections.has(itemId)) return;

    var ctx = {
      itemId: itemId,
      ws: null,
      retries: 0,
      countdownInterval: null,
      countdownRemaining: 0,
    };
    connections.set(itemId, ctx);
    openSocket(ctx);
  }

  function openSocket(ctx) {
    var ws = new WebSocket(getWsUrl(ctx.itemId));
    ctx.ws = ws;

    ws.onopen = function () {
      ctx.retries = 0;
    };

    ws.onmessage = function (e) {
      var evt;
      try { evt = JSON.parse(e.data); } catch (ex) { return; }
      handleEvent(ctx, evt);
    };

    ws.onclose = function () {
      var card = document.getElementById("card-" + ctx.itemId);
      if (!card || !ACTIVE_STATUSES.has(card.dataset.status)) {
        cleanup(ctx);
        return;
      }
      ctx.retries++;
      var delay = Math.min(1000 * Math.pow(2, ctx.retries), 30000);
      setTimeout(function () { openSocket(ctx); }, delay);
    };

    ws.onerror = function () {
      ws.close();
    };
  }

  function handleEvent(ctx, evt) {
    var id = ctx.itemId;

    switch (evt.event_type) {
      case "phase":
        updatePhase(id, evt.phase);
        appendLog(id, evt.message);
        break;

      case "progress":
        updatePhase(id, evt.phase);
        updateProgressBar(id, evt.current, evt.total);
        appendLog(id, evt.message);
        break;

      case "wait":
        updatePhase(id, "waiting");
        startCountdown(ctx, evt.wait_seconds || 0);
        appendLog(id, evt.message);
        break;

      case "log":
      case "stderr":
        appendLog(id, evt.message, evt.event_type === "stderr" ? "dim" : "");
        break;

      case "error":
        appendLog(id, evt.message, "error");
        break;

      case "done":
        appendLog(id, evt.message, "success");
        stopCountdown(ctx);
        updateProgressBar(id, 1, 1);
        refreshCard(id);
        break;
    }
  }

  var PHASE_DOT_DONE = "bg-emerald-500 border-emerald-500";
  var PHASE_DOT_ACTIVE = "bg-white border-white shadow-[0_0_6px_rgba(255,255,255,0.5)] animate-pulse";
  var PHASE_DOT_IDLE = "bg-zinc-800 border-zinc-700";
  var PHASE_LABEL_DONE = "text-emerald-500";
  var PHASE_LABEL_ACTIVE = "text-white";
  var PHASE_LABEL_IDLE = "text-zinc-600";
  var CONNECTOR_DONE = "bg-emerald-500/50";
  var CONNECTOR_IDLE = "bg-zinc-800";
  var ALL_DOT_CLASSES = (PHASE_DOT_DONE + " " + PHASE_DOT_ACTIVE + " " + PHASE_DOT_IDLE).split(" ");
  var ALL_LABEL_CLASSES = (PHASE_LABEL_DONE + " " + PHASE_LABEL_ACTIVE + " " + PHASE_LABEL_IDLE).split(" ");
  var ALL_CONNECTOR_CLASSES = (CONNECTOR_DONE + " " + CONNECTOR_IDLE).split(" ");

  function updatePhase(id, phase) {
    if (!phase) return;
    var panel = document.getElementById("progress-" + id);
    if (!panel) return;

    var phaseIdx = PHASE_ORDER.indexOf(phase);
    var steps = panel.querySelectorAll(".phase-step");
    var connectors = panel.querySelectorAll(".phase-connector");

    steps.forEach(function (step, i) {
      var dot = step.querySelector(".phase-dot");
      var label = step.querySelector(".phase-label");
      if (!dot || !label) return;

      step.classList.remove("active", "done");
      ALL_DOT_CLASSES.forEach(function (c) { dot.classList.remove(c); });
      ALL_LABEL_CLASSES.forEach(function (c) { label.classList.remove(c); });

      if (phaseIdx >= 0 && i < phaseIdx) {
        step.classList.add("done");
        PHASE_DOT_DONE.split(" ").forEach(function (c) { dot.classList.add(c); });
        PHASE_LABEL_DONE.split(" ").forEach(function (c) { label.classList.add(c); });
      } else if (phaseIdx >= 0 && i === phaseIdx) {
        step.classList.add("active");
        PHASE_DOT_ACTIVE.split(" ").forEach(function (c) { dot.classList.add(c); });
        PHASE_LABEL_ACTIVE.split(" ").forEach(function (c) { label.classList.add(c); });
      } else {
        PHASE_DOT_IDLE.split(" ").forEach(function (c) { dot.classList.add(c); });
        PHASE_LABEL_IDLE.split(" ").forEach(function (c) { label.classList.add(c); });
      }
    });

    connectors.forEach(function (conn, i) {
      ALL_CONNECTOR_CLASSES.forEach(function (c) { conn.classList.remove(c); });
      if (phaseIdx >= 0 && i < phaseIdx) {
        CONNECTOR_DONE.split(" ").forEach(function (c) { conn.classList.add(c); });
      } else {
        CONNECTOR_IDLE.split(" ").forEach(function (c) { conn.classList.add(c); });
      }
    });
  }

  function updateProgressBar(id, current, total) {
    var panel = document.getElementById("progress-" + id);
    if (!panel) return;

    var fill = panel.querySelector(".progress-bar-fill");
    var label = panel.querySelector(".progress-label");

    if (fill && total && total > 0) {
      var pct = Math.min(100, Math.round((current / total) * 100));
      fill.style.width = pct + "%";
    }

    if (label && current != null && total != null && total > 0) {
      label.textContent = current + " / " + total;
      label.style.display = "";
    }
  }

  function startCountdown(ctx, seconds) {
    stopCountdown(ctx);
    ctx.countdownRemaining = seconds;
    var timer = document.getElementById("timer-" + ctx.itemId);
    if (!timer) return;
    timer.style.display = "";
    renderTimer(ctx.itemId, seconds);

    ctx.countdownInterval = setInterval(function () {
      ctx.countdownRemaining--;
      if (ctx.countdownRemaining <= 0) {
        stopCountdown(ctx);
        return;
      }
      renderTimer(ctx.itemId, ctx.countdownRemaining);
    }, 1000);
  }

  function stopCountdown(ctx) {
    if (ctx.countdownInterval) {
      clearInterval(ctx.countdownInterval);
      ctx.countdownInterval = null;
    }
    var timer = document.getElementById("timer-" + ctx.itemId);
    if (timer) timer.style.display = "none";
  }

  function renderTimer(id, secs) {
    var timer = document.getElementById("timer-" + id);
    if (!timer) return;
    var m = Math.floor(secs / 60);
    var s = secs % 60;
    var display = m > 0 ? m + ":" + String(s).padStart(2, "0") : s + "s";
    timer.innerHTML =
      '<span class="text-xs text-zinc-400">Next action in ' +
      '<strong class="text-amber-400 font-mono text-sm">' + display + "</strong></span>";
  }

  function appendLog(id, message, cls) {
    var logEl = document.getElementById("logs-" + id);
    if (!logEl || !message) return;

    var line = document.createElement("div");
    line.className = "py-px";
    if (cls === "error") {
      line.className += " text-red-400 font-semibold";
    } else if (cls === "success") {
      line.className += " text-emerald-400 font-semibold";
    } else if (cls === "dim") {
      line.className += " text-zinc-600";
    } else {
      line.className += " text-zinc-500";
    }
    line.textContent = message;
    logEl.appendChild(line);

    while (logEl.children.length > MAX_LOG_LINES) {
      logEl.removeChild(logEl.firstChild);
    }

    logEl.scrollTop = logEl.scrollHeight;
  }

  function refreshCard(id) {
    setTimeout(function () {
      var card = document.getElementById("card-" + id);
      if (card && typeof htmx !== "undefined") {
        htmx.ajax("GET", "/content/" + id + "/status", { target: card, swap: "outerHTML" });
      }
    }, 1500);
  }

  function cleanup(ctx) {
    stopCountdown(ctx);
    if (ctx.ws) {
      try { ctx.ws.close(); } catch (ex) {}
    }
    connections.delete(ctx.itemId);
  }

  function scanCards() {
    document.querySelectorAll(".content-card").forEach(function (card) {
      var itemId = card.dataset.itemId;
      var status = card.dataset.status;
      if (itemId && ACTIVE_STATUSES.has(status)) {
        connectCard(card);
      } else if (itemId && connections.has(itemId)) {
        cleanup(connections.get(itemId));
      }
    });
  }

  var observer = new MutationObserver(function () {
    scanCards();
  });

  document.addEventListener("DOMContentLoaded", function () {
    scanCards();
    observer.observe(document.body, { childList: true, subtree: true });
  });

  document.addEventListener("htmx:afterSwap", function () {
    scanCards();
  });
})();
