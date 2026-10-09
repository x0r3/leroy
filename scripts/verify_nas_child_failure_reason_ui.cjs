// Read-only verification of a deliberately failed parent and its real child.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync, existsSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const proof = JSON.parse(readFileSync(resolve(root, 'test-results/nas-parity/followup/child-failure-reason-nas/report.json'), 'utf8'));
if (!proof.passed || !proof.expected_pipeline_failure || !proof.both_runs_remain_failed) throw Error('Actual negative-test receipt required');
const folder = resolve(root, 'test-results/nas-parity/visual-child-failure-reason');
if (existsSync(resolve(folder, 'report.json'))) throw Error('Retain the completed UI report');
mkdirSync(folder, { recursive: true });
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [], screenshots = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    const login = await page.request.post(base + '/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    const response = await page.request.get(base + '/api/runs/' + proof.parent_run);
    expect(response.ok()).toBe(true);
    const run = await response.json();
    expect(run.status).toBe('failed');
    expect(run.reason).toBe('acceptance: Child job did not succeed');
    expect(run.image_digest).toBe(proof.updated_image_used);
    for (const mobile of [false, true]) {
      await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
      await page.goto(base + '/#/runs/' + proof.parent_run);
      await expect(page.getByText(run.reason, { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Graph', exact: true }).click();
      await expect(page.locator('.svelte-flow__node')).toHaveCount(1);
      await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
      for (const results of [false, true]) {
        if (results) {
          if (mobile) await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
          await page.getByRole('button', { name: 'Ergebnisse', exact: true }).click();
        }
        const name = (mobile ? 'mobile' : 'desktop') + (results ? '-results' : '-graph');
        await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true });
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
        screenshots.push(name);
      }
      const child = page.locator('.child-row[href="#/runs/' + proof.child_run + '"]');
      await expect(child.locator('.badge')).toHaveClass(/\bfailed\b/);
      await child.click();
      await expect(page).toHaveURL(base + '/#/runs/' + proof.child_run);
      const parent = page.locator('.related a[href="#/runs/' + proof.parent_run + '"]');
      await expect(parent).toBeVisible(); await parent.click();
      await expect(page).toHaveURL(base + '/#/runs/' + proof.parent_run);
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), passed: true,
      parent_run: proof.parent_run, child_run: proof.child_run, expected_pipeline_failure: true,
      parent_reason_visible: true, both_runs_remain_failed: true, screenshots, errors, manual_visual_review: false }, null, 2));
    console.log('Four child-failure reason views captured; manual visual review remains.');
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
