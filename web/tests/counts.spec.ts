import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync, mkdirSync } from 'node:fs';

test('global active counts include runs outside the visible history and pipeline filter', async ({ page }) => {
  await page.request.post('/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: {
    username: 'admin', password: readFileSync('../.local/admin_password', 'utf8').trim(),
  }});
  const base = (await (await page.request.get('/api/runs?status=succeeded&limit=1')).json())[0];
  expect(base).toBeTruthy();
  // Explicit UI fixture: the newest 100 runs are done while older work is still active.
  const recent = Array.from({ length: 100 }, (_, i) => ({
    ...base, id: 'count-fixture-' + i, number: 10000 - i, status: 'succeeded',
  }));
  await page.route('**/api/runs?*', route => route.fulfill({ json: recent }));
  await page.route('**/api/system', async route => {
    const original = await route.fetch();
    await route.fulfill({ json: { ...await original.json(), counts: {
      succeeded: 100, queued: 7, running: 2, waiting: 1,
    } } });
  });
  await page.goto('/#/overview');
  const counter = page.locator('.stats > div').filter({ hasText: 'Aktive Ausführungen' });
  await expect(counter.locator('strong')).toHaveText('10');
  await expect(counter.locator('small')).toHaveText('7 in der Warteschlange');
  await expect(page.locator('.nav-count')).toHaveText('10');
  const folder = '../test-results/visual-counts';
  mkdirSync(folder, { recursive: true });
  for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]] as const) {
    await page.setViewportSize({ width, height });
    await expect(counter.locator('strong')).toHaveText('10');
    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations.filter(v => ['critical', 'serious'].includes(v.impact || ''))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    await page.screenshot({ path: `${folder}/${name}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/#/pipelines/' + base.pipeline_id);
  await expect(page.locator('.pipeline-config')).toBeVisible();
  await expect(page.locator('.nav-count')).toHaveText('10');
});
