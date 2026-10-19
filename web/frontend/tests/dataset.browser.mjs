import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';

const server=await createServer({root:fileURLToPath(new URL('..',import.meta.url)),server:{host:'127.0.0.1',port:0}});
let browser;
try {
  await server.listen();
  browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/dataset.html`);
  await page.waitForFunction(()=>Boolean(window.dataset));
  const options={fen:'4k3/8/8/8/8/8/P7/Q3K3 w - - 0 1',size:256,theme:'wood',shape:'classic',
    yaw:0,pitch:30,distance:19,light:3,lightYaw:0};
  const render=options=>page.evaluate(options=>window.dataset.sample(options),options);
  const occluded=await render(options), repeated=await render(options);
  assert.equal(occluded.image,repeated.image,'RGB pass must restore materials and lighting after mask rendering');
  assert.equal(occluded.mask,repeated.mask,'Instance pass must be deterministic');
  assert.equal(occluded.labels,repeated.labels);
  const clear=await render({...options,fen:'4k3/8/8/8/8/8/P7/4K3 w - - 0 1'});
  const pawn=sample=>sample.metadata.pieces.find(p=>p.square==='a2');
  assert(pawn(clear),'Unoccluded pawn must be labelled');
  assert((pawn(occluded)?.visiblePixels||0)<pawn(clear).visiblePixels,'Foreground queen must occlude pawn pixels');
  assert.deepEqual(occluded.metadata.corners.map(p=>p.classId),[12,13,14,15]);
  const [a1,h1,h8,a8]=occluded.metadata.corners.map(p=>p.point);
  assert(a1[0]<h1[0] && a8[0]<h8[0] && a1[1]>a8[1] && h1[1]>h8[1], 'Corner classes must follow player perspective');
  for(const sample of [occluded,clear]) for(const line of sample.labels.trim().split('\n')) {
    const [id,x,y,w,h]=line.split(' ').map(Number);
    assert(id>=0 && id<16 && x>=0 && x<=1 && y>=0 && y<=1 && w>0 && h>0);
  }
  assert.deepEqual(errors,[]);
  console.log('Passed: occlusion, renderer restoration, repeatability, corner semantics, YOLO labels');
} finally {await browser?.close();await server.close();}
