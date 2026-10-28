'use strict';
const $ = id => document.getElementById(id);
const pairedFragment = new URLSearchParams(location.hash.slice(1)).get('pair');
if (pairedFragment) {
  window.history.replaceState(null, '', location.pathname);
  if (/^[A-Za-z0-9_-]{32,100}$/.test(pairedFragment)) localStorage.setItem('hermes-pocket-token', pairedFragment);
}
let token = localStorage.getItem('hermes-pocket-token') || '';
let current = null, busy = false, ready = false, sending = false, uploading = false, polling = false;
let currentChat = null, rendered = '', fileRefreshKey = '';
const drafts = new Map(), cache = new Map(), openTools = new Set();
const welcome = $('messages').innerHTML;
const nativeApp = /HermesPocket\//.test(navigator.userAgent || '');
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function button(label, fn) {
  const b = el('button', label); b.type = 'button';
  b.onclick = async () => { try { await fn(); } catch (e) { notice(e.message); } };
  return b;
}
async function api(path, body) {
  const r = await fetch('/api/' + path, {
    method: body ? 'POST' : 'GET',
    headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json'},
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await r.json();
  if (!r.ok) throw Error(data.error || 'Connection failed');
  return data;
}
function notice(message) { $('notice').textContent = message || ''; }
function draft() {
  const key = current || 'new';
  if (!drafts.has(key)) drafts.set(key, {text: '', files: [], consent: false, loaded: false});
  return drafts.get(key);
}
function rememberDraft() { const d = draft(); d.text = $('prompt').value; d.consent = $('cloud-consent').checked; }
function controls() {
  $('send').disabled = busy || !ready || sending || uploading;
  $('attach').disabled = busy || !ready || sending || uploading;
  $('new').disabled = sending || uploading;
  $('mode').disabled = !!current || sending || uploading;
  $('models').disabled = !!current || sending || uploading;
}
function route() {
  const local = $('mode').value === 'local';
  $('models').hidden = !local;
  $('route-note').textContent = local ? 'Local · limited 1B accuracy' : 'Cloud · configured provider';
  $('cloud-consent-row').hidden = local || !draft().files.length;
}
async function models() {
  try {
    const r = await api('models'), selected = $('models').value;
    $('models').replaceChildren();
    for (const name of r.models) { const o = el('option', name); o.value = name; $('models').append(o); }
    if (r.models.includes(selected)) $('models').value = selected;
    if (!r.online && $('mode').value === 'local') notice(r.detail);
    else if (!r.models.length && $('mode').value === 'local') notice('No local model installed.');
  } catch (e) { notice(e.message); }
}
function switchChat(id) {
  if (sending || uploading) return;
  rememberDraft(); current = id; currentChat = null; busy = false; rendered = ''; fileRefreshKey = '';
  $('prompt').value = draft().text; $('cloud-consent').checked = draft().consent;
  $('sidebar').classList.remove('open'); renderDraft();
  $('messages').textContent = id ? 'Loading conversation…' : '';
  $('artifacts').textContent = id ? 'Open Files to refresh this conversation’s outputs.' : 'Choose a conversation first.';
  if (id) load(); else {
    $('messages').innerHTML = welcome; controls(); route();
    $('artifacts').textContent = 'Choose a conversation first.';
    notice('Choose Local or Cloud. Attachments stay on this phone until sent.');
    history().catch(e => notice(e.message));
  }
}
async function history() {
  const chats = await api('chats'); $('history').replaceChildren();
  for (const chat of chats) {
    const b = button(chat.title, () => switchChat(chat.id));
    b.className = chat.id === current ? 'active' : '';
    b.append(el('small', (chat.mode === 'local' ? 'LOCAL' : 'CLOUD') + (chat.state === 'running' ? ' · Working' : '')));
    $('history').append(b);
  }
}
function bytes(n) { return n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(1) + ' KB' : (n / 1048576).toFixed(1) + ' MB'; }
async function copy(text) {
  try {
    if (!navigator.clipboard) throw Error('Clipboard API unavailable');
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const field = el('textarea'); field.value = text; field.className = 'clipboard-fallback';
    document.body.append(field); field.select();
    const copied = document.execCommand('copy'); field.remove();
    if (!copied) throw Error('Copy unavailable. Select the message text and copy manually.');
  }
  notice('Copied to clipboard.');
}
function textData(text) { return btoa(unescape(encodeURIComponent(text))); }
async function exportData(action, name, mime, data, plainText) {
  if (nativeApp) {
    const result = window.prompt('HERMES_POCKET_EXPORT', JSON.stringify({action, name, mime, data}));
    if (result !== 'opened') throw Error(result || 'Android export was not opened.');
    notice(action === 'share' ? 'Android share chooser opened.' : 'Choose where to save in Android.');
    return;
  }
  const raw = Uint8Array.from(atob(data), c => c.charCodeAt(0));
  const blob = new Blob([raw], {type: mime});
  if (action === 'share') {
    if (plainText !== undefined && navigator.share) { await navigator.share({text: plainText}); return; }
    if (typeof File !== 'undefined' && navigator.canShare && navigator.share) {
      const files = [new File([blob], name, {type: mime})];
      if (navigator.canShare({files})) { await navigator.share({files}); return; }
    }
    throw Error('File sharing is unavailable in this browser. Use Save, then share from Files.');
  }
  const url = URL.createObjectURL(blob), a = el('a'); a.href = url; a.download = name;
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
  notice('Browser download requested.');
}
function textActions(parent, text, name) {
  const actions = el('div', undefined, 'message-actions');
  actions.append(button('Copy', () => copy(text)),
    button('Share', () => exportData('share', name, 'text/plain', textData(text), text)),
    button('Save', () => exportData('save', name, 'text/plain', textData(text), text)));
  parent.append(actions);
}
async function fileContent(file, cid) {
  // Re-fetch generated files: the agent may have updated their contents.
  if (file.source === 'upload' && cache.has(file.id)) return cache.get(file.id);
  const data = await api('files/' + encodeURIComponent(file.id) + '?chat=' + encodeURIComponent(cid));
  if (file.source === 'upload') {
    cache.set(file.id, data);
    if (cache.size > 6) cache.delete(cache.keys().next().value);
  }
  return data;
}
async function previewFile(file, cid) {
  const data = await fileContent(file, cid);
  $('preview-title').textContent = data.name; $('preview-body').replaceChildren(); $('preview-actions').replaceChildren();
  if (['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(data.mime)) {
    const img = el('img'); img.alt = data.name; img.src = 'data:' + data.mime + ';base64,' + data.data;
    $('preview-body').append(img);
  } else {
    $('preview-body').append(el('pre', data.preview || data.preview_error || 'No inline preview. Save this file to open it with an appropriate app.'));
  }
  $('preview-actions').append(button('Share file', () => exportData('share', data.name, data.mime, data.data)),
    button('Save file', () => exportData('save', data.name, data.mime, data.data)));
  if (!$('preview').open) $('preview').showModal();
}
function fileCard(file, cid, removable = false) {
  const card = el('div', undefined, 'attachment');
  card.append(button((file.mime.startsWith('image/') ? '▧ ' : '▤ ') + file.name, () => previewFile(file, cid)), el('small', bytes(file.size)));
  if (removable) card.append(button('Remove', async () => {
    if (sending || uploading) return;
    await api('files/remove', {chat: cid, id: file.id});
    const d = draft(); d.files = d.files.filter(f => f.id !== file.id); d.consent = false;
    cache.delete(file.id); $('cloud-consent').checked = false; renderDraft();
  }));
  return card;
}
function renderDraft() {
  $('draft-files').replaceChildren();
  for (const file of draft().files) $('draft-files').append(fileCard(file, current, true));
  route(); controls();
}
function render(chat) {
  currentChat = chat; busy = chat.state === 'running'; $('mode').value = chat.mode || 'cloud';
  route(); if (chat.mode === 'local') $('models').value = chat.model;
  controls(); $('status').textContent = busy ? 'Hermes is working…' : ready ? 'Connected · ' + (chat.mode === 'local' ? chat.model : 'Cloud provider') : 'Adapter check needed';
  const signature = JSON.stringify(chat);
  if (signature !== rendered) {
    rendered = signature;
    const area = $('messages'), near = area.scrollHeight - area.scrollTop - area.clientHeight < 120;
    area.replaceChildren();
    chat.messages.forEach((m, index) => {
      const item = el('div', undefined, 'message ' + m.role);
      item.append(el('div', m.role === 'user' ? 'YOU' : 'HERMES', 'role'), el('div', m.text, 'message-text'));
      for (const file of m.attachments || []) item.append(fileCard(file, chat.id));
      for (const tool of m.tools || []) {
        const details = el('details', undefined, 'tool-card'), key = chat.id + ':' + index + ':' + tool.id;
        details.open = openTools.has(key);
        details.ontoggle = () => { if (details.open) openTools.add(key); else openTools.delete(key); };
        details.append(el('summary', tool.name + ' · ' + tool.status));
        const text = 'Arguments:\n' + (tool.arguments || '(not available)') + '\n\nResult:\n' + (tool.output || (tool.status === 'running' ? 'Waiting…' : 'No result received.'));
        details.append(el('pre', text)); textActions(details, text, tool.name.replace(/[^a-z0-9_-]/gi, '_') + '-result.txt'); item.append(details);
      }
      if (m.activity) item.append(el('div', m.activity, 'activity'));
      if (m.text) textActions(item, m.text, 'hermes-message-' + (index + 1) + '.txt');
      area.append(item);
    });
    if (!chat.messages.length) area.innerHTML = welcome;
    if (near) area.scrollTop = area.scrollHeight;
  }
  notice(chat.error);
  const key = chat.id + ':' + signature;
  if (!busy && key !== fileRefreshKey && !$('file-panel').hidden) { fileRefreshKey = key; refreshFiles(); }
}
async function load() {
  if (!current) return; const id = current;
  try {
    const chat = await api('chats/' + id);
    if (id === current) {
      if (!draft().loaded && !sending && !uploading) {
        const pending = await api('drafts?chat=' + id);
        if (id !== current) return;
        draft().files = pending; draft().loaded = true; renderDraft();
      }
      render(chat);
    }
    await history();
  }
  catch (e) { notice(e.message); }
}
async function refreshFiles() {
  if (!current) { $('artifacts').textContent = 'Choose a conversation first.'; return; }
  const id = current;
  try {
    const files = await api('artifacts?chat=' + id);
    if (id !== current) return;
    $('artifacts').replaceChildren();
    if (!files.length) $('artifacts').textContent = 'No files created yet. Ask Hermes to create a downloadable file.';
    for (const file of files) $('artifacts').append(fileCard(file, id));
  } catch (e) { notice(e.message); }
}
async function connect() {
  try {
    const state = await api('status'); ready = state.ready;
    $('status').textContent = ready ? 'Connected · Hermes ready' : 'Adapter check needed';
    notice(state.ready ? '' : state.detail); controls(); $('settings').textContent = 'Paired';
    await models(); await history(); if (current) await load();
  } catch (e) { ready = false; controls(); $('status').textContent = 'Not connected'; notice(e.message); }
}
async function ensureChat() {
  if (current) return current;
  const d = draft(), chat = await api('chats', {mode: $('mode').value, model: $('models').value});
  current = chat.id; d.loaded = true; drafts.set(current, d); drafts.delete('new'); rendered = ''; controls(); return current;
}
function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(Error('Could not read ' + file.name)); reader.onabort = () => reject(Error('File read cancelled.'));
    reader.readAsDataURL(file);
  });
}
async function attachFiles(files) {
  if (uploading || sending || busy || !ready || !files.length) return;
  if (files.length + draft().files.length > 6) { notice('Attach up to six files per message.'); return; }
  if (files.some(f => !f.size || f.size > 10 * 1024 * 1024)) { notice('Choose nonempty files up to 10 MB each.'); return; }
  uploading = true; controls();
  try {
    rememberDraft(); const cid = await ensureChat();
    for (const file of files) {
      notice('Copying ' + file.name + ' to private phone storage…');
      const data = await readFile(file), meta = await api('files/upload', {chat: cid, name: file.name, data});
      draft().files.push(meta); draft().consent = false; $('cloud-consent').checked = false;
      renderDraft();
    }
    await load(); notice('Attached. Tap a filename to preview. Files have not been sent to the AI yet.');
  } catch (e) { notice(e.message); }
  finally { uploading = false; $('file-input').value = ''; renderDraft(); }
}
function transcript() {
  if (!currentChat) return '';
  return 'Hermes Pocket — ' + currentChat.title + '\nMode: ' + currentChat.mode + '\n\n' + currentChat.messages.map(m =>
    m.role.toUpperCase() + '\n' + m.text +
    (m.attachments || []).map(a => '\n[Attachment: ' + a.name + ']').join('') +
    (m.tools || []).map(t => '\n[Tool ' + t.name + ' · ' + t.status + ']\n' + (t.arguments || '') + '\n' + (t.output || '')).join('')
  ).join('\n\n');
}
$('settings').onclick = () => { $('token').value = token; $('pair').showModal(); };
$('close').onclick = () => $('pair').close();
$('pair-form').onsubmit = async e => { e.preventDefault(); token = $('token').value.trim(); localStorage.setItem('hermes-pocket-token', token); $('pair').close(); await connect(); };
$('menu').onclick = () => $('sidebar').classList.toggle('open');
$('new').onclick = () => switchChat(null);
$('mode').onchange = () => { draft().consent = false; $('cloud-consent').checked = false; route(); notice(''); models(); };
$('refresh').onclick = models;
$('prompt').oninput = rememberDraft;
$('cloud-consent').onchange = rememberDraft;
$('attach').onclick = () => $('file-input').click();
$('file-input').onchange = e => attachFiles(Array.from(e.target.files));
$('files-toggle').onclick = () => { $('file-panel').hidden = !$('file-panel').hidden; if (!$('file-panel').hidden) refreshFiles(); };
$('files-refresh').onclick = refreshFiles;
$('preview-close').onclick = () => $('preview').close();
$('export-close').onclick = () => $('export').close();
$('chat-export').onclick = () => { if (!currentChat) notice('Open a conversation first.'); else $('export').showModal(); };
$('export-copy').onclick = () => copy(transcript()).catch(e => notice(e.message));
for (const action of ['share', 'save']) $('export-' + action).onclick = () => {
  const text = transcript(); exportData(action, 'hermes-conversation.txt', 'text/plain', textData(text), text).catch(e => notice(e.message));
};
document.addEventListener('click', e => {
  const b = e.target.closest('[data-prompt]');
  if (b) { $('prompt').value = b.dataset.prompt; rememberDraft(); $('prompt').focus(); }
});
$('composer').onsubmit = async e => {
  e.preventDefault(); if (busy || !ready || sending || uploading) return;
  rememberDraft(); const d = draft(), message = d.text.trim() || (d.files.length ? 'Please analyse the attached files.' : '');
  if (!message) return;
  if (d.files.length && $('mode').value === 'cloud' && !d.consent) { notice('Review the Cloud sharing notice and tick the consent box before sending.'); return; }
  sending = true; controls();
  try {
    await ensureChat();
    await api('send', {id: current, message, attachments: d.files.map(f => f.id), consent: d.consent});
    d.text = ''; d.files = []; d.consent = false; $('prompt').value = ''; $('cloud-consent').checked = false;
    renderDraft(); await load();
  } catch (e) { notice(e.message); }
  finally { sending = false; controls(); }
};
setInterval(async () => {
  if (!current || polling || document.hidden || uploading || sending) return;
  polling = true; try { await load(); } finally { polling = false; }
}, 1400);
route(); controls(); if (token) connect(); else notice('Start the bridge in Termux, then tap Connect to pair.');
