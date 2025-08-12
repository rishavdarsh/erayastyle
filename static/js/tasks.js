// Minimal Kanban drag/drop with SortableJS + optimistic updates
(function () {
  function initBoard(boardEl) {
    const board = boardEl.dataset.board;
    boardEl.querySelectorAll('.kanban-col').forEach(function (col) {
      const status = col.dataset.status;
      new Sortable(col, {
        group: 'kanban-' + board,
        animation: 150,
        onAdd: function (evt) {
          const card = evt.item;
          const taskId = card.dataset.taskId;
          const toStatus = evt.to.dataset.status;
          const toBoard = evt.to.closest('[data-board]')?.dataset.board;

          // optimistic: already moved in DOM; send request
          fetch(`/api/tasks/${taskId}/move`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to_status: toStatus, to_board: toBoard })
          }).then(async (res) => {
            if (!res.ok) {
              const data = await res.json().catch(() => ({}));
              alert(data.detail || 'Failed to move task');
              // rollback
              evt.from.insertBefore(card, evt.from.children[evt.oldIndex] || null);
            }
          }).catch((e) => {
            alert('Network error');
            evt.from.insertBefore(card, evt.from.children[evt.oldIndex] || null);
          });
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-board]').forEach(initBoard);

    // basic websocket notifications
    try {
      const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/notifications');
      ws.onmessage = function (evt) {
        try {
          const msg = JSON.parse(evt.data);
          if (msg && msg.type === 'TASK_UPDATED') {
            console.log('Notification:', msg);
          }
        } catch (e) {}
      };
    } catch (e) {}
  });
})();


