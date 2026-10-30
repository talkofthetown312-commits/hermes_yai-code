'use strict';
// Simulated UI + real staging HTTP. NOT browser rendering or native Android acceptance.
const fs = require('fs'), vm = require('vm'), path = require('path');
class Element {
  constructor(tag, text = '') { this.tagName = tag; this._text = String(text || ''); this.children = []; this.attributes = {}; this.hidden = false; this.value = ''; this.files = []; this.parentElement = null; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent || '').join(''); }
  append(...children) { for (const child of children) { this.children.push(child); child.parentElement = this; } }
  replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  before(...children) { this.parentElement.append(...children); }
  focus() { this.focused = true; }
}
const nodes = new Map(), main = new Element('main'), footer = new Element('footer');
global.$ = id => { if (!nodes.has(id)) { const node = new Element('div'); nodes.set(id, node); main.append(node); } return nodes.get(id); };
global.el = (tag, text, cls) => { const node = new Element(tag, text); node.className = cls || ''; return node; };
footer.append($('composer')); main.append(footer);
$('evolution-panel').hidden = true;
$('evolution-toggle').onclick = async () => { $('evolution-panel').hidden = !$('evolution-panel').hidden; };
$('new').onclick = () => { $('prompt').value = ''; };
global.location = {hash: ''};
global.window = {events: {}, confirm: () => true, addEventListener(name, callback) { this.events[name] = callback; },
  history: {pushState(_state, _title, hash) { location.hash = hash; }}};
global.document = {hidden: false, events: {}, addEventListener(name, callback) { this.events[name] = callback; }};
global.token = 'synthetic-presence-only';
let calls = [], exportsMade = [], draftsRemembered = 0, deferredSearch = null, releaseSearch, failDashboard = false;
let deferredSuggestion = null, releaseSuggestion;
global.api = async (endpoint, body) => {
  calls.push({endpoint, method: body === undefined ? 'GET' : 'POST',
    modelBody: endpoint.startsWith('integration/model-assist/') ? JSON.stringify(body) : undefined});
  if (endpoint === 'integration/dashboard' && failDashboard) throw Error('Synthetic disconnected state');
  const response = await fetch(process.env.FIXTURE_URL + '/api/' + endpoint, {
    method: body === undefined ? 'GET' : 'POST', headers: {'Authorization': 'Bearer ' + process.env.FIXTURE_PAIRING, 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Request rejected');
  if (endpoint.startsWith('evolution/search?') && deferredSearch) await deferredSearch;
  if (endpoint === 'integration/model-assist/suggestion' && deferredSuggestion) await deferredSuggestion;
  return data;
};
global.textData = text => Buffer.from(text).toString('base64');
global.exportData = async (...args) => { exportsMade.push(args); };
global.rememberDraft = () => { draftsRemembered++; };
global.refreshFiles = async () => {};
let assertions = 0;
function check(value, message) { assertions++; if (!value) throw Error(message); }
function all(node) { return [node, ...node.children.flatMap(all)]; }
function findButton(label) { const node = all(main).find(item => item.tagName === 'button' && item.textContent === label); if (!node) throw Error('Missing button ' + label); return node; }
async function click(label) { await findButton(label).onclick(); }
function labeled(label) { const node = all(main).find(item => item.attributes['aria-label'] === label); if (!node) throw Error('Missing control ' + label); return node; }
function workspace(name) { return labeled(name + ' workspace'); }
async function run() {
  vm.runInThisContext(fs.readFileSync(path.join(__dirname, '../web/integration.js'), 'utf8'));
  await window.pocketIntegrationReady;
  check(calls.every(call => call.method === 'GET'), 'Opening mutated state');
  check(!workspace('dashboard').hidden && $('messages').hidden, 'Dashboard is not a real view');
  await click('Memory');
  check(workspace('dashboard').hidden && !workspace('memory').hidden, 'Memory navigation failed');
  await click('Allow hermes');
  labeled('Memory query').value = 'widget'; await click('Search memory');
  check(workspace('memory').textContent.includes('user_statement'), 'User provenance missing');
  check(workspace('memory').textContent.includes('content_hash'), 'Citation missing');
  check(workspace('memory').textContent.includes('Author: user'), 'Author missing');
  check(workspace('memory').textContent.includes('Verified: false'), 'Retrieved text promoted to fact');
  deferredSearch = new Promise(resolve => { releaseSearch = resolve; });
  const pending = findButton('Search memory').onclick();
  // Wait for the request to be received without relying on timing sleeps.
  await api('integration/dashboard');
  await click('Revoke hermes'); releaseSearch(); await pending; deferredSearch = null;
  check(!workspace('memory').textContent.includes('I prefer synthetic'), 'Revocation raced stale response');
  await click('Skills');
  check(!workspace('skills').hidden && workspace('memory').hidden, 'Skills navigation failed');
  const modelPosts = () => calls.filter(call => call.endpoint.startsWith('integration/model-assist/') && call.method === 'POST').length;
  if (process.env.FIXTURE_AI_MODE === 'enabled') {
    check(!findButton('Draft synthetic skill with free model').disabled, 'Configured model drafting unavailable');
    check(labeled('Synthetic AI assistance').textContent.includes('TEST TRANSPORT ONLY'), 'Fake model transport not labeled');
    labeled('Skill method').value = 'PRIVATE_CANARY_NEVER_SEND';
    const postsBefore = modelPosts(); window.confirm = () => false;
    await click('Draft synthetic skill with free model');
    check(modelPosts() === postsBefore, 'Cancelled model consent sent a request'); window.confirm = () => true;
    await click('Draft synthetic skill with free model');
    check(labeled('Skill method').value === 'PRIVATE_CANARY_NEVER_SEND', 'AI draft overwrote the form automatically');
    check(labeled('Synthetic AI assistance').textContent.includes('UNVERIFIED AI DRAFT'), 'AI draft provenance absent');
    check(findButton('Use AI suggestion in unsaved form').disabled, 'Unreviewed AI suggestion was adoptable');
    await click('Review synthetic AI draft');
    check(labeled('Synthetic AI assistance').textContent.includes('STILL NEEDS HUMAN REVIEW'), 'AI review presented as approval');
    deferredSuggestion = new Promise(resolve => { releaseSuggestion = resolve; });
    const pendingAdoption = findButton('Use AI suggestion in unsaved form').onclick();
    await api('integration/dashboard'); labeled('Skill method').value = 'NEW_PRIVATE_EDIT_WHILE_WAITING';
    releaseSuggestion(); await pendingAdoption; deferredSuggestion = null;
    check(labeled('Skill method').value === 'NEW_PRIVATE_EDIT_WHILE_WAITING', 'Late model suggestion overwrote a newer edit');
    await click('Use AI suggestion in unsaved form');
    check(labeled('Skill trigger').value.includes('UNVERIFIED AI-ASSISTED'), 'Adopted AI provenance missing');
    check(!calls.some(call => call.endpoint === 'evolution/teach'), 'AI suggestion saved automatically');
    check(!JSON.stringify(calls.filter(call => call.modelBody)).includes('PRIVATE_'), 'Private form text sent to model route');
  } else {
    check(findButton('Draft synthetic skill with free model').disabled, 'Default model drafting was enabled');
    const postsBefore = modelPosts(); await click('Draft synthetic skill with free model');
    check(modelPosts() === postsBefore, 'Disabled model control sent a request');
    check(findButton('Draft synthetic skill with free model').disabled, 'Disabled control enabled after error');
  }
  await click('Save synthetic picker fixture');
  check(exportsMade[0][1] === 'phase3-teaching-synthetic.md', 'Fixture Save is missing');
  labeled('Choose teaching file').files = [{name: 'synthetic.md', size: 30, text: async () => 'Synthetic imported method'}];
  await click('Import selected teaching text');
  check(labeled('Skill method').value === 'Synthetic imported method', 'Picker import failed');
  const fields = ['trigger','prerequisites','method','tools','inputs','outputs','risks','permissions','verification'];
  for (const field of fields) labeled('Skill ' + field).value = 'Synthetic ' + field + ' instructions.';
  await click('Save skill draft');
  check(workspace('skills').textContent.includes('"state": "draft"'), 'Draft not loaded');
  labeled('Skill method').value = 'Unsaved synthetic edit preserved on resume';
  await window.events.pageshow(); await document.events.visibilitychange();
  check(labeled('Skill method').value === 'Unsaved synthetic edit preserved on resume', 'Resume overwrote unsaved teaching text');
  await click('Memory'); await click('Skills');
  check(labeled('Skill method').value === 'Unsaved synthetic edit preserved on resume', 'Navigation overwrote unsaved teaching text');
  labeled('Skill method').value = 'Synthetic method instructions.';
  const previousApprovals = calls.filter(call => call.endpoint === 'evolution/approve').length;
  await click('Approve tested skill');
  check(calls.filter(call => call.endpoint === 'evolution/approve').length === previousApprovals, 'Untested approval sent');
  await click('Test saved skill');
  check(workspace('skills').textContent.includes('synthetic_contract_static'), 'No real test evidence');
  await click('Approve tested skill');
  check(workspace('skills').textContent.includes('"state": "approved"'), 'Approval not persisted');
  labeled('Guidance task').value = 'Synthetic UI task';
  await click('Save approved SKILL.md');
  check(exportsMade.at(-1)[1] === 'SKILL.md', 'Approved guidance not saved');
  check(exportsMade.at(-1)[4].includes('Guidance only'), 'Guidance format missing');
  await click('Share approved guidance');
  check(exportsMade.at(-1)[0] === 'share', 'Share adapter not invoked');
  await click('Reuse guidance in composer');
  check(!$('messages').hidden && !footer.hidden, 'Conversation navigation failed');
  check($('prompt').value.includes('Guidance only') && draftsRemembered === 1, 'Reuse not staged in composer');
  check(!calls.some(call => call.endpoint === 'send'), 'Reuse automatically sent');
  await click('Skills'); labeled('Skill method').value = 'Edited synthetic method'; await click('Save skill draft');
  const oldExports = exportsMade.length; await click('Save approved SKILL.md');
  check(exportsMade.length === oldExports, 'Stale approval exported after editing');
  await click('Test saved skill'); await click('Approve tested skill'); await click('Revoke approval');
  await click('Share approved guidance');
  check(exportsMade.length === oldExports, 'Revoked skill shared');
  await click('Dashboard');
  check(workspace('dashboard').textContent.includes('revoked skills'), 'Dashboard counts missing');
  failDashboard = true; await click('Refresh dashboard');
  check(workspace('dashboard').textContent.includes('counts are not known'), 'Failed dashboard showed fake zero counts');
  failDashboard = false;
  const writes = calls.filter(call => call.method === 'POST').length;
  await window.events.pageshow(); await document.events.visibilitychange();
  check(calls.filter(call => call.method === 'POST').length === writes, 'Resume mutated workflow');
  document.hidden = true; const callsBefore = calls.length; await document.events.visibilitychange();
  check(calls.length === callsBefore, 'Background started work'); document.hidden = false;
  location.hash = '#memory'; await window.events.popstate();
  check(!workspace('memory').hidden, 'Back/forward navigation failed');
  check(calls.filter(call => call.method === 'POST').length === writes, 'Back navigation wrote state');
  await click('Advanced'); check(!$('evolution-panel').hidden, 'Legacy workbench unavailable');
  await click('Files'); check(!$('file-panel').hidden && $('evolution-panel').hidden, 'Existing file view unavailable');
  check(!calls.some(call => /training|provider/.test(call.endpoint)), 'Unsafe endpoint called');
  console.log(JSON.stringify({assertions, native_android_verified: false, export_adapter: 'MOCKED', api: 'REAL_LOOPBACK',
 model_transport: process.env.FIXTURE_AI_MODE === 'enabled' ? 'FAKE_FOR_TESTS' : 'DISABLED'}));
}
run().catch(error => { console.error(error.stack); process.exitCode = 1; });
