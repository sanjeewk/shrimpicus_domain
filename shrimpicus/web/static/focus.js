(function () {
  "use strict";

  const stage = document.getElementById("focusStage");
  if (!stage) return;

  const bootstrap = JSON.parse(document.getElementById("focusBootstrap").textContent || "{}");

  const btn = document.getElementById("lockinBtn");
  const durationInput = document.getElementById("focusDuration");
  const groupSelect = document.getElementById("focusGroup");
  const sessionsEl = document.getElementById("focusSessions");

  const activeEl = document.getElementById("focusActive");
  const timerEl = document.getElementById("focusTimer");
  const metaEl = document.getElementById("focusMeta");
  const quoteEl = document.getElementById("focusQuote");
  const abortBtn = document.getElementById("focusAbort");

  const doneEl = document.getElementById("focusDone");
  const dismissBtn = document.getElementById("focusDismiss");

  const QUOTES = [
    "Discipline is doing what you hate, like a boss.",
    "You're not procrastinating. You're marinating in potential.",
    "Eyes on the prize. The prize is finishing this without opening a new tab.",
    "Future you is already flexing. Don't let them down.",
    "They said you couldn't. They were probably right, but let's find out.",
    "Touch focus. Not your phone.",
    "The grind never stops. Mostly because it forgot where the brakes are.",
    "Blink if you've opened Discord. We'll wait.",
    "One task at a time. Multitasking is a myth invented by chaos.",
    "Deep breath. Then deeper work. Then deeper snacks.",
    "Productivity is 1% inspiration and 99% refusing to Google random things.",
    "You vs. the thing you said you'd do. Place your bets.",
  ];

  let current = bootstrap.current || null;
  let endsAtMs = current ? Date.parse(current.ends_at) : 0;
  let lastShownSessionId = null;
  let quoteTimer = null;
  let pollTimer = null;

  function showIdle() {
    btn.hidden = false;
    activeEl.hidden = true;
    doneEl.hidden = true;
  }
  function showActive() {
    btn.hidden = true;
    activeEl.hidden = false;
    doneEl.hidden = true;
    rotateQuote(true);
  }
  function showDone() {
    btn.hidden = true;
    activeEl.hidden = true;
    doneEl.hidden = false;
    if (quoteTimer) { clearInterval(quoteTimer); quoteTimer = null; }
  }

  function rotateQuote(start) {
    if (start) {
      quoteEl.textContent = QUOTES[Math.floor(Math.random() * QUOTES.length)];
      if (quoteTimer) clearInterval(quoteTimer);
      quoteTimer = setInterval(() => {
        quoteEl.textContent = QUOTES[Math.floor(Math.random() * QUOTES.length)];
      }, 12000);
    }
  }

  function renderTimer() {
    if (!current) return;
    const remaining = Math.max(0, Math.floor((endsAtMs - Date.now()) / 1000));
    const m = Math.floor(remaining / 60);
    const s = remaining % 60;
    timerEl.textContent = String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
    const names = current.members.map((m) => m.username).join(", ");
    metaEl.textContent = "locked in with " + (names || "just you") +
      " — " + current.duration_minutes + " min round";
    if (remaining <= 0) {
      showDone();
      current = null;
    }
  }

  function renderSessions(state) {
    const active = state.active || [];
    if (!active.length) {
      sessionsEl.innerHTML = '<li class="focus__empty">No one is locked in right now.</li>';
      return;
    }
    sessionsEl.innerHTML = "";
    for (const s of active) {
      const isMe = current && s.id === current.id;
      const li = document.createElement("li");
      li.className = "focus__session" + (isMe ? " is-mine" : "");
      const mins = Math.max(0, Math.ceil(s.remaining_seconds / 60));
      li.innerHTML =
        '<div class="focus__session-main">' +
          '<span class="focus__session-creator">' + escapeHtml(s.creator_username) + (isMe ? " (you)" : "") + '</span>' +
          '<span class="focus__session-meta">' + mins + ' min left · ' + s.member_count + ' locked in</span>' +
        '</div>';
      if (!isMe) {
        const join = document.createElement("button");
        join.type = "button";
        join.className = "focus__join";
        join.textContent = "Join";
        join.addEventListener("click", () => joinSession(s.id));
        li.appendChild(join);
      }
      sessionsEl.appendChild(li);
    }
  }

  async function startSession() {
    const duration = parseInt(durationInput.value, 10) || 25;
    const groupId = groupSelect.value ? parseInt(groupSelect.value, 10) : null;
    btn.disabled = true;
    try {
      const res = await fetch("/focus/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration, group_id: groupId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "start failed");
      current = data;
      endsAtMs = Date.parse(data.ends_at);
      lastShownSessionId = data.id;
      showActive();
      renderTimer();
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  }

  async function joinSession(id) {
    try {
      const res = await fetch("/focus/" + id + "/join", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "join failed");
      current = data;
      endsAtMs = Date.parse(data.ends_at);
      showActive();
      renderTimer();
    } catch (e) {
      alert(e.message);
    }
  }

  async function leaveSession() {
    if (!current) return;
    const id = current.id;
    try {
      await fetch("/focus/" + id + "/leave", { method: "POST" });
    } catch (_) {}
    current = null;
    showIdle();
  }

  async function poll() {
    try {
      const res = await fetch("/api/focus/state");
      const state = await res.json();
      // If our current session just completed server-side, reflect that.
      if (current) {
        const mine = (state.active || []).find((s) => s.id === current.id);
        if (!mine) {
          // session ended while we were in it → celebrate
          showDone();
          current = null;
          renderSessions(state);
          return;
        }
        current = mine;
        endsAtMs = Date.parse(mine.ends_at);
      } else {
        renderSessions(state);
      }
      renderSessions(state);
    } catch (_) {}
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // boot
  if (current) {
    showActive();
    renderTimer();
  } else {
    showIdle();
  }
  renderSessions(bootstrap);

  btn.addEventListener("click", startSession);
  abortBtn.addEventListener("click", leaveSession);
  dismissBtn.addEventListener("click", () => { current = null; showIdle(); poll(); });

  setInterval(renderTimer, 1000);
  pollTimer = setInterval(poll, 5000);
})();
