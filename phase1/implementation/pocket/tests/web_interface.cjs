'use strict';
// Real parsed DOM + mocked transport/native intents, not visual Android automation.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const {parseHTML} = require(process.env.POCKET_LINKEDOM || (process.env.HOME + '/.cache/pocket-ui-qa/node_modules/linkedom'));
const root = path.join(__dirname, '..');
const {window} = parseHTML(fs.readFileSync(path.join(root, 'web/index.html'), 'utf8'));
const {document} = window, calls = [], exportsOpened = [], copied = [], chats = new Map(), files = new Map();
let failSend = false, next = 0;
for (const node of document.querySelectorAll('select')) {
  let value = node.id === 'mode' ? 'cloud' : '';
  Object.defineProperty(node, 'value', {get: () => value, set: v => {value = v;}});
}
for (const node of document.querySelectorAll('dialog')) {node.showModal = () => {node.open = true;}; node.close = () => {node.open = false;};}
const $ = id => document.getElementById(id);
const sandbox = {
  console, document, URLSearchParams, URL, Map, Set, Uint8Array, Blob,
  btoa: s => Buffer.from(s, 'binary').toString('base64'), atob: s => Buffer.from(s, 'base64').toString('binary'),
  encodeURIComponent, unescape, setTimeout, setInterval() {},
  navigator: {userAgent: 'Android HermesPocket/0.2.0', clipboard: {writeText: async t => copied.push(t)}},
  location: {hash: '', pathname: '/'},
  window: {history: {replaceState() {}}, prompt: (key, json) => {assert.equal(key, 'HERMES_POCKET_EXPORT');exportsOpened.push(JSON.parse(json));return 'opened';}},
  localStorage: {getItem: () => 'synthetic-pairing-value', setItem() {}},
  FileReader: class {readAsDataURL(file) {this.result = 'data:text/plain;base64,' + Buffer.from(file.content).toString('base64');this.onload();}},
  fetch: async (url, options) => {
    calls.push({url, options}); const body = options.body ? JSON.parse(options.body) : null;
    const route = url.slice(5); let data, ok = true;
    if (route === 'status') data = {ready: true};
    else if (route === 'models') data = {online: true, models: ['test-model']};
    else if (route === 'chats' && !body) data = [...chats.values()];
    else if (route === 'chats') {const id = String(++next).padStart(32, '0');chats.set(id, {id, mode: body.mode, model: body.model, messages: [], title: 'New conversation', state: 'idle'});data = {id};}
    else if (route.startsWith('chats/')) data = chats.get(route.split('/')[1]);
    else if (route === 'files/upload') {const id = 'file-' + files.size;data = {...body, id, mime: 'text/plain', size: Buffer.from(body.data, 'base64').length, source: 'upload', preview: Buffer.from(body.data, 'base64').toString()};files.set(id, data);}
    else if (route === 'files/remove') {files.delete(body.id);data = {ok: true};}
    else if (route.startsWith('files/')) data = files.get(route.split('/')[1].split('?')[0]);
    else if (route.startsWith('artifacts?') || route.startsWith('drafts?')) data = [];
    else if (route === 'send') {
      if (failSend) {ok = false; data = {error: 'Synthetic network failure'};}
      else {const chat = chats.get(body.id);chat.title = body.message;chat.messages.push({role: 'user', text: body.message, attachments: body.attachments.map(id => files.get(id))}, {role: 'assistant', text: '<script>untrusted()</script>', tools: [{id: 't1', name: 'terminal', status: 'completed', arguments: '{"command":"printf ok"}', output: '<img src=x onerror=bad()>\nok'}]});data = {ok: true};}
    } else throw Error('Unexpected route ' + route);
    return {ok, json: async () => data};
  }
};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(root, 'web/app.js'), 'utf8'), sandbox);
const run = source => vm.runInContext(source, sandbox);
const tick = () => new Promise(resolve => setImmediate(resolve));
let checks = 0;
function pass(name) {checks++;console.log('PASS: ' + name);}
(async () => {
  await tick();assert.equal($('send').disabled, false);assert.equal($('attach').disabled, false);pass('Connected controls');
  await run("attachFiles([{name:'invoice.txt',size:13,content:'invoice alpha'}])");
  assert.equal($('draft-files').querySelectorAll('.attachment').length, 1);assert.equal($('cloud-consent-row').hidden, false);pass('Phone file read/upload and Cloud notice');
  await $('draft-files').querySelector('button').onclick();assert.equal($('preview').open, true);assert.equal($('preview-body').querySelector('pre').textContent, 'invoice alpha');pass('Attachment text preview');
  $('prompt').value = 'Summarize';await $('composer').onsubmit({preventDefault() {}});
  assert.equal(calls.filter(c => c.url.endsWith('/send')).length, 0);assert.match($('notice').textContent, /consent/);pass('Cloud consent prevents send');
  $('cloud-consent').checked = true;failSend = true;await $('composer').onsubmit({preventDefault() {}});
  assert.equal($('prompt').value, 'Summarize');assert.equal($('draft-files').querySelectorAll('.attachment').length, 1);assert.match($('notice').textContent, /failure/);pass('Failed send preserves prompt and attachments');
  failSend = false;const before = calls.filter(c => c.url.endsWith('/send')).length;
  await Promise.all([$('composer').onsubmit({preventDefault() {}}), $('composer').onsubmit({preventDefault() {}})]);
  assert.equal(calls.filter(c => c.url.endsWith('/send')).length, before + 1);
  const request = calls.filter(c => c.url.endsWith('/send')).at(-1);assert.equal(JSON.parse(request.options.body).consent, true);assert.deepEqual(JSON.parse(request.options.body).attachments, ['file-0']);pass('Single submit and exact attachment IDs');
  assert.equal($('messages').querySelectorAll('script').length, 0);assert.equal($('messages').querySelectorAll('img').length, 0);
  assert.match($('messages').textContent, /untrusted/);assert.match($('messages').querySelector('.tool-card').textContent, /completed/);assert.match($('messages').querySelector('.tool-card pre').textContent, /printf ok/);pass('Expandable tool arguments/results and plain-text XSS boundary');
  const reply = $('messages').querySelector('.message.assistant');await reply.querySelectorAll(':scope > .message-actions button')[0].onclick();assert.equal(copied.at(-1), '<script>untrusted()</script>');pass('Copy response');
  await reply.querySelectorAll(':scope > .message-actions button')[1].onclick();await reply.querySelectorAll(':scope > .message-actions button')[2].onclick();assert.deepEqual(exportsOpened.slice(-2).map(x => x.action), ['share', 'save']);assert.equal(Buffer.from(exportsOpened.at(-1).data, 'base64').toString(), '<script>untrusted()</script>');pass('Native share and save payloads');
  $('chat-export').onclick();assert.equal($('export').open, true);$('export-copy').onclick();await tick();assert.match(copied.at(-1), /Tool terminal/);assert.match(copied.at(-1), /invoice.txt/);pass('Conversation export includes tools and attachment names');
  const oldId = run('current');$('prompt').value = 'unfinished draft';$('new').onclick();assert.equal($('prompt').value, '');await run('switchChat(' + JSON.stringify(oldId) + ')');await tick();assert.equal($('prompt').value, 'unfinished draft');pass('Drafts isolated and restored across conversations');
  $('new').onclick();const uploadCount = calls.filter(c => c.url.endsWith('/files/upload')).length;
  await run("attachFiles([{name:'huge.txt',size:11000000,content:'x'}])");assert.equal(calls.filter(c => c.url.endsWith('/files/upload')).length, uploadCount);assert.match($('notice').textContent, /10 MB/);pass('Oversized file rejected before transport');
  for (const call of calls) {assert(!call.url.includes('synthetic-pairing-value'));assert.equal(call.options.headers.Authorization, 'Bearer synthetic-pairing-value');}
  pass('Credentials only in auth headers');
  console.log('TOTAL FAILURES: 0; DOM flow checks=' + checks + ' (not device UI tests)');
})().catch(e => {console.error(e);process.exit(1);});
