import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
const password = readFileSync('../.local/admin_password', 'utf8').trim();
const screenshots = '../test-results/visual';
mkdirSync(screenshots, { recursive: true });

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `${screenshots}/${name}.png`, fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
  expect(overflow, `${name}: page must fit the viewport`).toBe(false);
}

test('all views, forms, graph, results, artifacts, history and mobile', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Anmelden →', exact: true })).toBeVisible();
  await shot(page, '01-login');
  await page.setViewportSize({ width: 390, height: 844 });
  await shot(page, '01-login-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel('Passwort', { exact: true }).fill('wrong-password');
  await page.getByRole('button', { name: 'Anmelden →', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await shot(page, '02-login-error');
  await page.getByLabel('Passwort', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Anmelden →', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Übersicht', exact: true })).toBeVisible();
  await expect(page.getByText('Controller verbunden', { exact: true })).toBeVisible();
  await shot(page, '03-overview');
  const accessibility = await new AxeBuilder({ page }).analyze();
  writeFileSync(`${screenshots}/accessibility.json`, JSON.stringify(accessibility.violations, null, 2));
  expect(accessibility.violations.filter(v => ['critical', 'serious'].includes(v.impact || ''))).toEqual([]);

  for (const [path, title] of [['pipelines', 'Pipelines'], ['runs', 'Ausführungen'], ['runners', 'Runner'], ['settings', 'System']]) {
    await page.goto('/#/' + path);
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
    if(path==='settings')await expect(page.locator('.system-panel')).toContainText('PostgreSQL');
    await shot(page, '04-' + path);
  }
  await page.goto('/#/pipelines');
  await page.getByLabel('Pipelines suchen').fill('does-not-exist');
  await expect(page.getByText('Keine passende Pipeline')).toBeVisible();
  await shot(page, '05-empty-filter');
  await page.getByLabel('Pipelines suchen').fill('');
  await page.getByLabel('Nach Projekt filtern').selectOption('Graphato');
  await expect(page.locator('.pipeline-card')).toHaveCount(4);

  const pipelines = await (await page.request.get('/api/pipelines')).json();
  for (const pipeline of pipelines) {
    await page.goto('/#/pipelines/' + pipeline.id);
    await expect(page.getByRole('heading', { name: pipeline.spec.name, exact: true })).toBeVisible();
    await page.getByText('Herkunft und Migration', { exact: true }).click();
    await shot(page, '06-definition-' + pipeline.id);
    await page.getByRole('button', { name: 'Pipeline starten →', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await shot(page, '07-form-' + pipeline.id);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }

  await page.goto('/#/pipelines/leroy-demo');
  await page.getByRole('button', { name: 'Pipeline starten →', exact: true }).click();
  await page.getByLabel('SECONDS', { exact: true }).fill('8');
  await page.getByRole('button', { name: 'Ausführung starten →', exact: true }).click();
  await expect(page).toHaveURL(/#\/runs\//);
  await expect(page.locator('.svelte-flow__node')).toHaveCount(5);
  await shot(page, '08-running-graph');
  await expect(page.getByRole('button', { name: 'Erneut ausführen', exact: true })).toBeVisible({ timeout: 45_000 });
  await shot(page, '09-success-graph');
  await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
  await expect(page.locator('.timeline-row')).toHaveCount(5);
  await shot(page, '10-timeline');
  await page.locator('.step-list button').filter({ hasText: 'Package results' }).click();
  for (const tab of ['Konsole', 'Ergebnisse', 'Artefakte', 'Ereignisse', 'Vergleichen']) {
    await page.getByRole('button', { name: tab, exact: true }).click();
    await shot(page, '11-detail-' + tab);
  }
  await page.getByRole('button', { name: 'Artefakte', exact: true }).click();
  const downloadPromise = page.waitForEvent('download');
  await page.locator('.artifact-row').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('result.json');
  const successfulURL = page.url();
  const request = await page.request.post('/api/pipelines/leroy-demo/runs', {
    headers: { 'X-Leroy-Request': '1' }, data: { parameters: { FAIL: true, SECONDS: 1 } },
  });
  expect(request.ok()).toBe(true);
  const failed = await request.json();
  await page.goto('/#/runs/' + failed.id);
  await expect(page.getByRole('button', { name: 'Erneut ausführen' })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.page-heading .badge')).toHaveText('Fehlgeschlagen', { timeout: 45_000 });
  await shot(page, '12-failed-graph');
  await page.getByRole('button', { name: 'Vergleichen', exact: true }).click();
  await expect(page.getByText('Vergleich mit erfolgreichem Lauf', { exact: false })).toBeVisible();
  await shot(page, '13-comparison');

  const cancelRequest = await page.request.post('/api/pipelines/leroy-demo/runs', {
    headers: { 'X-Leroy-Request': '1' }, data: { parameters: { SECONDS: 90 } },
  });
  await page.goto('/#/runs/' + (await cancelRequest.json()).id);
  await page.getByRole('button', { name: 'Lauf abbrechen', exact: true }).click();
  await expect(page.locator('.page-heading .badge')).toHaveText('Abgebrochen', { timeout: 30_000 });
  await shot(page, '14-cancelled');

  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ['overview', 'pipelines', 'runs', 'runners', 'settings', 'pipelines/nikicas-hub-deploy']) {
    await page.goto('/#/' + path);
    await expect(page.locator('main.page h1')).toBeVisible();
    await shot(page, '15-mobile-' + path.replaceAll('/', '-'));
  }
  await page.getByRole('button', { name: 'Pipeline starten →', exact: true }).click();
  await shot(page, '16-mobile-form');
  await page.keyboard.press('Escape');
  await page.goto(successfulURL);
  await expect(page.locator('.svelte-flow__node')).toHaveCount(5);
  await shot(page, '17-mobile-run');
  await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
  await shot(page, '18-mobile-timeline');
  expect(errors).toEqual([]);
});
