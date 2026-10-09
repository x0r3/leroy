// Focused read-only review of real follow-up run data on desktop and mobile.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const folder = resolve(root, 'test-results/nas-parity', process.argv[2]);
const ids = process.argv.slice(3);
const expectedStatus = process.env.LEROY_UI_EXPECT_STATUS || 'succeeded';
if (!['succeeded', 'failed', 'cancelled', 'timed_out', 'interrupted'].includes(expectedStatus)) throw Error('Unsupported expected run status');
if (!process.argv[2] || !/^[a-z0-9-]+$/.test(process.argv[2]) || !ids.length || ids.some(id => !/^[a-f0-9]{32}$/.test(id))) throw Error('Provide output label and real run IDs');
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [], artifacts = [];
  page.on('pageerror', e => errors.push(e.message));
  async function shot(name) {
    await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    screenshots.push(name);
  }
  try {
    const login = await page.request.post(base + '/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    for (const id of ids) {
      const response = await page.request.get(base + '/api/runs/' + id);
      expect(response.ok()).toBe(true);
      const run = await response.json();
      expect(run.status).toBe(expectedStatus);
      const selected = run.steps.find(step => ['failed', 'timed_out', 'cancelled', 'interrupted'].includes(step.status))?.id || run.artifacts[0]?.step_id || run.steps.at(-1).id;
      const selectedIndex = run.steps.findIndex(step => step.id === selected);
      for (const artifact of run.artifacts) {
        const reply = await page.request.get(base + '/api/artifacts/' + artifact.id);
        expect(reply.ok()).toBe(true);
        const bytes = await reply.body();
        expect(bytes.length).toBe(artifact.size);
        expect(createHash('sha256').update(bytes).digest('hex')).toBe(artifact.sha256);
        artifacts.push({run: id, name: artifact.name, sha256: artifact.sha256});
      }
      for (const mobile of [false, true]) {
        const label = id.slice(0, 8) + (mobile ? '-mobile' : '-desktop');
        await page.setViewportSize(mobile ? {width: 390, height: 844} : {width: 1440, height: 1000});
        await page.goto(base + '/#/runs/' + id);
        await page.reload();
        await page.getByRole('button', {name: 'Graph', exact: true}).click();
        await expect(page.locator('.svelte-flow__node')).toHaveCount(run.steps.length);
        await page.locator('.step-list > button').nth(selectedIndex).click();
        await page.getByRole('button', {name: 'Konsole', exact: true}).click();
        await expect(page.getByRole('region', {name: 'Konsolenausgabe'})).toHaveAttribute('aria-busy', 'false');
        await shot(label + '-graph');
        if (mobile) {
          await page.getByRole('button', {name: 'Zeitachse', exact: true}).click();
          if (process.env.LEROY_UI_CHECK_TIMELINE_STATUS === '1') {
            const colors = {succeeded:'rgb(120, 166, 116)', failed:'rgb(203, 145, 120)', timed_out:'rgb(203, 145, 120)', running:'rgb(130, 167, 199)', interrupted:'rgb(156, 123, 177)', cancelled:'rgb(156, 123, 177)', waiting:'rgb(207, 167, 86)', queued:'rgb(207, 167, 86)', pending:'rgb(158, 170, 161)', skipped:'rgb(158, 170, 161)'};
            for (let index = 0; index < run.steps.length; index++) {
              const row = page.locator('.timeline-row').nth(index);
              await expect(row).toHaveAttribute('aria-label', new RegExp(run.steps[index].name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
              await expect(row.locator('.bar')).toHaveCSS('background-color', colors[run.steps[index].status]);
            }
          }
        }
        for (const name of ['Ergebnisse', 'Artefakte']) {
          await page.getByRole('button', {name, exact: true}).click();
          await expect(page.getByRole('button', {name, exact: true})).toHaveClass(/active/);
          if (name === 'Artefakte') await expect(page.locator('.artifact-row')).toHaveCount(run.artifacts.filter(a => a.step_id === selected).length);
          await shot(label + '-' + (name === 'Ergebnisse' ? 'results' : 'artifacts'));
        }
      }
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({at: new Date().toISOString(), runs: ids, expected_status: expectedStatus, screenshots, artifacts, errors, passed: true, manual_visual_review: false}, null, 2));
    console.log('Follow-up run UI passed:', screenshots.length, 'screenshots;', artifacts.length, 'artifact hashes verified.');
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
