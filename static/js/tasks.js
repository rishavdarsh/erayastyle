// Enhanced Kanban with animations and better UX
(function () {
  let draggedCard = null;
  let dragStartColumn = null;

  function initBoard(boardEl) {
    const board = boardEl.dataset.board;
    boardEl.querySelectorAll('.kanban-col').forEach(function (col) {
      const status = col.dataset.status;
      
      new Sortable(col, {
        group: 'kanban-' + board,
        animation: 200,
        ghostClass: 'opacity-50',
        chosenClass: 'scale-105',
        dragClass: 'rotate-3',
        
        onStart: function (evt) {
          draggedCard = evt.item;
          dragStartColumn = evt.from;
          
          // Add visual feedback
          document.querySelectorAll('.kanban-col').forEach(col => {
            if (col !== evt.from) {
              col.classList.add('drag-over');
            }
          });
        },
        
        onEnd: function (evt) {
          // Remove visual feedback
          document.querySelectorAll('.kanban-col').forEach(col => {
            col.classList.remove('drag-over');
          });
          
          draggedCard = null;
          dragStartColumn = null;
        },
        
        onAdd: function (evt) {
          const card = evt.item;
          const taskId = card.dataset.taskId;
          const toStatus = evt.to.dataset.status;
          const toBoard = evt.to.closest('[data-board]')?.dataset.board;

          // Add loading state
          card.style.opacity = '0.7';
          card.style.pointerEvents = 'none';
          
          // Show loading indicator
          const loader = document.createElement('div');
          loader.className = 'absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg';
          loader.innerHTML = '<div class="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin"></div>';
          card.style.position = 'relative';
          card.appendChild(loader);

          // Send update request
          fetch(`/api/tasks/${taskId}/move`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to_status: toStatus, to_board: toBoard })
          }).then(async (res) => {
            if (!res.ok) {
              const data = await res.json().catch(() => ({}));
              showNotification(data.detail || 'Failed to move task', 'error');
              
              // Rollback with animation
              card.style.transform = 'scale(0.8)';
              setTimeout(() => {
                evt.from.insertBefore(card, evt.from.children[evt.oldIndex] || null);
                card.style.transform = 'scale(1)';
                card.style.opacity = '1';
                card.style.pointerEvents = 'auto';
                if (loader.parentNode) loader.remove();
              }, 200);
            } else {
              // Success animation
              card.style.transform = 'scale(1.05)';
              setTimeout(() => {
                card.style.transform = 'scale(1)';
                card.style.opacity = '1';
                card.style.pointerEvents = 'auto';
                if (loader.parentNode) loader.remove();
              }, 300);
              
              showNotification('Task moved successfully! ✨', 'success');
              updateColumnCounts();
            }
          }).catch((e) => {
            showNotification('Network error occurred', 'error');
            
            // Rollback
            evt.from.insertBefore(card, evt.from.children[evt.oldIndex] || null);
            card.style.opacity = '1';
            card.style.pointerEvents = 'auto';
            if (loader.parentNode) loader.remove();
          });
        }
      });
    });
  }

  function updateColumnCounts() {
    document.querySelectorAll('.kanban-col').forEach(col => {
      const count = col.querySelectorAll('[data-task-id]').length;
      const countBadge = col.parentElement.querySelector('[class*="rounded-full"]');
      if (countBadge) {
        countBadge.textContent = count;
      }
    });
  }

  function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg transform translate-x-full transition-all duration-300 z-50 ${
      type === 'success' ? 'bg-green-500' : 
      type === 'error' ? 'bg-red-500' : 
      'bg-blue-500'
    } text-white font-medium`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
      notification.style.transform = 'translateX(0)';
    }, 100);
    
    // Animate out
    setTimeout(() => {
      notification.style.transform = 'translateX(100%)';
      setTimeout(() => {
        if (notification.parentNode) {
          notification.remove();
        }
      }, 300);
    }, 3000);
  }

  function initTaskCards() {
    document.querySelectorAll('[data-task-id]').forEach(card => {
      // Add click handler for task details
      card.addEventListener('click', function(e) {
        if (e.target.closest('button')) return; // Don't trigger on button clicks
        
        // Add subtle animation
        card.style.transform = 'scale(0.98)';
        setTimeout(() => {
          card.style.transform = 'scale(1)';
        }, 150);
        
        // Could open task details modal here
        console.log('Task clicked:', card.dataset.taskId);
      });
      
      // Add hover effects
      card.addEventListener('mouseenter', function() {
        card.style.transform = 'translateY(-2px)';
      });
      
      card.addEventListener('mouseleave', function() {
        card.style.transform = 'translateY(0)';
      });
    });
  }

  // Initialize everything
  document.addEventListener('DOMContentLoaded', function () {
    // Initialize kanban boards
    document.querySelectorAll('[data-board]').forEach(initBoard);
    
    // Initialize task cards
    initTaskCards();
    
    // Update column counts on load
    updateColumnCounts();

    // Enhanced WebSocket notifications
    try {
      const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/notifications');
      
      ws.onopen = function() {
        console.log('🔗 Connected to task notifications');
      };
      
      ws.onmessage = function (evt) {
        try {
          const msg = JSON.parse(evt.data);
          if (msg && msg.type === 'TASK_UPDATED') {
            showNotification(`📋 ${msg.message || 'Task updated'}`, 'info');
            
            // Could refresh specific task card here
            console.log('Task notification:', msg);
          }
        } catch (e) {
          console.error('Failed to parse notification:', e);
        }
      };
      
      ws.onclose = function() {
        console.log('📡 Disconnected from notifications');
      };
    } catch (e) {
      console.error('WebSocket connection failed:', e);
    }

    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
      // Ctrl/Cmd + K for quick task search (future feature)
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        showNotification('⌨️ Quick search coming soon!', 'info');
      }
    });

    // Add smooth scrolling for long pages
    document.documentElement.style.scrollBehavior = 'smooth';
  });

  // Expose utilities globally
  window.taskUtils = {
    showNotification,
    updateColumnCounts
  };
})();

// ---- File Attachment Functions ----
function downloadAttachment(attachmentId) {
  window.open(`/api/attachments/${attachmentId}/download`, '_blank');
}

function uploadFileToTask(taskId, fileInput) {
  const file = fileInput.files[0];
  if (!file) {
    taskUtils.showNotification('Please select a file', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  // Show upload progress
  const uploadBtn = fileInput.parentElement.querySelector('.upload-btn');
  const originalText = uploadBtn.textContent;
  uploadBtn.textContent = 'Uploading...';
  uploadBtn.disabled = true;

  fetch(`/api/tasks/${taskId}/upload`, {
    method: 'POST',
    body: formData
  })
  .then(response => {
    if (!response.ok) {
      return response.json().then(err => Promise.reject(err));
    }
    return response.json();
  })
  .then(data => {
    taskUtils.showNotification(`✅ File "${data.filename}" uploaded successfully!`, 'success');
    
    // Reset file input
    fileInput.value = '';
    
    // Refresh the page to show new attachment
    setTimeout(() => {
      window.location.reload();
    }, 1000);
  })
  .catch(error => {
    console.error('Upload error:', error);
    taskUtils.showNotification(`❌ Upload failed: ${error.detail || 'Unknown error'}`, 'error');
  })
  .finally(() => {
    uploadBtn.textContent = originalText;
    uploadBtn.disabled = false;
  });
}

function deleteAttachment(attachmentId, filename) {
  if (!confirm(`Are you sure you want to delete "${filename}"?`)) {
    return;
  }

  fetch(`/api/attachments/${attachmentId}`, {
    method: 'DELETE'
  })
  .then(response => {
    if (!response.ok) {
      return response.json().then(err => Promise.reject(err));
    }
    return response.json();
  })
  .then(data => {
    taskUtils.showNotification(`✅ File "${filename}" deleted successfully!`, 'success');
    
    // Refresh the page to update attachments
    setTimeout(() => {
      window.location.reload();
    }, 1000);
  })
  .catch(error => {
    console.error('Delete error:', error);
    taskUtils.showNotification(`❌ Delete failed: ${error.detail || 'Unknown error'}`, 'error');
  });
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function getFileIcon(mimeType) {
  if (mimeType.startsWith('image/')) return '🖼️';
  if (mimeType.startsWith('video/')) return '🎥';
  if (mimeType.startsWith('audio/')) return '🎵';
  if (mimeType.includes('pdf')) return '📄';
  if (mimeType.includes('word') || mimeType.includes('document')) return '📝';
  if (mimeType.includes('sheet') || mimeType.includes('excel')) return '📊';
  if (mimeType.includes('zip') || mimeType.includes('rar')) return '🗜️';
  return '📎';
}

// Expose attachment functions globally
window.downloadAttachment = downloadAttachment;
window.uploadFileToTask = uploadFileToTask;
window.deleteAttachment = deleteAttachment;
window.formatFileSize = formatFileSize;
window.getFileIcon = getFileIcon;

// ---- Advanced Filtering & Search Functions ----
let currentFilters = {
  search: '',
  priority: '',
  status: '',
  dueDate: '',
  smartFilter: ''
};

function filterTasks() {
  const searchTerm = document.getElementById('searchInput')?.value.toLowerCase() || '';
  const priorityFilter = document.getElementById('priorityFilter')?.value || '';
  const statusFilter = document.getElementById('statusFilter')?.value || '';
  const dueDateFilter = document.getElementById('dueDateFilter')?.value || '';

  currentFilters = {
    search: searchTerm,
    priority: priorityFilter,
    status: statusFilter,
    dueDate: dueDateFilter,
    smartFilter: ''
  };

  applyFilters();
}

function applySmartFilter(filterType) {
  // Clear other filters
  document.getElementById('searchInput').value = '';
  document.getElementById('priorityFilter').value = '';
  document.getElementById('statusFilter').value = '';
  document.getElementById('dueDateFilter').value = '';

  // Update active chip
  document.querySelectorAll('.smart-filter-chip').forEach(chip => {
    chip.classList.remove('active');
  });
  event.target.classList.add('active');

  currentFilters = {
    search: '',
    priority: '',
    status: '',
    dueDate: '',
    smartFilter: filterType
  };

  applyFilters();
}

function clearFilters() {
  document.getElementById('searchInput').value = '';
  document.getElementById('priorityFilter').value = '';
  document.getElementById('statusFilter').value = '';
  document.getElementById('dueDateFilter').value = '';
  
  document.querySelectorAll('.smart-filter-chip').forEach(chip => {
    chip.classList.remove('active');
  });

  currentFilters = {
    search: '',
    priority: '',
    status: '',
    dueDate: '',
    smartFilter: ''
  };

  applyFilters();
}

function applyFilters() {
  const taskCards = document.querySelectorAll('.task-card');
  let visibleCount = 0;

  taskCards.forEach(card => {
    const shouldShow = shouldShowTask(card);
    
    if (shouldShow) {
      card.classList.remove('filtered-out');
      card.classList.add('filtered-in');
      visibleCount++;
    } else {
      card.classList.remove('filtered-in');
      card.classList.add('filtered-out');
    }
  });

  // Update result count
  updateFilterResultCount(visibleCount, taskCards.length);
}

function shouldShowTask(taskCard) {
  const taskData = extractTaskData(taskCard);
  
  // Search filter
  if (currentFilters.search) {
    const searchLower = currentFilters.search.toLowerCase();
    if (!taskData.title.toLowerCase().includes(searchLower) &&
        !taskData.description.toLowerCase().includes(searchLower) &&
        !taskData.tags.some(tag => tag.toLowerCase().includes(searchLower))) {
      return false;
    }
  }

  // Priority filter
  if (currentFilters.priority && taskData.priority !== currentFilters.priority) {
    return false;
  }

  // Status filter
  if (currentFilters.status && taskData.status !== currentFilters.status) {
    return false;
  }

  // Due date filter
  if (currentFilters.dueDate) {
    if (!matchesDueDateFilter(taskData.dueDate, currentFilters.dueDate)) {
      return false;
    }
  }

  // Smart filters
  if (currentFilters.smartFilter) {
    return matchesSmartFilter(taskData, currentFilters.smartFilter);
  }

  return true;
}

function extractTaskData(taskCard) {
  const titleEl = taskCard.querySelector('h4');
  const descEl = taskCard.querySelector('p');
  const priorityEl = taskCard.querySelector('[class*="priority-"], [class*="bg-red-"], [class*="bg-orange-"], [class*="bg-blue-"], [class*="bg-gray-"]');
  const statusEl = taskCard.querySelector('[class*="status-"]');
  const dueDateEl = taskCard.querySelector('[class*="text-red-400"], [class*="text-white/70"]');
  const tagsEls = taskCard.querySelectorAll('[class*="rounded-full"][class*="bg-white/"]');

  return {
    title: titleEl?.textContent || '',
    description: descEl?.textContent || '',
    priority: extractPriorityFromElement(priorityEl),
    status: extractStatusFromElement(taskCard),
    dueDate: extractDueDateFromElement(dueDateEl),
    tags: Array.from(tagsEls).map(el => el.textContent.trim()).filter(Boolean)
  };
}

function extractPriorityFromElement(element) {
  if (!element) return '';
  const text = element.textContent;
  if (text.includes('🔥') || text.includes('URGENT')) return 'URGENT';
  if (text.includes('⚡') || text.includes('HIGH')) return 'HIGH';
  if (text.includes('📋') || text.includes('MEDIUM')) return 'MEDIUM';
  if (text.includes('📝') || text.includes('LOW')) return 'LOW';
  return '';
}

function extractStatusFromElement(taskCard) {
  const statusText = taskCard.textContent;
  if (statusText.includes('Ready to start') || statusText.includes('TODO')) return 'TODO';
  if (statusText.includes('In Progress') || statusText.includes('IN_PROGRESS')) return 'IN_PROGRESS';
  if (statusText.includes('Under Review') || statusText.includes('REVIEW')) return 'REVIEW';
  if (statusText.includes('Completed') || statusText.includes('DONE')) return 'DONE';
  if (statusText.includes('Backlog') || statusText.includes('BACKLOG')) return 'BACKLOG';
  return '';
}

function extractDueDateFromElement(element) {
  if (!element || element.textContent.includes('No due date')) return null;
  // This is a simplified extraction - in a real app you'd parse the actual date
  return new Date(); // Placeholder
}

function matchesDueDateFilter(dueDate, filter) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const weekFromNow = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000);

  switch (filter) {
    case 'overdue':
      return dueDate && dueDate < today;
    case 'today':
      return dueDate && dueDate.toDateString() === today.toDateString();
    case 'week':
      return dueDate && dueDate >= today && dueDate <= weekFromNow;
    case 'none':
      return !dueDate;
    default:
      return true;
  }
}

function matchesSmartFilter(taskData, filterType) {
  const now = new Date();
  
  switch (filterType) {
    case 'my-overdue':
      return taskData.dueDate && taskData.dueDate < now && taskData.status !== 'DONE';
    case 'high-priority':
      return taskData.priority === 'URGENT' || taskData.priority === 'HIGH';
    case 'due-soon':
      const threeDaysFromNow = new Date(now.getTime() + 3 * 24 * 60 * 60 * 1000);
      return taskData.dueDate && taskData.dueDate <= threeDaysFromNow && taskData.dueDate >= now;
    case 'in-progress':
      return taskData.status === 'IN_PROGRESS';
    case 'no-assignee':
      return taskData.assignee === 'Unassigned';
    default:
      return true;
  }
}

function updateFilterResultCount(visible, total) {
  let countEl = document.getElementById('filterResultCount');
  if (!countEl) {
    countEl = document.createElement('div');
    countEl.id = 'filterResultCount';
    countEl.className = 'text-sm text-white/60 mt-2';
    document.querySelector('.glass').appendChild(countEl);
  }
  
  if (visible === total) {
    countEl.textContent = `Showing all ${total} tasks`;
  } else {
    countEl.textContent = `Showing ${visible} of ${total} tasks`;
  }
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  // Ctrl+K or Cmd+K to focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }
  
  // Escape to clear filters or close modal
  if (e.key === 'Escape') {
    if (currentTaskId) {
      closeTaskModal();
    } else {
      clearFilters();
    }
  }
});

// Expose filtering functions globally
window.filterTasks = filterTasks;
window.applySmartFilter = applySmartFilter;
window.clearFilters = clearFilters;

// ---- Task Modal Functions ----
let currentTaskId = null;

async function openTaskModal(taskId) {
  currentTaskId = taskId;
  const modal = document.getElementById('taskModal');
  
  // Show modal with animation
  modal.classList.remove('hidden');
  modal.classList.add('flex');
  
  // Animate in
  setTimeout(() => {
    modal.querySelector('.bg-slate-900').classList.add('animate-slide-in');
  }, 10);
  
  // Load task details
  await loadTaskDetails(taskId);
  await loadTaskComments(taskId);
  
  // Setup comment form
  setupCommentForm(taskId);
  
  // Prevent body scroll
  document.body.style.overflow = 'hidden';
}

function closeTaskModal() {
  const modal = document.getElementById('taskModal');
  
  // Animate out
  modal.querySelector('.bg-slate-900').classList.remove('animate-slide-in');
  
  setTimeout(() => {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.style.overflow = 'auto';
    currentTaskId = null;
  }, 300);
}

async function loadTaskDetails(taskId) {
  try {
    const response = await fetch(`/api/tasks/${taskId}`);
    if (!response.ok) throw new Error('Failed to load task');
    
    const task = await response.json();
    // Load users for assignee dropdown
    let users = [];
    try {
      const usersResp = await fetch('/api/users');
      if (usersResp.ok) users = await usersResp.json();
    } catch (_) {}

    // Update modal title
    document.getElementById('modalTitle').textContent = task.title;
    
    // Load task details
    const detailsContainer = document.getElementById('taskDetails');
    detailsContainer.innerHTML = `
      <div class="space-y-6">
        <!-- Title & Status -->
        <div class="flex items-center justify-between">
          <input id="taskTitleInput" value="${task.title}" class="text-2xl font-bold bg-transparent border-b border-transparent focus:border-white/30 outline-none" />
          <select id="statusSelect" class="form-input select-modern select-status px-3 py-1 rounded-full text-sm font-medium">
            ${['TODO','IN_PROGRESS','REVIEW','DONE','BACKLOG'].map(s => `<option value="${s}" ${task.status===s?'selected':''}>${s.replace('_',' ')}</option>`).join('')}
          </select>
        </div>
        
        <!-- Description -->
        <div>
          <h4 class="font-semibold mb-2">Description</h4>
          <textarea id="descInput" class="w-full bg-white/5 p-4 rounded-lg outline-none border border-white/10 focus:border-purple-400" rows="4">${task.description || ''}</textarea>
        </div>
        
        <!-- Task Info Grid -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <h4 class="font-semibold mb-2">Priority</h4>
            <select id="prioritySelect" class="form-input select-modern select-priority inline-flex items-center gap-2 px-3 py-1 rounded-lg">
              ${['URGENT','HIGH','MEDIUM','LOW'].map(p => `<option value="${p}" ${task.priority===p?'selected':''}>${p}</option>`).join('')}
            </select>
          </div>
          
          <div>
            <h4 class="font-semibold mb-2">Assigned To</h4>
            <select id="assigneeSelect" class="form-input select-modern select-assignee px-3 py-1 rounded-lg w-full">
              ${users.map(u => `<option value="${u.id}" ${task.assigned_to && task.assigned_to.id===u.id?'selected':''}>${u.name}</option>`).join('')}
            </select>
          </div>
          
          <div>
            <h4 class="font-semibold mb-2">Due Date</h4>
            <input id="dueDateInput" type="date" class="form-input px-3 py-1" value="${task.due_date? new Date(task.due_date).toISOString().slice(0,10):''}" />
          </div>
          
          <div>
            <h4 class="font-semibold mb-2">Created By</h4>
            <span class="text-white/70">${task.created_by?.name || 'Unknown'}</span>
          </div>
        </div>
        
        <!-- Tags -->
        ${task.tags && task.tags.length > 0 ? `
        <div>
          <h4 class="font-semibold mb-2">Tags</h4>
          <div class="flex flex-wrap gap-2">
            ${task.tags.map(tag => `
              <span class="px-2 py-1 bg-white/10 rounded-full text-xs border border-white/20">
                🏷️ ${tag}
              </span>
            `).join('')}
          </div>
        </div>
        ` : ''}
        
        <!-- Attachments -->
        <div>
          <h4 class="font-semibold mb-2">Attachments</h4>
          <div id="attachmentsList">
            <div class="text-white/50 text-sm">Loading attachments...</div>
          </div>
          <input type="file" id="modalFilePicker" class="hidden" onchange="uploadFileToTask('${taskId}', this)" />
        </div>
        
        <!-- Actions -->
        <div class="flex gap-3 pt-4 border-t border-white/10">
          <button onclick="editTask('${taskId}')" class="btn btn-secondary flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
            </svg>
            Edit Task
          </button>
          
          <button onclick="uploadToTask('${taskId}')" class="btn btn-secondary flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"></path>
            </svg>
            Add Attachment
          </button>
          
          <button onclick="deleteTaskFromModal('${taskId}', '${task.title}')" class="btn bg-red-600 hover:bg-red-700 text-white flex items-center gap-2 ml-auto">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
            </svg>
            Delete Task
          </button>
        </div>
      </div>
    `;
    
    // Load attachments
    loadTaskAttachments(taskId);
    // Wire inline edit handlers
    document.getElementById('taskTitleInput').addEventListener('blur', () => updateTaskField(taskId, { title: document.getElementById('taskTitleInput').value.trim() }));
    document.getElementById('descInput').addEventListener('blur', () => updateTaskField(taskId, { description: document.getElementById('descInput').value }));
    document.getElementById('prioritySelect').addEventListener('change', (e) => updateTaskField(taskId, { priority: e.target.value }));
    const assigneeEl = document.getElementById('assigneeSelect');
    if (assigneeEl) assigneeEl.addEventListener('change', (e) => updateTaskField(taskId, { assigned_to_id: e.target.value }));
    document.getElementById('dueDateInput').addEventListener('change', (e) => updateTaskField(taskId, { due_date: e.target.value }));
    document.getElementById('statusSelect').addEventListener('change', (e) => moveTaskStatus(taskId, e.target.value));
    
  } catch (error) {
    console.error('Error loading task details:', error);
    taskUtils.showNotification('Failed to load task details', 'error');
  }
}

async function loadTaskComments(taskId) {
  try {
    const response = await fetch(`/api/tasks/${taskId}/comments`);
    if (!response.ok) throw new Error('Failed to load comments');
    
    const comments = await response.json();
    const commentsList = document.getElementById('commentsList');
    
    if (comments.length === 0) {
      commentsList.innerHTML = '<div class="text-white/50 text-sm text-center py-8">No comments yet</div>';
      return;
    }
    
    commentsList.innerHTML = comments.map(comment => `
      <div class="bg-white/5 p-3 rounded-lg">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <div class="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center text-xs font-bold">
              ${comment.author_name[0]}
            </div>
            <span class="font-medium text-sm">${comment.author_name}</span>
            ${comment.mentions && comment.mentions.length > 0 ? `<span class="text-xs text-blue-300">mentioned ${comment.mentions.length} user(s)</span>` : ''}
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-white/50">${new Date(comment.created_at).toLocaleString()}</span>
            ${comment.can_delete ? `
              <button onclick="deleteComment('${comment.id}')" class="text-red-400 hover:text-red-300 text-xs">
                Delete
              </button>
            ` : ''}
          </div>
        </div>
        <div class="text-sm text-white/80">${highlightMentions(comment.text)}</div>
      </div>
    `).join('');
    
  } catch (error) {
    console.error('Error loading comments:', error);
    document.getElementById('commentsList').innerHTML = '<div class="text-red-400 text-sm">Failed to load comments</div>';
  }
}

function highlightMentions(text) {
  return text.replace(/@(\w+)/g, '<span class="text-blue-300 font-semibold">@$1</span>');
}

async function loadTaskAttachments(taskId) {
  try {
    const response = await fetch(`/api/tasks/${taskId}/attachments`);
    if (!response.ok) throw new Error('Failed to load attachments');
    
    const attachments = await response.json();
    const attachmentsList = document.getElementById('attachmentsList');
    
    if (attachments.length === 0) {
      attachmentsList.innerHTML = '<div class="text-white/50 text-sm">No attachments</div>';
      return;
    }
    
    attachmentsList.innerHTML = attachments.map(attachment => `
      <div class="flex items-center justify-between p-3 bg-white/5 rounded-lg">
        <div class="flex items-center gap-3">
          <span class="text-lg">${getFileIcon(attachment.mime_type)}</span>
          <div>
            <div class="font-medium text-sm">${attachment.filename}</div>
            <div class="text-xs text-white/50">${formatFileSize(attachment.size)} • ${attachment.uploaded_by}</div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button onclick="downloadAttachment('${attachment.id}')" class="text-blue-400 hover:text-blue-300 text-sm">
            Download
          </button>
          <button onclick="deleteAttachment('${attachment.id}', '${attachment.filename}')" class="text-red-400 hover:text-red-300 text-sm">
            Delete
          </button>
        </div>
      </div>
    `).join('');
    
  } catch (error) {
    console.error('Error loading attachments:', error);
  }
}

function setupCommentForm(taskId) {
  const form = document.getElementById('addCommentForm');
  const textarea = document.getElementById('commentText');
  
  form.onsubmit = async (e) => {
    e.preventDefault();
    
    const content = textarea.value.trim();
    if (!content) return;
    
    try {
      // Optimistic update
      const commentsList = document.getElementById('commentsList');
      const tempComment = document.createElement('div');
      tempComment.className = 'bg-white/5 p-3 rounded-lg opacity-50';
      tempComment.innerHTML = `
        <div class="flex items-center gap-2 mb-2">
          <div class="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center text-xs font-bold">
            ${window.currentUser?.name?.[0] || '?'}
          </div>
          <span class="font-medium text-sm">${window.currentUser?.name || 'You'}</span>
          <span class="text-xs text-white/50">Sending...</span>
        </div>
        <div class="text-sm text-white/80">${highlightMentions(content)}</div>
      `;
      commentsList.insertBefore(tempComment, commentsList.firstChild);
      
      const formData = new FormData();
      formData.append('content', content);
      
      const response = await fetch(`/api/tasks/${taskId}/comments`, {
        method: 'POST',
        body: formData
      });
      
      if (!response.ok) throw new Error('Failed to add comment');
      
      // Clear form
      textarea.value = '';
      
      // Reload comments (removes optimistic update)
      await loadTaskComments(taskId);
      
      taskUtils.showNotification('Comment added successfully', 'success');
      
    } catch (error) {
      console.error('Error adding comment:', error);
      // Remove optimistic update on error
      await loadTaskComments(taskId);
      taskUtils.showNotification('Failed to add comment', 'error');
    }
  };
}

// Helper functions for modal
function getStatusColor(status) {
  const colors = {
    'TODO': 'bg-gray-500/20 text-gray-300',
    'IN_PROGRESS': 'bg-blue-500/20 text-blue-300',
    'REVIEW': 'bg-yellow-500/20 text-yellow-300',
    'DONE': 'bg-green-500/20 text-green-300',
    'BACKLOG': 'bg-gray-500/20 text-gray-400'
  };
  return colors[status] || 'bg-gray-500/20 text-gray-300';
}

function getStatusIcon(status) {
  const icons = {
    'TODO': '📝',
    'IN_PROGRESS': '⚡',
    'REVIEW': '👀',
    'DONE': '✅',
    'BACKLOG': '📋'
  };
  return icons[status] || '📝';
}

function getPriorityColor(priority) {
  const colors = {
    'URGENT': 'bg-red-500/20 text-red-300',
    'HIGH': 'bg-orange-500/20 text-orange-300',
    'MEDIUM': 'bg-blue-500/20 text-blue-300',
    'LOW': 'bg-gray-500/20 text-gray-300'
  };
  return colors[priority] || 'bg-gray-500/20 text-gray-300';
}

function getPriorityIcon(priority) {
  const icons = {
    'URGENT': '🔥',
    'HIGH': '⚡',
    'MEDIUM': '📋',
    'LOW': '📝'
  };
  return icons[priority] || '📝';
}

async function deleteTaskFromModal(taskId, taskTitle) {
  if (!confirm(`Are you sure you want to delete the task "${taskTitle}"?\n\nThis action cannot be undone.`)) {
    return;
  }

  try {
    const response = await fetch(`/api/tasks/${taskId}`, {
      method: 'DELETE'
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete task');
    }

    taskUtils.showNotification('Task deleted successfully', 'success');
    
    // Close modal
    closeTaskModal();
    
    // Reload the dashboard to reflect changes
    setTimeout(() => {
      window.location.reload();
    }, 1000);

  } catch (error) {
    console.error('Error deleting task:', error);
    taskUtils.showNotification(error.message || 'Failed to delete task', 'error');
  }
}

// ---- Admin Functions ----
async function fixUserAssignments() {
  try {
    const response = await fetch('/api/debug/fix-user-assignments', {
      method: 'POST'
    });
    
    if (response.ok) {
      const result = await response.json();
      taskUtils.showNotification(result.message, 'success');
      
      // Reload page to see updated data
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    } else {
      throw new Error('Failed to fix user assignments');
    }
  } catch (error) {
    console.error('Error fixing user assignments:', error);
    taskUtils.showNotification('Failed to fix user assignments', 'error');
  }
}

async function syncAllUsers() {
  try {
    taskUtils.showNotification('Syncing all users...', 'info');
    
    const response = await fetch('/api/sync-users', {
      method: 'POST'
    });
    
    if (response.ok) {
      const result = await response.json();
      taskUtils.showNotification(result.message, 'success');
      
      // Reload page to see updated data
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    } else {
      throw new Error('Failed to sync users');
    }
  } catch (error) {
    console.error('Error syncing users:', error);
    taskUtils.showNotification('Failed to sync users', 'error');
  }
}

// Expose modal functions globally
window.openTaskModal = openTaskModal;
window.closeTaskModal = closeTaskModal;
window.deleteTaskFromModal = deleteTaskFromModal;
window.fixUserAssignments = fixUserAssignments;
window.syncAllUsers = syncAllUsers;


// Inline update helpers and modal actions
async function updateTaskField(taskId, payload) {
  try {
    const res = await fetch(`/api/tasks/${taskId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error('Failed to update');
    taskUtils.showNotification('Saved', 'success');
    if (payload.assigned_to_id || payload.priority || payload.title) {
      await loadTaskDetails(taskId);
    }
  } catch (e) {
    taskUtils.showNotification('Failed to save', 'error');
  }
}

function editTask(taskId) {
  const titleInput = document.getElementById('taskTitleInput');
  const assignee = document.getElementById('assigneeSelect');
  if (titleInput) {
    titleInput.focus();
    titleInput.select();
  }
  if (assignee) {
    assignee.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  taskUtils.showNotification('You can edit fields directly. Changes auto-save on blur/change.', 'info');
}

function uploadToTask(taskId) {
  const picker = document.getElementById('modalFilePicker');
  if (picker) picker.click();
}

window.editTask = editTask;
window.uploadToTask = uploadToTask;

