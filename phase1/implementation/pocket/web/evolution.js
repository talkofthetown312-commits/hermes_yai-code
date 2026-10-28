/* Isolated workbench; no HTML injection, eval, skill execution or automatic promotion. */
'use strict';
(() => {
  const panel = $('evolution-panel');
  let state = null, selected = null, candidate = null, legacy = null;
  const fields = ['trigger', 'prerequisites', 'method', 'tools', 'inputs', 'outputs', 'risks', 'permissions', 'verification'];
  const call = (path, data) => api('evolution/' + path, data);
  const status = el('p', 'Open the workbench to load its isolated fixture state.');
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  function act(label, fn) {
    const b = el('button', label); b.type = 'button';
    b.onclick = async () => {
      b.disabled = true;
      try { await fn(); } catch (e) { status.textContent = e.message; }
      finally { b.disabled = false; }
    };
    return b;
  }
  function title(text) { return el('h3', text); }
  function row(label, input) { const l = el('label', label); l.append(input); return l; }
  const refs = el('select'); refs.setAttribute('aria-label', 'Existing skill reference');
  const versions = el('select'); versions.setAttribute('aria-label', 'Draft or approved version');
  const draftFields = {};
  const form = el('div', undefined, 'evo-draft');
  for (const name of fields) {
    const t = el('textarea'); t.rows = name === 'method' ? 5 : 2; t.maxLength = name === 'method' ? 14000 : 2000;
    t.setAttribute('aria-label', name); draftFields[name] = t; form.append(row(name, t));
  }
  const evidence = el('pre', 'No test has been run.');
  const preview = el('pre', 'Select a reference or version to review it.');
  const scope = el('div');
  const query = el('input'); query.placeholder = 'Search granted synthetic records'; query.maxLength = 256;
  query.setAttribute('aria-label', 'Memory search');
  const results = el('pre', 'No search performed.');
  const candidates = el('select'); candidates.setAttribute('aria-label', 'Dataset candidate');
  const dataPreview = el('textarea'); dataPreview.rows = 7; dataPreview.maxLength = 32000; dataPreview.setAttribute('aria-label', 'Review redacted synthetic messages');
  const dataStatus = el('p', 'No personal records are available to this staged pipeline.');
  const task = el('input'); task.placeholder = 'Explicit task label'; task.maxLength = 128; task.setAttribute('aria-label', 'Reuse task');
  const historyBox = el('pre', 'Version history appears after selection.');
  const restoreVersion = el('input'); restoreVersion.type = 'number'; restoreVersion.min = '1'; restoreVersion.setAttribute('aria-label', 'Restore version as new draft');
  const picker = el('input'); picker.type = 'file'; picker.accept = '.txt,.md'; picker.setAttribute('aria-label', 'Choose teaching example');
  const health = el('pre');
  const memoryQueue = el('div');
  async function showMemoryCandidates() {
    memoryQueue.replaceChildren();
    const rows = await call('memory-candidates');
    if (!rows.length) memoryQueue.append(el('p', 'No extracted candidates for this project.'));
    for (const r of rows) {
      memoryQueue.append(el('pre', JSON.stringify(r, null, 2)));
      for (const [label, decision] of [['Accept reference (not live memory)', 'accept_reference'], ['Reject memory candidate', 'reject']]) {
        memoryQueue.append(act(label, async () => {
          if (!window.confirm('Review exactly this extracted statement? It will not be written to live memory or automatically used.')) return;
          await call('review-memory', {id:r.id, hash:r.hash, decision, confirm:true}); await showMemoryCandidates();
        }));
      }
    }
  }
  async function refresh() {
    state = await call('state');
    refs.replaceChildren(el('option', 'Choose a legacy reference (not approved)'));
    for (const r of state.skills.legacy) { const o = el('option', r.id + ' · legacy reference'); o.value = r.id; refs.append(o); }
    versions.replaceChildren(el('option', 'Choose a version'));
    for (const v of state.skills.versions) { const o = el('option', v.id.slice(0, 8) + ' · r' + v.revision + ' · ' + v.state); o.value = v.id; versions.append(o); }
    if (selected) versions.value = selected.id;
    candidates.replaceChildren(el('option', 'Choose synthetic candidate'));
    for (const c of state.candidates) { const o = el('option', c.id.slice(0, 8) + (c.revoked ? ' · revoked' : c.reviewed ? ' · reviewed' : ' · unreviewed')); o.value = c.id; candidates.append(o); }
    if (candidate) candidates.value = candidate.id;
    scope.replaceChildren();
    for (const source of state.source_choices) {
      const granted = !!state.grants[source.source_id];
      scope.append(act((granted ? 'Revoke ' : 'Allow local retrieval: ') + source.source_id, async () => {
        if (!window.confirm((granted ? 'Revoke' : 'Grant local-only retrieval of') + ' these synthetic record IDs: ' + source.records.join(', ') + '?')) return;
        await call(granted ? 'revoke-grant' : 'grant', granted ? {source: source.source_id} : {source: source.source_id, records: source.records, confirm: true});
        results.textContent = 'Scope changed. Run a new search; previous results cleared.'; await refresh();
      }));
    }
    health.textContent = JSON.stringify({scheduler: state.scheduler, curator: state.curator_example, jcode: state.jcode, training: state.training}, null, 2);
    status.textContent = 'Isolated project: ' + state.project + ' · synthetic data only · ' + state.skills.legacy.length + ' legacy references. No tools execute.';
  }
  async function loadSkill(id) {
    if (!id || id.startsWith('Choose')) return;
    selected = await call('skill?id=' + encodeURIComponent(id)); legacy = selected.legacy;
    for (const name of fields) draftFields[name].value = selected.body[name];
    preview.textContent = JSON.stringify({id: selected.id, revision: selected.revision, state: selected.state, hash: selected.hash, capabilities: selected.capabilities, approval: selected.approval}, null, 2);
    evidence.textContent = selected.test ? JSON.stringify(selected.test, null, 2) : 'No test has been run. Approval unavailable.';
    historyBox.textContent = JSON.stringify(await call('history?id=' + encodeURIComponent(id)), null, 2);
  }
  async function loadCandidate(id) {
    candidate = await call('candidate?id=' + encodeURIComponent(id));
    dataPreview.value = JSON.stringify(candidate.data.messages, null, 2);
    dataStatus.textContent = 'Row hash: ' + candidate.hash + ' · ' + (candidate.data.needs_reverification ? 'edited target needs new observed success proof; export blocked' : candidate.review ? 'consent reviewed' : 'consent required') + (candidate.revoked ? ' · REVOKED' : '');
  }
  versions.onchange = () => loadSkill(versions.value).catch(e => { status.textContent = e.message; });
  candidates.onchange = () => loadCandidate(candidates.value).catch(e => { status.textContent = e.message; });
  panel.append(el('h2', 'Hermes Evolution · staged workbench'), status,
    el('p', 'Teach → Test → Approve → Reuse. Tests here validate a guidance contract on fixtures; they do not prove model behavior. Cloud, live data, autonomous execution and training are disabled.'),
    title('Existing skill library'), refs,
    act('Review selected reference', async () => {
      const r = await call('reference?id=' + encodeURIComponent(refs.value)); legacy = r.id; preview.textContent = r.content;
    }),
    act('Teach new draft', async () => { selected = null; legacy = null; for (const name of fields) draftFields[name].value = ''; preview.textContent = 'New draft. No capabilities enabled.'; evidence.textContent = 'No test has been run.'; }),
    picker, act('Use selected example in draft (local preview only)', async () => {
      const file = picker.files[0]; if (!file || file.size > 16000) throw Error('Choose a .txt/.md example up to 16 KB. No upload is performed.');
      if (!window.confirm('Include this example in a local draft? It remains untrusted reference data.')) return;
      draftFields.method.value = await file.text();
    }), preview, title('Teach'), form,
    act('Save draft', async () => {
      const body = Object.fromEntries(fields.map(name => [name, draftFields[name].value]));
      const value = selected ? await call('edit-skill', {id: selected.id, body, revision: selected.revision}) : await call('teach', {body, legacy});
      await loadSkill(value.id); await refresh();
    }), versions,
    act('Test synthetic contract', async () => {
      if (!selected) throw Error('Save or select a draft first.');
      if (!window.confirm('Run static/synthetic contract checks with NO tools or model?')) return;
      evidence.textContent = JSON.stringify(await call('test', {id: selected.id, revision: selected.revision, confirm: true}), null, 2);
      await loadSkill(selected.id); await refresh();
    }), evidence,
    act('Approve exact tested version', async () => {
      if (!selected || !selected.test || !selected.test.passed) throw Error('A saved passing test is required.');
      if (!window.confirm('Approve guidance-only use of exactly hash ' + selected.hash + '? Review risks and test limitations first.')) return;
      await call('approve', {id: selected.id, hash: selected.hash, test_hash: selected.test.hash, confirm: true}); await loadSkill(selected.id); await refresh();
    }), task,
    act('Reuse selected approved guidance', async () => {
      if (!selected) throw Error('Select an approved version.');
      const bundle = await call('reuse', {id: selected.id, hash: selected.hash, task: task.value, confirm: true});
      preview.textContent = JSON.stringify(bundle, null, 2); status.textContent = 'Guidance bundle prepared. No agent launched, no tools added, no automatic chat send.';
    }),
    act('Revoke skill', async () => { if (!selected || !window.confirm('Revoke this skill approval?')) return; await call('revoke-skill', {id: selected.id}); await loadSkill(selected.id); await refresh(); }),
    title('Version history / rollback'), historyBox, restoreVersion,
    act('Restore historical body as new unapproved draft', async () => {
      if (!selected || !window.confirm('Preserve history and create a new unapproved revision?')) return;
      await call('restore-draft', {id: selected.id, old_revision: Number(restoreVersion.value), revision: selected.revision}); await loadSkill(selected.id); await refresh();
    }),
    title('Project-scoped read-only memory'), scope, query,
    act('Search authorized records', async () => { results.textContent = JSON.stringify(await call('search?q=' + encodeURIComponent(query.value)), null, 2); }), results,
    title('Memory extraction and scheduler health'), health,
    act('Extract fixture candidates for review (no promotion)', async () => { if (!window.confirm('Extract only synthetic user statements into the review queue?')) return; evidence.textContent = JSON.stringify(await call('extract-fixture', {confirm: true}), null, 2); await showMemoryCandidates(); }),
    act('Review extracted memory candidates', showMemoryCandidates), memoryQueue,
    title('Consent-reviewed synthetic dataset'), dataStatus,
    act('Select verified synthetic example', async () => { if (!window.confirm('Select the synthetic success fixture for review?')) return; const c = await call('select-example', {confirm: true}); await loadCandidate(c.id); await refresh(); }), candidates, dataPreview,
    act('Save redacted preview edits (invalidates consent)', async () => { if (!candidate) throw Error('Select a candidate.'); await call('edit-candidate', {id: candidate.id, messages: JSON.parse(dataPreview.value)}); await loadCandidate(candidate.id); await refresh(); }),
    act('Review and consent to exact synthetic row', async () => {
      if (!candidate || !window.confirm('Consent to local training-format export of exactly this reviewed synthetic row? This does not start training.')) return;
      await call('review', {id: candidate.id, hash: candidate.hash, confirm: true}); await loadCandidate(candidate.id); await refresh();
    }),
    act('Download reviewed synthetic JSONL', async () => {
      if (!candidate || !window.confirm('Final confirmation: save this synthetic-only JSONL? No cloud sharing or training.')) return;
      const out = await call('export', {ids: [candidate.id], confirm: true});
      await exportData('save', 'evolution-synthetic.jsonl', 'application/jsonl', textData(out.jsonl), out.jsonl);
      dataStatus.textContent = 'Synthetic export ' + out.id + ' generated; private manifest retained in sidecar. Saved-file delivery must be checked in Android.';
    }),
    act('Revoke dataset consent', async () => { if (!candidate || !window.confirm('Revoke future export eligibility? Already downloaded files cannot be recalled.')) return; await call('revoke-candidate', {id: candidate.id}); await loadCandidate(candidate.id); await refresh(); }),
    act('Refresh workbench', refresh)
  );
  $('evolution-toggle').onclick = async () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) { try { await refresh(); } catch (e) { status.textContent = e.message; } }
  };
})();
