import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('route changes wait for their own history instead of showing an empty or stale history', async ({ page }) => {
  await page.request.post('/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: {
    username: 'admin', password: readFileSync('../.local/admin_password', 'utf8').trim(),
  }});
  const pipelines = await (await page.request.get('/api/pipelines')).json();
  const [first, second] = pipelines.filter((p: any) => p.last_run);
  expect(second).toBeTruthy();
  // Delay only presentation data. No pipeline is started or changed by this test.
  const firstRun = first.last_run, secondRun = second.last_run;
  let releasePipeline!: () => void, releaseOverview!: () => void;
  const pipelineGate = new Promise<void>(resolve => { releasePipeline = resolve; });
  const overviewGate = new Promise<void>(resolve => { releaseOverview = resolve; });
  let delayOverview = false;
  await page.route('**/api/runs?*', async route => {
    const selected = new URL(route.request().url()).searchParams.get('pipeline');
    if (selected) {
      await pipelineGate;
      await route.fulfill({ json: [secondRun] });
    } else {
      if (delayOverview) await overviewGate;
      await route.fulfill({ json: delayOverview ? [firstRun, secondRun] : [firstRun] });
    }
  });
  try {
    await page.goto('/#/overview');
    await expect(page.locator('.run-link').filter({ hasText: first.id })).toBeVisible();
    await page.evaluate(id => { location.hash = '/pipelines/' + id; }, second.id);
    await expect(page.getByRole('status').filter({ hasText: 'Ansicht wird geladen' })).toBeVisible();
    await expect(page.getByText('Keine Ausführungen', { exact: true })).toHaveCount(0);
    await expect(page.locator('main.page .run-link')).toHaveCount(0);
    releasePipeline();
    await expect(page.locator('main.page h1')).toHaveText(second.spec.name);
    await expect(page.locator('main.page .run-link')).toHaveCount(1);
    await expect(page.locator('main.page .run-link')).toContainText(second.id);

    delayOverview = true;
    await page.evaluate(() => { location.hash = '/overview'; });
    await expect(page.getByRole('status').filter({ hasText: 'Ansicht wird geladen' })).toBeVisible();
    await expect(page.locator('.stats')).toHaveCount(0);
    releaseOverview();
    await expect(page.getByRole('heading', { name: 'Übersicht', exact: true })).toBeVisible();
    await expect(page.locator('main.page .run-link')).toHaveCount(2);
  } finally {
    releasePipeline();
    releaseOverview();
  }
});
