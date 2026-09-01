/** Classify / load recon scene artifacts for Flight3D (C.3). */
import * as THREE from 'three';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d';
import { authHeaders, authToken } from '../store/useMuraveiStore';

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
    headers: authHeaders(),
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

/** Build Points from Float32Array xyz in COLMAP/source coordinates. */
export function pointsFromSparse(sparse: Float32Array): THREE.Points {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(sparse, 3));
  return new THREE.Points(
    geo,
    new THREE.PointsMaterial({ color: 0x88ccff, size: 2.0, sizeAttenuation: true }),
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
  const hasColor = Boolean(geo.getAttribute('color'));
  const mat = new THREE.PointsMaterial({
    size: 2.0,
    sizeAttenuation: true,
    vertexColors: hasColor,
    color: hasColor ? 0xffffff : 0x88ccff,
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
): Promise<SplatHandle> {
  const viewer = new GaussianSplats3D.DropInViewer({
    gpuAcceleratedSort: true,
    sharedMemoryForWorkers: false,
    // Use parent scene camera/renderer via onBeforeRender of DropInViewer
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

export function frameObject(
  obj: THREE.Object3D,
  camera: THREE.PerspectiveCamera,
  controls: { target: THREE.Vector3; update: () => void },
) {
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
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
  controls.update();
}
