// Read-only browser verification of the deployed NAS controller.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, mkdirSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..');
const output = resolve(root, 'test-results/nas-parity', process.argv[3] || 'visual');
const adminPassword = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [];
  let parameterChecks = 0;
  page.on('pageerror', error => errors.push(error.message));
  async function shot(name) {
    await page.screenshot({ path: resolve(output, name + '.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), name + ' overflow').toBe(false);
    screenshots.push(name);
  }
  async function dialogShots(name) {
    const dialog = page.getByRole('dialog');
    await shot(name);
    const { height, total } = await dialog.evaluate(el => ({ height: el.clientHeight, total: el.scrollHeight }));
    for (let top = height * 0.8, index = 1; top < total; top += height * 0.8, index++) {
      if (total <= height + 1) break;
      await dialog.evaluate((el, value) => { el.scrollTop = value; }, top);
      await shot(name + '-scroll-' + index);
      if (top + height >= total) break;
    }
    await expect(dialog.getByRole('button', { name: 'Ausführung starten →', exact: true })).toBeInViewport();
  }
  try {
    await page.goto('http://192.168.178.97:8088/');
    await expect(page.getByRole('button', { name: 'Anmelden →', exact: true })).toBeVisible();
    await shot('login-desktop');
    await page.getByLabel('Passwort', { exact: true }).fill(adminPassword);
    const loginStarted = Date.now();
    const loginResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/auth/login' && response.request().method() === 'POST', { timeout: 60000 });
    await page.getByRole('button', { name: 'Anmelden →', exact: true }).click();
    expect((await loginResponse).status()).toBe(200);
    const loginMilliseconds = Date.now() - loginStarted;
    await expect(page.getByRole('heading', { name: 'Übersicht', exact: true })).toBeVisible();
    await expect(page.getByText('Controller verbunden', { exact: true })).toBeVisible();
    const pipelines = await (await page.request.get('http://192.168.178.97:8088/api/pipelines')).json();
    const baseline = JSON.parse(readFileSync(resolve(root, 'test-results/nas-parity/baseline.json')));
    const extras = { 'leroy-nas-diagnostics': 'diagnostic', 'leroy-home-lab-build': 'comparison' };
    const migrated = pipelines.filter(p => !Object.hasOwn(extras, p.id));
    expect(migrated.map(p => p.id).sort()).toEqual(baseline.pipelines.map(p => p.pipeline).sort());
    expect(migrated).toHaveLength(13);
    for (const p of pipelines.filter(p => Object.hasOwn(extras, p.id))) expect(p.spec.source?.kind).toBe(extras[p.id]);
    expect(pipelines.every(p => !p.enabled)).toBe(true);
    for (const mobile of [false, true]) {
      await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
      for (const path of ['overview', 'pipelines', 'runs', 'runners', 'settings']) {
        await page.goto('http://192.168.178.97:8088/#/' + path);
        await expect(page.locator('main.page h1')).toBeVisible();
        await shot((mobile ? 'mobile-' : 'desktop-') + path);
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    for (const p of pipelines) {
      await page.goto('http://192.168.178.97:8088/#/pipelines/' + p.id);
      await expect(page.getByRole('heading', { name: p.spec.name, exact: true })).toBeVisible();
      const historyResponse = await page.request.get('http://192.168.178.97:8088/api/runs?limit=100&pipeline=' + encodeURIComponent(p.id));
      expect(historyResponse.ok()).toBe(true);
      await expect(page.locator('main.page .run-link')).toHaveCount((await historyResponse.json()).length);
      await shot('definition-' + p.id);
      await page.getByRole('button', { name: 'Pipeline starten →', exact: true }).click();
      await expect(page.getByRole('dialog')).toBeVisible();
      for (const [index, parameter] of p.spec.parameters.entries()) {
        const input = page.getByRole('dialog').locator('.modal-content > label').nth(index).locator('input, select, textarea');
        if (parameter.kind === 'boolean') {
          await expect(input).toBeChecked({ checked: Boolean(parameter.default) });
        } else {
          await expect(input).toHaveValue(String(parameter.default ?? ''));
        }
        parameterChecks++;
      }
      await dialogShots('form-' + p.id);
      await page.keyboard.press('Escape');
    }
    await page.setViewportSize({ width: 390, height: 844 });
    for (const id of ['graphato-bootstrap-host', 'nikicas-hub-deploy']) {
      await page.goto('http://192.168.178.97:8088/#/pipelines/' + id);
      await page.getByRole('button', { name: 'Pipeline starten →', exact: true }).click();
      await dialogShots('mobile-form-' + id);
      await page.keyboard.press('Escape');
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (process.argv[2]) {
      const response = await page.request.get('http://192.168.178.97:8088/api/runs/' + process.argv[2]);
      expect(response.ok()).toBe(true);
      const run = await response.json();
      await page.goto('http://192.168.178.97:8088/#/runs/' + process.argv[2]);
      await expect(page.locator('.svelte-flow__node')).toHaveCount(run.steps.length);
      await shot('run-graph');
      await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
      await shot('run-timeline');
      for (const name of ['Konsole', 'Ergebnisse', 'Artefakte', 'Ereignisse', 'Vergleichen']) {
        await page.getByRole('button', { name, exact: true }).click();
        await expect(page.getByRole('button', { name, exact: true })).toHaveClass(/active/);
        if (name === 'Konsole') await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
        if (name === 'Vergleichen') await expect(page.getByRole('status').filter({ hasText: 'Vergleich wird geladen' })).toHaveCount(0);
        if (name === 'Ereignisse') {
          const step = run.steps.find(s => s.status === 'failed') || run.steps[0];
          const events = await page.request.get(`http://192.168.178.97:8088/api/runs/${run.id}/events?newest=true&step_id=${encodeURIComponent(step.id)}`);
          expect(events.ok()).toBe(true);
          await expect(page.locator('.event-list > div')).toHaveCount((await events.json()).length);
        }
        await shot('run-' + name);
      }
      await page.setViewportSize({ width: 390, height: 844 });
      await shot('run-mobile');
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(output, 'report.json'), JSON.stringify({ checked_at: new Date().toISOString(), screenshots, parameterChecks, loginMilliseconds, errors, passed: true }, null, 2));
    console.log('NAS UI passed:', screenshots.length, 'screenshots; no page errors or horizontal overflow.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(String(error.stack || error).replaceAll(adminPassword, '[REDACTED]')); process.exitCode = 1; });
