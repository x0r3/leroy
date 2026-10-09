// Diagnostic preload: retain only API timing, route, command name and status.
// Neither request/response headers nor payloads, cookies or tokens are written.
import { appendFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { performance } from 'node:perf_hooks';

export function routeMetadata(address, method = 'GET', body = '') {
  let path;
  try { path = new URL(address).pathname; } catch { return null; }
  if (!path.startsWith('/api/v1/')) return null;
  const route = ['/api/v1/commands', '/api/v1/events', '/api/v1/info',
    '/api/v1/browser/session', '/api/v1/browser/sessions'].includes(path) ? path : 'other-api';
  const command = route === '/api/v1/commands' && typeof body === 'string'
    ? body.slice(0, 512).match(/"command"\s*:\s*"([A-Za-z][A-Za-z0-9_]{0,99})"/)?.[1] ?? null : null;
  return { route, method: ['GET', 'POST', 'DELETE', 'PUT', 'PATCH'].includes(method) ? method : 'OTHER', command };
}

if (process.argv[1]?.endsWith('/open-runner.mjs')) {
  const path = '/artifacts/leroy-http-metadata.log';
  const started = performance.now();
  let buffer = [], count = 0, dropped = 0, requestsStarted = 0;
  const flush = () => {
    if (!buffer.length) return;
    appendFileSync(path, buffer.join(''), { mode: 0o600 });
    buffer = [];
  };
  function record(row) {
    if (++count > 200_000) { dropped++; return; }
    buffer.push(JSON.stringify(row) + '\n');
    if (buffer.length >= 1000) flush();
  }
  record({ kind: 'diagnostic-start', epoch_ms: Date.now(),
    metadata_only: true, request_behavior_changed: false });
  const interval = setInterval(flush, 500); interval.unref();
  process.on('exit', () => {
    buffer.push(JSON.stringify({ kind: 'diagnostic-end', recorded: Math.min(count, 200_000), dropped }) + '\n');
    flush();
  });
  const fetchOriginal = globalThis.fetch;
  globalThis.fetch = async function(input, init) {
    const metadata = routeMetadata(typeof input === 'string' ? input : input.url,
      init?.method ?? 'GET', init?.body);
    const at = performance.now() - started;
    const request = metadata ? { client: 'native-driver', request_id: ++requestsStarted,
      ...metadata, started_ms: at } : null;
    if (request) record({ kind: 'request-start', ...request });
    try {
      const response = await fetchOriginal.call(this, input, init);
      if (request) record({ kind: 'request', ...request,
        completed_ms: performance.now() - started, status: response.status });
      return response;
    } catch (error) {
      if (request) record({ kind: 'request', ...request,
        completed_ms: performance.now() - started, status: null, transport_error: true });
      throw error;
    }
  };
  const require = createRequire(process.argv[1]);
  const playwright = require('@playwright/test');
  let contexts = 0;
  for (const type of [playwright.chromium, playwright.firefox]) {
    const launch = type.launch;
    type.launch = async function(...args) {
      const browser = await launch.apply(this, args);
      const newContext = browser.newContext;
      browser.newContext = async function(...options) {
        const context = await newContext.apply(this, options);
        const id = ++contexts, requests = new WeakMap();
        context.on('request', request => {
          const metadata = routeMetadata(request.url(), request.method(), request.postData());
          if (metadata) {
            const row = { client: 'browser', context: id, request_id: ++requestsStarted,
              ...metadata, started_ms: performance.now() - started };
            requests.set(request, row);
            record({ kind: 'request-start', ...row });
          }
        });
        context.on('response', response => {
          const row = requests.get(response.request());
          if (row) record({ kind: 'request', ...row, completed_ms: performance.now() - started, status: response.status() });
        });
        context.on('requestfailed', request => {
          const row = requests.get(request);
          if (row) record({ kind: 'request', ...row, completed_ms: performance.now() - started, status: null, transport_error: true });
        });
        return context;
      };
      return browser;
    };
  }
  record({ kind: 'observer-ready', native_fetch: true, browser_contexts: true });
}
