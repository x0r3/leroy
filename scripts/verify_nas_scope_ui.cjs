// Read-only UI check of the accepted NAS topology; retain actual worker health.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const label = process.argv[2];
if (!/^[a-z0-9-]+$/.test(label || '')) throw Error('Provide a distinct evidence label');
const folder = resolve(root, 'test-results/nas-parity', 'visual-nas-scope-' + label);
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    const login = await page.request.post(base + '/api/auth/login', { timeout: 45000, headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    const pipelinesResponse = await page.request.get(base + '/api/pipelines', { timeout: 45000 });
    const runnersResponse = await page.request.get(base + '/api/runners', { timeout: 45000 });
    expect(pipelinesResponse.ok()).toBe(true); expect(runnersResponse.ok()).toBe(true);
    const pipelines = await pipelinesResponse.json(), runners = await runnersResponse.json();
    const antares = pipelines.find(p => p.id === 'antares-ci');
    expect(antares.enabled).toBe(false); expect(antares.spec.source.acceptance_excluded).toBe(true);
    expect(antares.spec.profile).toBe('image-builds');
    const pool = runners.find(r => r.id === 'runner-nas-linux-pool');
    const nas = runners.find(r => r.id === 'runner-nas-parity');
    expect(pool.online).toBe(false); expect(nas.profiles).toContain('graphato');
    expect(nas.profiles).not.toContain('antares');
    for (const mobile of [false, true]) {
      await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
      for (const route of ['/runners', '/pipelines/antares-ci']) {
        await page.goto(base + '/#' + route);
        if (route === '/runners') {
          for (const worker of [pool, nas]) {
            const card = page.locator('.runner-card').filter({ hasText: worker.id });
            await expect(card.locator('.badge')).toHaveText(worker.online ? 'Online' : 'Offline');
          }
        } else {
          await expect(page.getByRole('heading', { name: antares.spec.name, exact: true })).toBeVisible();
          await expect(page.locator('.page-heading')).toContainText(antares.spec.description);
          await expect(page.locator('.pipeline-config')).toContainText('Pausiert');
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
        const name = (mobile ? 'mobile' : 'desktop') + (route === '/runners' ? '-runners' : '-antares-exclusion');
        await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true }); screenshots.push(name);
      }
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), screenshots, errors, passed: true, manual_visual_review: false, nas_worker_online: nas.online, optional_pool_online: pool.online, antares_excluded: true, workload_acceptance_asserted: false }, null, 2));
    console.log(JSON.stringify({ passed: true, screenshots: screenshots.length, nas_worker_online: nas.online }));
  } finally { await browser.close(); }
})().catch(error => {
  const detail = String(error.stack || error).replaceAll(password, '[REDACTED]');
  writeFileSync(resolve(folder, 'failure.json'), JSON.stringify({ at: new Date().toISOString(), passed: false, error: detail }, null, 2));
  console.error(detail); process.exitCode = 1;
});
