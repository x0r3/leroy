import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

test('real migration runs, child navigation, all parameter fields and accessibility', async ({ page }) => {
  await page.request.post('/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: {
    username: 'admin', password: readFileSync('../.local/admin_password', 'utf8').trim(),
  }});
  const folder = '../test-results/visual-states';
  mkdirSync(folder, { recursive: true });
  const issues: unknown[] = [];
  for (const route of ['overview', 'pipelines', 'runs', 'runners', 'settings']) {
    await page.goto('/#/' + route);
    await expect(page.locator('main.page h1')).toBeVisible();
    const result = await new AxeBuilder({ page }).analyze();
    issues.push(...result.violations.map(v => ({ route, ...v })));
  }
  const pipelines = await (await page.request.get('/api/pipelines')).json();
  for (const pipeline of pipelines) {
    if (!pipeline.last_run) continue;
    await page.goto('/#/runs/' + pipeline.last_run.id);
    await expect(page.locator('.svelte-flow__node')).toHaveCount(pipeline.last_run.snapshot.steps.length);
    await page.screenshot({ path: `${folder}/run-${pipeline.id}.png`, fullPage: true });
    await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
    await page.screenshot({ path: `${folder}/timeline-${pipeline.id}.png`, fullPage: true });
    const result = await new AxeBuilder({ page }).analyze();
    issues.push(...result.violations.map(v => ({ route: pipeline.id, ...v })));
  }
  for (const id of ['nikicas-hub-deploy', 'music-library-sync-smartphone', 'graphato-postdeploy-web', 'gitea-bootstrap-repo']) {
    await page.goto('/#/pipelines/' + id);
    await page.getByRole('button', { name: 'Pipeline starten →', exact: true }).click();
    const result = await new AxeBuilder({ page }).analyze();
    issues.push(...result.violations.map(v => ({ route: 'form/' + id, ...v })));
    const dialog = page.getByRole('dialog');
    const height = await dialog.evaluate(el => el.scrollHeight);
    for (let position = 0; position < height; position += 650) {
      await dialog.evaluate((el, top) => { el.scrollTop = top }, position);
      await page.screenshot({ path: `${folder}/form-${id}-${position}.png` });
    }
    await expect(page.getByRole('button', { name: 'Ausführung starten →', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Abbrechen', exact: true }).click();
  }
  const parents = await (await page.request.get('/api/runs?pipeline=leroy-parent&status=succeeded&limit=1')).json();
  if (parents.length) {
    await page.goto('/#/runs/' + parents[0].id);
    await page.locator('.child-row').click();
    await expect(page.getByRole('link', { name: '↗ Übergeordneter Lauf' })).toBeVisible();
    await page.getByRole('link', { name: '↗ Übergeordneter Lauf' }).click();
    await expect(page.locator('.child-row')).toBeVisible();
  }
  writeFileSync(`${folder}/accessibility.json`, JSON.stringify(issues, null, 2));
  expect(issues.filter((v: any) => ['serious', 'critical'].includes(v.impact))).toEqual([]);
});
