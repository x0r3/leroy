// Read-only checks of the manual publication audit and its downloadable evidence.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const folder = resolve(root, 'test-results/nas-parity/visual-diagnostics');
const audit = resolve(root, 'test-results/nas-parity/aligned/graphato-ci/publication-audit');
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [];
  page.on('pageerror', e => errors.push(e.message));
  async function shot(name) {
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    screenshots.push(name);
  }
  try {
    const login = await page.request.post(base + '/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    const run = JSON.parse(readFileSync(resolve(audit, 'run.json')));
    expect(run.status).toBe('succeeded');
    const response = await page.request.get(base + '/api/pipelines');
    expect(response.ok()).toBe(true);
    const pipelines = await response.json();
    const baseline = JSON.parse(readFileSync(resolve(root, 'test-results/nas-parity/baseline.json')));
    expect(pipelines.map(p => p.id).sort()).toEqual([...baseline.pipelines.map(p => p.pipeline), 'leroy-nas-diagnostics', 'leroy-home-lab-build'].sort());
    expect(pipelines.every(p => !p.enabled)).toBe(true);
    const definition = pipelines.find(p => p.id === 'leroy-nas-diagnostics');
    expect(definition.spec.source.kind).toBe('diagnostic');
    await page.goto(base + '/#/pipelines/' + definition.id);
    await expect(page.getByRole('heading', { name: definition.spec.name, exact: true })).toBeVisible();
    await shot('desktop-definition');
    await page.getByRole('button', { name: 'Pipeline starten →', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('dialog').getByRole('button', { name: 'Ausführung starten →', exact: true })).toBeInViewport();
    await shot('desktop-start-form');
    await page.keyboard.press('Escape');
    await page.goto(base + '/#/runs/' + run.id);
    await expect(page.locator('.svelte-flow__node')).toHaveCount(1);
    await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
    await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toContainText('Published ZIP');
    await page.getByRole('button', { name: 'Artefakte', exact: true }).click();
    const artifact = run.artifacts.find(a => a.name === 'publication.json');
    expect(artifact).toBeTruthy();
    await expect(page.locator('.artifact-row')).toHaveCount(1);
    await expect(page.locator('.artifact-row')).toHaveAttribute('href', '/api/artifacts/' + artifact.id);
    const payload = await page.request.get(base + '/api/artifacts/' + artifact.id);
    expect(payload.ok()).toBe(true);
    const bytes = await payload.body();
    expect(bytes.length).toBe(artifact.size);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(artifact.sha256);
    await shot('desktop-audit-artifact');
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('mobile-audit-artifact');
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), run: run.id, screenshots, artifact: { name: artifact.name, size: artifact.size, sha256: artifact.sha256 }, triggersPaused: true, errors, passed: true }, null, 2));
    console.log('Publication audit UI passed:', screenshots.length, 'screenshots; downloaded evidence verified.');
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
