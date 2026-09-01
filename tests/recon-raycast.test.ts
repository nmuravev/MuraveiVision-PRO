import { expect, test } from '@playwright/test';
import * as THREE from 'three';
import {
  azimuthDeg,
  bboxCenterPixels,
  buildRayFromIntrinsics,
  distanceMeters,
  intersectRayWithPointCloud,
  transformRay,
} from '../src/lib/reconRaycast';

test('COLMAP intrinsics ray and sparse fallback share one coordinate space', () => {
  const pose = {
    R: [
      [1, 0, 0],
      [0, 1, 0],
      [0, 0, 1],
    ],
    t: [1, 2, 3],
    intrinsics: { fx: 1000, fy: 1000, cx: 960, cy: 540 },
    image_size: { width: 1920, height: 1080 },
  };
  const pixel = bboxCenterPixels(
    { x1: 0.4, y1: 0.4, x2: 0.6, y2: 0.6 },
    pose.image_size,
  );
  expect(pixel).toEqual({ u: 960, v: 540 });

  const ray = buildRayFromIntrinsics(pose, pixel.u, pixel.v);
  expect(ray.origin.toArray()).toEqual([-1, -2, -3]);
  expect(ray.direction.toArray()).toEqual([0, 0, 1]);

  const points = new Float32Array([-1, -2, 5, 10, 10, 10]);
  const hit = intersectRayWithPointCloud(ray, points);
  expect(hit?.toArray()).toEqual([-1, -2, 5]);
  expect(distanceMeters(ray.origin, hit!, 0.5)).toBe(4);

  const moved = transformRay(ray, new THREE.Matrix4().makeTranslation(10, 0, 0));
  expect(moved.origin.toArray()).toEqual([9, -2, -3]);
  expect(moved.direction.toArray()).toEqual([0, 0, 1]);
  expect(azimuthDeg(new THREE.Vector3(), new THREE.Vector3(0, 0, -1))).toBe(0);
});

