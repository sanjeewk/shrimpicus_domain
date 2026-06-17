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
      const status = col.className.match(/column--(\w+)/)[1];
      const pill = document.querySelector(`.pill--${status}`);
      if (pill) {
        const label = pill.textContent.split('·')[0].trim();
        pill.textContent = `${label} · ${list.children.length}`;
      }
    });
  }

  // Expose updateColumnCounts globally for delete functions
  window.updateColumnCounts = updateColumnCounts;
})();

// Delete single todo
async function deleteTodo(id) {
  if (!confirm('Delete this todo?')) return;

  const card = document.querySelector(`.card[data-id="${id}"]`);
  if (!card) return;

  card.classList.add('is-saving');

  try {
    const res = await fetch(`/todos/${id}/delete`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`status ${res.status}`);
    card.remove();
    if (window.updateColumnCounts) window.updateColumnCounts();
  } catch (err) {
    card.classList.remove('is-saving');
    card.classList.add('is-error');
    alert('Failed to delete todo');
    console.error('Failed to delete todo', err);
  }
}

// Delete all completed todos
async function deleteAllDone() {
  const doneCards = document.querySelectorAll('.column--done .card');
  if (doneCards.length === 0) return;

  if (!confirm(`Delete all ${doneCards.length} completed todos?`)) return;

  try {
    const res = await fetch('/todos/delete_all_done', {
      method: 'POST',
    });
    if (!res.ok) throw new Error(`status ${res.status}`);
    doneCards.forEach(card => card.remove());
    if (window.updateColumnCounts) window.updateColumnCounts();
  } catch (err) {
    alert('Failed to delete completed todos');
    console.error('Failed to delete completed todos', err);
  }
}
