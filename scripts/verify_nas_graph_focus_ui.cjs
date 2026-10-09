// Verify selected nodes with actual failed NAS run data, without starting jobs.
const {chromium, request, expect} = require('../web/node_modules/@playwright/test');
const {readFileSync, writeFileSync, mkdirSync} = require('node:fs');
const {resolve} = require('node:path');
const root=resolve(__dirname,'..'), nas='http://192.168.178.97:8088';
const base=process.argv[2]||nas, label=process.argv[3]||'visual-graph-focus';
if(![nas,'http://127.0.0.1:5184','http://127.0.0.1:5185'].includes(base)||!/^[a-z0-9-]+$/.test(label))throw Error('Unreviewed target');
const id='bc29298b409c4954b6ee7e41cdbf5cd2';
const folder=resolve(root,'test-results/nas-parity',label);
const password=readFileSync(resolve(root,'.local/nas-parity/config/admin_password'),'utf8').trim();
(async()=>{
  mkdirSync(folder,{recursive:true});
  const remote=await request.newContext({baseURL:nas});
  const login=await remote.post('/api/auth/login',{headers:{'X-Leroy-Request':'1'},data:{username:'admin',password}});
  expect(login.ok()).toBe(true);
  const browser=await chromium.launch({headless:true}), page=await browser.newPage();
  const errors=[],screenshots=[];
  let updates=0;
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',async route=>{
    expect(route.request().method()).toBe('GET');
    const url=new URL(route.request().url()), path=url.pathname+url.search;
    if(url.pathname.endsWith('/stream'))return route.fulfill({status:204});
    const response=await remote.get(path);expect(response.ok()).toBe(true);
    if(path==='/api/runs/'+id)updates++;
    await route.fulfill({response});
  });
  async function visibleNode(name){
    const node=page.locator('.svelte-flow__node').filter({hasText:name});
    await expect(node).toHaveCount(1);
    await expect.poll(async()=>{
      const n=await node.boundingBox(), g=await page.locator('.graph').boundingBox();
      return !!n&&!!g&&n.x>=g.x&&n.y>=g.y&&n.x+n.width<=g.x+g.width&&n.y+n.height<=g.y+g.height;
    }).toBe(true);
  }
  async function shot(name){await page.screenshot({path:resolve(folder,name+'.png'),fullPage:true});screenshots.push(name);}
  try{
    for(const mobile of [false,true]){
      const mode=mobile?'mobile':'desktop';
      await page.setViewportSize(mobile?{width:390,height:844}:{width:1440,height:1000});
      await page.goto(base+'/#/runs/'+id);
      await page.reload();
      await page.getByRole('button',{name:'Graph',exact:true}).click();
      await expect(page.locator('.svelte-flow__node')).toHaveCount(9);
      await visibleNode('Unit and integration tests');
      await shot(mode+'-failed-step');
      for(const [index,name,suffix] of [[8,'Clean isolated resources','last-step'],[0,'Checkout pinned revision','first-step']]){
        await page.locator('.step-list > button').nth(index).click();
        await visibleNode(name);await shot(mode+'-'+suffix);
      }
      const g=await page.locator('.graph').boundingBox();
      await page.mouse.move(g.x+g.width/2,g.y+g.height-80);
      await page.mouse.down();await page.mouse.move(g.x+g.width/2-60,g.y+g.height-50,{steps:8});await page.mouse.up();
      const viewport=page.locator('.svelte-flow__viewport');
      const transform=await viewport.getAttribute('style'), before=updates;
      await expect.poll(()=>updates,{timeout:12000}).toBeGreaterThanOrEqual(before+2);
      expect(await viewport.getAttribute('style')).toBe(transform);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false);
    }
    expect(errors).toEqual([]);
    writeFileSync(resolve(folder,'report.json'),JSON.stringify({at:new Date().toISOString(),run:id,base,source:'Actual NAS API responses',screenshots,errors,passed:true,manual_visual_review:false,pan_survives_refresh:true},null,2));
    console.log('Selected-node focus and preserved pan passed on desktop and mobile.');
  }catch(error){
    await page.screenshot({path:resolve(folder,'failure.png'),fullPage:true});
    console.error(JSON.stringify({errors,graph:await page.locator('.graph').boundingBox(),selected:await page.locator('.svelte-flow__node.selected').boundingBox(),viewport:await page.locator('.svelte-flow__viewport').getAttribute('style')}));
    throw error;
  }finally{await browser.close();await remote.dispose();}
})().catch(error=>{console.error(String(error.stack||error).replaceAll(password,'[REDACTED]'));process.exitCode=1;});
