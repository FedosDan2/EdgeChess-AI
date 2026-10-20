import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { Chess, type Square, type PieceSymbol, type Color } from "chess.js";

// Procedural solid pieces: no remote assets or runtime CDN dependencies.
// Replace this factory with a dataset-matched glTF set when those assets exist.
function piece(type: PieceSymbol, color: Color) {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({
    color: color === "w" ? 0xeadcc3 : 0x333b39,
    roughness: 0.3,
    metalness: 0.08,
  });
  const add = (geometry: THREE.BufferGeometry, y: number, x = 0, z = 0) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);
    return mesh;
  };
  const height = { p: 0.75, r: 0.95, n: 1.08, b: 1.17, q: 1.35, k: 1.48 }[type];
  const profile = [
    [0, 0],
    [0.29, 0],
    [0.33, 0.05],
    [0.33, 0.1],
    [0.28, 0.16],
    [0.24, 0.2],
    [0.2, 0.25],
    [0.15, height * 0.45],
    [0.13, height * 0.58],
    [0.22, height * 0.65],
    [0.22, height * 0.7],
    [0, height * 0.7],
  ];
  add(
    new THREE.LatheGeometry(
      profile.map(([r, y]) => new THREE.Vector2(r, y)),
      40,
    ),
    0,
  );
  if (type === "p") add(new THREE.SphereGeometry(0.21, 24, 16), height * 0.82);
  if (type === "r") {
    add(new THREE.CylinderGeometry(0.26, 0.21, 0.2, 32), height * 0.82);
    for (let i = 0; i < 6; i++) {
      const angle = (i * Math.PI) / 3;
      const m = add(
        new THREE.BoxGeometry(0.15, 0.17, 0.13),
        height,
        Math.cos(angle) * 0.2,
        Math.sin(angle) * 0.2,
      );
      m.rotation.y = -angle;
    }
  }
  if (type === "b") {
    const top = add(new THREE.SphereGeometry(0.21, 24, 16), height * 0.85);
    top.scale.set(0.8, 1.35, 0.8);
    add(new THREE.SphereGeometry(0.07, 16, 12), height * 1.12);
    // Dark inset suggests the traditional mitre cut.
    const cut = new THREE.Mesh(
      new THREE.BoxGeometry(0.035, 0.2, 0.34),
      new THREE.MeshStandardMaterial({ color: 0x544e42 }),
    );
    cut.position.y = height * 0.93;
    cut.rotation.z = -0.4;
    group.add(cut);
  }
  if (type === "q" || type === "k") {
    add(new THREE.CylinderGeometry(0.25, 0.17, 0.15, 32), height * 0.8);
    if (type === "q") {
      for (let i = 0; i < 8; i++) {
        const a = (i * Math.PI) / 4;
        add(
          new THREE.SphereGeometry(0.065, 12, 8),
          height * 0.94,
          Math.cos(a) * 0.2,
          Math.sin(a) * 0.2,
        );
      }
      add(new THREE.SphereGeometry(0.09, 16, 12), height);
    } else {
      add(new THREE.BoxGeometry(0.1, 0.35, 0.1), height * 0.98);
      add(new THREE.BoxGeometry(0.3, 0.09, 0.1), height * 1.01);
    }
  }
  if (type === "n") {
    const shape = new THREE.Shape();
    shape.moveTo(-0.23, 0);
    shape.lineTo(-0.26, 0.35);
    shape.lineTo(-0.12, 0.69);
    shape.lineTo(-0.04, 0.8);
    shape.lineTo(0.05, 0.67);
    shape.lineTo(0.25, 0.53);
    shape.lineTo(0.28, 0.34);
    shape.lineTo(0.03, 0.33);
    shape.lineTo(0.16, 0);
    shape.closePath();
    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: 0.23,
      bevelEnabled: true,
      bevelSize: 0.045,
      bevelThickness: 0.035,
      bevelSegments: 2,
      steps: 1,
    });
    geo.translate(0, 0, -0.115);
    const head = add(geo, height * 0.5);
    head.rotation.y = color === "w" ? -Math.PI / 2 : Math.PI / 2;
  }
  return group;
}

export class BoardScene {
  readonly chess = new Chess();
  readonly renderer: THREE.WebGLRenderer;
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(37, 4 / 3, 0.1, 100);
  readonly controls: OrbitControls;
  readonly pieces = new THREE.Group();
  readonly markers = new THREE.Group();
  readonly advice = new THREE.Group();
  mode: "2d" | "3d" = "3d";
  theme = "wood";
  shape = "classic";
  private imported: Record<string, THREE.Object3D> = {};
  private tabletop: THREE.Mesh | null = null;
  private textures = new Map<string, THREE.Texture>();
  private ray = new THREE.Raycaster();
  private selected: Square | null = null;
  private down = { x: 0, y: 0 };
  private tiles: THREE.Object3D[] = [];
  private adviceFen: string | null = null;
  private captureScene: THREE.WebGLRenderTarget | null = null;
  private captureOutput: THREE.WebGLRenderTarget | null = null;
  private capturePass: OutputPass | null = null;
  private capturePixels = new Uint8Array(0);
  onChange: () => void = () => {};
  onMessage: (message: string) => void = () => {};
  promotion: PieceSymbol = "q";

  constructor(host: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.setClearColor(0xdce1dc);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    host.prepend(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.minDistance = 9;
    this.controls.maxDistance = 27;
    this.controls.maxPolarAngle = Math.PI * 0.47;
    this.controls.minPolarAngle = 0.12;
    this.controls.enablePan = false;
    this.home();
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x788276, 2.4));
    const light = new THREE.DirectionalLight(0xfff4de, 3.5);
    light.position.set(-4, 12, 5);
    light.castShadow = true;
    light.shadow.mapSize.set(2048, 2048);
    Object.assign(light.shadow.camera, {
      left: -7,
      right: 7,
      top: 7,
      bottom: -7,
    });
    light.shadow.bias = -0.001;
    this.scene.add(light);
    const base = new THREE.Mesh(
      new THREE.BoxGeometry(8.65, 0.35, 8.65),
      new THREE.MeshStandardMaterial({ color: 0x544735, roughness: 0.55 }),
    );
    base.position.y = -0.2;
    base.receiveShadow = true;
    this.scene.add(base);
    const table = new THREE.Mesh(
      new THREE.BoxGeometry(24, 0.35, 20),
      new THREE.MeshStandardMaterial({ color: 0x8b684b, roughness: 0.85 }),
    );
    table.position.y = -0.55;
    table.receiveShadow = true;
    this.tabletop = table;
    this.scene.add(table);
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(200, 200),
      new THREE.MeshStandardMaterial({ color: 0xcdd4cd, roughness: 1 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.76;
    floor.receiveShadow = true;
    this.scene.add(floor);
    for (let rank = 0; rank < 8; rank++)
      for (let file = 0; file < 8; file++) {
        const square = `${"abcdefgh"[file]}${rank + 1}`;
        const tile = new THREE.Mesh(
          new THREE.BoxGeometry(1, 0.035, 1),
          new THREE.MeshStandardMaterial({
            color: (rank + file) % 2 === 0 ? 0x73816b : 0xede6d5,
            roughness: 0.75,
          }),
        );
        tile.position.set(file - 3.5, 0, 3.5 - rank);
        tile.receiveShadow = true;
        tile.userData.square = square;
        this.tiles.push(tile);
        this.scene.add(tile);
      }
    this.scene.add(this.pieces, this.markers, this.advice);
    this.rebuild();
    this.renderer.domElement.addEventListener("pointerdown", (e) => {
      this.down = { x: e.clientX, y: e.clientY };
    });
    this.renderer.domElement.addEventListener("pointerup", (e) => {
      if (
        e.button !== 0 ||
        Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y) > 5
      )
        return;
      const rect = this.renderer.domElement.getBoundingClientRect();
      this.ray.setFromCamera(
        new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          (-(e.clientY - rect.top) / rect.height) * 2 + 1,
        ),
        this.camera,
      );
      const hits = this.ray.intersectObjects(
        [...this.tiles, ...this.pieces.children],
        true,
      );
      if (!hits.length) return;
      let target: THREE.Object3D | null = hits[0].object;
      while (target && !target.userData.square) target = target.parent;
      if (target) this.choose(target.userData.square as Square);
    });
    new ResizeObserver(() => this.resize(host)).observe(host);
    this.resize(host);
  }
  private resize(host: HTMLElement) {
    this.renderer.setSize(host.clientWidth, host.clientHeight);
    this.camera.aspect = host.clientWidth / host.clientHeight;
    this.camera.updateProjectionMatrix();
  }
  setAppearance(mode: "2d" | "3d", theme: string, shape: string, light: number) {
    this.mode = mode; this.theme = theme; this.shape = shape;
    const palettes: Record<string, number[]> = {
      wood: [0xeadcc3, 0x333b39, 0x73816b, 0xede6d5, 0x8b684b],
      marble: [0xf3f1eb, 0x202126, 0x494b51, 0xe1dfd7, 0x8c8d91],
      walnut: [0xcfa66b, 0x342418, 0x72533d, 0xd7b994, 0x503627],
    };
    const colors = palettes[theme] || palettes.wood;
    this.tiles.forEach((tile, i) => {
      const material = (tile as THREE.Mesh).material as THREE.MeshStandardMaterial;
      const rank = Math.floor(i / 8), file = i % 8;
      material.color.setHex(colors[(rank + file) % 2 === 0 ? 2 : 3]);
    });
    if (this.tabletop) {
      (this.tabletop.material as THREE.MeshStandardMaterial).color.setHex(colors[4]);
      this.tabletop.visible = mode === "3d";
    }
    for (const object of this.scene.children) {
      if (object instanceof THREE.DirectionalLight) object.intensity = light;
    }
    this.controls.enabled = mode === "3d";
    this.home(); this.rebuild();
  }
  async loadPieceSet(buffer: ArrayBuffer) {
    const gltf = await new GLTFLoader().parseAsync(buffer, "");
    const models: Record<string, THREE.Object3D> = {};
    for (const color of ["w", "b"]) for (const type of ["P", "N", "B", "R", "Q", "K"]) {
      const name = color + type;
      const object = gltf.scene.getObjectByName(name);
      if (!object) throw new Error(`В GLB отсутствует объект ${name}`);
      const clone = object.clone(true);
      clone.traverse((node) => {
        if (node instanceof THREE.Mesh) {
          node.geometry = node.geometry.clone();
          node.material = Array.isArray(node.material) ? node.material.map(m => m.clone()) : node.material.clone();
          node.castShadow = node.receiveShadow = true;
        }
      });
      clone.position.set(0, 0, 0);
      const box = new THREE.Box3().setFromObject(clone), size = box.getSize(new THREE.Vector3());
      if (Math.max(size.x,size.z) <= 0) throw new Error("Пустая геометрия GLB");
      const scale = .75 / Math.max(size.x,size.z);
      const holder = new THREE.Group(); holder.add(clone);
      clone.position.sub(box.getCenter(new THREE.Vector3()));
      clone.position.y += size.y / 2;
      holder.scale.setScalar(scale);
      models[name] = holder;
    }
    for (const model of Object.values(this.imported)) this.clear(model as THREE.Group);
    this.imported = models;
    this.shape = "glb"; this.rebuild();
  }
  private makePiece(type: PieceSymbol, color: Color) {
    if (this.mode === "2d") {
      const key = color + type.toUpperCase();
      let texture = this.textures.get(key);
      if (!texture) {
        texture = new THREE.TextureLoader().load(`/pieces/cburnett/${key}.svg`);
        texture.colorSpace = THREE.SRGBColorSpace;
        this.textures.set(key, texture);
      }
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(.88,.88), new THREE.MeshBasicMaterial({ map: texture, transparent: true }));
      mesh.rotation.x = -Math.PI / 2;
      const group = new THREE.Group(); group.add(mesh); return group;
    }
    const key = color + type.toUpperCase();
    if (this.shape === "glb" && this.imported[key]) {
      const object = this.imported[key].clone(true);
      object.traverse((node) => {
        if (node instanceof THREE.Mesh) {
          node.geometry = node.geometry.clone();
          node.material = Array.isArray(node.material) ? node.material.map(m => m.clone()) : node.material.clone();
        }
      });
      return object;
    }
    const object = piece(type, color);
    const colors = this.theme === "marble" ? [0xf3f1eb,0x202126] : this.theme === "walnut" ? [0xcfa66b,0x342418] : [0xeadcc3,0x333b39];
    object.traverse(node => {
      if (node instanceof THREE.Mesh) (node.material as THREE.MeshStandardMaterial).color.setHex(colors[color === "w" ? 0 : 1]);
    });
    if (this.shape === "slim") object.scale.set(.8,1.2,.8);
    return object;
  }
  home() {
    const damping = this.controls.enableDamping;
    this.controls.enableDamping = false;
    this.controls.update(); // Consume the remaining drag before restoring the view.
    this.camera.up.set(0, this.mode === "2d" ? 0 : 1, this.mode === "2d" ? -1 : 0);
    if (this.mode === "2d") this.camera.position.set(0,16,0.001);
    else this.camera.position.set(9, 11, 13);
    this.controls.target.set(0, 0.2, 0);
    if (this.mode === "3d") this.controls.update();
    else this.camera.lookAt(this.controls.target);
    this.controls.enableDamping = damping;
  }
  private clear(group: THREE.Group) {
    group.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
        object.geometry.dispose();
        const materials = Array.isArray(object.material)
          ? object.material
          : [object.material];
        materials.forEach((m) => m.dispose());
      }
    });
    group.clear();
  }
  showAdvice(uci: string | null) {
    this.clear(this.advice);
    this.adviceFen = null;
    delete this.renderer.domElement.dataset.adviceMove;
    if (!uci) return;
    const move = this.chess.moves({ verbose: true }).find(m => m.from + m.to + (m.promotion || "") === uci);
    if (!move) return;
    this.adviceFen = this.chess.fen();
    this.renderer.domElement.dataset.adviceMove = uci;
    for (const [square, color] of [[move.from, 0x28b4ff], [move.to, 0x44df83]] as const) {
      const tile = new THREE.Mesh(
        new THREE.PlaneGeometry(.94, .94),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .55, depthWrite: false }),
      );
      tile.rotation.x = -Math.PI / 2;
      tile.position.set(square.charCodeAt(0) - 100.5, .025, 4.5 - Number(square[1]));
      this.advice.add(tile);
      const outline = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(-.47, 0, -.47), new THREE.Vector3(.47, 0, -.47),
          new THREE.Vector3(.47, 0, .47), new THREE.Vector3(-.47, 0, .47),
        ]),
        new THREE.LineBasicMaterial({ color }),
      );
      outline.position.copy(tile.position).add(new THREE.Vector3(0, .001, 0));
      this.advice.add(outline);
    }
  }
  rebuild() {
    if (this.adviceFen !== this.chess.fen()) this.showAdvice(null);
    this.clear(this.pieces);
    this.clear(this.markers);
    this.selected = null;
    for (const row of this.chess.board())
      for (const p of row)
        if (p) {
          const mesh = this.makePiece(p.type, p.color);
          mesh.position.set(
            p.square.charCodeAt(0) - 97 - 3.5,
            0.035,
            3.5 - (Number(p.square[1]) - 1),
          );
          mesh.userData.square = p.square;
          this.pieces.add(mesh);
        }
    this.onChange();
  }
  private choose(square: Square) {
    const p = this.chess.get(square);
    if (this.selected) {
      try {
        this.chess.move({
          from: this.selected,
          to: square,
          promotion: this.promotion,
        });
        this.rebuild();
        this.onMessage("Ход выполнен");
        return;
      } catch {
        /* Another own piece selects it below. */
      }
    }
    this.clear(this.markers);
    this.selected = null;
    if (p?.color !== this.chess.turn()) {
      this.onMessage("Выберите фигуру стороны, чей сейчас ход");
      return;
    }
    this.selected = square;
    for (const move of this.chess.moves({ square, verbose: true })) {
      const marker = new THREE.Mesh(
        new THREE.CylinderGeometry(0.12, 0.12, 0.02, 24),
        new THREE.MeshBasicMaterial({ color: 0xd9aa46 }),
      );
      marker.position.set(
        move.to.charCodeAt(0) - 100.5,
        0.06,
        4.5 - Number(move.to[1]),
      );
      this.markers.add(marker);
    }
    this.onMessage(
      `Выбрано ${square.toUpperCase()} · нажмите на клетку назначения`,
    );
  }
  render() {
    if (this.mode === "3d") this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
  async snapshot() {
    // Never render a hint-free frame into the visible canvas. Restore scene
    // state synchronously, before bitmap decoding or the next animation frame.
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    if (!size.x || !size.y) throw new Error("Cannot capture an empty viewport");
    // The encoder sends 960x720; do not allocate display-resolution HDR/MSAA
    // buffers on high-DPI monitors just to downscale them immediately afterward.
    const scale = Math.min(1, 960 / size.x, 720 / size.y);
    const width = Math.max(1, Math.round(size.x * scale));
    const height = Math.max(1, Math.round(size.y * scale));
    if (!this.captureScene) {
      this.captureScene = new THREE.WebGLRenderTarget(width, height, {
        type: THREE.HalfFloatType,
        samples: Math.min(4, this.renderer.capabilities.maxSamples),
      });
      this.captureOutput = new THREE.WebGLRenderTarget(width, height, { depthBuffer: false });
      this.capturePass = new OutputPass();
    }
    const output = this.captureOutput!;
    this.captureScene.setSize(width, height);
    output.setSize(width, height);
    if (this.capturePixels.length !== width * height * 4) {
      this.capturePixels = new Uint8Array(width * height * 4);
    }
    const target = this.renderer.getRenderTarget();
    const markersVisible = this.markers.visible, adviceVisible = this.advice.visible;
    try {
      this.markers.visible = this.advice.visible = false;
      this.renderer.setRenderTarget(this.captureScene);
      this.renderer.render(this.scene, this.camera);
      // Render targets are linear HDR: apply the display's tone mapping and
      // sRGB conversion explicitly before reading 8-bit pixels for YOLO.
      this.capturePass!.render(this.renderer, output, this.captureScene, 0, false);
      this.renderer.readRenderTargetPixels(output, 0, 0, width, height, this.capturePixels);
    } finally {
      this.markers.visible = markersVisible;
      this.advice.visible = adviceVisible;
      this.renderer.setRenderTarget(target);
    }
    // WebGL's origin is bottom-left; ImageData's is top-left. Each snapshot
    // owns its pixels, so simultaneous stream/export requests cannot overwrite it.
    const image = new ImageData(width, height);
    const rowBytes = width * 4;
    for (let row = 0; row < height; row++) {
      const offset = (height - row - 1) * rowBytes;
      image.data.set(this.capturePixels.subarray(offset, offset + rowBytes), row * rowBytes);
    }
    return createImageBitmap(image);
  }
}
