// Driver-only checks for a separate upstream proposal; no network or application acceptance.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import test from 'node:test';

const folder = resolve('.local/graphato-native-rate-proposal');
const original = await readFile(resolve(folder, 'original-command.txt'), 'utf8');
const proposed = await readFile(resolve(folder, 'proposed-command.txt'), 'utf8');
const limited = (seconds = 1, header = String(seconds), kind = 'serverRateLimited') => ({
  status: 429, value: { error: { kind, message: 'bounded rejection', retryAfterSeconds: seconds } }, header,
});
const success = { status: 200, value: { result: 'accepted' } };

function harness(source, responses) {
  let now = 0, accepted = 0;
  const requests = [], waits = [], budgets = [];
  const fetch = async (url, options) => {
    requests.push({ url, body: options.body });
    const item = responses[Math.min(requests.length - 1, responses.length - 1)];
    if (item instanceof Error) throw item;
    if (item.status === 200) accepted++;
    return { status: item.status, headers: { get: () => item.header ?? null }, json: async () => item.value };
  };
  const driver = new Function('fetch', 'delay', 'Date', 'AbortSignal', 'randomUUID',
    'fixture', 'apiContractHeaders', 'token', 'acceptanceFailure', 'secrets', `return (${source});`)(
    fetch, async ms => { waits.push(ms); now += ms; }, { now: () => now },
    { timeout: ms => { budgets.push(ms); return {}; } }, () => 'one-logical-request',
    { apiBase: 'http://fixture.invalid' }, {}, 'synthetic-token',
    value => Object.assign(new Error(value.message ?? 'failure'), { kind: value.kind }), [],
  );
  return { driver, requests, waits, budgets, accepted: () => accepted, now: () => now };
}

test('original driver reproduces immediate failure on a transient rate rejection', async () => {
  const value = harness(original, [limited(), success]);
  await assert.rejects(value.driver('sendSessionPrompt', {}), { kind: 'serverRateLimited' });
  assert.equal(value.requests.length, 1); assert.equal(value.accepted(), 0);
});

test('opt-in retry waits, preserves the request body and completes one accepted mutation', async () => {
  const value = harness(proposed, [limited(), success]);
  const records = [];
  assert.equal(await value.driver('sendSessionPrompt', {}, { rateLimitRetries: 2,
    onRateLimit: record => records.push(record) }), 'accepted');
  assert.deepEqual(value.waits, [1000]); assert.equal(value.requests.length, 2);
  assert.equal(value.requests[0].body, value.requests[1].body);
  assert.equal(value.accepted(), 1); assert.equal(records.length, 1);
  assert.deepEqual(value.budgets, [90000, 89000]);
});

test('commands outside the opt-in soak retain immediate rate-limit failure', async () => {
  const value = harness(proposed, [limited(), success]);
  await assert.rejects(value.driver('createStory', {}), { kind: 'serverRateLimited' });
  assert.equal(value.requests.length, 1); assert.deepEqual(value.waits, []);
});

test('two retries bound persistent throttling to three attempts', async () => {
  const value = harness(proposed, [limited()]);
  await assert.rejects(value.driver('sendSessionPrompt', {}, { rateLimitRetries: 2 }),
    { kind: 'serverRateLimited' });
  assert.equal(value.requests.length, 3); assert.deepEqual(value.waits, [1000, 1000]);
  assert.equal(value.accepted(), 0);
});

test('concurrency rejection, server failure and transport uncertainty are not retried', async () => {
  for (const response of [limited(1, null, 'runtime'),
    { status: 500, value: { error: { kind: 'runtime', message: 'server failure' } } }, new Error('transport failed')]) {
    const value = harness(proposed, [response, success]);
    await assert.rejects(value.driver('sendSessionPrompt', {}, { rateLimitRetries: 2 }));
    assert.equal(value.requests.length, 1); assert.deepEqual(value.waits, []);
  }
});

test('invalid or inconsistent Retry-After is rejected', async () => {
  for (const response of [limited(1, null), limited(1, '0'), limited(1, '-1'),
    limited(1, '2'), limited(61, '61'), limited(1, 'not-a-number')]) {
    const value = harness(proposed, [response, success]);
    await assert.rejects(value.driver('sendSessionPrompt', {}, { rateLimitRetries: 2 }));
    assert.equal(value.requests.length, 1); assert.deepEqual(value.waits, []);
  }
});

test('the original ninety-second total budget bounds waiting across retries', async () => {
  const value = harness(proposed, [limited(60)]);
  await assert.rejects(value.driver('sendSessionPrompt', {}, { rateLimitRetries: 2 }),
    { kind: 'serverRateLimited' });
  assert.deepEqual(value.waits, [60000]); assert.equal(value.requests.length, 2);
  assert.deepEqual(value.budgets, [90000, 30000]);
});

test('the caller can enforce a shared budget and stop sustained throttling', async () => {
  const value = harness(proposed, [limited(), success]);
  await assert.rejects(value.driver('sendSessionPrompt', {}, { rateLimitRetries: 2,
    onRateLimit: () => { throw new Error('shared retry budget exhausted'); } }),
  /shared retry budget exhausted/);
  assert.equal(value.requests.length, 1); assert.equal(value.accepted(), 0);
});
