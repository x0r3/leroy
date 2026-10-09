// Read-only visual checks of the actual long Graphato run and its child hierarchy.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const phase = process.argv[2] || 'live';
if (!['live', 'final'].includes(phase)) throw new Error('Expected live or final');
const folder = resolve(root, 'test-results/nas-parity/visual-graphato-' + phase);
mkdirSync(folder, { recursive: true });
const id = JSON.parse(readFileSync(resolve(root, 'test-results/nas-parity/aligned/graphato-ci/pair.json'))).leroy_run;
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const screenshots = [], errors = [], relationships = [];
  page.on('pageerror', e => errors.push(e.message));
  async function run(runId) {
    const response = await page.request.get(base + '/api/runs/' + runId);
    expect(response.ok()).toBe(true);
    return response.json();
  }
  async function shot(name, locator) {
    if (locator) await locator.screenshot({ path: resolve(folder, name + '.png') });
    else { await page.evaluate(() => scrollTo(0, 0)); await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true }); }
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    screenshots.push(name);
  }
  try {
    const login = await page.request.post(base + '/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    const ci = await run(id);
    expect(ci.steps).toHaveLength(10);
    await page.goto(base + '/#/runs/' + id);
    await expect(page.locator('.svelte-flow__node')).toHaveCount(ci.steps.length);
    await expect(page.locator('.svelte-flow__minimap')).toBeVisible();
    const index = ci.steps.findIndex(s => s.id === 'server');
    await page.locator('.step-list button').nth(index).click();
    await expect(page.locator('.step-detail h2')).toHaveText(ci.steps[index].name);
    await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
    await shot('desktop-graph-and-log');
    await page.locator('.svelte-flow__controls-fitview').click();
    await expect(page.locator('.svelte-flow__node').last()).toBeInViewport();
    await shot('desktop-whole-graph', page.getByRole('region', { name: 'Pipeline-Visualisierung' }));
    await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
    await expect(page.locator('.timeline-row')).toHaveCount(ci.steps.length);
    await shot('desktop-timeline');
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('mobile-timeline');
    await page.getByRole('button', { name: 'Graph', exact: true }).click();
    await expect(page.locator('.svelte-flow__node')).toHaveCount(ci.steps.length);
    await shot('mobile-graph-and-log');
    if (phase === 'final') {
      expect(ci.children).toHaveLength(1);
      const acceptance = await run(ci.children[0].id);
      expect(acceptance.parent_id).toBe(id);
      expect(acceptance.children).toHaveLength(2);
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.locator('.child-row').click();
      await expect(page.locator('.page-heading h1')).toHaveText('graphato-release-acceptance');
      await expect(page.getByRole('link', { name: '↗ Übergeordneter Lauf' })).toHaveAttribute('href', '#/runs/' + id);
      await expect(page.locator('.child-row')).toHaveCount(2);
      await shot('acceptance-parent-and-children');
      for (const child of acceptance.children) {
        const details = await run(child.id);
        expect(details.parent_id).toBe(acceptance.id);
        await page.locator('.child-row').filter({ hasText: child.pipeline_id }).click();
        await expect(page.locator('.page-heading h1')).toHaveText(child.pipeline_id);
        await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
        await shot(child.pipeline_id);
        relationships.push({ parent: acceptance.id, child: child.id, status: details.status });
        await page.getByRole('link', { name: '↗ Übergeordneter Lauf' }).click();
        await expect(page.locator('.child-row')).toHaveCount(2);
      }
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), run: id, status: ci.status, screenshots, relationships, errors, passed: true }, null, 2));
    console.log('Graphato', phase, 'UI passed:', screenshots.length, 'screenshots.');
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
