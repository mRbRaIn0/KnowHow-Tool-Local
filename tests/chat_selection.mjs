// Run with: node --experimental-vm-modules tests/chat_selection.mjs
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm';
const context = createContext({ console, URLSearchParams });
let posted;
const callbacks = [];
const api = { status: () => new Promise(resolve => callbacks.push(resolve)) };
const apiModule = new SyntheticModule(['api', 'streamPost'], function () {
  this.setExport('api', api);
  this.setExport('streamPost', (url, body, handlers) => {
    posted = { url, body, handlers };
    return () => {};
  });
}, { context });
const store = new SourceTextModule(await readFile('frontend/js/store.js', 'utf8'), { context });
await store.link(() => apiModule);
await store.evaluate();
const older = store.namespace.refreshStatus();
const newer = store.namespace.refreshStatus();
callbacks[1]({ model: { name: 'new' } });
await newer;
callbacks[0]({ model: { name: 'old' } });
await older;
assert.equal(store.namespace.state.status.model.name, 'new');
const stream = new SourceTextModule(await readFile('frontend/js/chatstream.js', 'utf8'), { context });
await stream.link(name => name === './api.js' ? apiModule : store);
await stream.evaluate();
const selection = { model: 'qwen3.5:9b', thinking: false };
const run = stream.namespace.send('test', 'hello', selection);
selection.model = 'changed-after-send';
assert.equal(posted.body.model, 'qwen3.5:9b');
assert.equal(posted.body.thinking, false);
posted.handlers.onEvent({ type: 'start', model: 'qwen3.5:9b', thinking: false, message_id: 12 });
assert.equal(run.model, 'qwen3.5:9b');
assert.equal(run.thinkingEnabled, false);
console.log('PASS: stale status ignored; per-message selection captured and server state retained.');
