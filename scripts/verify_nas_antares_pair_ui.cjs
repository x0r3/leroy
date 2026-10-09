// Read-only desktop/mobile checks of an actual terminal Antares comparison run.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');
const [runId, commit] = process.argv.slice(2);
if (!/^[a-f0-9]{32}$/.test(runId || '') || !/^[a-f0-9]{40}$/.test(commit || '')) throw Error('Actual run ID and frozen commit required');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const folder = resolve(root, 'test-results/nas-parity', 'visual-antares-' + runId);
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [], artifacts = [];
  page.on('pageerror', error => errors.push(error.message));
  async function shot(name) {
    await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    screenshots.push(name);
  }
  try {
    const login = await page.request.post(base + '/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    const response = await page.request.get(base + '/api/runs/' + runId);
    expect(response.ok()).toBe(true);
    const run = await response.json();
    expect(run.pipeline_id).toBe('antares-ci'); expect(run.commit).toBe(commit);
    expect(['succeeded', 'failed', 'timed_out', 'interrupted']).toContain(run.status);
    expect(run.steps.map(step => step.id).sort()).toEqual(['checkout', 'toolchain', 'postgres', 'dependencies', 'static', 'tests', 'build', 'browsers', 'cleanup'].sort());
    const selected = run.steps.findIndex(step => ['failed', 'timed_out', 'interrupted'].includes(step.status));
    const index = selected >= 0 ? selected : run.steps.findIndex(step => step.id === 'browsers');
    for (const mobile of [false, true]) {
      await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
      await page.goto(base + '/#/runs/' + runId);
      await page.getByRole('button', { name: 'Graph', exact: true }).click();
      await expect(page.locator('.svelte-flow__node')).toHaveCount(9);
      await page.locator('.step-list > button').nth(index).click();
      await page.getByRole('button', { name: 'Konsole', exact: true }).click();
      await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
      if (run.steps[index].log_bytes) await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).not.toBeEmpty();
      await shot((mobile ? 'mobile' : 'desktop') + '-graph-console');
      await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
      await page.getByRole('button', { name: 'Ergebnisse', exact: true }).click();
      await shot((mobile ? 'mobile' : 'desktop') + '-timeline-results');
      await page.getByRole('button', { name: 'Artefakte', exact: true }).click();
      await shot((mobile ? 'mobile' : 'desktop') + '-artifacts');
    }
    const item = run.artifacts.find(a => a.name.endsWith('test-failed-1.png')) || run.artifacts.find(a => a.name.endsWith('.json')) || run.artifacts[0];
    if (item) {
      const reply = await page.request.get(base + '/api/artifacts/' + item.id);
      expect(reply.ok()).toBe(true); const data = await reply.body();
      expect(data.length).toBe(item.size);
      expect(createHash('sha256').update(data).digest('hex')).toBe(item.sha256);
      artifacts.push({ name: item.name, size: item.size, sha256: item.sha256 });
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), run: runId, commit, status: run.status, screenshots, artifacts, errors, passed: true, manual_visual_review: false }, null, 2));
    console.log(JSON.stringify({ run: runId, status: run.status, screenshots: screenshots.length, artifacts: artifacts.length, passed: true }));
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
