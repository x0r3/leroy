// Test the separate candidate's actual capture helper, including failure cleanup.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { mkdirSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { pathToFileURL } = require('node:url');
const folder = resolve(__dirname, '../test-results/nas-parity/followup/arena-capture-helper-fixture');
const helper = resolve(__dirname, '../.sources/antares-capture-validation/tests/e2e/helpers/capture-clock.ts');
const delay = milliseconds => new Promise(done => setTimeout(done, milliseconds));

(async () => {
  const { withPausedCaptureClock } = await import(pathToFileURL(helper).href);
  mkdirSync(folder, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const records = [];
  try {
    for (const mode of ['original', 'paused-slow-protocol', 'callback-failure']) {
      const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
      if (mode !== 'original') await page.clock.install();
      await page.setContent('<section aria-label="Live-Kampfarena" data-attack-phase="attacker" style="height:600px;background:#234;color:white">Arena</section><script>setTimeout(()=>document.querySelector("section").dataset.attackPhase="defender",1400)</script>');
      const arena = page.getByLabel('Live-Kampfarena');
      await expect(arena).toHaveAttribute('data-attack-phase', 'attacker', { timeout: 2200 });
      if (mode === 'paused-slow-protocol') {
        const pause = page.clock.pauseAt.bind(page.clock);
        page.clock.pauseAt = async value => { await delay(250); return pause(value); };
      }
      let failure;
      try {
        const capture = async () => {
          if (mode === 'callback-failure') throw new Error('deliberate-capture-failure');
          await expect(arena).toHaveAttribute('data-attack-phase', 'attacker', { timeout: 100 });
          await delay(1700);
          await arena.screenshot({ path: resolve(folder, mode + '.png'), animations: 'allow' });
          await expect(arena).toHaveAttribute('data-attack-phase', 'attacker', { timeout: 100 });
        };
        if (mode === 'original') await capture();
        else await withPausedCaptureClock(page, capture);
      } catch (error) { failure = String(error); }
      if (mode === 'original') expect(failure).toContain('toHaveAttribute');
      else if (mode === 'callback-failure') expect(failure).toContain('deliberate-capture-failure');
      else expect(failure).toBeUndefined();
      await expect(arena).toHaveAttribute('data-attack-phase', 'defender', { timeout: 2200 });
      records.push({ mode, original100msAssertionPassed: !failure,
        failureCleanupVerified: mode === 'callback-failure', nextRealPhaseVerifiedAfterResume: true });
      await page.close();
    }
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ localFixtureOnly: true,
      applicationModified: false, fullCiAcceptance: false, helper, records, passed: true }, null, 2));
    console.log(JSON.stringify({ passed: true, records }));
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error)); process.exitCode = 1; });
