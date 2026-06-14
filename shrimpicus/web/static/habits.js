(function () {
  const list = document.querySelector(".habit-list");
  if (!list) return;

  const doneTodayEl = document.querySelector(".js-done-today");

  // Handle day button clicks
  list.addEventListener("click", async (e) => {
    const dayBtn = e.target.closest(".habit-day");
    if (dayBtn) {
      await toggleSpecificDay(dayBtn);
      return;
    }

    const deleteBtn = e.target.closest(".habit-delete");
    if (deleteBtn) {
      await deleteHabit(deleteBtn);
      return;
    }
  });

  async function toggleSpecificDay(dayBtn) {
    const row = dayBtn.closest(".habit-row");
    const id = row.dataset.id;
    const date = dayBtn.dataset.date;
    const habitColor = row.dataset.color;

    if (!date || row.classList.contains("is-saving")) return;

    row.classList.add("is-saving");
    row.style.opacity = "0.6";

    try {
      const res = await fetch(`/api/habits/${id}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date })
      });

      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = await res.json();

      applyState(row, data, habitColor);

      // Update done-today counter if we toggled today
      const today = new Date().toISOString().split("T")[0];
      if (date === today && doneTodayEl) {
        const wasDone = dayBtn.classList.contains("is-checked");
        const nowDone = data.done_today;
        if (wasDone !== nowDone) {
          const n = parseInt(doneTodayEl.textContent, 10) || 0;
          doneTodayEl.textContent = String(Math.max(0, n + (nowDone ? 1 : -1)));
        }
      }
    } catch (err) {
      console.error("Failed to toggle habit day", err);
      alert("Failed to update habit. Please try again.");
    } finally {
      row.classList.remove("is-saving");
      row.style.opacity = "";
    }
  }

  async function deleteHabit(deleteBtn) {
    const row = deleteBtn.closest(".habit-row");
    const id = row.dataset.id;
    const name = row.querySelector(".habit-name").textContent;

    if (!confirm(`Delete habit "${name}"?`)) return;

    row.style.opacity = "0.5";

    try {
      const chatId = new URLSearchParams(window.location.search).get("chat") || "";
      const formData = new FormData();
      formData.append("chat", chatId);

      const res = await fetch(`/habits/${id}/delete`, {
        method: "POST",
        body: formData
      });

      if (!res.ok) throw new Error(`status ${res.status}`);

      // Redirect to refresh the page
      window.location.reload();
    } catch (err) {
      console.error("Failed to delete habit", err);
      alert("Failed to delete habit. Please try again.");
      row.style.opacity = "";
    }
  }

  function applyState(row, data, habitColor) {
    row.classList.toggle("goal-met", data.goal_met);

    // Update goal progress
    const goalEl = row.querySelector(".habit-goal");
    if (goalEl && data.week_count !== undefined) {
      const goal = row.dataset.weeklyGoal || 7;
      goalEl.textContent = `${data.week_count}/${goal} this week`;
    }

    // Update all 7 day cells
    const days = row.querySelectorAll(".habit-day");
    if (data.last7 && days.length === data.last7.length) {
      days.forEach((dayCell, i) => {
        dayCell.classList.toggle("is-checked", data.last7[i].done);
        // Apply habit color to checked circles
        const circle = dayCell.querySelector(".day-circle");
        if (circle && data.last7[i].done) {
          circle.style.setProperty("--habit-color", habitColor);
          circle.style.background = habitColor;
          circle.style.borderColor = habitColor;
        } else if (circle) {
          circle.style.background = "";
          circle.style.borderColor = "";
        }
      });
    }
  }

  // Initialize habit colors on page load
  document.querySelectorAll(".habit-row").forEach(row => {
    const color = row.dataset.color;
    row.querySelectorAll(".habit-day.is-checked .day-circle").forEach(circle => {
      circle.style.setProperty("--habit-color", color);
      circle.style.background = color;
      circle.style.borderColor = color;
    });
  });
})();
