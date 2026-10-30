"""Phase 3-only frontend hardening; never imports an app or handles a real token.

Transform the reviewed baseline source before copying it into synthetic staging.
The original Phase 1/2 files and server authentication policy remain unchanged.
"""

MARKER = '// Pocket Phase 3: guarded browser pairing bootstrap v1'

ORIGINAL_BOOTSTRAP = """'use strict';
const $ = id => document.getElementById(id);
const pairedFragment = new URLSearchParams(location.hash.slice(1)).get('pair');
if (pairedFragment) {
  window.history.replaceState(null, '', location.pathname);
  if (/^[A-Za-z0-9_-]{32,100}$/.test(pairedFragment)) localStorage.setItem('hermes-pocket-token', pairedFragment);
}
let token = localStorage.getItem('hermes-pocket-token') || '';"""

GUARDED_BOOTSTRAP = """'use strict';
// Pocket Phase 3: guarded browser pairing bootstrap v1
// Initialize before storage/history APIs can throw or reenter another script.
let token = '';
const pocketPairingState = {link: false, linkValid: false, saved: false, storage: 'not-read'};
const $ = id => document.getElementById(id);
function pocketStagingPairingValue(value) {
  if (typeof value !== 'string') return '';
  const candidate = value.trim();
  return /^[A-Za-z0-9_-]{32,100}$/.test(candidate) ? candidate : '';
}
(() => {
  let fragment = null;
  try { fragment = new URLSearchParams(location.hash.slice(1)).get('pair'); } catch (_) {}
  const fromLink = pocketStagingPairingValue(fragment);
  pocketPairingState.link = fragment !== null;
  pocketPairingState.linkValid = !!fromLink;
  if (fromLink) {
    // In-memory pairing must survive blocked/full browser storage.
    token = fromLink;
    try { localStorage.setItem('hermes-pocket-token', token); pocketPairingState.storage = 'saved'; }
    catch (_) { pocketPairingState.storage = 'write-blocked'; }
  } else {
    try {
      const saved = localStorage.getItem('hermes-pocket-token');
      pocketPairingState.saved = !!saved;
      pocketPairingState.storage = 'read-ok';
      token = pocketStagingPairingValue(saved);
    } catch (_) { pocketPairingState.storage = 'read-blocked'; }
  }
  if (fragment !== null) {
    // A URL-cleanup failure must never abort initialization or print the link.
    try { window.history.replaceState(null, '', location.pathname); } catch (_) {}
  }
})();"""

ORIGINAL_API = """async function api(path, body) {
  const r = await fetch('/api/' + path, {
    method: body ? 'POST' : 'GET',
    headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/json'},"""

GUARDED_API = """async function api(path, body) {
  const headerToken = pocketStagingPairingValue(token);
  if (!headerToken) throw Error('Not paired [pairing-check v2: link=' +
    pocketPairingState.link + ', valid-link=' + pocketPairingState.linkValid +
    ', saved=' + pocketPairingState.saved + ', storage=' + pocketPairingState.storage +
    ']. Use the private staging link or Connect with the existing staging token.');
  const r = await fetch('/api/' + path, {
    method: body ? 'POST' : 'GET',
    headers: {Authorization: 'Bearer ' + headerToken, 'Content-Type': 'application/json'},"""

ORIGINAL_SUBMIT = """$('pair-form').onsubmit = async e => { e.preventDefault(); token = $('token').value.trim(); localStorage.setItem('hermes-pocket-token', token); $('pair').close(); await connect(); };"""

GUARDED_SUBMIT = """$('pair-form').onsubmit = async e => {
  e.preventDefault();
  const candidate = pocketStagingPairingValue($('token').value);
  if (!candidate) {
    notice('Invalid pairing text. Use only the existing staging token from the private pairing link.');
    return;
  }
  token = candidate;
  try { localStorage.setItem('hermes-pocket-token', token); } catch (_) {}
  $('pair').close();
  await connect();
};"""


def harden_pairing_javascript(source):
    """Return a complete, idempotent patch or refuse an unknown source layout."""
    if MARKER in source:
        if (source.count(MARKER) == 1 and GUARDED_BOOTSTRAP in source
                and GUARDED_API in source and GUARDED_SUBMIT in source):
            return source
        raise ValueError('Incomplete staging pairing patch refused')
    replacements = ((ORIGINAL_BOOTSTRAP, GUARDED_BOOTSTRAP),
                    (ORIGINAL_API, GUARDED_API), (ORIGINAL_SUBMIT, GUARDED_SUBMIT),
                    ("'Staging connected · Models disabled'", "'Staging connected · Normal chat disabled'"),
                    ('Synthetic-only preview. No model or agent runs here.',
                     'Synthetic-only preview. Normal chat is disabled; synthetic AI assistance is separate and opt-in.'))
    if any(source.count(old) != 1 for old, _ in replacements):
        raise ValueError('Unknown Pocket frontend layout; pairing patch refused')
    result = source
    for old, new in replacements:
        result = result.replace(old, new, 1)
    return result
