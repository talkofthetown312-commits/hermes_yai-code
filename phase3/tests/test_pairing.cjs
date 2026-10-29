'use strict';
// Exercises the actual main frontend initializer, api() and pairing form, not an
// injected overlay transport. DOM/storage are simulated; native rendering is not.
const fs = require('fs');
const vm = require('vm');
const {legacy, fixed} = JSON.parse(fs.readFileSync(0, 'utf8'));
const synthetic = 'SYNTHETIC_' + 'A'.repeat(40);
const oldValid = 'SYNTHETIC_' + 'B'.repeat(40);
let assertions = 0;
function check(condition, label) {
  assertions++;
  if (!condition) throw Error(label);
}
function harness(source, options = {}) {
  const memory = new Map([['hermes-pocket-token', options.stored ?? '']]);
  const nodes = {'token': {value: ''}, 'pair-form': {}, 'pair': {close() { result.closed++; }}};
  const result = {requests: 0, writes: 0, connects: 0, closed: 0, notices: [], reentrant: []};
  const storage = {
    getItem(key) { if (options.getThrows) throw Error('Synthetic storage read blocked'); return memory.get(key); },
    setItem(key, value) { if (options.setThrows) throw Error('Synthetic storage write blocked'); result.writes++; memory.set(key, value); }
  };
  let context;
  const history = {replaceState() {
    if (options.historyThrows) throw Error('Synthetic history update blocked');
    if (options.reenter) result.reentrant.push(vm.runInContext("api('status')", context));
  }};
  const sandbox = {
    URLSearchParams: options.urlThrows ? class { constructor() { throw Error('Synthetic fragment parse blocked'); } } : URLSearchParams,
    document: {getElementById: id => nodes[id]},
    location: {hash: options.fragment === undefined ? '' : '#pair=' + encodeURIComponent(options.fragment), pathname: '/'},
    window: {history}, localStorage: storage,
    notice: message => result.notices.push(message),
    connect: async () => { result.connects++; await vm.runInContext("api('status')", context); },
    fetch: async (path, request) => {
      // Real Headers enforces the browser's byte-string header restriction.
      const headers = new Headers(request.headers); result.requests++;
      result.headerMatchesSynthetic = headers.get('Authorization') === 'Bearer ' + synthetic;
      result.headerMatchesOld = headers.get('Authorization') === 'Bearer ' + oldValid;
      return {ok: !options.unauthorized, json: async () => options.unauthorized ?
        {error: 'Pairing required'} : {ready: false, adapter: 'phone-staging-no-agent'}};
    }
  };
  context = vm.createContext(sandbox);
  const initializer = source.slice(0, source.indexOf('let current ='));
  const api = source.slice(source.indexOf('async function api('), source.indexOf('function notice('));
  try { vm.runInContext(initializer + '\n' + api, context); } catch (error) { result.bootError = error; }
  const start = source.indexOf("$('pair-form').onsubmit =");
  const end = source.indexOf("$('menu').onclick", start);
  try { vm.runInContext(source.slice(start, end), context); } catch (error) { result.formError = error; }
  result.api = () => vm.runInContext("api('status')", context);
  result.submit = async value => { nodes.token.value = value; await nodes['pair-form'].onsubmit({preventDefault() {}}); };
  return result;
}
async function rejects(action, expected) {
  try { await action(); return false; } catch (error) { return expected(error); }
}
(async () => {
  let h = harness(legacy, {stored: 'bad\u2022pairing'});
  check(await rejects(h.api, e => e.name === 'TypeError'), 'Legacy Unicode-header defect was not reproduced');
  h = harness(legacy, {fragment: synthetic, setThrows: true});
  check(!!h.bootError, 'Legacy storage failure did not abort startup');
  check(await rejects(h.api, e => e.name === 'ReferenceError' && /before initialization/.test(e.message)), 'Legacy token TDZ was not reproduced');
  h = harness(legacy, {fragment: synthetic, historyThrows: true});
  check(!!h.bootError && await rejects(h.api, e => e.name === 'ReferenceError'), 'Legacy history failure did not expose uninitialized token');

  h = harness(fixed, {stored: 'bad\u2022pairing'});
  check(!h.bootError, 'Malformed stored text aborted repaired startup');
  check(await rejects(h.api, e => /Not paired/.test(e.message)) && h.requests === 0, 'Malformed stored text reached Headers/fetch');
  h = harness(fixed, {fragment: synthetic, stored: 'bad\u2022pairing'}); await h.api();
  check(!h.bootError && h.headerMatchesSynthetic, 'Fresh ASCII fragment did not replace malformed stored value');
  h = harness(fixed, {fragment: synthetic, setThrows: true}); await h.api();
  check(!h.bootError && h.headerMatchesSynthetic, 'Storage write failure lost valid in-memory pairing');
  h = harness(fixed, {fragment: synthetic, historyThrows: true}); await h.api();
  check(!h.bootError && h.headerMatchesSynthetic, 'History failure lost valid in-memory pairing');
  h = harness(fixed, {getThrows: true});
  check(!h.bootError && await rejects(h.api, e => /Not paired/.test(e.message)), 'Storage read failure exposed TDZ');
  h = harness(fixed, {stored: synthetic, urlThrows: true}); await h.api();
  check(!h.bootError && h.headerMatchesSynthetic, 'Fragment API failure broke valid stored pairing');
  h = harness(fixed, {fragment: synthetic, reenter: true}); await Promise.all(h.reentrant);
  check(h.requests === 1 && h.headerMatchesSynthetic, 'History reentry observed uninitialized pairing');
  h = harness(fixed, {fragment: 'invalid\u2022fragment', stored: oldValid}); await h.api();
  check(h.headerMatchesOld && h.writes === 0, 'Invalid fragment overwrote a valid existing value');
  h = harness(fixed, {stored: 'x'.repeat(101)});
  check(await rejects(h.api, e => /Not paired/.test(e.message)) && h.requests === 0, 'Oversized stored value reached fetch');
  h = harness(fixed, {stored: 'token\r\nInjection'});
  check(await rejects(h.api, e => /Not paired/.test(e.message)) && h.requests === 0, 'Control characters reached headers');
  h = harness(fixed); await h.submit('bad\u2022manual-input');
  check(h.writes === 0 && h.requests === 0 && h.closed === 0 && h.notices.length === 1, 'Malformed manual entry was persisted or sent');
  check(!h.notices.join('').includes('bad\u2022manual-input'), 'Notice echoed pairing input');
  h = harness(fixed, {setThrows: true}); await h.submit(synthetic);
  check(h.connects === 1 && h.closed === 1 && h.headerMatchesSynthetic, 'Manual pairing failed when storage was blocked');
  h = harness(fixed, {fragment: synthetic, unauthorized: true});
  check(await rejects(h.api, e => e.message === 'Pairing required'), 'Repair bypassed server authorization rejection');
  h = harness(fixed, {fragment: synthetic}); const state = await h.api();
  check(state.ready === false && state.adapter === 'phone-staging-no-agent', 'Repair claimed a live chat backend');
  console.log(JSON.stringify({status: 'PASS', assertions, legacy_failures_reproduced: 3,
    actual_main_frontend_code: true, simulated_dom_storage: true,
    native_android_rendering: false, real_credentials_used: false}));
})().catch(error => { console.error(error.name + ': ' + error.message); process.exit(1); });
