// Inspect the real interrupted attempt and its retry without starting another job.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const folder = resolve(root, 'test-results/nas-parity', process.argv[2] || 'visual-retry');
const pair = JSON.parse(readFileSync(resolve(root, 'test-results/nas-parity/aligned/graphato-ci/pair.json')));
const old = pair.leroy_attempts.at(-1).run_id;
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [], screenshots = [];
  page.on('pageerror', e => errors.push(e.message));
  try {
    const response = await page.request.post(base + '/api/auth/login', {
      headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password },
    });
    expect(response.status()).toBe(200);
    const oldResponse = await page.request.get(base + '/api/runs/' + old);
    expect(oldResponse.ok()).toBe(true);
    const prior = await oldResponse.json();
    expect(['failed', 'interrupted']).toContain(prior.status);
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.goto(base + '/#/runs/' + pair.leroy_run);
      const original = page.getByRole('link', { name: '↗ Ursprünglicher Versuch' });
      await expect(original).toHaveAttribute('href', '#/runs/' + old);
      await expect(page.locator('.svelte-flow__node')).toHaveCount(10);
      await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
      await page.screenshot({ path: resolve(folder, name + '-retry.png'), fullPage: true });
      screenshots.push(name + '-retry');
      await original.click();
      await expect(page.locator('.notice.' + prior.status)).toHaveText(prior.reason);
      await expect(page.locator('.page-heading .badge')).toHaveText(prior.status === 'interrupted' ? 'Unterbrochen' : 'Fehlgeschlagen');
      await expect(page.getByRole('button', { name: 'Erneut ausführen', exact: true })).toBeVisible();
      await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
      await page.screenshot({ path: resolve(folder, name + '-interrupted.png'), fullPage: true });
      screenshots.push(name + '-interrupted');
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), run: pair.leroy_run, retry_of: old, screenshots, errors, passed: true }, null, 2));
    console.log('Retry relationship and interruption UI passed:', screenshots.length, 'screenshots');
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
