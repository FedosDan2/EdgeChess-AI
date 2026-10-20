import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { createServer } from 'vite';

// Deterministic UI fixtures; the separate advisor test covers real YOLO/Stockfish.
const server = await createServer({root:fileURLToPath(new URL('..',import.meta.url)),server:{host:'127.0.0.1',port:0}});
await server.listen();
const browser = await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
try {
  const page = await browser.newPage({viewport:{width:1024,height:900}});
  // Layout/state fixtures are not a GPU benchmark. Bound software WebGL work.
  await page.addInitScript(() => {
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = callback => window.setTimeout(() => raf(callback), 100);
  });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const initial = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR';
  const configuration = {profile:'3d',backend:'onnx',model:'chess3d_m',provider:'CPUExecutionProvider',
    input_size:640,warmup_runs:5,models:[{key:'chess3d_m',conversion_verified:true}],
    model_choices:{chess3d_m:'YOLOv8m'},stockfish:{available:true}};
  let game, feed = true, frames = 0;
  let speechState = 'playing', speechStops = 0;
  const adviceRequests = [];
  let observation = {placement:initial,status:'ok',warnings:[]};
  await page.route('**/api/health',route=>route.fulfill({json:{status:'ready',...configuration}}));
  await page.route('**/api/game',route=>{
    game = route.request().postDataJSON();
    return route.fulfill({json:{...game,plies:game.moves.length,fen:game.initial_fen}});
  });
  await page.route('**/api/advice',route=>{
    const request = route.request().postDataJSON();
    adviceRequests.push(request);
    return route.fulfill({json:{move_san:'e4',move_uci:'e2e4',
      speech:{state:request.speak ? 'queued' : 'disabled'},
      engine:'Stockfish fixture',elapsed_ms:1000,source:'history_verified_by_yolo'}});
  });
  await page.route('**/api/speech',route=>route.fulfill({json:{state:speechState,
    game_id:game.game_id,revision:game.revision}}));
  await page.route('**/api/speech/stop',route=>{
    ++speechStops;
    return route.fulfill({json:{state:'idle'}});
  });
  await page.routeWebSocket('**/api/stream?*',ws=>{
    ws.send(JSON.stringify({type:'ready',...configuration}));
    ws.onMessage(message=>{
      const id = Number(Buffer.from(message).readBigUInt64BE(0));
      ws.send(JSON.stringify({type:'ack',id}));
      if (!feed) return;
      ++frames;
      ws.send(JSON.stringify({type:'result',id,...observation,profile:'3d',backend:'onnx',
        width:960,height:720,detections:[],pieces:[],game_revision:game?.revision,
        timings:{inference_ms:25,preprocess_ms:4,postprocess_ms:3,processing_ms:32,queue_ms:1},
        stages:{},counters:{received:frames,processed:frames,replaced:0}}));
    });
  });
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}`);
  await page.selectOption('#capture-fps','10').catch(error => {
    throw new Error(`${error.message}; page errors: ${errors.join('; ')}`);
  });
  await page.waitForFunction(() => document.querySelector('#recognition-score').textContent === '64/64');
  observation = {placement:initial.replace('rnbqkbnr','rnbq1bnr'),status:'ok',warnings:[]};
  await page.waitForFunction(() => document.querySelector('#recognition-score').textContent === '63/64'
    && document.querySelector('#recognition-badge').textContent === 'Есть отличия');
  observation = {placement:initial,status:'ambiguous',warnings:['cell_conflict:e4']};
  await page.waitForFunction(() => document.querySelector('#recognition-badge').textContent === 'Проверьте');
  observation = {placement:null,status:'corners_missing',warnings:[]};
  await page.waitForFunction(() => document.querySelector('#recognition-badge').textContent === 'Нет позиции');
  assert.equal(await page.locator('#recognition-score').textContent(),'—');
  observation = {placement:initial,status:'ok',warnings:[]};
  await page.waitForFunction(() => !document.querySelector('#ask-advice').disabled);
  await page.locator('#ask-advice').dispatchEvent('click');
  await page.waitForFunction(() => document.querySelector('#advice-result').textContent.includes('Ход не применён'));
  assert.equal(adviceRequests.length, 1);
  assert.equal(adviceRequests[0].speak, true);
  await page.waitForFunction(() => document.querySelector('#speech-status').textContent.includes('Звук на аудиовыходе сервера'));
  const stopped = page.waitForResponse(response => response.url().endsWith('/api/speech/stop'));
  await page.uncheck('#advisor-speech');
  await stopped;
  await page.waitForFunction(() => document.querySelector('#speech-status').textContent === '');
  assert(speechStops > 0, 'Disabling speech must stop server playback');
  await page.locator('#ask-advice').dispatchEvent('click');
  await page.waitForFunction(() => document.querySelector('#advice-result').textContent.includes('Ход не применён'));
  assert.equal(adviceRequests.length, 2);
  assert.equal(adviceRequests[1].speak, false);
  await page.check('#advisor-speech');
  speechState = 'error';
  await page.locator('#ask-advice').dispatchEvent('click');
  await page.waitForFunction(() => document.querySelector('#speech-status').textContent.includes('Ошибка озвучки'));
  assert((await page.locator('#advice-result').textContent()).includes('e2e4'));
  await page.setViewportSize({width:1366,height:768});
  await page.evaluate(() => window.scrollTo(0,0));
  assert(await page.locator('#stockfish-card').evaluate(element => element.getBoundingClientRect().bottom <= 768),
    'Summary with audio status must fit the first desktop screen');
  await page.uncheck('#advisor-speech');
  const artifacts = fileURLToPath(new URL('../../../artifacts/', import.meta.url));
  await mkdir(artifacts,{recursive:true});
  feed = false;
  await page.waitForFunction(() => document.querySelector('#accuracy').textContent === 'Нет свежего результата');
  assert.equal(await page.locator('#recognition-score').textContent(),'—');
  await page.click('#pause');
  assert.equal(await page.locator('#recognition-score').textContent(),'—', 'Paused stream must not show stale correctness');

  const checked = [];
  for (const [width,height] of [[1920,1080],[1440,900],[1366,768],[768,1024],[390,844],[320,568]]) {
    await page.setViewportSize({width,height});
    await page.evaluate(() => window.scrollTo(0,0));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const geometry = await page.evaluate(() => {
      const rect = selector => {
        const r = document.querySelector(selector).getBoundingClientRect();
        return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};
      };
      const ids = [...document.querySelectorAll('[id]')].map(e=>e.id);
      return {pageWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth,
        board:rect('.board-panel'),sidebar:rect('.live-sidebar'),
        cards:['#performance-card','#recognition-card','#stockfish-card'].map(rect),
        controls:rect('.controls-grid'),scene:rect('#scene-settings'),
        duplicateIds:ids.filter((id,i)=>ids.indexOf(id)!==i)};
    });
    assert(geometry.pageWidth <= width+1, `${width}: horizontal overflow`);
    assert.deepEqual(geometry.duplicateIds, []);
    assert(geometry.controls.y >= geometry.board.bottom-1, `${width}: settings must be below board`);
    assert(geometry.scene.y >= geometry.board.bottom-1);
    if (width>820) {
      assert(geometry.sidebar.x >= geometry.board.right, `${width}: live summary must be on right`);
      for (const card of geometry.cards) assert(card.bottom <= height, `${width}: summary must fit first screen`);
    } else {
      assert(geometry.sidebar.y >= geometry.board.bottom-1, `${width}: mobile summary must stack`);
    }
    checked.push({width,height,summaryBottom:Math.round(geometry.sidebar.bottom)});
  }
  await page.setViewportSize({width:1920,height:1080});
  await page.evaluate(() => window.scrollTo(0,0));
  await page.screenshot({path:`${artifacts}/ui-layout-desktop.png`});
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(() => window.scrollTo(0,0));
  await page.screenshot({path:`${artifacts}/ui-layout-mobile.png`,fullPage:true});
  const details = page.locator('.recognition-details > details');
  assert.equal(await details.getAttribute('open'), null);
  await details.locator('summary').click();
  assert(await page.locator('#recognized-placement').isVisible());
  await page.locator('#castling').fill('KQkq');
  await page.locator('#castling').blur();
  const history = page.locator('.game-details');
  await history.locator('summary').click();
  assert(await page.locator('#sync-game').isVisible());
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({fixtures:true,responsive:checked,recognitionStates:true,speechControls:true,detailsAccessible:true,errors}));
} finally { await browser.close(); await server.close(); }
