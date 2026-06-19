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

(function () {
  const form = document.querySelector('[data-todo-form]');
  if (!form) return;

  const categoryInput = form.querySelector('[data-category-input]');
  const dueInput = form.querySelector('[data-due-date-input]');
  const dueLabel = form.querySelector('[data-due-date-label]');
  const optionsToggle = form.querySelector('[data-options-toggle]');
  const optionsPanel = form.querySelector('#todoOptions');
  const calendarToggle = form.querySelector('[data-calendar-toggle]');
  const calendarPanel = form.querySelector('#todoCalendarPanel');
  const calendarLabel = form.querySelector('[data-calendar-label]');
  const calendarGrid = form.querySelector('[data-calendar-grid]');
  const prevBtn = form.querySelector('[data-calendar-prev]');
  const nextBtn = form.querySelector('[data-calendar-next]');

  const today = startOfDay(new Date());
  let selectedDate = null;
  let visibleMonth = new Date(today.getFullYear(), today.getMonth(), 1);

  optionsToggle?.addEventListener('click', () => {
    const expanded = optionsToggle.getAttribute('aria-expanded') === 'true';
    setOptionsExpanded(!expanded);
  });

  calendarToggle?.addEventListener('click', () => {
    const expanded = calendarToggle.getAttribute('aria-expanded') === 'true';
    setCalendarExpanded(!expanded);
  });

  form.querySelectorAll('[data-category-value]').forEach((button) => {
    button.addEventListener('click', () => {
      categoryInput.value = button.dataset.categoryValue || 'General';
      form.querySelectorAll('[data-category-value]').forEach((candidate) => {
        const selected = candidate === button;
        candidate.classList.toggle('is-selected', selected);
        candidate.setAttribute('aria-checked', selected ? 'true' : 'false');
      });
    });
  });

  form.querySelectorAll('[data-date-offset]').forEach((button) => {
    button.addEventListener('click', () => {
      const offset = Number(button.dataset.dateOffset || 0);
      const date = new Date(today);
      date.setDate(today.getDate() + offset);
      setSelectedDate(date);
      visibleMonth = new Date(date.getFullYear(), date.getMonth(), 1);
      setCalendarExpanded(false);
      renderCalendar();
    });
  });

  const clearButton = form.querySelector('[data-date-clear]');
  if (clearButton) {
    clearButton.addEventListener('click', () => {
      selectedDate = null;
      dueInput.value = '';
      dueLabel.textContent = 'No due date';
      setCalendarExpanded(false);
      updateQuickButtons();
      renderCalendar();
    });
  }

  prevBtn?.addEventListener('click', () => {
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1);
    renderCalendar();
  });

  nextBtn?.addEventListener('click', () => {
    visibleMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1);
    renderCalendar();
  });

  form.addEventListener('reset', () => {
    window.setTimeout(() => {
      categoryInput.value = 'General';
      selectedDate = null;
      dueInput.value = '';
      dueLabel.textContent = 'No due date';
      setOptionsExpanded(false);
      setCalendarExpanded(false);
      visibleMonth = new Date(today.getFullYear(), today.getMonth(), 1);
      form.querySelectorAll('[data-category-value]').forEach((button) => {
        const selected = button.dataset.categoryValue === 'General';
        button.classList.toggle('is-selected', selected);
        button.setAttribute('aria-checked', selected ? 'true' : 'false');
      });
      renderCalendar();
      updateQuickButtons();
    }, 0);
  });

  function setOptionsExpanded(expanded) {
    if (!optionsPanel || !optionsToggle) return;
    optionsPanel.hidden = !expanded;
    optionsToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    optionsToggle.setAttribute('aria-label', expanded ? 'Hide todo options' : 'Show todo options');
    optionsToggle.classList.toggle('is-open', expanded);
    if (!expanded) setCalendarExpanded(false);
  }

  function setCalendarExpanded(expanded) {
    if (!calendarPanel || !calendarToggle) return;
    calendarPanel.hidden = !expanded;
    calendarToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    calendarToggle.classList.toggle('is-open', expanded);
    if (expanded) renderCalendar();
  }

  function setSelectedDate(date) {
    selectedDate = startOfDay(date);
    dueInput.value = toISODate(selectedDate);
    dueLabel.textContent = formatDueDate(selectedDate);
    updateQuickButtons();
  }

  function renderCalendar() {
    if (!calendarGrid || !calendarLabel) return;

    calendarLabel.textContent = visibleMonth.toLocaleDateString(undefined, {
      month: 'long',
      year: 'numeric',
    });
    calendarGrid.innerHTML = '';

    const firstOfMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
    const mondayOffset = (firstOfMonth.getDay() + 6) % 7;
    const cursor = new Date(firstOfMonth);
    cursor.setDate(firstOfMonth.getDate() - mondayOffset);

    for (let i = 0; i < 42; i += 1) {
      const cellDate = new Date(cursor);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'date-cell';
      button.textContent = String(cellDate.getDate());
      button.dataset.date = toISODate(cellDate);

      if (cellDate.getMonth() !== visibleMonth.getMonth()) button.classList.add('is-outside');
      if (sameDay(cellDate, today)) button.classList.add('is-today');
      if (selectedDate && sameDay(cellDate, selectedDate)) button.classList.add('is-selected');

      button.addEventListener('click', () => {
        setSelectedDate(cellDate);
        setCalendarExpanded(false);
        renderCalendar();
      });

      calendarGrid.appendChild(button);
      cursor.setDate(cursor.getDate() + 1);
    }
  }

  function updateQuickButtons() {
    form.querySelectorAll('[data-date-offset]').forEach((button) => {
      const offset = Number(button.dataset.dateOffset || 0);
      const date = new Date(today);
      date.setDate(today.getDate() + offset);
      button.classList.toggle('is-selected', !!selectedDate && sameDay(date, selectedDate));
    });
    clearButton?.classList.toggle('is-selected', !selectedDate);
  }

  function startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
  }

  function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear()
      && a.getMonth() === b.getMonth()
      && a.getDate() === b.getDate();
  }

  function toISODate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function formatDueDate(date) {
    if (sameDay(date, today)) return 'Due today';

    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    if (sameDay(date, tomorrow)) return 'Due tomorrow';

    return `Due ${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
  }

  renderCalendar();
  updateQuickButtons();
})();
