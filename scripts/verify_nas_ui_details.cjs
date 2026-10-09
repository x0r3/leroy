// Read-only verification of populated NAS run details, including artifact downloads.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, mkdirSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');
const root = resolve(__dirname, '..');
const base = 'http://192.168.178.97:8088';
const output = resolve(root, 'test-results/nas-parity/visual-populated-details');
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [], downloads = [];
  page.on('pageerror', error => errors.push(error.message));
  async function get(path) {
    const response = await page.request.get(base + path);
    expect(response.ok()).toBe(true);
    return response.json();
  }
  async function shot(name, fullPage = true) {
    if (fullPage) await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: resolve(output, name + '.png'), fullPage });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    screenshots.push(name);
  }
  async function tab(name) {
    const button = page.getByRole('button', { name, exact: true });
    await button.click();
    await expect(button).toHaveClass(/active/);
  }
  try {
    await page.goto(base);
    await page.getByLabel('Passwort', { exact: true }).fill(password);
    const login = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/login' && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Anmelden →', exact: true }).click();
    expect((await login).status()).toBe(200);
    const hub = await get('/api/runs/5e5bc152147a414fbafd8c92e46a1e96');
    const artifact = hub.artifacts.find(a => a.name === 'images.json');
    expect(artifact).toBeTruthy();
    await page.goto(base + '/#/runs/' + hub.id);
    const index = hub.steps.findIndex(s => s.id === artifact.step_id);
    await page.locator('.step-list button').nth(index).click();
    await tab('Artefakte');
    await expect(page.locator('.artifact-row')).toHaveCount(hub.artifacts.filter(a => a.step_id === artifact.step_id).length);
    const link = page.locator('.artifact-row').filter({ hasText: artifact.name });
    await expect(link).toHaveAttribute('href', '/api/artifacts/' + artifact.id);
    const response = await page.request.get(base + await link.getAttribute('href'));
    expect(response.ok()).toBe(true);
    const bytes = await response.body();
    expect(bytes.length).toBe(artifact.size);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(artifact.sha256);
    downloads.push({ name: artifact.name, size: bytes.length, sha256: artifact.sha256 });
    await shot('artifact-desktop');
    await page.setViewportSize({ width: 390, height: 844 });
    await shot('artifact-mobile');
    await page.setViewportSize({ width: 1440, height: 1000 });
    const events = await get(`/api/runs/${hub.id}/events?newest=true&step_id=${encodeURIComponent(artifact.step_id)}`);
    expect(events.length).toBeGreaterThan(0);
    await tab('Ereignisse');
    await expect(page.locator('.event-list > div')).toHaveCount(events.length);
    await page.locator('.event-list > div').first().scrollIntoViewIfNeeded();
    await shot('events-desktop', false);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('.event-list > div').first().scrollIntoViewIfNeeded();
    await shot('events-mobile', false);
    let olderEvents = 0;
    if (events.length === 500) {
      const older = await get(`/api/runs/${hub.id}/events?newest=true&step_id=${encodeURIComponent(artifact.step_id)}&before=${events.at(-1).id}`);
      await page.getByRole('button', { name: 'Ältere Ereignisse laden', exact: true }).click();
      await expect(page.locator('.event-list > div')).toHaveCount(events.length + older.length);
      olderEvents = older.length;
      await page.locator('.event-list > div').last().scrollIntoViewIfNeeded();
      await shot('events-mobile-older', false);
    }
    const run = await get('/api/runs/e0d321ad9e2c4849af6fb0d81cfcf819');
    const previous = await get(`/api/runs?pipeline=${run.pipeline_id}&status=succeeded&before=${run.number}&limit=1`);
    expect(previous).toHaveLength(1);
    await page.goto(base + '/#/runs/' + run.id);
    await tab('Vergleichen');
    await expect(page.locator('.comparison')).toBeVisible();
    await expect(page.getByRole('link', { name: '#' + previous[0].number, exact: true })).toHaveAttribute('href', '#/runs/' + previous[0].id);
    await shot('comparison-mobile');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await shot('comparison-desktop');
    expect(errors).toEqual([]);
    writeFileSync(resolve(output, 'report.json'), JSON.stringify({ checked_at: new Date().toISOString(), screenshots, downloads, eventCount: events.length, olderEvents, comparedRun: run.id, previousRun: previous[0].id, errors, passed: true }, null, 2));
    console.log('Populated NAS details passed:', screenshots.length, 'screenshots and artifact SHA-256 verified.');
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
