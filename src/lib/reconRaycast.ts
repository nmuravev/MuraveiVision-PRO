/** 2D→3D raycast math (COLMAP intrinsics, not Three.js NDC). */
import * as THREE from 'three';

export type CameraIntrinsics = {
  fx: number;
  fy: number;
  cx: number;
  cy: number;
};

export type CameraPose = {
  R: number[][];
  t: number[];
  intrinsics: CameraIntrinsics;
  image_size: { width: number; height: number };
};

export type WorldRay = {
  origin: THREE.Vector3;
  direction: THREE.Vector3;
};

type SplatHit = {
  origin: THREE.Vector3;
  point?: THREE.Vector3;
  distance: number;
  splatIndex?: number;
};

type SplatPickingViewer = {
  viewer?: {
    raycaster?: {
      ray: { origin: THREE.Vector3; direction: THREE.Vector3 };
      intersectSplatMesh: (mesh: unknown, hits: SplatHit[]) => SplatHit[];
    };
    splatMesh?: unknown;
  };
};

export function bboxCenterPixels(
  bbox: { x1: number; y1: number; x2: number; y2: number },
  imageSize: { width: number; height: number },
): { u: number; v: number } {
  const cx = ((bbox.x1 + bbox.x2) / 2) * imageSize.width;
  const cy = ((bbox.y1 + bbox.y2) / 2) * imageSize.height;
  return { u: cx, v: cy };
}

/** COLMAP: x_cam = R @ X_world + t; ray origin C = -R^T t, dir_world = R^T @ dir_cam. */
export function buildRayFromIntrinsics(pose: CameraPose, u: number, v: number): WorldRay {
  const { fx, fy, cx, cy } = pose.intrinsics;
  const xCam = (u - cx) / fx;
  const yCam = (v - cy) / fy;
  const dirLocal = new THREE.Vector3(xCam, yCam, 1).normalize();

  const R = new THREE.Matrix3().set(
    pose.R[0][0], pose.R[0][1], pose.R[0][2],
    pose.R[1][0], pose.R[1][1], pose.R[1][2],
    pose.R[2][0], pose.R[2][1], pose.R[2][2],
  );
  const Rt = R.clone().transpose();
  const t = new THREE.Vector3(pose.t[0], pose.t[1], pose.t[2]);
  const origin = t.clone().applyMatrix3(Rt).multiplyScalar(-1);
  const direction = dirLocal.applyMatrix3(Rt).normalize();
  return { origin, direction };
}

/** Fallback when splat depth-pick unavailable: nearest sparse point near ray. */
export function intersectRayWithPointCloud(
  ray: WorldRay,
  points: Float32Array | number[][],
  maxDistance = 500,
  angleThresholdDeg = 2.5,
): THREE.Vector3 | null {
  const cosTh = Math.cos((angleThresholdDeg * Math.PI) / 180);
  let best: THREE.Vector3 | null = null;
  let bestDist = Infinity;
  const count = points instanceof Float32Array ? points.length / 3 : points.length;
  for (let i = 0; i < count; i += 1) {
    let px: number;
    let py: number;
    let pz: number;
    if (points instanceof Float32Array) {
      px = points[i * 3];
      py = points[i * 3 + 1];
      pz = points[i * 3 + 2];
    } else {
      const p = points[i];
      px = p[0];
      py = p[1];
      pz = p[2];
    }
    const p = new THREE.Vector3(px, py, pz);
    const op = p.clone().sub(ray.origin);
    const dist = op.length();
    if (dist > maxDistance || dist < 1e-4) continue;
    const cosA = op.dot(ray.direction) / dist;
    if (cosA < cosTh) continue;
    const along = op.dot(ray.direction);
    if (along < 0) continue;
    const perp = op.clone().sub(ray.direction.clone().multiplyScalar(along)).length();
    const score = along + perp * 4;
    if (score < bestDist) {
      bestDist = score;
      best = p;
    }
  }
  return best;
}

export function distanceMeters(
  from: THREE.Vector3,
  to: THREE.Vector3,
  scaleMPerUnit: number | null | undefined,
): number | null {
  if (scaleMPerUnit == null || scaleMPerUnit <= 0) return null;
  return from.distanceTo(to) * scaleMPerUnit;
}

/** Azimuth degrees in scene horizontal plane; 0 = scale_direction projected on XZ. */
export function azimuthDeg(
  from: THREE.Vector3,
  to: THREE.Vector3,
  scaleDirection?: number[] | null,
): number | null {
  const dx = to.x - from.x;
  const dz = to.z - from.z;
  if (Math.hypot(dx, dz) < 1e-6) return null;
  let refX = 0;
  let refZ = -1;
  if (scaleDirection && scaleDirection.length >= 3) {
    refX = scaleDirection[0];
    refZ = scaleDirection[2];
    const len = Math.hypot(refX, refZ);
    if (len > 1e-6) {
      refX /= len;
      refZ /= len;
    }
  }
  const targetAngle = Math.atan2(dx, dz);
  const refAngle = Math.atan2(refX, refZ);
  let deg = ((targetAngle - refAngle) * 180) / Math.PI;
  if (deg < 0) deg += 360;
  return deg;
}

/** Transform a ray while preserving direction semantics (no translation on direction). */
export function transformRay(ray: WorldRay, matrix: THREE.Matrix4): WorldRay {
  return {
    origin: ray.origin.clone().applyMatrix4(matrix),
    direction: ray.direction.clone().transformDirection(matrix).normalize(),
  };
}

/**
 * Use GaussianSplats3D's own splat-tree raycaster (not THREE.Raycaster).
 * The optional scene transform maps COLMAP/source coordinates into rendered
 * world coordinates; the returned hit is mapped back into source coordinates.
 */
export function pickSplatAlongRay(
  dropInViewer: SplatPickingViewer,
  sourceRay: WorldRay,
  sceneTransform?: THREE.Matrix4,
): THREE.Vector3 | null {
  const viewer = dropInViewer.viewer;
  const raycaster = viewer?.raycaster;
  const splatMesh = viewer?.splatMesh;
  if (!raycaster || !splatMesh) return null;

  const renderedRay = sceneTransform
    ? transformRay(sourceRay, sceneTransform)
    : {
        origin: sourceRay.origin.clone(),
        direction: sourceRay.direction.clone(),
      };
  raycaster.ray.origin.copy(renderedRay.origin);
  raycaster.ray.direction.copy(renderedRay.direction);

  const hits: SplatHit[] = [];
  raycaster.intersectSplatMesh(splatMesh, hits);
  const point = hits[0]?.origin ?? hits[0]?.point;
  if (!point) return null;

  const sourcePoint = point.clone();
  if (sceneTransform) sourcePoint.applyMatrix4(sceneTransform.clone().invert());
  return sourcePoint;
}
