(function () {
  const lists = document.querySelectorAll(".column__list");
  if (!lists.length || typeof Sortable === "undefined") return;

  lists.forEach((list) => {
    Sortable.create(list, {
      group: "kanban",
      animation: 140,
      ghostClass: "sortable-ghost",
      chosenClass: "sortable-chosen",
      dragClass: "sortable-drag",
      onEnd: handleEnd,
    });
  });

  async function handleEnd(evt) {
    const card = evt.item;
    const newList = evt.to;
    const oldList = evt.from;
    const newStatus = newList.dataset.status;
    const oldStatus = oldList.dataset.status;
    if (!newStatus || newStatus === card.dataset.status) return;

    const id = card.dataset.id;
    card.classList.add("is-saving");
    card.classList.remove("is-error");

    try {
      const res = await fetch(`/api/todos/${id}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
      card.dataset.status = newStatus;
      updateColumnCounts();
    } catch (err) {
      card.classList.add("is-error");
      oldList.appendChild(card);
      console.error("Failed to update status", err);
    } finally {
      card.classList.remove("is-saving");
    }
  }

  function updateColumnCounts() {
    document.querySelectorAll(".column").forEach((col) => {
      const list = col.querySelector(".column__list");
      const count = col.querySelector(".column__count");
      if (list && count) count.textContent = list.children.length;
    });
    const todoCount = document.querySelectorAll('[data-status="to_do"] .card').length
      || document.querySelectorAll('.column__list[data-status="to_do"] .card').length;
    const todoPill = document.querySelector(".pill--todo");
    const doingPill = document.querySelector(".pill--doing");
    const donePill = document.querySelector(".pill--done");
    const counts = {
      to_do: document.querySelector('.column__list[data-status="to_do"]').children.length,
      doing: document.querySelector('.column__list[data-status="doing"]').children.length,
      done:  document.querySelector('.column__list[data-status="done"]').children.length,
    };
    if (todoPill)  todoPill.textContent  = `To do · ${counts.to_do}`;
    if (doingPill) doingPill.textContent = `Doing · ${counts.doing}`;
    if (donePill)  donePill.textContent  = `Done · ${counts.done}`;
  }
})();
