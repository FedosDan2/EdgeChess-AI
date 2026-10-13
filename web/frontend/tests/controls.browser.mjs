import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import * as THREE from 'three';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.EDGECHESS_WEB_URL || 'http://127.0.0.1:8000');await page.waitForLoadState('networkidle');
 await page.click('#pause');await page.selectOption('#source-mode','3d');await page.uncheck('#boxes');
 // Let resize/render and outstanding stream work settle before the pixel baseline.
 await page.waitForTimeout(350);
 const rect=await page.locator('#viewport > canvas').first().boundingBox();
 const hit=await page.evaluate(({x,y})=>({id:document.elementFromPoint(x,y).id,preview:getComputedStyle(document.querySelector('#still-frame')).display}),{x:rect.x+rect.width/2,y:rect.y+rect.height/2});
 assert.equal(hit.id,'');assert.equal(hit.preview,'none');
 const canvas=page.locator('#viewport > canvas').first();
 const initial=await canvas.screenshot();
 await page.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2);await page.mouse.down();await page.mouse.move(rect.x+rect.width/2+180,rect.y+rect.height/2+40,{steps:20});await page.mouse.up();await page.waitForTimeout(350);
 const rotated=await canvas.screenshot();assert(!initial.equals(rotated),'Dragging must change the 3D view');
 await page.click('#home');await page.waitForTimeout(150);
 const reset=await canvas.screenshot();assert(initial.equals(reset),'Home must restore the exact view without residual damping');
 const camera=new THREE.PerspectiveCamera(37,rect.width/rect.height,.1,100);camera.position.set(9,11,13);camera.lookAt(0,.2,0);camera.updateMatrixWorld();
 const squarePoint=(square)=>{const p=new THREE.Vector3(square.charCodeAt(0)-97-3.5,.035,4.5-Number(square[1])).project(camera);return {x:rect.x+(p.x+1)*rect.width/2,y:rect.y+(1-p.y)*rect.height/2}};
 for(const square of ['e2','e4']) {const p=squarePoint(square);await page.mouse.click(p.x,p.y);}
 assert((await page.locator('#fen').inputValue()).includes('4P3'),'e2-e4 should change the FEN');
 assert.equal(await page.locator('#turn').textContent(),'Ход чёрных');
 for(const square of ['e7','e5']) {const p=squarePoint(square);await page.mouse.click(p.x,p.y);}
 assert.equal(await page.locator('#turn').textContent(),'Ход белых');
 const fen3d=await page.locator('#fen').inputValue();
 await page.click('#reset');await page.selectOption('#source-mode','2d');await page.waitForTimeout(500);
 const r2=await canvas.boundingBox();const camera2=new THREE.PerspectiveCamera(37,r2.width/r2.height,.1,100);camera2.up.set(0,0,-1);camera2.position.set(0,16,.001);camera2.lookAt(0,.2,0);camera2.updateMatrixWorld();
 for(const square of ['e2','e4']) {const p=new THREE.Vector3(square.charCodeAt(0)-97-3.5,.035,4.5-Number(square[1])).project(camera2);await page.mouse.click(r2.x+(p.x+1)*r2.width/2,r2.y+(1-p.y)*r2.height/2);}
 assert.equal(await page.locator('#turn').textContent(),'Ход чёрных');assert.deepEqual(errors,[]);
 const report={mouseReachesScene:true,previewHidden:true,rotation:true,exactCameraReset:true,whiteAndBlackMoves3d:true,moves2d:true,fen3d,errors};
 console.log(JSON.stringify(report));
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
