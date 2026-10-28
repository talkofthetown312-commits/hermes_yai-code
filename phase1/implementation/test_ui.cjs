'use strict';
// Simulated DOM with actual authenticated localhost API. Not a browser/rendering test.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
class Element {
  constructor(tag, text = '') { this.tagName = tag; this._text = String(text || ''); this.children = []; this.attributes = {}; this.value = ''; this.hidden = false; this.disabled = false; this.files = []; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map(x => x.textContent || '').join(''); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  setAttribute(k,v) { this.attributes[k] = String(v); }
}
const nodes = new Map();
global.$ = id => { if (!nodes.has(id)) nodes.set(id, new Element('div')); return nodes.get(id); };
global.el = (tag,text,cls) => { const e = new Element(tag,text); if (cls) e.className = cls; return e; };
let confirmations = 0, savedFiles = [], calls = [];
global.window = {confirm() { confirmations++; return true; }};
global.api = async (endpoint,data) => {
  const headers = {'Authorization':'Bearer '+process.env.FIXTURE_PAIRING};
  const opts = {headers};
  if (data !== undefined) { opts.method = 'POST'; headers['Content-Type']='application/json'; opts.body=JSON.stringify(data); }
  const r = await fetch(process.env.FIXTURE_URL+'/api/'+endpoint,opts);
  const out = await r.json(); calls.push({endpoint,method:opts.method || 'GET'});
  if (!r.ok) throw Error(out.error || 'HTTP error');
  return out;
};
global.textData = t => Buffer.from(t).toString('base64');
global.exportData = async (...args) => { savedFiles.push(args); };
const assertions=[];
const check = (ok,msg) => { if (!ok) throw Error(msg); assertions.push(msg); };
function all(e) { return [e,...e.children.flatMap(c => typeof c === 'object' ? all(c) : [])]; }
function button(label) { const b = all($('evolution-panel')).find(e => e.tagName==='button' && e.textContent===label); check(b,'Missing button '+label); return b; }
function labeled(label) { const e = all($('evolution-panel')).find(e => e.attributes['aria-label']===label); check(e,'Missing labeled control '+label); return e; }
async function click(label) { await button(label).onclick(); }
async function main() {
  $('evolution-panel').hidden = true; // Matches the hidden attribute in index.html.
  vm.runInThisContext(fs.readFileSync(path.join(__dirname,'pocket/web/evolution.js'),'utf8'));
  await $('evolution-toggle').onclick();
  check(calls.length===1 && calls[0].endpoint==='evolution/state','Opening panel must not execute tests/approve/export');
  await click('Teach new draft');
  for (const f of ['trigger','prerequisites','method','tools','inputs','outputs','risks','permissions','verification']) labeled(f).value = 'Synthetic '+f+' procedure.';
  await click('Save draft');
  await click('Approve exact tested version');
  check(!calls.some(c => c.endpoint==='evolution/approve'),'Missing-test approval attempted');
  await click('Test synthetic contract');
  await click('Approve exact tested version');
  labeled('Reuse task').value='synthetic-dom-task';
  await click('Reuse selected approved guidance');
  let state = await api('evolution/state');
  check(state.skills.versions.length===1 && state.skills.versions[0].state==='approved','Approved state absent');
  check(calls.filter(c => c.endpoint==='evolution/reuse').length===1,'Explicit reuse absent');
  labeled('method').value='Edited synthetic guidance';
  await click('Save draft');
  state = await api('evolution/state');
  check(state.skills.versions[0].state==='draft' && state.skills.versions[0].revision===2,'Edit did not invalidate approval');
  await click('Allow local retrieval: hermes');
  labeled('Memory search').value='widget';
  await click('Search authorized records');
  let result = await api('evolution/search?q=widget'); check(result.count===1,'Granted record unavailable');
  await click('Revoke hermes');
  result = await api('evolution/search?q=widget'); check(result.count===0,'Revocation failed');
  await click('Extract fixture candidates for review (no promotion)');
  await click('Accept reference (not live memory)');
  const memories = await api('evolution/memory-candidates');
  check(memories.length===1 && memories[0].state==='reviewed_reference_not_verified' && !memories[0].verified, 'Memory review promoted or lost provenance');
  await click('Select verified synthetic example');
  check(labeled('Review redacted synthetic messages').value.includes('SYNTHETIC_FIXTURE_OK'),'Dataset preview absent');
  await click('Review and consent to exact synthetic row');
  await click('Download reviewed synthetic JSONL');
  check(savedFiles.length===1,'Reviewed dataset not delivered to save adapter');
  const row = JSON.parse(savedFiles[0][4].trim()); check(row.messages[1].content==='SYNTHETIC_FIXTURE_OK','Unexpected dataset content');
  await click('Revoke dataset consent');
  await click('Download reviewed synthetic JSONL'); check(savedFiles.length===1,'Revoked data exported');
  check(confirmations>=8,'Explicit confirmation controls missing');
  check(!fs.readFileSync(path.join(__dirname,'pocket/web/evolution.js'),'utf8').includes('innerHTML'),'Unsafe HTML injection');
  const report = {status:'PASS',assertion_count:assertions.length,assertions,simulated_dom:true,actual_phone_rendering:false,native_picker_share_save:false,authenticated_http_calls:calls.length,explicit_confirmation_controls:confirmations,synthetic_save_adapter_calls:savedFiles.length,teach_test_approve_reuse:true,edit_invalidation:true,project_grant_revocation:true,consent_review_export_revocation:true,agent_execution:false};
  fs.writeFileSync(path.join(__dirname,'UI_QA.json'),JSON.stringify(report,null,2));
  process.stdout.write(JSON.stringify(report));
}
main().catch(e => { console.error(e.message); process.exitCode=1; });
