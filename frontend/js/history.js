(async function () {
  const token = sessionStorage.getItem('token');
  if (!token) { window.location.href = '/index.html'; return; }
  const user = JSON.parse(sessionStorage.getItem('user') || '{}');

  /* ── Nav ── */
  document.getElementById('nav-username').textContent = user.name || '';
  if (user.role === 'admin') document.getElementById('nav-admin').style.display = '';
  document.getElementById('btn-logout').addEventListener('click', logoutToLogin);

  const tbody       = document.getElementById('history-body');
  const pageLabel   = document.getElementById('page-label');
  const btnPrev     = document.getElementById('btn-prev');
  const btnNext     = document.getElementById('btn-next');
  const filterWrap  = document.getElementById('user-filter-wrap');
  const userFilter  = document.getElementById('user-filter');

  let currentPage = 1;
  const LIMIT = 20;
  let totalPages = 1;
  let selectedUserId = '';
  const userNameById = new Map();
  if (user.id) userNameById.set(user.id, user.name || '');

  /* ── Admin: load users for filter ── */
  if (user.role === 'admin') {
    filterWrap.style.display = '';
    try {
      const users = await getUsers();
      (users || []).forEach(u => {
        const opt = document.createElement('option');
        opt.value       = u._id;
        opt.textContent = u.name;
        userFilter.appendChild(opt);
        userNameById.set(u._id, u.name);
      });
    } catch { /* ignore */ }
    userFilter.addEventListener('change', () => {
      selectedUserId = userFilter.value;
      currentPage = 1;
      loadHistory();
    });
  }

  async function loadHistory() {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted);">Loading…</td></tr>';
    try {
      let result;
      if (user.role === 'admin') {
        result = await getAllHistory(currentPage, LIMIT, selectedUserId);
      } else {
        result = await getMyHistory(currentPage, LIMIT);
      }

      const items = Array.isArray(result) ? result : (result.items || result.sessions || []);
      totalPages  = result.total_pages || 1;
      pageLabel.textContent = `Page ${currentPage} of ${totalPages}`;
      btnPrev.disabled = currentPage <= 1;
      btnNext.disabled = currentPage >= totalPages;

      if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted);">No brews recorded yet ☕</td></tr>';
        return;
      }

      tbody.innerHTML = items.map(row => {
        const duration = (row.duration_seconds != null)
          ? formatDuration(row.duration_seconds)
          : (row.started_at && row.completed_at
              ? formatDuration((new Date(row.completed_at) - new Date(row.started_at)) / 1000)
              : '—');
        return `<tr>
          <td>${formatDate(row.completed_at || row.created_at)}</td>
          <td>${row.recipe_name || '—'}</td>
          <td>${duration}</td>
          <td>${row.worker_name || row.user_name || row.brewed_by || userNameById.get(row.user_id) || '—'}</td>
        </tr>`;
      }).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="4" style="color:var(--danger);">${err.message}</td></tr>`;
    }
  }

  btnPrev.addEventListener('click', () => { if (currentPage > 1) { currentPage--; loadHistory(); } });
  btnNext.addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; loadHistory(); } });

  loadHistory();
})();
