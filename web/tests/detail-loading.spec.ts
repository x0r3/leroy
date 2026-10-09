import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('changing steps never attributes the previous log or events to the new step', async ({ page }) => {
  await page.request.post('/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: {
    username: 'admin', password: readFileSync('../.local/admin_password', 'utf8').trim(),
  }});
  const runs = await (await page.request.get('/api/runs?status=succeeded&limit=100')).json();
  let run: any;
  for (const row of runs) {
    const candidate = await (await page.request.get('/api/runs/' + row.id)).json();
    if (candidate.steps.length >= 2) { run = candidate; break; }
  }
  expect(run).toBeTruthy();
  const [first, second] = run.steps;
  let releaseLog!: () => void, releaseEvents!: () => void, releaseComparison!: () => void;
  const logGate = new Promise<void>(resolve => { releaseLog = resolve; });
  const eventGate = new Promise<void>(resolve => { releaseEvents = resolve; });
  const comparisonGate = new Promise<void>(resolve => { releaseComparison = resolve; });
  await page.route(`**/api/runs/${run.id}/logs/**`, async route => {
    const sid = new URL(route.request().url()).pathname.split('/').at(-1);
    if (sid === second.id) await logGate;
    await route.fulfill({ json: { text: sid === first.id ? 'first-step-only' : 'second-step-only', next_offset: 32 } });
  });
  await page.route(`**/api/runs/${run.id}/events?*`, async route => {
    const sid = new URL(route.request().url()).searchParams.get('step_id');
    if (sid === second.id) await eventGate;
    await route.fulfill({ json: [{ id: sid === first.id ? 1 : 2, kind: sid === first.id ? 'first.event' : 'second.event', created_at: run.created_at, data: {} }] });
  });
  await page.route('**/api/runs?pipeline=*&status=succeeded&before=*&limit=1', async route => {
    await comparisonGate;
    await route.fulfill({ json: [] });
  });
  try {
    await page.goto('/#/runs/' + run.id);
    await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveText('first-step-only');
    await page.locator('.step-list button').nth(1).click();
    await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveText('Ausgabe wird geladen …');
    releaseLog();
    await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveText('second-step-only');
    await page.locator('.step-list button').nth(0).click();
    await page.getByRole('button', { name: 'Ereignisse', exact: true }).click();
    await expect(page.locator('.event-list')).toContainText('first.event');
    await page.locator('.step-list button').nth(1).click();
    await expect(page.locator('.event-list')).toContainText('Ereignisse werden geladen …');
    await expect(page.locator('.event-list')).not.toContainText('first.event');
    releaseEvents();
    await expect(page.locator('.event-list')).toContainText('second.event');
    await page.getByRole('button', { name: 'Vergleichen', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Vergleich wird geladen' })).toBeVisible();
    await expect(page.locator('.event-list')).toHaveCount(0);
    releaseComparison();
    await expect(page.getByText('Noch kein erfolgreicher Vergleichslauf', { exact: true })).toBeVisible();
  } finally { releaseLog(); releaseEvents(); releaseComparison(); }
});
