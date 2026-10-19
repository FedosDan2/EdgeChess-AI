import {parseArgs} from 'node:util';
import {mkdir, writeFile, access} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {chromium} from 'playwright';
import {Chess} from 'chess.js';

const {values} = parseArgs({options:{
  output:{type:'string',default:'../../data/synthetic-demo'},
  positions:{type:'string',default:'24'}, views:{type:'string',default:'2'},
  size:{type:'string',default:'640'}, seed:{type:'string',default:'42'},
  glb:{type:'string'},
}});
const positions=Number(values.positions), views=Number(values.views), size=Number(values.size), seed=Number(values.seed);
for(const [key,value] of Object.entries({positions,views,size,seed}))
  if(!Number.isSafeInteger(value) || value < (key==='positions'?10:key==='seed'?0:1))
    throw new Error(`Invalid --${key}`);
if(size<128 || size>2048) throw new Error('--size must be between 128 and 2048');
const output=path.resolve(values.output);
// Refuse overwriting an existing dataset, including a partially generated one.
try { await access(output); throw new Error(`Output exists: ${output}; choose another --output`); }
catch(e) { if(e.code!=='ENOENT') throw e; }
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
let state=seed>>>0;
const random=()=>{state=(state+0x6D2B79F5)>>>0;let t=state;t=Math.imul(t^(t>>>15),t|1);
  t^=t+Math.imul(t^(t>>>7),t|61);return ((t^(t>>>14))>>>0)/4294967296;};
const pick=items=>items[Math.floor(random()*items.length)];
const range=(lo,hi)=>lo+random()*(hi-lo);
const fens=[], seen=new Set();
while(fens.length<positions) {
  const chess=new Chess(); const plies=fens.length===0?0:Math.floor(range(5,100));
  for(let i=0;i<plies && !chess.isGameOver();i++) chess.move(pick(chess.moves()));
  // Turn, castling rights and counters do not change the rendered arrangement.
  const key=chess.fen().split(' ')[0];
  if(!seen.has(key)) {seen.add(key);fens.push(chess.fen());}
}
const order=fens.map((_,i)=>i);
for(let i=order.length-1;i>0;i--) {const j=Math.floor(random()*(i+1));[order[i],order[j]]=[order[j],order[i]];}
const trainEnd=Math.floor(positions*.8),valEnd=trainEnd+Math.max(1,Math.floor(positions*.1));
const splits=new Map(order.map((id,i)=>[id,i<trainEnd?'train':i<valEnd?'val':'test']));
const server=await createServer({root,server:{host:'127.0.0.1',port:0}});
let browser;
try {
  await server.listen();
  const address=server.httpServer.address();
  browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const page=await browser.newPage({viewport:{width:size,height:size}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${address.port}/dataset.html`);
  await page.waitForFunction(()=>Boolean(window.dataset));
  if(values.glb) {
    const {readFile}=await import('node:fs/promises');
    const bytes=Array.from(await readFile(path.resolve(values.glb)));
    await page.evaluate(async bytes=>window.dataset.loadPieceSet(new Uint8Array(bytes).buffer),bytes);
  }
  const classes=await page.evaluate(()=>window.dataset.classes);
  await mkdir(output,{recursive:true});
  for(const split of ['train','val','test']) for(const dir of ['images','labels','masks','metadata'])
    await mkdir(path.join(output,split,dir),{recursive:true});
  const records=[];
  for(let position=0;position<positions;position++) for(let view=0;view<views;view++) {
    const split=splits.get(position),id=`position_${String(position).padStart(4,'0')}_view_${String(view).padStart(2,'0')}`;
    const options={fen:fens[position],size,theme:pick(['wood','marble','walnut']),
      shape:values.glb?'glb':pick(['classic','slim']),yaw:range(0,360),pitch:range(30,80),distance:range(19,23),
      light:range(2,5),lightYaw:range(0,360)};
    const sample=await page.evaluate(options=>window.dataset.sample(options),options);
    if(errors.length) throw new Error(errors.join('\n'));
    const png=data=>Buffer.from(data.split(',')[1],'base64');
    await writeFile(path.join(output,split,'images',`${id}.png`),png(sample.image));
    await writeFile(path.join(output,split,'masks',`${id}.png`),png(sample.mask));
    await writeFile(path.join(output,split,'labels',`${id}.txt`),sample.labels);
    await writeFile(path.join(output,split,'metadata',`${id}.json`),JSON.stringify(sample.metadata,null,2)+'\n');
    records.push({id,split,position,view,...options,pieces:sample.metadata.pieces.length});
    console.log(`${records.length}/${positions*views} ${split}/${id} (${sample.metadata.pieces.length} visible pieces)`);
  }
  // Relative image paths work when the folder is moved to a colleague's machine.
  await writeFile(path.join(output,'data.yaml'),`train: train/images\nval: val/images\ntest: test/images\nnc: ${classes.length}\nnames:\n${classes.map((name,i)=>`  ${i}: ${name}`).join('\n')}\n`);
  await writeFile(path.join(output,'manifest.json'),JSON.stringify({generator:'EdgeChess BoardScene',seed,size,
    positions,views,classes,instanceMaskEncoding:'RGB=(instance_id,0,0), background=0; IDs local to each image',
    splitPolicy:'80/10/10 by unique legal position, not individual frames',
    glb:values.glb?path.basename(values.glb):null,records},null,2)+'\n');
  console.log(`Dataset ready: ${output}`);
} finally {
  await browser?.close(); await server.close();
}
