import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('UI connection loss, session expiry and history pagination', async ({ page, context }) => {
  await page.request.post('/api/auth/login', { headers: { 'X-Leroy-Request': '1' }, data: {
    username: 'admin', password: readFileSync('../.local/admin_password', 'utf8').trim(),
  }});
  await page.goto('/#/overview');
  await expect(page.getByText('Controller verbunden', {exact:true})).toBeVisible();
  await page.route('**/api/**', route=>route.abort());
  await expect(page.getByText('Verbindung unterbrochen', {exact:true})).toBeVisible({timeout:10000});
  await page.screenshot({path:'../test-results/visual/19-connection-lost.png'});
  await page.unroute('**/api/**');
  await expect(page.getByText('Controller verbunden', {exact:true})).toBeVisible({timeout:10000});

  // Large-history fixtures exercise presentation only, never migration acceptance.
  const [sample] = await (await page.request.get('/api/runs?status=succeeded&limit=1')).json();
  await page.route('**/api/runs?limit=100*', route=>{
    const before = new URL(route.request().url()).searchParams.has('before');
    const rows = Array.from({length:before?1:100},(_,i)=>({...sample,
      id:`ui-fixture-${before?'older':i}`, number:before?900:1000-i,
      pipeline_id:'ui-pagination-fixture', actor:'UI fixture',
    }));
    return route.fulfill({json:rows});
  });
  await page.goto('/#/runs');
  const older=page.getByRole('button',{name:'Ältere Ausführungen laden',exact:true});
  await expect(older).toBeVisible();
  await older.click();
  await expect(page.getByText('#900',{exact:true})).toBeVisible();
  await expect(older).toHaveCount(0);
  await page.getByText('#900',{exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:'../test-results/visual/20-older-history-fixture.png'});
  await page.unroute('**/api/runs?limit=100*');

  await context.clearCookies();
  await expect(page.getByRole('button',{name:'Anmelden →',exact:true})).toBeVisible({timeout:10000});
  await expect(page.getByRole('alert')).toContainText('Sitzung ist abgelaufen');
  await page.screenshot({path:'../test-results/visual/21-session-expired.png'});
});
