// Read-only inspection of a completed, real candidate pipeline and its children.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');
const root = resolve(__dirname, '..'), base = 'http://192.168.178.97:8088';
const [runId, commit, ...options] = process.argv.slice(2);
if (options.some(option => !['--allow-failed', '--release-only', '--incomplete-ci', '--interrupted-release'].includes(option))) throw Error('Unknown outcome option');
const allowFailed = options.includes('--allow-failed'), releaseOnly = options.includes('--release-only'), incompleteCi = options.includes('--incomplete-ci'), interruptedRelease = options.includes('--interrupted-release');
if (releaseOnly && incompleteCi) throw Error('Select one scenario');
if (interruptedRelease && (!releaseOnly || incompleteCi)) throw Error('Interrupted release requires release-only');
if (!/^[a-f0-9]{32}$/.test(runId || '') || !/^[a-f0-9]{40}$/.test(commit || '')) throw Error('Provide the actual CI run and candidate commit');
const outputLabel = process.env.LEROY_UI_OUTPUT_LABEL;
if (outputLabel && !/^[a-z0-9-]+$/.test(outputLabel)) throw Error('Invalid evidence output label');
const folder = resolve(root, 'test-results/nas-parity', outputLabel || 'visual-graphato-' + commit.slice(0, 12) + (releaseOnly ? '-existing-host' : incompleteCi ? '-interrupted-' + runId.slice(0, 8) : ''));
const password = readFileSync(resolve(root, '.local/nas-parity/config/admin_password'), 'utf8').trim();
mkdirSync(folder, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], screenshots = [], runs = [], artifacts = [], visited = new Set();
  page.on('pageerror', error => errors.push(error.message));
  async function collect(id, parent) {
    expect(visited.has(id)).toBe(false); visited.add(id);
    const response = await page.request.get(base + '/api/runs/' + id);
    expect(response.ok()).toBe(true);
    const run = await response.json();
    if (interruptedRelease) expect(run.status).toBe('interrupted');
    else if (incompleteCi) expect(['failed', 'interrupted', 'timed_out', 'cancelled']).toContain(run.status);
    else if (allowFailed) expect(['succeeded', 'failed', 'interrupted', 'timed_out', 'cancelled']).toContain(run.status);
    else expect(run.status).toBe('succeeded');
    expect(run.commit).toBe(commit);
    expect(run.parent_id).toBe(parent); runs.push(run);
    for (const child of run.children) await collect(child.id, id);
  }
  async function shot(name) {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: resolve(folder, name + '.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    screenshots.push(name);
  }
  try {
    const login = await page.request.post(base + '/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: { username: 'admin', password } });
    expect(login.status()).toBe(200);
    await collect(runId, null);
    const expectedPipelines = interruptedRelease ? ['graphato-release-acceptance', 'graphato-postdeploy-web'] : incompleteCi ? ['graphato-ci'] : ['graphato-release-acceptance', 'graphato-postdeploy-web', 'graphato-postdeploy-quality'];
    if (!releaseOnly && !incompleteCi) expectedPipelines.push('graphato-ci');
    expect(runs.map(run => run.pipeline_id).sort()).toEqual(expectedPipelines.sort());
    for (const run of runs) {
      const receipt = run.artifacts.find(item => item.name.endsWith('result.json')) || run.artifacts.find(item => item.name.endsWith('.json')) || run.artifacts[0];
      if (receipt) {
        const reply = await page.request.get(base + '/api/artifacts/' + receipt.id);
        expect(reply.ok()).toBe(true);
        const bytes = await reply.body();
        expect(bytes.length).toBe(receipt.size);
        expect(createHash('sha256').update(bytes).digest('hex')).toBe(receipt.sha256);
        artifacts.push({ run: run.id, name: receipt.name, sha256: receipt.sha256, artifact_kind: receipt.name.endsWith('result.json') ? 'check_result' : receipt.name.endsWith('.json') ? 'other_json' : 'other_artifact' });
      }
      for (const mobile of [false, true]) {
        await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 });
        await page.goto(base + '/#/runs/' + run.id);
        if (!run.runner && ['succeeded', 'failed', 'interrupted', 'timed_out', 'cancelled'].includes(run.status)) {
          await expect(page.getByText('Wartet auf Kapazität', { exact: true })).toHaveCount(0);
          await expect(page.getByText('Nicht zugewiesen', { exact: true })).toBeVisible();
        }
        await page.getByRole('button', { name: 'Graph', exact: true }).click();
        await expect(page.locator('.svelte-flow__node')).toHaveCount(run.steps.length);
        await expect(page.locator('.child-row')).toHaveCount(run.children.length);
        const failedIndex = run.steps.findIndex(step => ['failed', 'interrupted', 'timed_out', 'cancelled'].includes(step.status));
        const index = failedIndex >= 0 ? failedIndex : receipt ? run.steps.findIndex(step => step.id === receipt.step_id) : run.steps.length - 1;
        await page.locator('.step-list > button').nth(index).click();
        await page.getByRole('button', { name: 'Konsole', exact: true }).click();
        await expect(page.getByRole('region', { name: 'Konsolenausgabe' })).toHaveAttribute('aria-busy', 'false');
        const label = run.pipeline_id + (mobile ? '-mobile' : '-desktop');
        await shot(label + '-graph');
        if (mobile) await page.getByRole('button', { name: 'Zeitachse', exact: true }).click();
        await page.getByRole('button', { name: 'Ergebnisse', exact: true }).click();
        if (!run.image_digest && ['succeeded', 'failed', 'interrupted', 'timed_out', 'cancelled'].includes(run.status)) {
          await expect(page.getByText('Runner-Image noch nicht aufgelöst', { exact: true })).toHaveCount(0);
          await expect(page.getByText('Nicht erfasst', { exact: true })).toBeVisible();
        }
        await shot(label + '-results');
        if (outputLabel) {
          await page.getByRole('button', { name: 'Artefakte', exact: true }).click();
          await shot(label + '-artifacts');
        }
        for (const child of run.children) {
          const link = page.locator('.child-row[href="#/runs/' + child.id + '"]');
          const childRun = runs.find(item => item.id === child.id);
          await expect(link.locator('.badge')).toHaveClass(new RegExp('\\b' + childRun.status + '\\b'));
          await link.click();
          await expect(page).toHaveURL(base + '/#/runs/' + child.id);
          const parent = page.locator('.related a[href="#/runs/' + run.id + '"]');
          await expect(parent).toBeVisible(); await parent.click();
          await expect(page).toHaveURL(base + '/#/runs/' + run.id);
          await expect(page.locator('.child-row')).toHaveCount(run.children.length);
        }
      }
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ at: new Date().toISOString(), commit, scenario: interruptedRelease ? 'interrupted-release' : releaseOnly ? 'root-private-existing-host' : incompleteCi ? 'incomplete-ci' : 'fresh-target', runs: runs.map(run => run.id), observed_statuses: Object.fromEntries(runs.map(run => [run.pipeline_id, run.status])), failed_pipeline_results_allowed: allowFailed || incompleteCi || interruptedRelease, missing_original_pipelines: interruptedRelease ? ['graphato-postdeploy-quality'] : [], expected_pipeline_tree_observed: true, does_not_certify_full_release: true, screenshots, artifacts, errors, passed: true, manual_visual_review: false }, null, 2));
    console.log('Candidate hierarchy UI passed:', screenshots.length, 'screenshots and', artifacts.length, 'verified artifact downloads.');
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error.stack || error).replaceAll(password, '[REDACTED]')); process.exitCode = 1; });
