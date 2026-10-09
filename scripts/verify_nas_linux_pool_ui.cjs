// Read-only verification of the new worker and the live distributed observer.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const folder = resolve(root, 'test-results/nas-parity/visual-linux-pool');
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
const identity = JSON.parse(readFileSync(resolve(root, 'test-results/nas-parity/followup/antares-jenkins-58da3ef5d112-linux-pool-volume-owner/run-id.json')));
mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [];
  page.on('pageerror', error => errors.push(error.message));
  async function shot(name) {
    await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    screenshots.push(name);
  }
  try {
    const login = await page.request.post(base + '/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    const response = await page.request.get(base + '/api/runners');
    expect(response.ok()).toBe(true);
    const workers = await response.json();
    const pool = workers.find(worker => worker.id === 'runner-nas-linux-pool');
    expect(pool).toBeTruthy(); expect(pool.online).toBe(true); expect(pool.profiles).toEqual(['antares-linux']);
    const nas = workers.find(worker => worker.id === 'runner-nas-parity');
    expect(nas.online).toBe(true); expect(nas.profiles).not.toContain('antares');
    for (const mobile of [false, true]) {
      await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
      await page.goto(base + '/#/runners');
      await expect(page.getByRole('heading', { name: 'runner-nas-linux-pool', exact: true })).toBeVisible();
      await expect(page.locator('.runner-card').filter({ hasText: 'runner-nas-linux-pool' })).toContainText('antares-linux');
      await shot((mobile ? 'mobile' : 'desktop') + '-runners');
      await page.goto(base + '/#/runs/' + identity.id);
      await expect(page.locator('.run-facts')).toContainText('runner-nas-linux-pool');
      await expect(page.locator('.svelte-flow__node')).toHaveCount(1);
      await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
      await shot((mobile ? 'mobile' : 'desktop') + '-observer');
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), observer: identity.id, worker: pool.id, profiles: pool.profiles, screenshots, errors, passed: true, manual_visual_review: false }, null, 2));
    console.log(JSON.stringify({ screenshots: screenshots.length, worker: pool.id, passed: true }));
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
