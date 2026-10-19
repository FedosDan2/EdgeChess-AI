import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { Chess } from 'chess.js';
import * as THREE from 'three';

const browser = await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(process.env.EDGECHESS_WEB_URL || 'http://127.0.0.1:8000');
  await page.waitForFunction(() => document.querySelector('#game-history').textContent.includes('История: 0'));
  await page.waitForFunction(() => document.querySelector('#status').textContent.includes('Поток активен'), null, {timeout:30000});
  // A live real YOLO stream continues during real CPU engine requests.
  await page.waitForFunction(() => !document.querySelector('#ask-advice').disabled);
  const before = await page.locator('#fen').inputValue();
  const request = page.waitForResponse(r => r.url().endsWith('/api/advice'));
  await page.click('#ask-advice');
  const response = await request;
  assert.equal(response.status(), 200);
  const advice = await response.json();
  assert.equal(advice.source, 'history_verified_by_yolo');
  assert(new Chess(before).moves({verbose:true}).some(m => m.from+m.to+(m.promotion||'') === advice.move_uci));
  assert.equal(await page.locator('#fen').inputValue(), before, 'Advice must not apply a move');
  await page.uncheck('#advisor-vision');
  await page.selectOption('#advisor-side', 'b');
  await page.waitForFunction(() => document.querySelector('#advice-status').textContent.includes('другой стороны'));
  assert(await page.locator('#ask-advice').isDisabled());
  await page.selectOption('#advisor-side', 'w');
  await page.waitForFunction(() => !document.querySelector('#ask-advice').disabled);
  // Play real mouse moves; preserve the initial FEN and UCI history on server.
  const rect = await page.locator('#viewport > canvas').first().boundingBox();
  const camera = new THREE.PerspectiveCamera(37,rect.width/rect.height,.1,100);
  camera.position.set(9,11,13);camera.lookAt(0,.2,0);camera.updateMatrixWorld();
  for (const square of ['e2','e4']) {
    const p = new THREE.Vector3(square.charCodeAt(0)-97-3.5,.035,4.5-Number(square[1])).project(camera);
    await page.mouse.click(rect.x+(p.x+1)*rect.width/2,rect.y+(1-p.y)*rect.height/2);
  }
  await page.waitForFunction(() => document.querySelector('#game-history').textContent.includes('История: 1'));
  assert(await page.locator('#ask-advice').isDisabled());
  await page.selectOption('#advisor-side', 'b');
  await page.waitForFunction(() => !document.querySelector('#ask-advice').disabled);
  await page.click('#ask-advice');
  await page.waitForFunction(() => document.querySelector('#advice-result').textContent.includes('Ход не применён'));
  assert((await page.locator('#advice-result').textContent()).includes('только история UI'));
  // Custom FEN starts a fresh history; terminal positions disable the action.
  await page.locator('#fen').fill('7k/6Q1/6K1/8/8/8/8/8 b - - 0 1');
  await page.click('#apply');
  await page.waitForFunction(() => document.querySelector('#advice-status').textContent === 'Партия завершена');
  assert(await page.locator('#ask-advice').isDisabled());
  await page.click('#reset');
  await page.selectOption('#advisor-side', 'w');
  await page.check('#advisor-vision');
  await page.click('#pause');
  await page.waitForFunction(() => document.querySelector('#ask-advice').disabled);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({realStockfish:advice.engine,move:advice.move_uci,realYoloVerified:true,noAutoMove:true,
    wrongSideBlocked:true,historyAfterMove:true,customFenAndMate:true,pausedVisionBlocked:true,errors}));
} finally { await browser.close(); }
