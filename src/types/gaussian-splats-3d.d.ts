declare module '@mkkellogg/gaussian-splats-3d' {
  import type { Object3D, Vector3 } from 'three';

  export type SplatSceneOptions = {
    path?: string;
    format?: number;
    splatAlphaRemovalThreshold?: number;
    showLoadingUI?: boolean;
    position?: [number, number, number];
    rotation?: [number, number, number, number];
    scale?: [number, number, number];
  };

  export class DropInViewer extends Object3D {
    viewer: {
      splatMesh: unknown;
      raycaster: {
        ray: { origin: Vector3; direction: Vector3 };
        intersectSplatMesh(
          mesh: unknown,
          hits: Array<{ origin: Vector3; distance: number; splatIndex?: number }>,
        ): Array<{ origin: Vector3; distance: number; splatIndex?: number }>;
      };
    };
    splatMesh: unknown;
    constructor(options?: Record<string, unknown>);
    addSplatScene(path: string, options?: SplatSceneOptions): Promise<void>;
    addSplatScenes(scenes: SplatSceneOptions[]): Promise<void>;
    dispose(): void;
  }

  export class Viewer {
    constructor(options?: Record<string, unknown>);
    addSplatScene(path: string, options?: SplatSceneOptions): Promise<void>;
    start(): void;
    update(): void;
    dispose(): void;
  }

  export const SceneFormat: {
    Ply: number;
    Splat: number;
    KSplat: number;
  };
}
