(function () {
  "use strict";

  const MAX_LOG_LINES = 150;
  const ACTIVE_STATUSES = new Set(["generating", "queued", "posting"]);
  const PHASE_ORDER = ["discovery", "generation", "posting"];
  const connections = new Map();

  function getWsUrl(itemId) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws/content/${itemId}`;
  }

  function connectCard(card) {
    const itemId = card.dataset.itemId;
    const status = card.dataset.status;
    if (!itemId || !ACTIVE_STATUSES.has(status)) return;
    if (connections.has(itemId)) return;

    const ctx = {
      itemId,
      ws: null,
      retries: 0,
      countdownInterval: null,
      countdownRemaining: 0,
    };
    connections.set(itemId, ctx);
    openSocket(ctx);
  }

  function openSocket(ctx) {
    const ws = new WebSocket(getWsUrl(ctx.itemId));
    ctx.ws = ws;

    ws.onopen = function () {
      ctx.retries = 0;
    };

    ws.onmessage = function (e) {
      let evt;
      try { evt = JSON.parse(e.data); } catch { return; }
      handleEvent(ctx, evt);
    };

    ws.onclose = function () {
      const card = document.getElementById("card-" + ctx.itemId);
      if (!card || !ACTIVE_STATUSES.has(card.dataset.status)) {
        cleanup(ctx);
        return;
      }
      ctx.retries++;
      const delay = Math.min(1000 * Math.pow(2, ctx.retries), 30000);
      setTimeout(function () { openSocket(ctx); }, delay);
    };

    ws.onerror = function () {
      ws.close();
    };
  }

  function handleEvent(ctx, evt) {
    const id = ctx.itemId;

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

  function updatePhase(id, phase) {
    if (!phase) return;
    const panel = document.getElementById("progress-" + id);
    if (!panel) return;

    const phaseIdx = PHASE_ORDER.indexOf(phase);
    const steps = panel.querySelectorAll(".phase-step");
    const connectors = panel.querySelectorAll(".phase-connector");

    steps.forEach(function (step, i) {
      step.classList.remove("active", "done");
      if (phaseIdx >= 0) {
        if (i < phaseIdx) step.classList.add("done");
        else if (i === phaseIdx) step.classList.add("active");
      }
    });

    connectors.forEach(function (conn, i) {
      conn.classList.toggle("done", phaseIdx >= 0 && i < phaseIdx);
    });
  }

  function updateProgressBar(id, current, total) {
    const panel = document.getElementById("progress-" + id);
    if (!panel) return;

    const fill = panel.querySelector(".progress-bar-fill");
    const label = panel.querySelector(".progress-label");

    if (fill && total && total > 0) {
      const pct = Math.min(100, Math.round((current / total) * 100));
      fill.style.width = pct + "%";
      fill.dataset.progress = pct;
    }

    if (label && current != null && total != null && total > 0) {
      label.textContent = current + " / " + total;
      label.style.display = "";
    }
  }

  function startCountdown(ctx, seconds) {
    stopCountdown(ctx);
    ctx.countdownRemaining = seconds;
    const timer = document.getElementById("timer-" + ctx.itemId);
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
    const timer = document.getElementById("timer-" + ctx.itemId);
    if (timer) timer.style.display = "none";
  }

  function renderTimer(id, secs) {
    const timer = document.getElementById("timer-" + id);
    if (!timer) return;
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    const display = m > 0 ? m + ":" + String(s).padStart(2, "0") : s + "s";
    timer.innerHTML =
      '<span class="timer-icon">&#9202;</span>' +
      '<span class="timer-text">Next action in <strong class="timer-value">' +
      display + "</strong></span>";
  }

  function appendLog(id, message, cls) {
    const logEl = document.getElementById("logs-" + id);
    if (!logEl || !message) return;

    const line = document.createElement("div");
    line.className = "log-line" + (cls ? " " + cls : "");
    line.textContent = message;
    logEl.appendChild(line);

    while (logEl.children.length > MAX_LOG_LINES) {
      logEl.removeChild(logEl.firstChild);
    }

    logEl.scrollTop = logEl.scrollHeight;
  }

  function refreshCard(id) {
    setTimeout(function () {
      const card = document.getElementById("card-" + id);
      if (card && typeof htmx !== "undefined") {
        htmx.ajax("GET", "/content/" + id + "/status", { target: card, swap: "outerHTML" });
      }
    }, 1500);
  }

  function cleanup(ctx) {
    stopCountdown(ctx);
    if (ctx.ws) {
      try { ctx.ws.close(); } catch {}
    }
    connections.delete(ctx.itemId);
  }

  function scanCards() {
    document.querySelectorAll(".content-card").forEach(function (card) {
      const itemId = card.dataset.itemId;
      const status = card.dataset.status;
      if (itemId && ACTIVE_STATUSES.has(status)) {
        connectCard(card);
      } else if (itemId && connections.has(itemId)) {
        cleanup(connections.get(itemId));
      }
    });
  }

  // Observe DOM for card swaps (HTMX replaces outerHTML)
  const observer = new MutationObserver(function () {
    scanCards();
  });

  document.addEventListener("DOMContentLoaded", function () {
    scanCards();
    observer.observe(document.body, { childList: true, subtree: true });
  });

  // Re-scan after HTMX swaps
  document.addEventListener("htmx:afterSwap", function () {
    scanCards();
  });
})();
