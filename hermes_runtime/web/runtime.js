'use strict';
(() => {
  const panel = $('runtime-panel'), status = el('p'), jobs = el('div');
  status.setAttribute('role', 'status');
  const action = (label, fn) => button(label, async () => {
    try { await fn(); } catch (e) { status.textContent = e.message; }
  });
  function field(label, multiline = false) {
    const input = el(multiline ? 'textarea' : 'input');
    input.setAttribute('aria-label', label);
    if (multiline) input.rows = 6;
    const wrapper = el('label', label); wrapper.append(input); panel.append(wrapper);
    return input;
  }
  async function refresh() {
    const state = await api('runtime');
    status.textContent = 'Project ' + state.project + ' · tools disabled · no provider fallback';
    jobs.replaceChildren(el('pre', JSON.stringify(state.scheduler, null, 2)));
    for (const task of state.jobs) {
      jobs.append(el('pre', JSON.stringify(task, null, 2)));
      if (task.status === 'running') jobs.append(action('Cancel task ' + task.id.slice(0, 8), async () => {
        await api('cancel', {id: task.id}); await refresh();
      }));
    }
  }
  panel.append(el('h2', 'Tasks and setup'), status, action('Refresh tasks and scheduler', refresh), jobs);
  const interval = field('Extraction interval in seconds'); interval.type = 'number'; interval.value = '21600'; interval.min = '60';
  panel.append(action('Enable best effort extraction', async () => {
    if (!window.confirm('Extract reviewed memory candidates from specifically granted records while this runtime is running?')) return;
    await api('evolution/schedule', {enabled: true, interval_seconds: Number(interval.value), confirm: true}); await refresh();
  }), action('Disable extraction schedule', async () => {
    await api('evolution/schedule', {enabled: false, interval_seconds: Number(interval.value), confirm: true}); await refresh();
  }));
  const source = field('Source ID'), records = field('Exact record IDs separated by commas');
  panel.append(action('Grant memory extraction for these records', async () => {
    if (!window.confirm('Allow extraction into the review queue for exactly these records? This does not write live Hermes memory.')) return;
    await api('evolution/grant', {source: source.value, records: records.value.split(',').map(s => s.trim()).filter(Boolean), purpose: 'memory', confirm: true});
    status.textContent = 'Extraction grant saved.';
  }), action('Extract granted records now', async () => {
    if (!window.confirm('Extract candidates from granted records now?')) return;
    status.textContent = JSON.stringify(await api('evolution/extract', {confirm: true}));
  }), action('Clear selected chat guidance', async () => { window.runtimeSkill = null; status.textContent = 'Guidance cleared.'; }));
  panel.append(el('h3', 'Reviewed correction dataset'), el('p', 'Provide alternating user/assistant messages as JSON. Accept only answers you have checked. License describes your rights to use these messages. Separate export consent is required in the workbench.'));
  const correction = field('Correction messages JSON', true), license = field('Dataset license or rights');
  panel.append(action('Accept exact correction for dataset review', async () => {
    if (!window.confirm('Have you checked this exact correction and confirmed your rights to use it?')) return;
    const result = await api('evolution/accept-correction', {messages: JSON.parse(correction.value), license: license.value, confirm: true});
    status.textContent = 'Candidate ' + result.id + ' created. Review and consent in Skills & memory.';
  }));
  panel.append(el('h3', 'Advisory coding'), el('p', 'Submit only code and specifications you choose to share. Planning and review use the local model. Proposals never run tools or apply patches.'));
  const specification = field('Coding specification', true), local = field('Local planner and reviewer model');
  const worker = field('Worker route: local or cloud'); worker.value = 'local';
  const model = field('Explicit worker model');
  panel.append(action('Request coding proposal', async () => {
    if (!window.confirm('Run this advisory coding task? Cloud mode sends the specification and local plan to the selected free model.')) return;
    const task = await api('coding', {specification: specification.value, local_model: local.value,
      worker_mode: worker.value, worker_model: model.value, cloud_consent: worker.value === 'cloud', synthetic: false, confirm: true});
    status.textContent = 'Started task ' + task.id; await refresh();
  }));
  panel.append(el('h3', 'External training runner'), el('p', 'Requires a host-configured runner and three independent reviewed dataset families. No GPU is created and no model is promoted. The runner receives the exported data.'));
  const ids = field('Consented candidate IDs separated by commas'), recipe = field('Training recipe JSON', true);
  recipe.value = JSON.stringify({base_model: 'Qwen/Qwen2.5-1.5B-Instruct', revision: '', seed: 42, rank: 8, epochs: 1, max_eval_loss: 3}, null, 2);
  panel.append(action('Start configured training runner', async () => {
    if (!window.confirm('Authorize the configured host runner to read these exact reviewed rows and execute the displayed training recipe?')) return;
    const task = await api('training', {ids: ids.value.split(',').map(s => s.trim()).filter(Boolean), recipe: JSON.parse(recipe.value), confirm: true, allow_runner_data_access: true});
    status.textContent = 'Started training task ' + task.id; await refresh();
  }));
  $('runtime-toggle').onclick = async () => { panel.hidden = !panel.hidden; if (!panel.hidden) await refresh(); };
  $('cancel-task').onclick = async () => {
    try {
      if (!current) throw Error('Open a conversation first.');
      const chat = await api('chats/' + current);
      if (!chat.job) throw Error('No active reply.');
      await api('cancel', {id: chat.job}); notice('Cancellation requested.');
    } catch (e) { notice(e.message); }
  };
  setInterval(() => { if (!panel.hidden && token) refresh().catch(e => { status.textContent = e.message; }); }, 2000);
})();
