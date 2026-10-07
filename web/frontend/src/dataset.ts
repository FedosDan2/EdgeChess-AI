import * as THREE from "three";
import { BoardScene } from "./scene";

const names = ["queen", "king", "bishop", "knight", "rook", "pawn"];
const symbols = ["q", "k", "b", "n", "r", "p"];
const classes = ["white", "black"].flatMap(color => names.map(name => `${color}_${name}`))
  .concat(["corner_white_left", "corner_white_right", "corner_black_left", "corner_black_right"]);
const host = document.querySelector<HTMLElement>("#scene")!;
const board = new BoardScene(host);
board.controls.enabled = false;

// Dedicated entry point shares the production scene, without UI or inference.
function sample(options: {fen: string; size: number; theme: string; shape: string;
  yaw: number; pitch: number; distance: number; light: number; lightYaw: number}) {
  const {size} = options;
  host.style.width = host.style.height = `${size}px`;
  board.chess.load(options.fen);
  board.setAppearance("3d", options.theme, options.shape, options.light);
  board.controls.enabled = false;
  board.renderer.setPixelRatio(1);
  board.renderer.setSize(size, size);
  board.camera.aspect = 1;
  board.camera.updateProjectionMatrix();
  const yaw = THREE.MathUtils.degToRad(options.yaw), pitch = THREE.MathUtils.degToRad(options.pitch);
  board.camera.position.set(Math.sin(yaw)*Math.cos(pitch)*options.distance,
    Math.sin(pitch)*options.distance, Math.cos(yaw)*Math.cos(pitch)*options.distance);
  board.camera.lookAt(0, .2, 0);
  board.camera.updateMatrixWorld();
  for (const object of board.scene.children) if (object instanceof THREE.DirectionalLight) {
    const a = THREE.MathUtils.degToRad(options.lightYaw);
    object.position.set(Math.sin(a)*7, 12, Math.cos(a)*7);
  }
  board.renderer.render(board.scene, board.camera);
  const image = board.renderer.domElement.toDataURL("image/png");

  // All geometry participates in depth testing. Non-piece surfaces occlude in black.
  const target = new THREE.WebGLRenderTarget(size, size, {depthBuffer: true});
  const black = new THREE.MeshBasicMaterial({color: 0});
  const originals = new Map<THREE.Mesh, THREE.Material | THREE.Material[]>();
  const materials: THREE.Material[] = [black];
  const pieces = board.pieces.children.map((object, index) => {
    const p = board.chess.get(object.userData.square)!;
    const material = new THREE.MeshBasicMaterial();
    material.color.setRGB((index+1)/255, 0, 0, THREE.LinearSRGBColorSpace);
    materials.push(material);
    return {object, material, instance: index+1, square: object.userData.square as string,
      classId: symbols.indexOf(p.type) + (p.color === "w" ? 0 : 6)};
  });
  const pixels = new Uint8Array(size*size*4);
  const tone = board.renderer.toneMapping, clear = board.renderer.getClearColor(new THREE.Color());
  const alpha = board.renderer.getClearAlpha(), shadows = board.renderer.shadowMap.enabled;
  const background = board.scene.background;
  try {
    board.scene.traverse(object => { if (object instanceof THREE.Mesh) {
      originals.set(object, object.material); object.material = black;
    }});
    for (const p of pieces) p.object.traverse(object => {
      if (object instanceof THREE.Mesh) object.material = p.material;
    });
    board.scene.background = null;
    board.renderer.toneMapping = THREE.NoToneMapping;
    board.renderer.shadowMap.enabled = false;
    board.renderer.setClearColor(0, 1);
    board.renderer.setRenderTarget(target);
    board.renderer.render(board.scene, board.camera);
    board.renderer.readRenderTargetPixels(target, 0, 0, size, size, pixels);
  } finally {
    board.renderer.setRenderTarget(null);
    for (const [object, material] of originals) object.material = material;
    board.scene.background = background;
    board.renderer.toneMapping = tone;
    board.renderer.shadowMap.enabled = shadows;
    board.renderer.setClearColor(clear, alpha);
    target.dispose(); materials.forEach(material => material.dispose());
  }
  const bounds = pieces.map(() => [size, size, -1, -1, 0]);
  const maskCanvas = document.createElement("canvas"); maskCanvas.width = maskCanvas.height = size;
  const context = maskCanvas.getContext("2d")!;
  const mask = context.createImageData(size, size);
  for (let y=0; y<size; y++) for (let x=0; x<size; x++) {
    const source = ((size-1-y)*size+x)*4, dest = (y*size+x)*4;
    const id = pixels[source]; mask.data[dest] = id; mask.data[dest+3] = 255;
    if (!id) continue;
    if (id > bounds.length || pixels[source+1] || pixels[source+2]) throw new Error("Invalid instance color");
    const b = bounds[id-1]; b[0]=Math.min(b[0],x); b[1]=Math.min(b[1],y);
    b[2]=Math.max(b[2],x); b[3]=Math.max(b[3],y); b[4]++;
  }
  context.putImageData(mask,0,0);
  const annotations = pieces.flatMap((p,i) => bounds[i][4] ? [{
    classId: p.classId, className: classes[p.classId], instance: p.instance, square: p.square,
    bbox: bounds[i].slice(0,4), visiblePixels: bounds[i][4],
  }] : []);
  const corners = [[-4,4],[4,4],[4,-4],[-4,-4]].map(([x,z],i) => {
    const point = new THREE.Vector3(x,.0175,z).project(board.camera);
    const cx=(point.x+1)*size/2, cy=(1-point.y)*size/2, half=size*.025;
    if (cx < half || cy < half || cx >= size-half || cy >= size-half)
      throw new Error("Board corner outside frame; increase camera distance");
    return {classId:12+i, className:classes[12+i], point:[cx,cy],
      bbox:[cx-half,cy-half,cx+half,cy+half]};
  });
  const labels = [...annotations,...corners].map(({classId,bbox:[x1,y1,x2,y2]}) =>
    `${classId} ${[(x1+x2)/(2*size),(y1+y2)/(2*size),(x2-x1)/size,(y2-y1)/size].map(v=>v.toFixed(6)).join(" ")}`
  ).join("\n")+"\n";
  return {image, mask:maskCanvas.toDataURL("image/png"), labels,
    metadata:{...options, bboxConvention:"visible instance pixels, inclusive extrema; YOLO width=xmax-xmin (ChessRender360)",
      pieces:annotations, corners, hiddenSquares:pieces.filter((_,i)=>!bounds[i][4]).map(p=>p.square)}};
}

Object.assign(window, {dataset:{sample, classes, loadPieceSet:(buffer: ArrayBuffer)=>board.loadPieceSet(buffer)}});
