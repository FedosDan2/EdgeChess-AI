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
  const result = await page.evaluate(async () => {
    const board = window.board;
    const snapshot = async () => {
      const bitmap = await board.snapshot();
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width; canvas.height = bitmap.height;
      canvas.getContext('2d').drawImage(bitmap,0,0); bitmap.close();
      return canvas.toDataURL();
    };
    const modes = [];
    for (const mode of ['3d','2d']) {
      board.setAppearance(mode,'wood','classic',3.5);
      board.controls.enabled = false;
      board.showAdvice(null); board.render();
      const before = board.renderer.domElement.toDataURL();
      const input = await snapshot();
      board.showAdvice('e2e4'); board.render();
      const visible = board.renderer.domElement.toDataURL();
      const captured = await snapshot();
      const restored = board.renderer.domElement.toDataURL() === visible;
      const squares = board.advice.children.filter(c => c.isMesh).map(c => [c.position.x,c.position.z]);
      const preserved = board.advice.visible && board.renderer.domElement.dataset.adviceMove === 'e2e4';
      board.chess.move('e4'); board.rebuild();
      const cleared = board.advice.children.length === 0 && !board.renderer.domElement.dataset.adviceMove;
      board.chess.reset(); board.rebuild();
      modes.push({mode,visible:before!==visible,excluded:input===captured,squares,preserved,cleared,restored});
    }
    board.chess.load('7k/P7/8/8/8/8/8/7K w - - 0 1'); board.rebuild();
    board.showAdvice('a7a8n');
    const promotion = board.renderer.domElement.dataset.adviceMove === 'a7a8n';
    board.showAdvice('a7a8');
    const illegalRejected = board.advice.children.length === 0;
    return {modes,promotion,illegalRejected};
  });
  for (const mode of result.modes) {
    assert(mode.visible, `${mode.mode}: highlight must be visible`);
    assert(mode.excluded, `${mode.mode}: highlight must not enter YOLO snapshot`);
    assert(mode.preserved && mode.cleared && mode.restored);
    assert.deepEqual(mode.squares, [[.5,2.5],[.5,.5]]);
  }
  assert(result.promotion && result.illegalRejected);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({...result,errors}));
} finally { await browser?.close(); await server.close(); }
