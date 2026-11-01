'use strict';
const $ = id => document.getElementById(id);
let token = '', selected = null, current = null, pollTimer = null, busy = false;
function node(tag, value, className) { const element = document.createElement(tag); if (value !== undefined) element.textContent = value; if (className) element.className = className; return element; }
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body ? 'POST' : 'GET', cache: 'no-store', headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Request failed');
  return result;
}
function notice(value) { $('notice').textContent = value; }
function renderTask(task) {
  const messages = $('messages');
  const follow = !current || !task || current.id !== task.id || messages.scrollTop + messages.clientHeight >= messages.scrollHeight - 40;
  current = task; $('task-title').textContent = task ? task.prompt : 'Start a task';
  $('task-status').textContent = task ? task.status.replaceAll('_', ' ') : '';
  $('messages').replaceChildren();
  if (task) for (const message of task.messages) {
    const card = node('article', undefined, 'message');
    card.append(node('strong', message.sender + ' → ' + message.recipient));
    card.append(node('small', ' · ' + message.kind));
    const body = message.body;
    card.append(node('p', body.summary || body.text || body.instruction || body.reason || (body.attempt ? 'Attempt ' + body.attempt : 'Decision recorded')));
    for (const key of ['findings', 'issues', 'risks']) if (Array.isArray(body[key]) && body[key].length) {
      const list = node('ul'); for (const value of body[key]) list.append(node('li', value)); card.append(list);
    }
    if (body.artifacts) for (const artifact of body.artifacts) {
      const details = node('details'); details.append(node('summary', 'Proposed file: ' + artifact.path), node('pre', artifact.content)); card.append(details);
    }
    if (body.checks) for (const check of body.checks) card.append(node('p', check.path + ' · ' + check.check + ': ' + (check.passed ? 'passed' : 'failed')));
    if (body.assignments || body.records) {
      const details = node('details'); details.append(node('summary', body.assignments ? 'Delegated instructions' : 'Local source excerpts'), node('pre', JSON.stringify(body.assignments || body.records, null, 2))); card.append(details);
    }
    $('messages').append(card);
  }
  if (follow) messages.scrollTop = messages.scrollHeight;
  $('approval').hidden = !task || task.status !== 'awaiting_approval';
  $('cancel').hidden = !task || !['queued', 'running', 'awaiting_approval'].includes(task.status);
  for (const element of document.querySelectorAll('.agent')) {
    const step = task && task.steps.find(item => item.role === element.dataset.role);
    element.dataset.state = step ? step.status : 'idle';
    element.querySelector('.activity').textContent = step ? step.status + ' · attempt ' + step.attempts : 'idle';
  }
}
async function refresh() {
  const state = await api('state');
  $('connection').textContent = state.scheduler_alive ? 'Connected · scheduler active' : 'Connected · scheduler stopped';
  if (!$('agents').children.length) for (const role of state.roles) {
    const card = node('div', undefined, 'agent'); card.dataset.role = role;
    card.append(node('strong', role), node('span', 'idle', 'activity'));
    const route = state.routes[role]; card.append(node('div', route ? route.provider + ' · ' + route.model : 'Local read-only sources', 'route')); $('agents').append(card);
  }
  if (!$('memory').querySelector('input') && state.memory_sources.length) for (const name of state.memory_sources) {
    const label = node('label', undefined, 'check'), box = node('input'); box.type = 'checkbox'; box.value = name;
    box.onchange = () => { if (box.checked) $('cloud').checked = false; };
    label.append(box, node('span', name)); $('memory').append(label);
  }
  $('tasks').replaceChildren();
  for (const task of state.tasks) {
    const button = node('button', task.prompt.slice(0, 70) + ' · ' + task.status); button.type = 'button';
    button.setAttribute('aria-current', String(selected === task.id));
    button.onclick = async () => { selected = task.id; try { await refresh(); } catch (error) { notice(error.message); } };
    $('tasks').append(button);
  }
  if (selected) { const task = await api('tasks/' + selected); if (!current || current.id !== task.id || current.revision !== task.revision) renderTask(task); }
}
async function poll() {
  clearTimeout(pollTimer);
  try { if (!busy) await refresh(); } catch (error) { notice(error.message); }
  pollTimer = setTimeout(poll, 1200);
}
$('pair-form').onsubmit = async event => {
  event.preventDefault(); const value = $('token').value.trim();
  if (!/^[A-Za-z0-9_-]{32,100}$/.test(value)) return notice('Enter the workspace pairing token.');
  token = value;
  try { await refresh(); $('token').value = ''; $('pair-form').hidden = true; $('workspace').hidden = false; notice(''); poll(); }
  catch (error) { token = ''; notice(error.message); }
};
$('new-task').onclick = () => { selected = null; renderTask(null); $('prompt').focus(); };
$('cloud').onchange = () => { if ($('cloud').checked) for (const box of $('memory').querySelectorAll('input')) box.checked = false; };
$('compose').onsubmit = async event => {
  event.preventDefault(); if (busy) return; busy = true; $('send').disabled = true;
  try {
    const task = await api('tasks', {prompt: $('prompt').value, cloud_consent: $('cloud').checked,
      memory_sources: [...$('memory').querySelectorAll('input:checked')].map(box => box.value)});
    selected = task.id; renderTask(task); $('prompt').value = ''; notice(''); await refresh();
  } catch (error) { notice(error.message); }
  finally { busy = false; $('send').disabled = false; }
};
async function decision(action) {
  if (!current || busy) return; busy = true;
  try { renderTask(await api('tasks/' + current.id + '/decision', {action, revision: current.revision, result_hash: current.result_hash})); notice(''); await refresh(); }
  catch (error) { notice(error.message); await refresh().catch(() => {}); }
  finally { busy = false; }
}
$('approve').onclick = () => decision('approve'); $('reject').onclick = () => decision('reject'); $('cancel').onclick = () => decision('cancel');
