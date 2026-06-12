(function () {
  const list = document.querySelector(".habit-list");
  if (!list) return;

  const doneTodayEl = document.querySelector(".js-done-today");

  list.addEventListener("click", async (e) => {
    const btn = e.target.closest(".habit__check");
    if (btn) {
      await toggleToday(btn);
      return;
    }

    const dayBtn = e.target.closest(".habit__day");
    if (dayBtn) {
      await toggleSpecificDay(dayBtn);
      return;
    }
  });

  async function toggleToday(btn) {
    const item = btn.closest(".habit");
    const id = item.dataset.id;
    if (item.classList.contains("is-saving")) return;

    item.classList.add("is-saving");
    item.classList.remove("is-error");
    try {
      const res = await fetch(`/api/habits/${id}/toggle`, { method: "POST" });
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = await res.json();
      applyState(item, data);
      bumpDoneToday(data.done_today);
    } catch (err) {
      item.classList.add("is-error");
      console.error("Failed to toggle habit", err);
    } finally {
      item.classList.remove("is-saving");
    }
  }

  async function toggleSpecificDay(dayBtn) {
    const item = dayBtn.closest(".habit");
    const id = item.dataset.id;
    const date = dayBtn.dataset.date;
    if (!date || item.classList.contains("is-saving")) return;

    item.classList.add("is-saving");
    item.classList.remove("is-error");
    try {
      const res = await fetch(`/api/habits/${id}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date })
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = await res.json();
      applyState(item, data);
      // Only bump today counter if we toggled today
      const today = new Date().toISOString().split("T")[0];
      if (date === today) {
        bumpDoneToday(data.done_today);
      }
    } catch (err) {
      item.classList.add("is-error");
      console.error("Failed to toggle habit day", err);
    } finally {
      item.classList.remove("is-saving");
    }
  }

  function applyState(item, data) {
    item.classList.toggle("is-done", data.done_today);
    item.classList.toggle("goal-met", data.goal_met);
    const btn = item.querySelector(".habit__check");
    btn.setAttribute("aria-pressed", data.done_today ? "true" : "false");

    const cur = item.querySelector(".js-current");
    const best = item.querySelector(".js-best");
    if (cur) cur.textContent = data.current_streak;
    if (best) best.textContent = data.longest_streak;

    // Update goal progress
    const progressEl = item.querySelector(".habit__goal-progress");
    if (progressEl && data.week_count !== undefined) {
      const goal = item.dataset.weeklyGoal || 7;
      progressEl.textContent = `${data.week_count}/${goal}`;
    }

    // Update all 7 day cells from the returned last7 data
    const days = item.querySelectorAll(".habit__day");
    if (data.last7 && days.length === data.last7.length) {
      days.forEach((dayCell, i) => {
        dayCell.classList.toggle("is-on", data.last7[i].done);
      });
    }

    // Toggle duck visibility
    let duck = item.querySelector(".habit__duck");
    if (data.goal_met && !duck) {
      // Insert duck if goal just met
      const nameEl = item.querySelector(".habit__name");
      duck = document.createElement("span");
      duck.className = "habit__duck";
      duck.setAttribute("aria-label", "Goal achieved!");
      duck.setAttribute("title", "Weekly goal achieved!");
      duck.innerHTML = `<svg viewBox="0 0 32 32" width="20" height="20" class="duck-spin">
        <ellipse cx="16" cy="20" rx="9" ry="7" fill="#fbbf24"/>
        <circle cx="16" cy="13" r="6" fill="#fbbf24"/>
        <ellipse cx="9" cy="12" rx="3" ry="2.5" fill="#fbbf24"/>
        <circle cx="14" cy="12" r="1.5" fill="#1a0d2e"/>
        <circle cx="18" cy="12" r="1.5" fill="#1a0d2e"/>
        <path d="M 8 12 Q 5 12 4 13" stroke="#ff570a" stroke-width="1.5" fill="none"/>
      </svg>`;
      nameEl.appendChild(duck);
    } else if (!data.goal_met && duck) {
      // Remove duck if goal no longer met
      duck.remove();
    }
  }

  function bumpDoneToday(nowDone) {
    if (!doneTodayEl) return;
    const n = parseInt(doneTodayEl.textContent, 10) || 0;
    doneTodayEl.textContent = String(Math.max(0, n + (nowDone ? 1 : -1)));
  }
})();
