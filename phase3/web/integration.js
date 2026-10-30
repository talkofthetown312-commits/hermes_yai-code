/* Phase 3 additive Pocket integration: no automatic mutation, execution or promotion. */
'use strict';
(() => {
  const views = ['dashboard', 'memory', 'skills', 'conversation', 'files', 'advanced'];
  let view = 'dashboard', preferences = {view, revision: 0}, selected = null;
  let generation = 0, memoryGeneration = 0, skillGeneration = 0;
  const root = el('section', undefined, 'integration'); root.id = 'integration-root';
  root.setAttribute('aria-label', 'Pocket integration dashboard');
  const nav = el('div', undefined, 'integration-nav'); nav.setAttribute('role', 'navigation');
  nav.setAttribute('aria-label', 'Pocket sections');
  const message = el('p'); message.id = 'integration-status';
  message.setAttribute('role', 'status'); message.setAttribute('aria-live', 'polite');
  const panels = {}, buttons = {};
  function action(label, handler) {
    const button = el('button', label); button.type = 'button';
    button.onclick = async () => {
      button.disabled = true;
      try { await handler(); } catch (error) { message.textContent = error.message; }
      finally { button.disabled = false; }
    };
    return button;
  }
  function field(label, node) {
    const wrapper = el('label', label); node.setAttribute('aria-label', label);
    wrapper.append(node); return wrapper;
  }
  const call = (path, body) => api('evolution/' + path, body);
  for (const name of ['dashboard', 'memory', 'skills']) {
    panels[name] = el('section'); panels[name].hidden = true;
    panels[name].setAttribute('aria-label', name + ' workspace'); root.append(panels[name]);
  }
  for (const name of views) {
    buttons[name] = action(name[0].toUpperCase() + name.slice(1), () => navigate(name, true));
    buttons[name].setAttribute('data-view', name); nav.append(buttons[name]);
  }
  root.append(message); $('messages').before(nav, root);
  const cards = el('div', undefined, 'integration-cards');
  panels.dashboard.append(el('h2', 'Pocket dashboard'),
    el('p', 'PHASE 3 · ISOLATED SYNTHETIC STAGING. These are actual sidecar counts, not production data.'), cards,
    action('Refresh dashboard', refreshDashboard),
    action('Find memory with provenance', () => navigate('memory', true)),
    action('Teach → Test → Approve → Reuse', () => navigate('skills', true)));
  async function refreshDashboard() {
    const sequence = ++generation; cards.replaceChildren(el('p', 'Loading dashboard…'));
    try {
      const data = await api('integration/dashboard');
      if (sequence !== generation) return;
      preferences = data.preferences; cards.replaceChildren();
      for (const [label, value] of Object.entries(data.skills)) {
        const card = el('article'); card.append(el('strong', String(value)), el('p', label + ' skills')); cards.append(card);
      }
      cards.append(el('p', data.granted_sources + ' granted sources · ' + data.audit_events + ' workflow audit events'),
        el('p', 'Agent: ' + data.agent + ' · Providers: ' + data.providers + ' · Training: ' + data.training),
        el('p', 'Scheduler: ' + data.scheduler + ' · Reuse: guidance only, never execution or installation.'));
      message.textContent = 'Connected to isolated persistent state. Android native acceptance is not yet verified.';
    } catch (error) {
      if (sequence === generation) cards.replaceChildren(el('p', 'Dashboard unavailable. Refresh to retry; counts are not known.'));
      throw error;
    }
  }
  const scopes = el('div'), query = el('input'), results = el('div');
  query.maxLength = 256; query.placeholder = 'Search only explicitly granted records';
  panels.memory.append(el('h2', 'Memory with provenance'),
    el('p', 'Default denied. Select synthetic sources below. Retrieved statements remain unverified; assistant drafts are not user facts.'),
    scopes, field('Memory query', query), action('Search memory', searchMemory), results);
  async function refreshScopes() {
    const sequence = ++memoryGeneration;
    scopes.replaceChildren(el('p', 'Loading source permissions…')); results.replaceChildren();
    try {
      const state = await call('state');
      if (sequence !== memoryGeneration) return;
      scopes.replaceChildren();
      for (const source of state.source_choices) {
        const granted = !!state.grants[source.source_id];
        const label = (granted ? 'Revoke ' : 'Allow ') + source.source_id;
        scopes.append(action(label, async () => {
          if (!window.confirm(label + ' exactly these synthetic records: ' + source.records.join(', ') + '?')) return;
          ++memoryGeneration; results.replaceChildren(el('p', 'Scope changed; previous results cleared.'));
          await call(granted ? 'revoke-grant' : 'grant', granted ? {source: source.source_id} :
            {source: source.source_id, records: source.records, confirm: true});
          await refreshScopes();
        }));
      }
    } catch (error) {
      if (sequence === memoryGeneration) scopes.replaceChildren(el('p', 'Permissions unavailable. Retry by reopening Memory.'));
      throw error;
    }
  }
  async function searchMemory() {
    const sequence = ++memoryGeneration; results.replaceChildren(el('p', 'Searching authorized records…'));
    try {
      const data = await call('search?q=' + encodeURIComponent(query.value));
      if (sequence !== memoryGeneration || view !== 'memory') return;
      results.replaceChildren(el('p', data.count + ' result(s) · ' + data.status));
      if (data.errors.length || data.truncated) results.append(el('p', 'Partial results: a source was unavailable or the result budget was reached.'));
      for (const item of data.results) {
        const card = el('article', undefined, 'provenance-card');
        card.append(el('h3', item.claim_type + (item.disputed ? ' · DISPUTED' : '')),
          el('p', item.snippet), el('p', 'Author: ' + item.author_role + ' · Verified: ' + item.verified),
          el('p', 'Project: ' + item.project + ' · Sensitivity: ' + item.sensitivity));
        for (const citation of item.citations) card.append(el('pre', JSON.stringify(citation, null, 2)));
        results.append(card);
      }
      results.append(el('p', data.guidance));
    } catch (error) {
      if (sequence === memoryGeneration) results.replaceChildren(el('p', 'Search unavailable. No cached results are shown.'));
      throw error;
    }
  }
  const fields = ['trigger', 'prerequisites', 'method', 'tools', 'inputs', 'outputs', 'risks', 'permissions', 'verification'];
  const inputs = {}, versions = el('select'), evidence = el('pre', 'Select or save a draft.'), task = el('input');
  versions.setAttribute('aria-label', 'Integrated skill version'); task.maxLength = 128;
  panels.skills.append(el('h2', 'Teach → Test → Approve → Reuse'),
    el('p', 'Guidance-only contracts. Test is deterministic/static, not model validation. Every approval binds the exact saved hash.'), versions);
  const picker = el('input'); picker.type = 'file'; picker.accept = '.txt,.md';
  panels.skills.append(action('New skill draft', async () => {
    ++skillGeneration; selected = null; versions.value = ''; for (const name of fields) inputs[name].value = '';
    evidence.textContent = 'Unsaved draft. No approval or execution.';
  }), action('Save synthetic picker fixture', async () => {
    const text = '# Synthetic teaching example\nReview blue synthetic widgets. No tools execute.\n';
    await exportData('save', 'phase3-teaching-synthetic.md', 'text/markdown', textData(text), text);
  }), field('Choose teaching file', picker), action('Import selected teaching text', async () => {
    const file = picker.files[0];
    if (!file || file.size > 16000 || !/\.(txt|md)$/i.test(file.name)) throw Error('Choose a .txt/.md teaching file up to 16 KB.');
    if (!window.confirm('Copy this file text into an untrusted local draft? No upload or automatic save. Use only the synthetic fixture for staging.')) return;
    inputs.method.value = await file.text();
  }));
  for (const name of fields) {
    inputs[name] = el('textarea'); inputs[name].rows = name === 'method' ? 5 : 2;
    inputs[name].maxLength = name === 'method' ? 14000 : 2000;
    panels.skills.append(field('Skill ' + name, inputs[name]));
  }
  const modelPanel = el('section', undefined, 'model-assist');
  modelPanel.setAttribute('aria-label', 'Synthetic AI assistance');
  const modelStatus = el('p', 'Checking synthetic model-assistance configuration…');
  const modelOutput = el('pre', 'No AI draft requested. Nothing is saved or approved automatically.');
  modelOutput.setAttribute('aria-live', 'polite');
  let modelConfigured = false, modelCandidate = null, modelReviewed = false, modelBusy = false, modelGeneration = 0;
  function updateModelButtons() {
    generateModel.disabled = modelBusy || !modelConfigured;
    reviewModel.disabled = modelBusy || !modelConfigured || !modelCandidate;
    adoptModel.disabled = modelBusy || !modelConfigured || !modelCandidate || !modelReviewed;
  }
  function modelButton(label, handler) {
    const button = el('button', label); button.type = 'button';
    button.onclick = async () => {
      if (modelBusy) return;
      modelBusy = true; updateModelButtons();
      try { await handler(); } catch (error) { modelOutput.textContent = 'AI assistance blocked: ' + error.message; }
      finally { modelBusy = false; updateModelButtons(); }
    };
    return button;
  }
  const generateModel = modelButton('Draft synthetic skill with free model', async () => {
    if (!modelConfigured) throw Error('Synthetic model assistance is not configured.');
    if (!window.confirm('Send ONLY the fixed synthetic blue-widget example to the configured zero-price cloud endpoint? No form text, files or memories are sent. No fallback, save, approval or execution.')) return;
    const sequence = ++modelGeneration; modelCandidate = null; modelReviewed = false;
    modelOutput.textContent = 'Requesting an UNVERIFIED synthetic AI draft…';
    const result = await api('integration/model-assist/draft', {fixture: 'synthetic-blue-widgets-v1', confirm: true});
    if (sequence !== modelGeneration || view !== 'skills') return;
    if (!result || typeof result.draft_id !== 'string' || typeof result.hash !== 'string' ||
        !result.body || !fields.every(name => typeof result.body[name] === 'string') ||
        result.verified !== false || result.saved !== false || result.approved !== false) throw Error('Invalid unverified model draft; form unchanged.');
    modelCandidate = result;
    modelOutput.textContent = 'UNVERIFIED AI DRAFT · NOT SAVED OR APPROVED\n' + JSON.stringify(result, null, 2);
  });
  const reviewModel = modelButton('Review synthetic AI draft', async () => {
    const candidate = modelCandidate;
    if (!modelConfigured || !candidate) throw Error('Generate a synthetic AI draft first.');
    if (!window.confirm('Send ONLY the cached synthetic model draft for AI review? Your edited form/private context is not sent. AI review is not success evidence or approval.')) return;
    const sequence = modelGeneration; modelReviewed = false;
    const result = await api('integration/model-assist/review', {draft_id: candidate.draft_id, hash: candidate.hash, confirm: true});
    if (sequence !== modelGeneration || modelCandidate !== candidate || view !== 'skills') return;
    if (!result.review || result.review.status !== 'needs_human_review' || result.verified !== false ||
        result.draft_id !== candidate.draft_id || result.hash !== candidate.hash ||
        result.saved !== false || result.approved !== false) throw Error('Invalid unapproved model review.');
    modelReviewed = true;
    modelOutput.textContent = 'AI REVIEW · STILL NEEDS HUMAN REVIEW · NOT VERIFIED\n' + JSON.stringify(result, null, 2);
  });
  const adoptModel = modelButton('Use AI suggestion in unsaved form', async () => {
    const candidate = modelCandidate;
    if (!modelConfigured || !candidate || !modelReviewed) throw Error('Generate and review a synthetic draft first.');
    if (!window.confirm('Replace the teaching form with this UNVERIFIED AI suggestion as a NEW UNSAVED draft? Current form edits will be replaced. No save, test, approval or execution.')) return;
    const sequence = modelGeneration, editGeneration = skillGeneration;
    const before = fields.map(name => inputs[name].value);
    const result = await api('integration/model-assist/suggestion', {draft_id: candidate.draft_id, hash: candidate.hash, confirm: true});
    if (sequence !== modelGeneration || modelCandidate !== candidate || view !== 'skills') return;
    if (editGeneration !== skillGeneration || fields.some((name, index) => inputs[name].value !== before[index])) throw Error('Teaching form changed while waiting; suggestion not applied.');
    if (!result.body || !fields.every(name => typeof result.body[name] === 'string') || result.verified !== false ||
        result.draft_id !== candidate.draft_id || result.hash !== candidate.hash || result.saved !== false || result.approved !== false) throw Error('Invalid synthetic suggestion; form unchanged.');
    ++skillGeneration; selected = null; versions.value = '';
    for (const name of fields) inputs[name].value = result.body[name];
    evidence.textContent = 'UNVERIFIED AI-ASSISTED SYNTHETIC DRAFT. Not saved, tested or approved. Review/correct it before Save.';
  });
  modelPanel.append(el('h3', 'AI assistance · synthetic examples only'),
    el('p', 'Only the fixed blue-widget fixture and its cached AI output can leave the phone. No current form, file, memory or conversation is uploaded. A model critique is not verification; Save/Test/Approve/Reuse remain separate human actions.'),
    modelStatus, generateModel, reviewModel, adoptModel, modelOutput);
  panels.skills.append(modelPanel);
  updateModelButtons();
  async function refreshModelStatus() {
    try {
      const status = await api('integration/model-assist');
      modelConfigured = status.configured === true;
      modelStatus.textContent = (status.test_transport ? 'TEST TRANSPORT ONLY · no live model proof. ' : '') +
        (modelConfigured ? 'Configured, not a guarantee of endpoint availability. State: ' + status.state + '. Normal chat remains disabled.' :
          'Not enabled. An explicitly configured synthetic-only credential is required; no model request is made by opening this panel.');
    } catch (error) {
      modelConfigured = false; modelStatus.textContent = 'Model-assistance configuration unavailable; no request will be sent.';
    }
    updateModelButtons();
  }
  async function refreshVersions() {
    const state = await call('state'); versions.replaceChildren(el('option', 'Choose a saved skill'));
    for (const item of state.skills.versions) {
      const option = el('option', item.id.slice(0, 8) + ' · r' + item.revision + ' · ' + item.state);
      option.value = item.id; versions.append(option);
    }
    if (selected) versions.value = selected.id;
  }
  async function loadSkill(id) {
    const sequence = ++skillGeneration; selected = null;
    if (!id || id.startsWith('Choose')) return;
    const fresh = await call('skill?id=' + encodeURIComponent(id));
    if (sequence !== skillGeneration) return;
    selected = fresh;
    for (const name of fields) inputs[name].value = selected.body[name];
    evidence.textContent = JSON.stringify({id: selected.id, revision: selected.revision, state: selected.state,
      hash: selected.hash, test: selected.test, approval: selected.approval, expires: selected.expires}, null, 2);
  }
  versions.onchange = async () => {
    try { await loadSkill(versions.value); } catch (error) { selected = null; evidence.textContent = 'Skill unavailable.'; message.textContent = error.message; }
  };
  async function skillAction(operation) {
    const saved = selected;
    if (!saved) throw Error('Save or select a skill first.');
    if (!window.confirm('Confirm ' + operation + ' for exactly saved revision ' + saved.revision + '? Unsaved form edits are not included.')) return;
    if (operation === 'test') await call('test', {id: saved.id, revision: saved.revision, confirm: true});
    if (operation === 'approve') {
      if (!saved.test || !saved.test.passed) throw Error('A passing saved contract test is required.');
      await call('approve', {id: saved.id, hash: saved.hash, test_hash: saved.test.hash, confirm: true});
    }
    if (operation === 'revoke') await call('revoke-skill', {id: saved.id});
    await loadSkill(saved.id); await refreshVersions();
  }
  async function reuse(actionName) {
    if (!selected) throw Error('Select an approved skill first.');
    if (!window.confirm('Reuse exactly this saved guidance for the named task? No execution, installation or automatic send.')) return;
    // Always revalidate at the action boundary, including repeated save/share attempts.
    const bundle = await call('reuse', {id: selected.id, hash: selected.hash, task: task.value, confirm: true});
    evidence.textContent = bundle.skill_md;
    if (actionName === 'composer') {
      if ($('prompt').value.trim() && !window.confirm('Replace the current unsent composer text?')) return;
      $('prompt').value = bundle.skill_md; rememberDraft(); await navigate('conversation', true); $('prompt').focus();
    } else await exportData(actionName, 'SKILL.md', 'text/markdown', textData(bundle.skill_md), bundle.skill_md);
  }
  panels.skills.append(action('Save skill draft', async () => {
    const body = Object.fromEntries(fields.map(name => [name, inputs[name].value]));
    const value = selected ? await call('edit-skill', {id: selected.id, revision: selected.revision, body}) : await call('teach', {body});
    await loadSkill(value.id); await refreshVersions();
  }), action('Test saved skill', () => skillAction('test')),
  action('Approve tested skill', () => skillAction('approve')), evidence,
  field('Guidance task', task), action('Reuse guidance in composer', () => reuse('composer')),
  action('Save approved SKILL.md', () => reuse('save')), action('Share approved guidance', () => reuse('share')),
  action('Revoke approval', () => skillAction('revoke')),
  action('Refresh skills', async () => {
    if (selected && fields.some(name => inputs[name].value !== selected.body[name]) &&
        !window.confirm('Discard unsaved teaching edits and reload the saved version?')) return;
    if (selected) await loadSkill(selected.id); await refreshVersions();
  }));
  const openAdvanced = $('evolution-toggle').onclick;
  async function navigate(next, persist = false) {
    if (!views.includes(next)) next = 'dashboard';
    if (view === 'skills' && next !== 'skills') ++modelGeneration;
    ++memoryGeneration; ++generation; results.replaceChildren();
    view = next; root.setAttribute('data-section', view);
    for (const name of Object.keys(panels)) panels[name].hidden = name !== view;
    for (const name of views) buttons[name].setAttribute('aria-current', name === view ? 'page' : 'false');
    $('messages').hidden = view !== 'conversation'; $('composer').parentElement.hidden = view !== 'conversation';
    $('file-panel').hidden = view !== 'files';
    if (view === 'advanced' && $('evolution-panel').hidden) await openAdvanced();
    $('evolution-panel').hidden = view !== 'advanced';
    if (persist) {
      preferences = await api('integration/preferences', {view, revision: preferences.revision, confirm: true});
      window.history.pushState(null, '', '#' + view);
    }
    if (view === 'dashboard') await refreshDashboard();
    if (view === 'memory') await refreshScopes();
    // Hiding/resuming a view must not overwrite unsaved teaching text. Backend
    // hashes/revisions still reject stale actions; Refresh explicitly reloads it.
    if (view === 'skills') { await refreshVersions(); await refreshModelStatus(); }
    if (view === 'files') await refreshFiles();
    message.textContent = 'Section: ' + view + ' · isolated staging · normal chat disabled; synthetic AI assistance requires explicit opt-in.';
  }
  $('evolution-toggle').onclick = () => navigate(view === 'advanced' ? 'dashboard' : 'advanced', true).catch(error => { message.textContent = error.message; });
  $('files-toggle').onclick = () => navigate('files', true).catch(error => { message.textContent = error.message; });
  const originalNew = $('new').onclick;
  $('new').onclick = async () => { await navigate('conversation', true); if (originalNew) originalNew(); };
  async function resume() {
    if (document.hidden) return;
    try {
      const data = await api('integration/dashboard'); preferences = data.preferences;
      await navigate(view, false);
    } catch (error) { message.textContent = 'Staging connection unavailable; retry: ' + error.message; results.replaceChildren(); }
  }
  window.addEventListener('popstate', () => navigate(location.hash.slice(1), false).catch(error => { message.textContent = error.message; }));
  window.addEventListener('pageshow', resume);
  document.addEventListener('visibilitychange', resume);
  document.addEventListener('click', event => {
    if (event.target.closest && event.target.closest('#history button')) navigate('conversation', true).catch(error => { message.textContent = error.message; });
  });
  async function start() {
    if (!token) { message.textContent = 'Pair this staging origin before opening the dashboard. Never use production credentials.'; return; }
    const data = await api('integration/dashboard'); preferences = data.preferences;
    await navigate(views.includes(location.hash.slice(1)) ? location.hash.slice(1) : preferences.view, false);
  }
  const originalPair = $('pair-form').onsubmit;
  $('pair-form').onsubmit = async event => {
    if (originalPair) await originalPair(event);
    try { await start(); } catch (error) { message.textContent = error.message; }
  };
  // Opening/reopening performs GETs only. No tests, grants or approvals run automatically.
  window.pocketIntegrationReady = start().catch(error => { message.textContent = error.message; });
})();
