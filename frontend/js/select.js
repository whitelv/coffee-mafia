(async function () {
  const raw = sessionStorage.getItem('token');
  if (!raw) { window.location.href = '/index.html'; return; }
  const user = JSON.parse(sessionStorage.getItem('user') || '{}');
  syncEspDisplay().catch(() => {});

  /* ── Nav ── */
  document.getElementById('nav-username').textContent = user.name || '';
  if (user.role === 'admin') {
    document.getElementById('nav-history').style.display = '';
    document.getElementById('nav-admin').style.display   = '';
  }
  document.getElementById('btn-logout').addEventListener('click', logoutToLogin);

  /* ── Recipes ── */
  function estimatedTime(steps) {
    const secs = (steps || [])
      .filter(s => s.type === 'timer')
      .reduce((sum, s) => sum + (s.target_value || 0), 0);
    if (!secs) return null;
    const m = Math.round(secs / 60);
    return `~${m || 1}m`;
  }

  const grid = document.getElementById('recipe-grid');
  const resumeBanner = document.getElementById('resume-banner');
  const resumeText = document.getElementById('resume-text');
  const btnDiscard = document.getElementById('btn-discard');

  function resetRecipeCards() {
    grid.querySelectorAll('.card-clickable').forEach(card => {
      card.style.pointerEvents = '';
      card.style.opacity = '';
    });
  }

  async function startRecipe(recipeId, card = null) {
    if (card) {
      resetRecipeCards();
      card.style.pointerEvents = 'none';
      card.style.opacity = '0.6';
    }
    try {
      sessionStorage.removeItem('session_id');
      const session = await createSession({ recipe_id: recipeId, esp_id: 'ESP32_BAR_01' });
      sessionStorage.setItem('session_id', session.session_id);
      window.location.href = '/brew.html';
    } catch (err) {
      if (card) {
        card.style.pointerEvents = '';
        card.style.opacity = '';
      }
      showToast(err.message || 'Could not start session', 'error');
    }
  }

  async function loadCurrentSessionBanner() {
    resumeBanner.style.display = 'none';
    sessionStorage.removeItem('session_id');
    try {
      const current = await getCurrentSession();
      if (!current || !current.session) return;
      sessionStorage.setItem('session_id', current.session._id);
      const recipeName = current.recipe ? current.recipe.name : 'brew session';
      resumeText.textContent = `You have an unfinished ${recipeName}.`;
      resumeBanner.style.display = '';
    } catch {
      sessionStorage.removeItem('session_id');
    }
  }

  window.addEventListener('pageshow', () => {
    resetRecipeCards();
    loadCurrentSessionBanner();
  });

  btnDiscard.addEventListener('click', async () => {
    btnDiscard.disabled = true;
    try {
      await discardSession();
      sessionStorage.removeItem('session_id');
      resumeBanner.style.display = 'none';
      showToast('Session discarded', 'success');
    } catch (err) {
      showToast(err.message || 'Could not discard session', 'error');
    } finally {
      btnDiscard.disabled = false;
    }
  });

  try {
    await loadCurrentSessionBanner();
    const recipes = await getRecipes();
    if (!recipes || recipes.length === 0) {
      grid.innerHTML = '<p style="color:var(--text-muted);">No recipes available.</p>';
      return;
    }
    grid.innerHTML = '';
    sessionStorage.removeItem('restart_recipe_id');

    recipes.forEach(recipe => {
      const card = document.createElement('div');
      card.className = 'card card-clickable';

      const stepCount = (recipe.steps || []).length;
      const estTime   = estimatedTime(recipe.steps);

      card.innerHTML = `
        <div class="recipe-name">${recipe.name}</div>
        <div class="recipe-desc">${recipe.description || ''}</div>
        <div class="recipe-card-meta">
          <span class="badge">${stepCount} step${stepCount !== 1 ? 's' : ''}</span>
          ${estTime ? `<span class="badge badge-accent">${estTime}</span>` : ''}
        </div>`;

      card.addEventListener('click', async () => {
        await startRecipe(recipe._id, card);
      });

      grid.appendChild(card);
    });
  } catch (err) {
    grid.innerHTML = `<p style="color:var(--danger);">${err.message}</p>`;
  }
})();
