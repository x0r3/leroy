// Local diagnostic fixture, separate from the frozen NAS application checkout.
const { chromium, expect } = require('../web/node_modules/@playwright/test');
const { mkdirSync, writeFileSync } = require('node:fs');
const { resolve } = require('node:path');
const folder = resolve(__dirname, '../test-results/nas-parity/followup/arena-clock-fixture');
mkdirSync(folder, { recursive: true });
const delay = milliseconds => new Promise(done => setTimeout(done, milliseconds));
(async () => {
  const browser = await chromium.launch({ headless: true });
  const records = [];
  try {
    for (const controlled of [false, true]) {
      const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
      if (controlled) await page.clock.install();
      await page.setContent('<section aria-label="Live-Kampfarena" data-attack-phase="attacker" style="height:600px;background:#234;color:white">Arena</section><script>setTimeout(()=>document.querySelector("section").dataset.attackPhase="defender",1400)</script>');
      const arena = page.getByLabel('Live-Kampfarena');
      await expect(arena).toHaveAttribute('data-attack-phase', 'attacker', { timeout: 2200 });
      if (controlled) await page.clock.pauseAt(Date.now() + 100);
      let assertionPassed = true;
      try {
        // Reproduce a slow validation/capture operation without changing the deadline.
        await delay(1700);
        await arena.screenshot({ path: resolve(folder, controlled ? 'controlled.png' : 'original.png'), animations: 'allow' });
        await expect(arena).toHaveAttribute('data-attack-phase', 'attacker', { timeout: 100 });
      } catch (error) {
        if (!String(error).includes('toHaveAttribute')) throw error;
        assertionPassed = false;
      } finally { if (controlled) await page.clock.resume(); }
      expect(assertionPassed).toBe(controlled);
      await expect(arena).toHaveAttribute('data-attack-phase', 'defender', { timeout: 2200 });
      records.push({ controlledClock: controlled, original100msAssertionPassed: assertionPassed, nextPhaseVerifiedAfterResume: true });
      await page.close();
    }
    writeFileSync(resolve(folder, 'report.json'), JSON.stringify({ localFixtureOnly: true, applicationModified: false, fullCiAcceptance: false, records, passed: true }, null, 2));
    console.log(JSON.stringify(records));
  } finally { await browser.close(); }
})().catch(error => { console.error(String(error)); process.exitCode = 1; });
