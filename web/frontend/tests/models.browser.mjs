import {chromium} from 'playwright';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const waiting=new Map();
  page.on('websocket',ws=>ws.on('framereceived',frame=>{
    try {
      const data=JSON.parse(frame.payload);
      if(data.type==='result') waiting.get(data.model)?.(data);
    } catch { /* Binary messages are unrelated to result checks. */ }
  }));
  const resultFor=key=>new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{waiting.delete(key);reject(new Error(`No inference result: ${key}`))},30000);
    waiting.set(key,data=>{clearTimeout(timer);waiting.delete(key);resolve(data)});
  });
  const initial=resultFor('chess3d_m');
  await page.goto(process.env.EDGECHESS_WEB_URL||'http://127.0.0.1:8000');
  await page.waitForFunction(()=>document.querySelector('#model').options.length>0);
  await page.selectOption('#source-mode','3d');
  await page.selectOption('#profile','3d');
  await page.selectOption('#model','chess3d_m');
  assert.equal((await initial).profile,'3d');
  assert.equal(await page.locator('#model').inputValue(),'chess3d_m');
  assert.equal(await page.locator('#model option').count(),2);
  let next=resultFor('chess3d');
  await page.selectOption('#model','chess3d');
  assert.equal((await next).profile,'3d');
  next=resultFor('board2d + pieces2d');
  await page.selectOption('#source-mode','2d');
  await page.selectOption('#profile','2d');
  assert.equal((await next).profile,'2d');
  assert(await page.locator('#model').isDisabled());
  assert(!(await page.locator('#model-label').isVisible()));
  next=resultFor('chess3d');
  await page.selectOption('#source-mode','3d');
  await page.selectOption('#profile','3d');
  assert.equal((await next).profile,'3d');
  assert.equal(await page.locator('#model').inputValue(),'chess3d');
  next=resultFor('chess3d_m');
  await page.selectOption('#model','chess3d_m');
  assert.equal((await next).profile,'3d');
  assert.deepEqual(errors,[]);
  await page.click('#pause');
  console.log('PASS: new 3D → small 3D → 2D → small 3D → new 3D; real streamed inference, no browser errors');
} finally {await browser.close();}
