(async function () {
  const token = sessionStorage.getItem('token');
  if (!token) { window.location.href = '/index.html'; return; }
  const user = JSON.parse(sessionStorage.getItem('user') || '{}');
  if (user.role !== 'admin') { window.location.href = '/select.html'; return; }

  document.getElementById('nav-username').textContent = user.name || '';
  document.getElementById('btn-logout').addEventListener('click', logoutToLogin);

  /* ── Tabs ── */
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
    });
  });

  /* ══════════════════════════════════════════════
     USERS
  ══════════════════════════════════════════════ */
  let editingUserId = null;

  async function loadUsers() {
    const tbody = document.getElementById('users-body');
    try {
      const users = await getUsers();
      tbody.innerHTML = (users || []).map(u => `
        <tr>
          <td>${u.name}</td>
          <td><span class="badge">${u.role}</span></td>
          <td class="actions">
            <button class="btn btn-sm btn-secondary" onclick="openUserModal('${u._id}','${u.name}','${u.rfid_uid || ''}','${u.role}')">Edit</button>
            <button class="btn btn-sm btn-danger" onclick="deleteUserRow('${u._id}','${u.name}')">Delete</button>
          </td>
        </tr>`).join('') || '<tr><td colspan="3" style="color:var(--text-muted);">No users found.</td></tr>';
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  window.openUserModal = function (id, name, rfid, role) {
    editingUserId = id || null;
    document.getElementById('user-modal-title').textContent = id ? 'Edit User' : 'Add User';
    document.getElementById('u-name').value = name || '';
    document.getElementById('u-rfid').value = rfid || '';
    document.getElementById('u-role').value = role || 'client';
    document.getElementById('user-modal').classList.add('open');
  };

  window.deleteUserRow = async function (id, name) {
    if (!confirm(`Delete user "${name}"?`)) return;
    try {
      await deleteUser(id);
      showToast('User deleted', 'success');
      loadUsers();
    } catch (err) { showToast(err.message, 'error'); }
  };

  function closeUserModal() {
    document.getElementById('user-modal').classList.remove('open');
    editingUserId = null;
  }

  document.getElementById('btn-add-user').addEventListener('click', () => openUserModal(null, '', '', 'client'));
  document.getElementById('user-modal-close').addEventListener('click', closeUserModal);
  document.getElementById('btn-user-cancel').addEventListener('click', closeUserModal);
  document.getElementById('user-modal').querySelector('.modal-backdrop').addEventListener('click', closeUserModal);

  document.getElementById('btn-user-save').addEventListener('click', async () => {
    const btn  = document.getElementById('btn-user-save');
    const name = document.getElementById('u-name').value.trim();
    const rfid = document.getElementById('u-rfid').value.trim();
    const role = document.getElementById('u-role').value;
    if (!name) { showToast('Name is required', 'error'); return; }
    if (!rfid) { showToast('RFID UID is required', 'error'); return; }
    setButtonLoading(btn, true);
    try {
      if (editingUserId) {
        await updateUser(editingUserId, { name, rfid_uid: rfid, role });
        showToast('User updated', 'success');
      } else {
        await createUser({ name, rfid_uid: rfid, role });
        showToast('User created', 'success');
      }
      closeUserModal();
      loadUsers();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setButtonLoading(btn, false);
    }
  });

  /* ══════════════════════════════════════════════
     RECIPES
  ══════════════════════════════════════════════ */
  let editingRecipeId = null;
  let editorSteps     = [];
  let pendingStepType = null;
  let dragSrcIndex    = null;

  async function loadRecipes() {
    const list = document.getElementById('recipes-list');
    try {
      const recipes = await getRecipes();
      list.innerHTML = (recipes || []).map(r => `
        <div class="card" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;">
          <div>
            <strong>${r.name}</strong>
            <span class="badge" style="margin-left:0.5rem;">${(r.steps||[]).length} steps</span>
          </div>
          <div class="actions">
            <button class="btn btn-sm btn-secondary" onclick="openEditor('${r._id}')">Edit</button>
            <button class="btn btn-sm btn-danger"    onclick="deleteRecipeRow('${r._id}','${r.name}')">Delete</button>
          </div>
        </div>`).join('') || '<p style="color:var(--text-muted);">No recipes yet.</p>';
    } catch (err) { showToast(err.message, 'error'); }
  }

  window.deleteRecipeRow = async function (id, name) {
    if (!confirm(`Delete recipe "${name}"?`)) return;
    try {
      await deleteRecipe(id);
      showToast('Recipe deleted', 'success');
      loadRecipes();
    } catch (err) { showToast(err.message, 'error'); }
  };

  window.openEditor = async function (id) {
    editingRecipeId = id || null;
    editorSteps     = [];
    document.getElementById('editor-title').textContent = id ? 'Edit Recipe' : 'New Recipe';
    document.getElementById('ed-name').value  = '';
    document.getElementById('ed-desc').value  = '';
    closeAddStepPanel();

    if (id) {
      try {
        const r = await getRecipe(id);
        document.getElementById('ed-name').value = r.name        || '';
        document.getElementById('ed-desc').value = r.description || '';
        editorSteps = (r.steps || []).map(s => ({ ...s }));
      } catch (err) { showToast(err.message, 'error'); return; }
    }

    renderStepRows();
    document.getElementById('recipe-editor').classList.add('open');
    document.getElementById('recipe-editor').scrollIntoView({ behavior: 'smooth' });
  };

  document.getElementById('btn-add-recipe').addEventListener('click', () => openEditor(null));

  document.getElementById('btn-cancel-recipe').addEventListener('click', () => {
    document.getElementById('recipe-editor').classList.remove('open');
    editingRecipeId = null;
    editorSteps     = [];
  });

  /* ── Step rows ── */
  const STEP_ICONS = { weight: '⚖️', timer: '⏱️', instruction: '📋' };

  function stepSummary(step) {
    if (step.type === 'weight')      return `${step.label} — ${step.target_value}g ±${step.tolerance || 0}g`;
    if (step.type === 'timer')       return `${step.label} — ${step.target_value}s`;
    if (step.type === 'instruction') return `${step.label}`;
    return step.label || step.type;
  }

  function renderStepRows() {
    const ul = document.getElementById('step-rows');
    ul.innerHTML = '';
    editorSteps.forEach((step, i) => {
      const li = document.createElement('li');
      li.className   = 'step-row';
      li.draggable   = true;
      li.dataset.idx = i;
      li.innerHTML   = `
        <span class="drag-handle" title="Drag to reorder">&#8801;</span>
        <span class="step-type-icon">${STEP_ICONS[step.type] || '•'}</span>
        <span class="step-row-label">${stepSummary(step)}</span>
        <button class="btn btn-sm btn-danger" data-del="${i}">&#10005;</button>`;

      li.querySelector('[data-del]').addEventListener('click', () => {
        editorSteps.splice(i, 1);
        renderStepRows();
      });

      li.addEventListener('dragstart', () => {
        dragSrcIndex = i;
        li.classList.add('dragging');
      });
      li.addEventListener('dragend', () => li.classList.remove('dragging'));
      li.addEventListener('dragover', e => { e.preventDefault(); li.classList.add('drag-over'); });
      li.addEventListener('dragleave', () => li.classList.remove('drag-over'));
      li.addEventListener('drop', e => {
        e.preventDefault();
        li.classList.remove('drag-over');
        if (dragSrcIndex === null || dragSrcIndex === i) return;
        const moved = editorSteps.splice(dragSrcIndex, 1)[0];
        editorSteps.splice(i, 0, moved);
        dragSrcIndex = null;
        renderStepRows();
      });

      ul.appendChild(li);
    });
  }

  /* ── Add step panel ── */
  function closeAddStepPanel() {
    document.getElementById('add-step-panel').classList.remove('open');
    document.getElementById('step-fields').innerHTML = '';
    pendingStepType = null;
  }

  document.getElementById('btn-add-step').addEventListener('click', () => {
    document.getElementById('add-step-panel').classList.toggle('open');
  });

  document.querySelectorAll('[data-stype]').forEach(btn => {
    btn.addEventListener('click', () => {
      pendingStepType = btn.dataset.stype;
      const fields = document.getElementById('step-fields');

      if (pendingStepType === 'weight') {
        fields.innerHTML = `
          <div class="form-group"><label>Label</label><input class="input" id="sf-label" placeholder="e.g. Add coffee"/></div>
          <div class="form-group"><label>Target (g)</label><input class="input" type="number" id="sf-target" placeholder="18"/></div>
          <div class="form-group"><label>Tolerance (g)</label><input class="input" type="number" id="sf-tol" placeholder="0.5"/></div>`;
      } else if (pendingStepType === 'timer') {
        fields.innerHTML = `
          <div class="form-group"><label>Label</label><input class="input" id="sf-label" placeholder="e.g. Bloom"/></div>
          <div class="form-group"><label>Duration (seconds)</label><input class="input" type="number" id="sf-target" placeholder="30"/></div>`;
      } else if (pendingStepType === 'instruction') {
        fields.innerHTML = `
          <div class="form-group full-width"><label>Label</label><input class="input" id="sf-label" placeholder="e.g. Rinse filter"/></div>
          <div class="form-group full-width"><label>Instruction text</label><textarea class="input" id="sf-text" placeholder="Describe the step…"></textarea></div>`;
      }
    });
  });

  document.getElementById('btn-cancel-step').addEventListener('click', closeAddStepPanel);

  document.getElementById('btn-confirm-step').addEventListener('click', () => {
    if (!pendingStepType) { showToast('Pick a step type first', 'error'); return; }
    const label  = (document.getElementById('sf-label')?.value || '').trim();
    const target = parseFloat(document.getElementById('sf-target')?.value || '0');
    const tol    = parseFloat(document.getElementById('sf-tol')?.value   || '0');
    const text   = (document.getElementById('sf-text')?.value   || '').trim();
    if (!label) { showToast('Label is required', 'error'); return; }

    const step = { type: pendingStepType, label };
    if (pendingStepType === 'weight')      { step.target_value = target; step.tolerance = tol; }
    if (pendingStepType === 'timer')       { step.target_value = target; }
    if (pendingStepType === 'instruction') { step.instruction_text = text; }

    editorSteps.push(step);
    renderStepRows();
    closeAddStepPanel();
  });

  /* ── Save recipe ── */
  document.getElementById('btn-save-recipe').addEventListener('click', async () => {
    const btn  = document.getElementById('btn-save-recipe');
    const name = document.getElementById('ed-name').value.trim();
    const desc = document.getElementById('ed-desc').value.trim();
    if (!name) { showToast('Recipe name is required', 'error'); return; }
    if (editorSteps.length === 0) { showToast('Add at least one step', 'error'); return; }

    setButtonLoading(btn, true);
    try {
      let id = editingRecipeId;
      if (!id) {
        const created = await createRecipe({ name, description: desc, steps: editorSteps });
        id = created._id;
      } else {
        await updateRecipe(id, { name, description: desc });
        await updateSteps(id, editorSteps);
      }
      showToast('Recipe saved', 'success');
      document.getElementById('recipe-editor').classList.remove('open');
      editingRecipeId = null;
      editorSteps     = [];
      loadRecipes();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setButtonLoading(btn, false);
    }
  });

  /* ── Init ── */
  loadUsers();
  loadRecipes();
})();
