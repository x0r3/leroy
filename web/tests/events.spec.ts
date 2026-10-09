import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('long event history and viewer controls', async ({page})=>{
  await page.request.post('/api/auth/login',{headers:{'X-Leroy-Request':'1'},data:{username:'admin',password:readFileSync('../.local/admin_password','utf8').trim()}});
  const [run]=await (await page.request.get('/api/runs?pipeline=leroy-demo&status=succeeded&limit=1')).json();
  let resumed=false;
  // Presentation-only fixture: real cursor semantics are covered against PostgreSQL.
  await page.route(`**/api/runs/${run.id}/events*`,route=>{
    const older=new URL(route.request().url()).searchParams.has('before');
    return route.fulfill({json:Array.from({length:older?2:500},(_,i)=>({
      id:resumed?(older?2500-i:3000-i):(older?500-i:1000-i),run_id:run.id,step_id:null,kind:older?'run.queued':'step.succeeded',
      created_at:new Date().toISOString(),data:{reason:older?'Ältester Eintrag aus der Testhistorie':'Aktueller Eintrag aus der Testhistorie'},
    }))});
  });
  await page.goto('/#/runs/'+run.id);
  await page.getByRole('button',{name:'Ereignisse',exact:true}).click();
  await expect(page.getByText('Aktueller Eintrag aus der Testhistorie').first()).toBeVisible();
  const older=page.getByRole('button',{name:'Ältere Ereignisse laden',exact:true});
  await older.click();
  await expect(older).toHaveCount(0);
  await page.getByText('Ältester Eintrag aus der Testhistorie').last().scrollIntoViewIfNeeded();
  await page.screenshot({path:'../test-results/visual/22-event-history.png'});
  await page.setViewportSize({width:390,height:844});
  await page.getByText('Ältester Eintrag aus der Testhistorie').last().scrollIntoViewIfNeeded();
  await page.screenshot({path:'../test-results/visual/23-event-history-mobile.png'});
  // Returning to a busy run after >500 new events must expose the intervening history.
  resumed=true;
  await expect(older).toBeVisible({timeout:10000});
  await older.click();
  await expect(older).toHaveCount(0);
  await page.route('**/api/auth/me',route=>route.fulfill({json:{name:'viewer',role:'viewer'}}));
  await page.reload();
  await expect(page.getByRole('heading',{name:run.pipeline_id,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Erneut ausführen',exact:true})).toHaveCount(0);
  await page.screenshot({path:'../test-results/visual/24-viewer-run-mobile.png'});
  await page.goto('/#/pipelines/leroy-demo');
  await expect(page.getByRole('button',{name:'Pipeline starten →',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Pausiert · aktivieren',exact:true})).toBeDisabled();
  await page.setViewportSize({width:1440,height:1000});
  await page.screenshot({path:'../test-results/visual/25-viewer-pipeline.png'});
});
