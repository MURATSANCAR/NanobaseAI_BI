import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { PaperFinish } from './api';

/** 3B kitap sahnesi (yalnız bu ekranda, kod bölmeyle yüklenir). Birim milimetre; kitap y ekseni yukarıda, ön kapak
 *  kameraya (+z) bakar. Sırt (cilt) çizgisi gövdenin x=0 noktasındadır; kapalı kitap x∈[0, tw], açık kitapta sol yığın
 *  x∈[−tw, 0], sağ yığın x∈[0, tw].
 *
 *  Kalınlık gerçek: yaprak sayısı × kâğıt kalınlığı + iki kapak kartonu. Açıkken iki sayfa yığını (sol: çevrilmiş
 *  yapraklar, sağ: kalanlar) ve çevrilen tek yaprak çizilir; yaprak kıvrılarak döner (uç kısmı gövdeden geride kalır).
 *
 *  Hareket: kapak açılışı, sayfa çevirme ve kamera geçişi açıklayıcı hareket (satış/kurul sunumu, seyrek) — güçlü
 *  ease-in-out; sunum modunda doğrusal yavaş dönüş. `reduceMotion` ya da klavyeyle çevirmede geçiş anlıktır.
 *  Sahne yalnız bir şey değişince çizilir (fare/dokunma, animasyon, doku yüklenmesi); boşta GPU çalışmaz. */

export type BookDims = {
  trimW: number;
  trimH: number;
  bleed: number;
  pages: number;
  caliper: number;
  board: number;
  /** Kapak açılımı: genişlik (mm) ve sırt (tel dikişte 0). null → kapak henüz yok. */
  cover: { width: number; spine: number } | null;
};
export type BookLook = { white: string; finish: PaperFinish | 'screen' };
export type BookState = { open: boolean; spread: number; spreads: number; busy: boolean };

// Güçlü ease-in-out (ekranda yer değiştiren hareket): cubic-bezier(0.77, 0, 0.175, 1).
const easeInOut = bezier(0.77, 0, 0.175, 1);
const COVER_MS = 900;
const FLIP_MS = 720;
const CAMERA_MS = 900;
const SPIN_PERIOD_S = 24;          // sunumda bir tam tur
const SWAY_PERIOD_S = 14;          // açık kitapta hafif salınım
const SEGMENTS = 36;               // çevrilen yaprağın kıvrım dilimi
const ROUGH: Record<BookLook['finish'], number> = { gloss: 0.34, matte: 0.78, uncoated: 0.92, screen: 0.6 };

type Tween = { from: number; to: number; start: number; ms: number; done?: () => void };
type Flip = { dir: 1 | -1; start: number; ms: number; from: number };

export class BookScene {
  readonly canvas: HTMLCanvasElement;
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(30, 1, 1, 8000);
  private controls: OrbitControls;
  private root = new THREE.Group();        // döner (sunum), kitabın görünen merkezi orijinde
  private body = new THREE.Group();        // sırt çizgisi x=0
  private backBoard: THREE.Mesh;
  private frontPivot = new THREE.Group();
  private frontBoard: THREE.Mesh;
  private spine: THREE.Mesh;
  private left: THREE.Mesh;
  private right: THREE.Mesh;
  private leafPivot = new THREE.Group();
  private leafFront: THREE.Mesh;
  private leafBack: THREE.Mesh;
  private leafGeo: THREE.PlaneGeometry;
  private shadow: THREE.Mesh;
  private loader = new THREE.TextureLoader();
  private textures = new Map<string, TexEntry>();
  private tokens: Record<string, number> = {};
  private pageUrl: ((n: number) => string) | null = null;
  private coverUrl: string | null = null;
  private look: BookLook = { white: '#ffffff', finish: 'screen' };
  private mats: Record<string, THREE.MeshStandardMaterial> = {};
  private edgeU: THREE.CanvasTexture;
  private edgeV: THREE.CanvasTexture;
  private raf = 0;
  private dirty = true;
  private wakeUntil = 0;
  private last = 0;
  private openT = 0;                        // 0 kapalı, 1 açık
  private openTween: Tween | null = null;
  private camTween: { from: THREE.Vector3; to: THREE.Vector3; rotFrom: number; rotTo: number; start: number; ms: number } | null = null;
  private flip: Flip | null = null;
  private spread = 0;                       // çevrilmiş yaprak sayısı (0 = ilk sayfa sağda)
  private spin = false;
  private spinClock = 0;
  private recording: { start: number; ms: number; base: number; open: boolean } | null = null;
  private ro: ResizeObserver;
  private down: { x: number; y: number; t: number } | null = null;
  private raycaster = new THREE.Raycaster();
  private disposed = false;

  constructor(private host: HTMLElement, private dims: BookDims, private reduceMotion: boolean,
              private onState: (s: BookState) => void) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.canvas = this.renderer.domElement;
    this.canvas.removeAttribute('data-engine');       // ekrana giden işaretlemede teknoloji adı olmasın
    this.canvas.style.display = 'block';
    this.canvas.style.width = '100%';
    this.canvas.style.height = '100%';
    host.appendChild(this.canvas);

    // Işık: yüzü kameraya dönük sayfada doku rengi korunur (ortam + ana ışık ≈ π); arka ışık dönerken arka kapağı
    // karanlıkta bırakmaz. Parlak kâğıtta ana ışığın yansıması görünür.
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.68 * Math.PI));
    const key = new THREE.DirectionalLight(0xffffff, 0.34 * Math.PI);
    key.position.set(260, 380, 700);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(0xffffff, 0.22 * Math.PI);
    rim.position.set(-300, 120, -600);
    this.scene.add(rim);

    this.edgeU = edgeTexture(true);
    this.edgeV = edgeTexture(false);
    const { trimW: tw, trimH: th, board } = dims;
    const m = (name: string, color = '#ffffff', rough = 0.6) =>
      (this.mats[name] = new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0 }));

    // Kapak kartonları: ön (dönen menteşe) ve arka. Kenarlar kartonun açık rengi.
    const boardGeo = new THREE.BoxGeometry(tw, th, board);
    const edge = m('boardEdge', '#e9e4da', 0.8);
    this.backBoard = new THREE.Mesh(boardGeo, [edge, edge, edge, edge, m('backInside', '#f7f5f0', 0.85), m('back', '#dcd6ca', 0.5)]);
    this.backBoard.position.set(tw / 2, 0, board / 2);
    this.frontBoard = new THREE.Mesh(boardGeo, [edge, edge, edge, edge, m('front', '#dcd6ca', 0.5), m('frontInside', '#f7f5f0', 0.85)]);
    this.frontBoard.position.set(tw / 2, 0, board / 2);
    this.frontPivot.add(this.frontBoard);

    // Sırt: normali −x; doku u'su arkadan öne (+z).
    const spineGeo = new THREE.PlaneGeometry(1, th);
    spineGeo.rotateY(-Math.PI / 2);
    this.spine = new THREE.Mesh(spineGeo, m('spine', '#cfc8ba', 0.5));

    // Sayfa yığınları: üst yüz sayfanın dokusu, kenarlar çizgili kâğıt.
    const stack = (top: string, side: string) => {
      const g = new THREE.BoxGeometry(1, 1, 1);
      const eU = m(`${side}EdgeU`, '#ffffff', 0.9);
      const eV = m(`${side}EdgeV`, '#ffffff', 0.9);
      eU.map = this.edgeU.clone();
      eV.map = this.edgeV.clone();
      const paper = m(`${side}Under`, '#ffffff', 0.9);
      return new THREE.Mesh(g, [eU, paper, eV, eV, m(top, '#ffffff', 0.6), paper]);
    };
    this.right = stack('rightTop', 'r');
    this.left = stack('leftTop', 'l');
    // Solda yığının dış kenarı −x yüzüdür.
    (this.left.material as THREE.Material[])[0] = this.mats.lUnder;
    (this.left.material as THREE.Material[])[1] = this.mats.lEdgeU;

    // Çevrilen yaprak: aynı geometri iki yüz (ön = tek sayfa, arka = çift sayfa, arka doku yatay çevrik).
    this.leafGeo = new THREE.PlaneGeometry(tw, th, SEGMENTS, 1);
    this.leafGeo.translate(tw / 2, 0, 0);
    this.leafFront = new THREE.Mesh(this.leafGeo, m('leafFront', '#ffffff', 0.6));
    this.leafBack = new THREE.Mesh(this.leafGeo, m('leafBack', '#ffffff', 0.6));
    this.mats.leafFront.side = THREE.FrontSide;
    this.mats.leafBack.side = THREE.BackSide;
    this.leafPivot.add(this.leafFront, this.leafBack);
    this.leafPivot.visible = false;

    // Yumuşak zemin gölgesi (kitapla döner).
    const sh = shadowTexture();
    this.shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ map: sh, transparent: true, depthWrite: false, opacity: 0.55 }));
    this.shadow.rotation.x = -Math.PI / 2;
    this.shadow.position.y = -th / 2 - 0.6;

    this.body.add(this.backBoard, this.frontPivot, this.spine, this.left, this.right, this.leafPivot);
    this.root.add(this.body, this.shadow);
    this.scene.add(this.root);

    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.enablePan = false;
    this.controls.rotateSpeed = 0.7;
    this.controls.minPolarAngle = 0.12;
    this.controls.maxPolarAngle = Math.PI - 0.12;
    this.controls.addEventListener('change', () => this.invalidate());
    this.controls.addEventListener('start', () => { this.wakeUntil = Infinity; this.invalidate(); });
    this.controls.addEventListener('end', () => { this.wakeUntil = performance.now() + 1500; this.invalidate(); });
    this.canvas.addEventListener('pointerdown', this.onDown);
    this.canvas.addEventListener('pointerup', this.onUp);

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(host);
    this.resize();
    this.layout();
    this.placeCamera(false);
    this.emit();
  }

  // ---------------------------------------------------------------- dışa açık
  get spreads() { return Math.ceil(this.dims.pages / 2); }
  get isOpen() { return this.openT > 0.5; }

  /** Kâğıt görünümü ve doku adresleri (kâğıt değişince bütün dokular yenilenir). */
  setSource(look: BookLook, pageUrl: (n: number) => string, coverUrl: string | null) {
    const changed = look.white !== this.look.white || look.finish !== this.look.finish;
    this.look = look;
    this.pageUrl = pageUrl;
    this.coverUrl = coverUrl;
    if (changed) {
      const rough = ROUGH[look.finish];
      for (const k of ['rightTop', 'leftTop', 'leafFront', 'leafBack']) this.mats[k].roughness = rough;
      for (const k of ['rEdgeU', 'rEdgeV', 'lEdgeU', 'lEdgeV', 'rUnder', 'lUnder', 'frontInside', 'backInside']) this.mats[k].color.set(look.white);
    }
    this.applyCover();
    this.applyPages();
    this.invalidate();
  }

  /** Kâğıt değişince kalınlık değişir (yaprak × kâğıt kalınlığı); sırt dokusu da buna göre kırpılır. */
  setCaliper(caliper: number) {
    if (caliper === this.dims.caliper) return;
    this.dims = { ...this.dims, caliper };
    this.layout();
    this.applyCover();
    this.invalidate();
  }

  setOpen(open: boolean, animate = true) {
    if (this.recording) return;
    if (!open && this.spread > 0) this.finishFlip();
    if (!open) this.spread = 0;
    const to = open ? 1 : 0;
    this.applyPages();
    if (!animate || this.reduceMotion) {
      this.openTween = null;
      this.openT = to;
      this.layout();
      this.placeCamera(false);
    } else {
      this.openTween = { from: this.openT, to, start: performance.now(), ms: COVER_MS * Math.abs(to - this.openT) || 1 };
      this.placeCamera(true);
    }
    this.emit();
    this.invalidate();
  }

  /** Sonraki (+1) / önceki (−1) açılım. Sürmekte olan çevirme varsa önce o biter (tıklama sırası kaybolmaz). */
  turn(dir: 1 | -1, animate = true) {
    if (this.recording) return;
    if (!this.isOpen) { if (dir > 0) this.setOpen(true, animate); return; }
    // Çevirme sürerken yeni istek: süren yaprak yerine oturur, yenisi daha çabuk döner (art arda çevirme gecikmesin).
    const chained = !!this.flip;
    this.finishFlip();
    const to = this.spread + dir;
    if (to < 0 || to > this.spreads) return;
    if (!animate || this.reduceMotion) {
      this.spread = to;
      this.applyPages();
      this.layout();
    } else {
      this.flip = { dir, start: performance.now(), ms: chained ? FLIP_MS * 0.55 : FLIP_MS, from: this.spread };
      this.applyPages();
    }
    this.emit();
    this.invalidate();
  }

  goTo(spread: number) {
    if (this.recording) return;
    this.finishFlip();
    this.spread = Math.max(0, Math.min(this.spreads, Math.round(spread)));
    if (!this.isOpen) { this.openT = 1; this.openTween = null; this.placeCamera(false); }
    this.applyPages();
    this.layout();
    this.emit();
    this.invalidate();
  }

  setSpin(on: boolean) {
    this.spin = on && !this.reduceMotion;
    this.spinClock = 0;
    this.invalidate();
  }

  resetView() {
    this.placeCamera(!this.reduceMotion);
    this.invalidate();
  }

  /** Şeffaf zeminli PNG (ekrandakinin `scale` katı çözünürlükte). */
  async png(scale = 2): Promise<Blob> {
    const pr = this.renderer.getPixelRatio();
    this.renderer.setPixelRatio(pr * scale);
    this.renderer.render(this.scene, this.camera);
    const blob = await new Promise<Blob | null>((res) => this.canvas.toBlob(res, 'image/png'));
    this.renderer.setPixelRatio(pr);
    this.invalidate();
    if (!blob) throw new Error('Görüntü alınamadı');
    return blob;
  }

  /** Kısa dönen video (kapalı kitapta tam tur, açıkta hafif salınım). Tarayıcının kaydedicisiyle; zemin düz renk. */
  async video(seconds: number, background: string, onProgress: (p: number) => void): Promise<{ blob: Blob; ext: string }> {
    const types = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4'];
    const type = types.find((t) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t));
    if (!type || !this.canvas.captureStream) throw new Error('Bu tarayıcı video kaydı desteklemiyor');
    this.finishFlip();
    const { width, height } = this.host.getBoundingClientRect();
    const W = 1280;
    const H = Math.round((W * Math.max(1, height)) / Math.max(1, width) / 2) * 2;
    const pr = this.renderer.getPixelRatio();
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(W, H, false);
    this.camera.aspect = W / H;
    this.camera.updateProjectionMatrix();
    this.scene.background = new THREE.Color(background);
    const stream = this.canvas.captureStream(30);
    const rec = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 8_000_000 });
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    const stopped = new Promise<void>((res) => { rec.onstop = () => res(); });
    const ms = seconds * 1000;
    this.recording = { start: performance.now(), ms, base: this.root.rotation.y, open: this.isOpen };
    rec.start(250);
    this.invalidate();
    await new Promise<void>((res) => {
      const tick = () => {
        if (this.disposed) return res();
        const p = Math.min(1, (performance.now() - (this.recording?.start ?? 0)) / ms);
        onProgress(p);
        if (p >= 1) return res();
        setTimeout(tick, 100);
      };
      tick();
    });
    rec.stop();
    await stopped;
    stream.getTracks().forEach((t) => t.stop());
    if (this.recording) this.root.rotation.y = this.recording.base;
    this.recording = null;
    this.scene.background = null;
    this.renderer.setPixelRatio(pr);
    this.resize();
    const mime = type.split(';')[0];
    return { blob: new Blob(chunks, { type: mime }), ext: mime === 'video/mp4' ? 'mp4' : 'webm' };
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    this.canvas.removeEventListener('pointerdown', this.onDown);
    this.canvas.removeEventListener('pointerup', this.onUp);
    this.controls.dispose();
    this.textures.forEach((e) => e.base.dispose());
    this.textures.clear();
    this.scene.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const mats = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : [];
      mats.forEach((mt) => { (mt as THREE.MeshStandardMaterial).map?.dispose(); mt.dispose(); });
    });
    this.renderer.dispose();
    this.canvas.remove();
  }

  // ---------------------------------------------------------------- çizim döngüsü
  invalidate() {
    this.dirty = true;
    if (!this.raf && !this.disposed) this.raf = requestAnimationFrame(this.loop);
  }

  private loop = (now: number) => {
    this.raf = 0;
    const dt = this.last ? Math.min(0.1, (now - this.last) / 1000) : 0;
    this.last = now;
    let active = false;

    if (this.openTween) {
      const tw = this.openTween;
      const p = Math.min(1, (now - tw.start) / tw.ms);
      this.openT = tw.from + (tw.to - tw.from) * easeInOut(p);
      if (p >= 1) { this.openTween = null; this.openT = tw.to; this.emit(); }
      active = true;
    }
    if (this.flip) {
      const p = Math.min(1, (now - this.flip.start) / this.flip.ms);
      if (p >= 1) this.finishFlip(); else active = true;
    }
    if (this.camTween) {
      const c = this.camTween;
      const p = Math.min(1, (now - c.start) / c.ms);
      const e = easeInOut(p);
      this.camera.position.lerpVectors(c.from, c.to, e);
      this.root.rotation.y = c.rotFrom + (c.rotTo - c.rotFrom) * e;
      this.controls.target.set(0, 0, 0);
      if (p >= 1) this.camTween = null;
      active = true;
    }
    if (this.recording) {
      const r = this.recording;
      const p = Math.min(1, (now - r.start) / r.ms);
      this.root.rotation.y = r.base + (r.open ? 0.42 * Math.sin(p * Math.PI * 2) : p * Math.PI * 2);
      active = true;
    } else if (this.spin && !this.camTween) {
      this.spinClock += dt;
      if (this.isOpen) this.root.rotation.y = 0.35 * Math.sin((this.spinClock / SWAY_PERIOD_S) * Math.PI * 2);
      else this.root.rotation.y += (dt / SPIN_PERIOD_S) * Math.PI * 2;
      active = true;
    }
    if (active) this.layout();
    const moved = this.controls.update();
    if (active || moved || this.dirty) {
      this.renderer.render(this.scene, this.camera);
      this.dirty = false;
    }
    if (active || moved || now < this.wakeUntil) this.raf = requestAnimationFrame(this.loop);
    else this.last = 0;
  };

  // ---------------------------------------------------------------- yerleşim
  private thickness() { return this.dims.caliper * this.spreads; }

  /** Her karede: kapak açıklığı, yığın kalınlıkları ve çevrilen yaprağın kıvrımı. */
  private layout() {
    const { trimW: tw, trimH: th, board, caliper: c } = this.dims;
    const L = this.spreads;
    const e = this.openT;
    const T = this.thickness();
    const flip = this.flip;
    const fp = flip ? easeInOut(Math.min(1, (performance.now() - flip.start) / flip.ms)) : 0;
    const leftN = flip ? (flip.dir > 0 ? flip.from : flip.from - 1) : this.spread;
    const rightN = flip ? (flip.dir > 0 ? L - flip.from - 1 : L - flip.from) : L - this.spread;

    // Görünen merkez orijinde: kapalıyken kitabın ortası, açıkken sırt çizgisi.
    this.body.position.set(-(tw / 2) * (1 - e), 0, -(((T + 2 * board) / 2) * (1 - e) + board * e));

    // Ön kapak: sırt çizgisinde menteşe; kapalıyken yığının üstünde, açıkken solda masada.
    this.frontPivot.position.set(0, 0, board + T + (board - (board + T)) * e);
    this.frontPivot.rotation.y = -Math.PI * e;

    // Sırt: kitap açıldıkça altta düzleşir.
    const sw = Math.max(0.2, (T + 2 * board) * (1 - e) + board * e);
    this.spine.scale.set(sw, 1, 1);
    this.spine.position.set(0, 0, sw / 2);
    this.spine.visible = e < 0.98;

    const place = (mesh: THREE.Mesh, n: number, side: 1 | -1) => {
      const h = Math.max(0.05, n * c);
      mesh.visible = n > 0 && (side > 0 || e > 0.02);
      mesh.scale.set(tw - 0.3, th - 0.6, h);
      mesh.position.set(side * (tw / 2), 0, board + h / 2);
      const mats = mesh.material as THREE.MeshStandardMaterial[];
      const rep = Math.max(1, n / 4);
      for (const mt of mats) if (mt.map && (mt.map as THREE.CanvasTexture).isCanvasTexture) {
        const t = mt.map;
        if (mt === this.mats.rEdgeU || mt === this.mats.lEdgeU) t.repeat.set(rep, 1); else t.repeat.set(1, rep);
      }
    };
    // Kapalı kitapta sol yığın yoktur; sağ yığın bütün yapraklar (sağ üst yüz ilk sayfa, kapağın altında).
    place(this.right, rightN, 1);
    place(this.left, leftN, -1);

    this.leafPivot.visible = !!flip;
    if (flip) {
      const t = flip.dir > 0 ? fp : 1 - fp;       // 0 sağda düz, 1 solda düz
      const zR = board + (L - flip.from - (flip.dir > 0 ? 0 : -1)) * c;
      const zL = board + (flip.dir > 0 ? flip.from + 1 : flip.from) * c;
      this.leafPivot.position.set(0, 0, zR + (zL - zR) * t);
      curl(this.leafGeo, tw, t);
    }
    this.shadow.scale.set((tw + 24) * (1 + e), T + 2 * board + 40 + 60 * e, 1);
    this.shadow.position.x = 0;
  }

  private finishFlip() {
    if (!this.flip) return;
    this.spread = this.flip.from + this.flip.dir;
    this.flip = null;
    this.applyPages();
    this.layout();
    this.emit();
  }

  private emit() {
    this.onState({ open: this.openTween ? this.openTween.to === 1 : this.isOpen, spread: this.spread,
                   spreads: this.spreads, busy: !!(this.flip || this.openTween || this.recording) });
  }

  // ---------------------------------------------------------------- kamera
  private fit(open: boolean) {
    const { trimW: tw, trimH: th, board } = this.dims;
    const half = THREE.MathUtils.degToRad(this.camera.fov / 2);
    const t = Math.tan(half);
    // Açık kitap: iki sayfa yan yana; sunumdaki salınımda yakın kenar büyüdüğü için pay geniş.
    if (open) return Math.max(th / 2 / t, tw / (t * this.camera.aspect)) * 1.3;
    // Kapalı kitap her yöne dönebilir: çevreleyen küre kadraja sığar (kenar kameraya dönünce de kesilmez).
    const r = Math.hypot(tw / 2, th / 2, this.thickness() / 2 + board);
    const halfH = Math.atan(t * this.camera.aspect);
    return Math.max(r / Math.sin(half), r / Math.sin(halfH)) * 1.06;
  }

  private placeCamera(animate: boolean) {
    const open = this.openTween ? this.openTween.to === 1 : this.openT > 0.5;
    const d = this.fit(open);
    // Açık kitap hafif yukarıdan: çevrilen yaprağın kıvrımı görünsün; kapalı kitap sırtı da gösteren açıdan.
    const az = open ? -0.12 : -0.5, el = open ? 0.36 : 0.16;
    const to = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)).multiplyScalar(d);
    this.controls.minDistance = d * 0.45;
    this.controls.maxDistance = d * 3;
    // Dönüş en yakın tam tura geri gelir (sunumdan çıkıp kitabı açınca ters dönmesin).
    const rot = this.root.rotation.y;
    const rotTo = Math.round(rot / (Math.PI * 2)) * Math.PI * 2;
    if (!animate || this.reduceMotion) {
      this.camTween = null;
      this.camera.position.copy(to);
      this.root.rotation.y = rotTo;
      this.controls.target.set(0, 0, 0);
      this.controls.update();
    } else {
      this.camTween = { from: this.camera.position.clone(), to, rotFrom: rot, rotTo, start: performance.now(), ms: CAMERA_MS };
    }
  }

  private resize() {
    if (this.recording) return;
    const { width, height } = this.host.getBoundingClientRect();
    if (!width || !height) return;
    const open = this.openTween ? this.openTween.to === 1 : this.openT > 0.5;
    const before = this.fit(open);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    // Alan değişince (telefon döndü, tam ekran) kitap kadraja yeniden sığar; kullanıcının yakınlaştırması oranla korunur.
    const k = this.fit(open) / before;
    if (Number.isFinite(k) && Math.abs(k - 1) > 1e-3) {
      this.camera.position.multiplyScalar(k);
      if (this.camTween) this.camTween.to.multiplyScalar(k);
      this.controls.minDistance *= k;
      this.controls.maxDistance *= k;
      this.controls.update();
    }
    this.invalidate();
  }

  // ---------------------------------------------------------------- dokunuş: sayfaya tıklayınca çevir
  private onDown = (e: PointerEvent) => { this.down = { x: e.clientX, y: e.clientY, t: performance.now() }; };

  private onUp = (e: PointerEvent) => {
    const d = this.down;
    this.down = null;
    if (!d || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 6 || performance.now() - d.t > 500) return;
    const r = this.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const hit = this.raycaster.intersectObject(this.body, true)[0];
    if (!hit) return;
    if (!this.isOpen) { this.setOpen(true); return; }
    const local = this.body.worldToLocal(hit.point.clone());
    this.turn(local.x >= 0 ? 1 : -1);
  };


  // ---------------------------------------------------------------- dokular
  /** Görüntü bir kez indirilir; aynı görüntünün bölgeleri (sayfanın kırpılmış hâli, kapağın ön/arka/sırtı) GPU'da
   *  aynı kaynağı paylaşır. Doku yüklenene kadar yüzey kâğıt rengindedir (eski sayfa görünmez). */
  private load(url: string, fn?: (base: THREE.Texture) => void) {
    let e = this.textures.get(url);
    if (!e) {
      const entry: TexEntry = { base: null as unknown as THREE.Texture, ready: false, waiters: [] };
      entry.base = this.loader.load(url, () => {
        entry.ready = true;
        entry.waiters.splice(0).forEach((f) => f(entry.base));
        this.invalidate();
      }, undefined, () => { entry.waiters.length = 0; });
      entry.base.colorSpace = THREE.SRGBColorSpace;
      this.textures.set(url, (e = entry));
    }
    if (fn) { if (e.ready) fn(e.base); else e.waiters.push(fn); }
    return e;
  }

  private assign(name: string, r: Region | null) {
    const token = (this.tokens[name] = (this.tokens[name] ?? 0) + 1);
    if (!r) { this.setMap(name, null); return; }
    const e = this.load(r.url);
    if (!e.ready) this.setMap(name, null);
    this.load(r.url, (base) => {
      if (this.tokens[name] !== token || this.disposed) return;
      const t = base.clone();
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
      t.wrapS = THREE.RepeatWrapping;
      t.repeat.set(r.mirror ? -(r.x1 - r.x0) : r.x1 - r.x0, r.y1 - r.y0);
      t.offset.set(r.mirror ? r.x1 : r.x0, r.y0);
      t.needsUpdate = true;
      this.setMap(name, t);
      this.invalidate();
    });
  }

  private setMap(name: string, t: THREE.Texture | null) {
    const mt = this.mats[name];
    if (mt.map && mt.map !== t) mt.map.dispose();
    mt.map = t;
    mt.color.set(t ? '#ffffff' : this.look.white);
    mt.needsUpdate = true;
  }

  private page(n: number, mirror = false): Region | null {
    if (n < 1 || n > this.dims.pages) return null;
    const { trimW: tw, trimH: th, bleed: b } = this.dims;
    const W = tw + 2 * b, H = th + 2 * b;
    return { url: this.pageUrl!(n), x0: b / W, x1: (b + tw) / W, y0: b / H, y1: (b + th) / H, mirror };
  }

  private applyPages() {
    if (!this.pageUrl) return;
    const f = this.flip;
    const s = f ? f.from : this.spread;
    if (f && f.dir > 0) {
      this.assign('leafFront', this.page(2 * s + 1));
      this.assign('leafBack', this.page(2 * s + 2, true));
      this.assign('rightTop', this.page(2 * s + 3));
      this.assign('leftTop', this.page(2 * s));
    } else if (f && f.dir < 0) {
      this.assign('leafFront', this.page(2 * s - 1));
      this.assign('leafBack', this.page(2 * s, true));
      this.assign('rightTop', this.page(2 * s + 1));
      this.assign('leftTop', this.page(2 * s - 2));
    } else {
      this.assign('rightTop', this.page(2 * s + 1));
      this.assign('leftTop', this.page(2 * s));
    }
    // Komşu açılımlar önceden indirilir: çevirmede boş sayfa görünmesin.
    for (const n of [2 * s - 2, 2 * s - 1, 2 * s + 2, 2 * s + 3, 2 * s + 4, 2 * s + 5]) {
      if (n >= 1 && n <= this.dims.pages) this.load(this.pageUrl!(n));
    }
    this.trimTextures();
  }

  private applyCover() {
    const cv = this.dims.cover;
    const url = this.coverUrl;
    if (!cv || !url) {
      for (const k of ['front', 'back', 'spine']) this.assign(k, null);
      return;
    }
    const { trimW: tw, trimH: th, bleed: b } = this.dims;
    const Wc = cv.width, Hc = th + 2 * b;
    const y0 = b / Hc, y1 = (b + th) / Hc;
    const sp = cv.spine;
    const fold = b + tw;
    const half = Math.max(0.5, (this.thickness() + 2 * this.dims.board) / 2);
    this.assign('front', { url, x0: (fold + sp) / Wc, x1: (fold + sp + tw) / Wc, y0, y1 });
    this.assign('back', { url, x0: b / Wc, x1: fold / Wc, y0, y1 });
    // Tel dikişte açılımda sırt yok: katlama çizgisinin çevresi sırt olur.
    this.assign('spine', sp > 0 ? { url, x0: fold / Wc, x1: (fold + sp) / Wc, y0, y1 }
      : { url, x0: (fold - half) / Wc, x1: (fold + half) / Wc, y0, y1 });
  }

  /** Yalnız kapak ve bulunulan açılımın çevresi bellekte tutulur; öteki görüntüler bırakılır, gerekince yeniden
   *  indirilir (tarayıcı önbelleğinden). Hiçbir sayfa erişilmez olmaz. */
  private trimTextures() {
    const keep = new Set<string>();
    if (this.coverUrl) keep.add(this.coverUrl);
    const s = this.flip ? this.flip.from : this.spread;
    for (let n = 2 * s - 4; n <= 2 * s + 7; n++) if (n >= 1 && n <= this.dims.pages && this.pageUrl) keep.add(this.pageUrl(n));
    for (const [url, e] of this.textures) if (!keep.has(url)) { e.base.dispose(); this.textures.delete(url); }
  }
}

type TexEntry = { base: THREE.Texture; ready: boolean; waiters: ((t: THREE.Texture) => void)[] };
type Region = { url: string; x0: number; x1: number; y0: number; y1: number; mirror?: boolean };

// ------------------------------------------------------------------ yardımcılar
/** Yaprağın kıvrımı: taban açısı t·π, uç kısmı çevirmenin ortasında en çok geride kalır. Dilim dilim toplanır. */
function curl(geo: THREE.PlaneGeometry, tw: number, t: number) {
  const pos = geo.attributes.position as THREE.BufferAttribute;
  const base = t * Math.PI;
  const bend = Math.sin(t * Math.PI) * 0.55;
  const cols = SEGMENTS + 1;
  const xs = new Float32Array(cols), zs = new Float32Array(cols);
  const ds = tw / SEGMENTS;
  for (let i = 1; i < cols; i++) {
    const s = (i - 0.5) / SEGMENTS;
    const a = Math.min(Math.PI, Math.max(0, base - bend * s * s));
    xs[i] = xs[i - 1] + Math.cos(a) * ds;
    zs[i] = zs[i - 1] + Math.sin(a) * ds;
  }
  for (let v = 0; v < pos.count; v++) {
    const i = v % cols;
    pos.setX(v, xs[i]);
    pos.setZ(v, zs[i] + 0.02);
  }
  pos.needsUpdate = true;
  geo.computeVertexNormals();
  geo.computeBoundingSphere();
}

/** Sayfa kenarı: ince yaprak çizgileri. `alongU`: çizgiler u yönünde değişir (sağ kenar yüzü). */
function edgeTexture(alongU: boolean): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = alongU ? 32 : 4;
  c.height = alongU ? 4 : 32;
  const g = c.getContext('2d')!;
  g.fillStyle = '#ffffff';
  g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = 'rgba(0,0,0,0.10)';
  for (let i = 0; i < 4; i++) {
    if (alongU) g.fillRect(i * 8 + 6, 0, 1, c.height);
    else g.fillRect(0, i * 8 + 6, c.width, 1);
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function shadowTexture(): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d')!;
  const r = g.createRadialGradient(64, 64, 4, 64, 64, 64);
  r.addColorStop(0, 'rgba(20,24,40,0.55)');
  r.addColorStop(0.6, 'rgba(20,24,40,0.18)');
  r.addColorStop(1, 'rgba(20,24,40,0)');
  g.fillStyle = r;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** CSS cubic-bezier ile aynı eğri (x → y, Newton + ikiye bölme). */
function bezier(x1: number, y1: number, x2: number, y2: number) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sx = (t: number) => ((ax * t + bx) * t + cx) * t;
  const sy = (t: number) => ((ay * t + by) * t + cy) * t;
  const dx = (t: number) => (3 * ax * t + 2 * bx) * t + cx;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) {
      const e = sx(t) - x;
      const d = dx(t);
      if (Math.abs(e) < 1e-5) return sy(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    let lo = 0, hi = 1;
    t = x;
    for (let i = 0; i < 30; i++) {
      const v = sx(t);
      if (Math.abs(v - x) < 1e-5) break;
      if (v < x) lo = t; else hi = t;
      t = (lo + hi) / 2;
    }
    return sy(t);
  };
}
