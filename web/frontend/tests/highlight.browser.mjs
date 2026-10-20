import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';

const server = await createServer({appType:'custom',root:fileURLToPath(new URL('..',import.meta.url)),server:{host:'127.0.0.1',port:0}});
server.middlewares.use('/highlight-test', (_req, res) => {
  res.setHeader('Content-Type', 'text/html');
  res.end(`<div id="scene" style="width:800px;height:600px"></div><script type="module">
    import {BoardScene} from '/src/scene.ts';
    window.board = new BoardScene(document.getElementById('scene'));
  </script>`);
});
let browser;
try {
  await server.listen();
  browser = await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/highlight-test`);
  await page.waitForFunction(() => Boolean(window.board)).catch(error => {
    throw new Error(`${error.message}; page errors: ${errors.join('; ')}`);
  });
  await page.evaluate(() => window.board.setAppearance('2d','wood','classic',3.5));
  await page.waitForFunction(() => [...window.board.textures.values()].every(t => t.image?.complete));
  const result = await page.evaluate(async () => {
    const board = window.board;
    let snapshotPixels;
    const snapshot = async () => {
      const bitmap = await board.snapshot();
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width; canvas.height = bitmap.height;
      canvas.getContext('2d').drawImage(bitmap,0,0); bitmap.close();
      snapshotPixels = canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
      return canvas.toDataURL();
    };
    const modes = [];
    for (const mode of ['3d','2d']) {
      board.setAppearance(mode,'wood','classic',3.5);
      board.controls.enabled = false;
      board.showAdvice(null); board.render();
      const before = board.renderer.domElement.toDataURL();
      const reference = document.createElement('canvas');
      reference.width = board.renderer.domElement.width; reference.height = board.renderer.domElement.height;
      const referenceContext = reference.getContext('2d');
      referenceContext.drawImage(board.renderer.domElement,0,0);
      const displayPixels = referenceContext.getImageData(0,0,reference.width,reference.height).data;
      const input = await snapshot();
      let colorDelta = 0;
      for (let i=0; i<displayPixels.length; i+=4) for (let c=0; c<3; c++) {
        colorDelta += Math.abs(displayPixels[i+c]-snapshotPixels[i+c]);
      }
      const meanColorDelta = colorDelta / (reference.width*reference.height*3);
      board.choose('g1'); // legal-move dots and Stockfish marks coexist
      board.showAdvice('e2e4'); board.render();
      const visible = board.renderer.domElement.toDataURL();
      const captured = await snapshot();
      const restored = board.renderer.domElement.toDataURL() === visible;
      // Delay bitmap completion across a display frame. A snapshot must not
      // hide markers during this wait or draw any clean pass to the screen.
      const originalBitmap = window.createImageBitmap.bind(window);
      const originalRender = board.renderer.render;
      const renders = [];
      let release;
      const hold = new Promise(resolve => { release = resolve; });
      window.createImageBitmap = (...args) => originalBitmap(...args).then(async bitmap => {
        await hold;
        return bitmap;
      });
      board.renderer.render = function(scene, camera) {
        renders.push({screen:this.getRenderTarget()===null,markers:board.markers.visible,advice:board.advice.visible});
        return originalRender.call(this,scene,camera);
      };
      let synchronousVisibility, visibleDuringDecode;
      try {
        const pending = board.snapshot();
        synchronousVisibility = board.markers.visible && board.advice.visible;
        await new Promise(requestAnimationFrame);
        board.render();
        visibleDuringDecode = board.renderer.domElement.toDataURL() === visible;
        release();
        (await pending).close();
      } finally {
        release();
        window.createImageBitmap = originalBitmap;
        board.renderer.render = originalRender;
      }
      const isolated = !renders.some(r => r.screen && (!r.markers || !r.advice));
      const squares = board.advice.children.filter(c => c.isMesh).map(c => [c.position.x,c.position.z]);
      const preserved = board.advice.visible && board.renderer.domElement.dataset.adviceMove === 'e2e4';
      board.chess.move('e4'); board.rebuild();
      const cleared = board.advice.children.length === 0 && !board.renderer.domElement.dataset.adviceMove;
      board.chess.reset(); board.rebuild();
      modes.push({mode,visible:before!==visible,excluded:input===captured,squares,preserved,cleared,restored,
        synchronousVisibility,visibleDuringDecode,isolated,meanColorDelta});
    }
    board.chess.load('7k/P7/8/8/8/8/8/7K w - - 0 1'); board.rebuild();
    board.showAdvice('a7a8n');
    const promotion = board.renderer.domElement.dataset.adviceMove === 'a7a8n';
    board.showAdvice('a7a8');
    const illegalRejected = board.advice.children.length === 0;
    board.chess.reset(); board.setAppearance('3d','wood','classic',3.5);
    board.showAdvice('e2e4'); board.choose('g1'); board.render();
    const originalRead = board.renderer.readRenderTargetPixels;
    let errorRestoresState = false;
    board.renderer.readRenderTargetPixels = () => { throw new Error('Simulated capture failure'); };
    try {
      await board.snapshot();
    } catch {
      errorRestoresState = board.markers.visible && board.advice.visible && board.renderer.getRenderTarget() === null;
    } finally { board.renderer.readRenderTargetPixels = originalRead; }
    const initial = await snapshot();
    const first = snapshot();
    board.chess.move('e4'); board.rebuild();
    const second = snapshot();
    const concurrent = await Promise.all([first,second]);
    const independentSnapshots = concurrent[0] === initial && concurrent[1] !== initial;
    const target = board.captureScene;
    const host = board.renderer.domElement.parentElement;
    host.style.width = '1600px'; host.style.height = '1200px'; board.resize(host);
    const large = await board.snapshot();
    const bounded = large.width === 960 && large.height === 720;
    large.close();
    host.style.width = '400px'; host.style.height = '300px'; board.resize(host);
    const small = await board.snapshot();
    const reusedAfterResize = board.captureScene === target && small.width === 400 && small.height === 300;
    small.close();
    return {modes,promotion,illegalRejected,errorRestoresState,independentSnapshots,bounded,reusedAfterResize};
  });
  for (const mode of result.modes) {
    assert(mode.visible, `${mode.mode}: highlight must be visible`);
    assert(mode.excluded, `${mode.mode}: highlight must not enter YOLO snapshot`);
    assert(mode.preserved && mode.cleared && mode.restored);
    assert(mode.synchronousVisibility && mode.visibleDuringDecode && mode.isolated,
      `${mode.mode}: capture must never hide marks on the visible framebuffer`);
    assert(mode.meanColorDelta < 3, `${mode.mode}: capture must preserve display colors and orientation`);
    assert.deepEqual(mode.squares, [[.5,2.5],[.5,.5]]);
  }
  assert(result.promotion && result.illegalRejected);
  assert(result.errorRestoresState && result.independentSnapshots && result.bounded && result.reusedAfterResize, JSON.stringify(result));
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({...result,errors}));
} finally { await browser?.close(); await server.close(); }
