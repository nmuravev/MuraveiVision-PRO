/** Classify / load recon scene artifacts for Flight3D (C.3). */
import * as THREE from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d';
import { authHeaders, authToken } from '../store/useMuraveiStore';
import { SILENT_API_ERROR_HEADER } from './apiError';

export type SceneArtifactKind = 'points' | 'splat' | 'none';

export function classifyArtifact(artifact: string | null | undefined): SceneArtifactKind {
  if (!artifact) return 'none';
  const n = artifact.toLowerCase().trim();
  if (n.endsWith('.splat') || n.endsWith('.ksplat') || n === 'model.ply') return 'splat';
  if (n.endsWith('.ply')) return 'points'; // preview.ply — colored COLMAP cloud
  return 'none';
}

export function reconAssetUrl(jobId: string, name: string): string {
  const token = encodeURIComponent(authToken());
  return `/api/recon/asset/${encodeURIComponent(jobId)}/${encodeURIComponent(name)}?token=${token}`;
}

/** Fetch asset as blob URL (auth-safe for loaders that cannot set headers). */
export async function fetchAssetBlobUrl(jobId: string, name: string): Promise<string> {
  const res = await fetch(`/api/recon/asset/${encodeURIComponent(jobId)}/${encodeURIComponent(name)}`, {
    headers: {
      ...authHeaders(),
      [SILENT_API_ERROR_HEADER]: '1',
    },
  });
  if (!res.ok) {
    throw new Error(res.status === 404 ? `Файл не найден: ${name}` : `Ошибка загрузки ${name} (${res.status})`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export function disposeSceneChildren(group: THREE.Group) {
  while (group.children.length) {
    const c = group.children[0];
    group.remove(c);
    c.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const mat = mesh.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else if (mat) (mat as THREE.Material).dispose();
    });
  }
}

/** Metrics for COLMAP sparse cluster (degenerate recon detection). */
export function sparseClusterMetrics(sparse: Float32Array): {
  count: number;
  maxDim: number;
  minDim: number;
} {
  const n = sparse.length / 3;
  if (n === 0) return { count: 0, maxDim: 0, minDim: 0 };
  let minX = Infinity;
  let minY = Infinity;
  let minZ = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let maxZ = -Infinity;
  for (let i = 0; i < n; i++) {
    const x = sparse[i * 3];
    const y = sparse[i * 3 + 1];
    const z = sparse[i * 3 + 2];
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    minZ = Math.min(minZ, z);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
    maxZ = Math.max(maxZ, z);
  }
  const sx = maxX - minX;
  const sy = maxY - minY;
  const sz = maxZ - minZ;
  const maxDim = Math.max(sx, sy, sz, 0.001);
  const minDim = Math.min(sx, sy, sz);
  return { count: n, maxDim, minDim };
}

export function isSparseClusterWeak(sparse: Float32Array): boolean {
  const { count, maxDim, minDim } = sparseClusterMetrics(sparse);
  if (count < 100) return true;
  if (maxDim < 0.5) return true;
  if (minDim > 0 && maxDim / Math.max(minDim, 0.001) > 40) return true;
  return false;
}

let _discMap: THREE.CanvasTexture | null = null;

/** Soft disc sprite so points render as circles, not WebGL squares («кубики»). */
export function pointDiscTexture(): THREE.CanvasTexture {
  if (_discMap) return _discMap;
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (ctx) {
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.55, 'rgba(255,255,255,0.85)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);
  }
  _discMap = new THREE.CanvasTexture(canvas);
  _discMap.needsUpdate = true;
  return _discMap;
}

function sparsePointSize(maxDim: number, pointCount = 0): number {
  // Dense clouds look like voxels if points are too large
  const base = Math.max(0.006, Math.min(0.045, maxDim * 0.0045));
  if (pointCount > 20_000) return base * 0.55;
  if (pointCount > 5_000) return base * 0.75;
  return base;
}

/** Build Points from Float32Array xyz in COLMAP/source coordinates. */
export function pointsFromSparse(sparse: Float32Array): THREE.Points {
  const { maxDim } = sparseClusterMetrics(sparse);
  const n = Math.floor(sparse.length / 3);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(sparse, 3));
  return new THREE.Points(
    geo,
    new THREE.PointsMaterial({
      color: 0x7ab8e8,
      size: sparsePointSize(maxDim, n),
      sizeAttenuation: true,
      map: pointDiscTexture(),
      transparent: true,
      depthWrite: false,
      alphaTest: 0.05,
    }),
  );
}

/** Load ASCII/binary PLY as points, preserving COLMAP/source coordinates. */
export async function loadPlyAsPoints(url: string): Promise<THREE.Points> {
  const loader = new PLYLoader();
  const geo = await new Promise<THREE.BufferGeometry>((resolve, reject) => {
    loader.load(url, resolve, undefined, reject);
  });
  if (!geo.getAttribute('position')) {
    throw new Error('PLY без позиций');
  }
  const pos = geo.getAttribute('position') as THREE.BufferAttribute;
  const arr = pos.array as Float32Array;
  const xyz =
    pos.itemSize === 3 && arr.length === pos.count * 3
      ? arr
      : (() => {
          const out = new Float32Array(pos.count * 3);
          for (let i = 0; i < pos.count; i++) {
            out[i * 3] = pos.getX(i);
            out[i * 3 + 1] = pos.getY(i);
            out[i * 3 + 2] = pos.getZ(i);
          }
          return out;
        })();
  const { maxDim } = sparseClusterMetrics(xyz);
  const hasColor = Boolean(geo.getAttribute('color'));
  const mat = new THREE.PointsMaterial({
    size: sparsePointSize(maxDim, pos.count),
    sizeAttenuation: true,
    vertexColors: hasColor,
    color: hasColor ? 0xffffff : 0x7ab8e8,
    map: pointDiscTexture(),
    transparent: true,
    depthWrite: false,
    alphaTest: 0.05,
  });
  return new THREE.Points(geo, mat);
}

export type SplatHandle = {
  viewer: GaussianSplats3D.DropInViewer;
  blobUrl: string;
  dispose: () => void;
};

/** Load 3DGS .ply / .splat / .ksplat via DropInViewer into a Three.js group. */
export async function loadSplatDropIn(
  parent: THREE.Group,
  blobUrl: string,
  formatHint?: 'ply' | 'splat' | 'ksplat',
  three?: { camera?: THREE.Camera; renderer?: THREE.WebGLRenderer },
): Promise<SplatHandle> {
  const viewer = new GaussianSplats3D.DropInViewer({
    gpuAcceleratedSort: false,
    sharedMemoryForWorkers: false,
    ...(three?.camera ? { camera: three.camera } : {}),
    ...(three?.renderer ? { renderer: three.renderer } : {}),
  });
  const opts: GaussianSplats3D.SplatSceneOptions = {
    splatAlphaRemovalThreshold: 5,
    showLoadingUI: false,
  };
  if (formatHint === 'ply' && GaussianSplats3D.SceneFormat) {
    opts.format = GaussianSplats3D.SceneFormat.Ply;
  }
  if (formatHint === 'splat' && GaussianSplats3D.SceneFormat) {
    opts.format = GaussianSplats3D.SceneFormat.Splat;
  }
  if (formatHint === 'ksplat' && GaussianSplats3D.SceneFormat) {
    opts.format = GaussianSplats3D.SceneFormat.KSplat;
  }

  await viewer.addSplatScene(blobUrl, opts);
  parent.add(viewer);

  return {
    viewer,
    blobUrl,
    dispose: () => {
      try {
        parent.remove(viewer);
        viewer.dispose();
      } catch {
        /* ignore */
      }
      URL.revokeObjectURL(blobUrl);
    },
  };
}

export type SplatBoundsProbe = {
  ready: boolean;
  empty: boolean;
  fakeUnit: boolean;
  size: [number, number, number];
  /** True when bounds are usable for framing (non-empty, not placeholder 2³). */
  usable: boolean;
};

function isFakeUnitBox(sz: THREE.Vector3): boolean {
  return (
    Math.abs(sz.x - 2) < 0.05 && Math.abs(sz.y - 2) < 0.05 && Math.abs(sz.z - 2) < 0.05
  );
}

/** DropInViewer often reports placeholder ≈[2,2,2] — not usable for camera framing. */
export function isPlaceholderBounds(obj: THREE.Object3D): boolean {
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return true;
  return isFakeUnitBox(box.getSize(new THREE.Vector3()));
}

type OrbitLike = {
  target: THREE.Vector3;
  update: () => void;
  minDistance?: number;
  maxDistance?: number;
};

/** Dolly limits relative to content size so zoom can approach small clouds. */
export function tuneOrbitLimits(controls: OrbitLike, maxDim: number): void {
  const dim = Math.max(maxDim, 0.01);
  if (typeof controls.minDistance === 'number') {
    controls.minDistance = Math.max(dim * 0.002, 0.005);
  }
  if (typeof controls.maxDistance === 'number') {
    controls.maxDistance = Math.max(dim * 80, 20);
  }
}

export function frameObject(
  obj: THREE.Object3D,
  camera: THREE.PerspectiveCamera,
  controls: OrbitLike,
): boolean {
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return false;
  const size = box.getSize(new THREE.Vector3());
  // Reject DropInViewer placeholder [2,2,2] — framing it leaves a distant "dot"
  if (isFakeUnitBox(size)) return false;
  const maxDim = Math.max(size.x, size.y, size.z, 0.01);
  const minDim = Math.min(size.x, size.y, size.z);
  const center = box.getCenter(new THREE.Vector3());
  controls.target.copy(center);

  let camPos: THREE.Vector3;
  if (minDim / maxDim < 0.2) {
    const thinAxis = size.z === minDim ? 'z' : size.y === minDim ? 'y' : 'x';
    if (thinAxis === 'z') {
      camPos = new THREE.Vector3(center.x, center.y + maxDim * 1.4, center.z + maxDim * 0.15);
    } else if (thinAxis === 'y') {
      camPos = new THREE.Vector3(
        center.x + maxDim * 0.6,
        center.y + maxDim * 0.2,
        center.z + maxDim * 0.6,
      );
    } else {
      camPos = new THREE.Vector3(center.x + maxDim * 0.15, center.y + maxDim * 1.4, center.z);
    }
  } else {
    camPos = new THREE.Vector3(
      center.x + maxDim * 0.55,
      center.y + maxDim * 0.35,
      center.z + maxDim * 0.55,
    );
  }
  camera.position.copy(camPos);
  camera.near = Math.min(camera.near, Math.max(maxDim * 0.0005, 0.001));
  camera.far = Math.max(camera.far, maxDim * 200);
  camera.updateProjectionMatrix();
  tuneOrbitLimits(controls, maxDim);
  controls.update();
  return true;
}

/**
 * Poll DropInViewer world bounds after addSplatScene.
 * Library often reports a placeholder ≈[2,2,2] until meshes settle — wait up to maxMs.
 */
export async function probeSplatBounds(
  viewer: GaussianSplats3D.DropInViewer,
  opts?: { maxMs?: number; isStale?: () => boolean },
): Promise<SplatBoundsProbe> {
  const maxMs = opts?.maxMs ?? 15_000;
  const isStale = opts?.isStale ?? (() => false);
  const t0 = performance.now();
  let readySince: number | null = null;
  let last: SplatBoundsProbe = {
    ready: false,
    empty: true,
    fakeUnit: false,
    size: [0, 0, 0],
    usable: false,
  };

  while (performance.now() - t0 < maxMs && !isStale()) {
    await new Promise<void>((r) => requestAnimationFrame(() => r()));
    const inner = (viewer as unknown as { viewer?: { splatRenderReady?: boolean } }).viewer;
    const ready = Boolean(inner?.splatRenderReady);
    const box = new THREE.Box3().setFromObject(viewer);
    const empty = box.isEmpty();
    let size: [number, number, number] = [0, 0, 0];
    let fakeUnit = false;
    if (!empty) {
      const sz = box.getSize(new THREE.Vector3());
      size = [sz.x, sz.y, sz.z];
      fakeUnit = isFakeUnitBox(sz);
    }
    last = {
      ready,
      empty,
      fakeUnit,
      size,
      usable: !empty && !fakeUnit,
    };
    if (last.usable) break;
    if (ready) {
      if (readySince == null) readySince = performance.now();
      // Placeholder [2,2,2] often sticks after ready — don't block 15s
      if (fakeUnit && performance.now() - readySince > 3_000) break;
    }
  }

  return last;
}
