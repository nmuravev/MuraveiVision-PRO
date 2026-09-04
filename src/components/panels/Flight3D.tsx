import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';
import { useReconStore } from '../../store/useReconStore';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import {
  azimuthDeg,
  buildRayFromIntrinsics,
  distanceMeters,
  intersectRayWithPointCloud,
  pickSplatAlongRay,
  transformRay,
  type CameraPose,
} from '../../lib/reconRaycast';
import {
  classifyArtifact,
  disposeSceneChildren,
  fetchAssetBlobUrl,
  frameObject,
  isSparseClusterWeak,
  loadPlyAsPoints,
  loadSplatDropIn,
  pointsFromSparse,
  type SplatHandle,
} from '../../lib/reconSceneArtifact';
import { OpsStatusBar } from '../OpsStatusBar';
import { SILENT_API_ERROR_HEADER } from '../../lib/apiError';
import { computeReconSegment, isReconReady, useReconBuild } from '../../hooks/useReconBuild';
import { useReconTrain } from '../../hooks/useReconTrain';
import {
  formatTimecode,
  interpolateTrack,
  makeOrigin,
  toLocal,
  type GeoPoint,
} from '../../lib/geoLocal';

type DetMarker = {
  id: string;
  time_sec: number;
  class_name: string;
  lat: number;
  lon: number;
  alt: number;
};

function disposeObject(obj: THREE.Object3D) {
  obj.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (mesh.geometry) mesh.geometry.dispose();
    const mat = mesh.material;
    if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
    else if (mat) mat.dispose();
  });
}

export const Flight3D: React.FC = () => {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    trackLine: THREE.Line | null;
    trackGroup: THREE.Group;
    targetsGroup: THREE.Group;
    sceneGroup: THREE.Group;
    raycastGroup: THREE.Group;
    camMarker: THREE.Group;
    origin: ReturnType<typeof makeOrigin>;
    track: GeoPoint[];
    dets: DetMarker[];
    raf: number;
  } | null>(null);

  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const sourcePath = useViewerStore((s) => s.viewers[focusedViewerId]?.sourcePath);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const mediaDuration = useTimelineStore((s) => s.mediaDuration);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const detections = useMuraveiStore((s) => s.detections);
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const setActiveDetectionId = useMuraveiStore((s) => s.setActiveDetectionId);

  const viewMode = useReconStore((s) => s.viewMode);
  const manifest = useReconStore((s) => s.manifest);
  const reconMessage = useReconStore((s) => s.reconMessage);
  const reconProgress = useReconStore((s) => s.reconProgress);
  const reconRunning = useReconStore((s) => s.reconRunning);
  const sparsePoints = useReconStore((s) => s.sparsePoints);
  const sparseWeak = useReconStore((s) => s.sparseWeak);
  const colmapAvailable = useReconStore((s) => s.colmapAvailable);
  const raycastMarkers = useReconStore((s) => s.raycastMarkers);
  const pendingRaycast = useReconStore((s) => s.pendingRaycast);
  const toast = useReconStore((s) => s.toast);
  const setViewMode = useReconStore((s) => s.setViewMode);
  const setManifest = useReconStore((s) => s.setManifest);
  const setSparsePoints = useReconStore((s) => s.setSparsePoints);
  const clearPendingRaycast = useReconStore((s) => s.clearPendingRaycast);
  const addRaycastMarker = useReconStore((s) => s.addRaycastMarker);
  const setToast = useReconStore((s) => s.setToast);

  const { pct: reconPct, startRecon, stopRecon } = useReconBuild(sourcePath, isAuthenticated);
  const {
    presets: trainPresets,
    train,
    training,
    colmapRunning: trainSeesColmap,
    startTrain,
    stopTrain,
  } = useReconTrain(manifest?.job_id, isAuthenticated);

  const needsTrainBanner =
    viewMode === 'scene' &&
    manifest?.status === 'colmap_done' &&
    classifyArtifact(manifest.artifact) !== 'splat' &&
    !training &&
    train.status !== 'error';

  const [track, setTrack] = useState<GeoPoint[]>([]);
  const [geoDets, setGeoDets] = useState<DetMarker[]>([]);
  const [status, setStatus] = useState<string>('Нет данных');
  const [showTrack, setShowTrack] = useState(true);
  const [showTargets, setShowTargets] = useState(true);
  const [busy, setBusy] = useState(false);
  const [camAlt, setCamAlt] = useState<number | null>(null);
  const [scaleMeters, setScaleMeters] = useState('10');
  const [scalePick, setScalePick] = useState<THREE.Vector3[]>([]);
  const [sceneLoading, setSceneLoading] = useState(false);
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [sceneKind, setSceneKind] = useState<'points' | 'splat' | 'empty'>('empty');
  const viewModeRef = useRef(viewMode);
  const scalePickRef = useRef(scalePick);
  const sparseRef = useRef(sparsePoints);
  const splatHandleRef = useRef<SplatHandle | null>(null);
  const framedKeyRef = useRef('');
  const cameraSnapRef = useRef<{
    jobId: string;
    pos: THREE.Vector3;
    target: THREE.Vector3;
  } | null>(null);
  viewModeRef.current = viewMode;
  scalePickRef.current = scalePick;
  sparseRef.current = sparsePoints;

  const fileLabel = useMemo(
    () => (sourcePath ? sourcePath.replace(/^.*[/\\]/, '') : 'нет видео'),
    [sourcePath],
  );

  const playheadOutsideSegment = useMemo(() => {
    if (!manifest || viewMode !== 'scene') return false;
    const { t_start, t_end } = manifest;
    return playheadPosition < t_start - 0.5 || playheadPosition > t_end + 0.5;
  }, [manifest, viewMode, playheadPosition]);

  const loadManifest = useCallback(async () => {
    if (!sourcePath || !isAuthenticated) {
      setManifest(null);
      setSparsePoints(null, false);
      return;
    }
    const q = encodeURIComponent(sourcePath);
    const res = await fetch(`/api/recon/manifest?video_path=${q}`, { headers: authHeaders() });
    if (!res.ok) return;
    const data = (await res.json()) as {
      manifest?: typeof manifest;
      colmap_available?: boolean;
    };
    const man = data.manifest ?? null;
    setManifest(man, Boolean(data.colmap_available));
    if (man?.job_id && man.sparse_file && isReconReady(man)) {
      const sp = await fetch(`/api/recon/asset/${man.job_id}/${man.sparse_file}`, {
        headers: authHeaders(),
      });
      if (sp.ok) {
        const pts = (await sp.json()) as { points?: number[][]; count?: number };
        const n = pts.points?.length ?? 0;
        const flat = new Float32Array(n * 3);
        pts.points?.forEach((p, i) => {
          flat[i * 3] = p[0];
          flat[i * 3 + 1] = p[1];
          flat[i * 3 + 2] = p[2];
        });
        setSparsePoints(flat.length ? flat : null, flat.length ? isSparseClusterWeak(flat) : false);
      }
    } else {
      setSparsePoints(null, false);
    }
  }, [sourcePath, isAuthenticated, setManifest, setSparsePoints]);

  useEffect(() => {
    void loadManifest();
  }, [loadManifest]);

  useEffect(() => {
    if (!sourcePath || !isAuthenticated) {
      setTrack([]);
      setGeoDets([]);
      setStatus(sourcePath ? 'Нужна авторизация' : 'Откройте MP4 во Viewer');
      return;
    }
    let cancelled = false;
    setBusy(true);
    setStatus('Загрузка телеметрии…');

    const load = async () => {
      await fetch('/api/geo/import', {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/json',
          [SILENT_API_ERROR_HEADER]: '1',
        },
        body: JSON.stringify({ video_path: sourcePath }),
      }).catch(() => null);

      const q = encodeURIComponent(sourcePath);
      const [trRes, detRes] = await Promise.all([
        fetch(`/api/geo/track?video_path=${q}`, { headers: authHeaders() }),
        fetch(`/api/geo/detections?video_path=${q}`, { headers: authHeaders() }),
      ]);

      if (cancelled) return;

      let points: GeoPoint[] = [];
      if (trRes.ok) {
        const data = (await trRes.json()) as { points?: GeoPoint[] };
        points = Array.isArray(data.points) ? data.points : [];
      }

      let dets: DetMarker[] = [];
      if (detRes.ok) {
        const data = (await detRes.json()) as {
          detections?: {
            id: string;
            time_sec: number;
            class_name: string;
            gps_lat?: number | null;
            gps_lon?: number | null;
            gps_alt?: number | null;
          }[];
        };
        dets = (data.detections || [])
          .filter((d) => d.gps_lat != null && d.gps_lon != null)
          .map((d) => ({
            id: d.id,
            time_sec: d.time_sec,
            class_name: d.class_name,
            lat: Number(d.gps_lat),
            lon: Number(d.gps_lon),
            alt: Number(d.gps_alt ?? 0),
          }));
      }

      if (!dets.length) {
        const base = sourcePath.replace(/^.*[/\\]/, '').toLowerCase();
        dets = detections
          .filter((d) => {
            if (d.is_deleted || d.gps_lat == null || d.gps_lon == null) return false;
            const dv = (d.source_video || '').replace(/\\/g, '/').toLowerCase();
            return dv === sourcePath.replace(/\\/g, '/').toLowerCase() || dv.endsWith(base);
          })
          .map((d) => ({
            id: d.id,
            time_sec: d.time_sec,
            class_name: d.class_name,
            lat: Number(d.gps_lat),
            lon: Number(d.gps_lon),
            alt: Number(d.gps_alt ?? 0),
          }));
      }

      setTrack(points);
      setGeoDets(dets);
      if (viewMode === 'geo') {
        if (!points.length) setStatus('Нет sidecar SRT/CSV · режим Сцена для visual-only 3D');
        else setStatus(`Трек: ${points.length} тчк · целей: ${dets.length}`);
      }
    };

    void load()
      .catch((err: unknown) => {
        if (!cancelled) setStatus(err instanceof Error ? err.message : 'Ошибка загрузки');
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourcePath, isAuthenticated]);

  useEffect(() => {
    if (!reconRunning && manifest?.job_id) {
      void loadManifest();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reconRunning, manifest?.job_id, manifest?.status]);

  const runBuild3d = () => {
    const { tStart, tEnd } = computeReconSegment(playheadPosition, mediaDuration);
    void startRecon({ tStart, tEnd, openSceneOnDone: true });
  };

  useEffect(() => {
    if (!pendingRaycast || !sourcePath) return;
    let cancelled = false;

    const run = async () => {
      const q = encodeURIComponent(sourcePath);
      const tq = encodeURIComponent(String(pendingRaycast.timeSec));
      const res = await fetch(`/api/recon/poses?video_path=${q}&time_sec=${tq}`, {
        headers: authHeaders(),
      });
      if (!res.ok) {
        setToast('Нет camera poses — сначала «Построить 3D»');
        clearPendingRaycast();
        return;
      }
      const data = (await res.json()) as { pose: CameraPose; manifest?: typeof manifest };
      const pose = data.pose;
      const ray = buildRayFromIntrinsics(pose, pendingRaycast.u, pendingRaycast.v);
      let hit: THREE.Vector3 | null = null;
      const sceneState = sceneRef.current;
      if (splatHandleRef.current && sceneState) {
        sceneState.sceneGroup.updateMatrixWorld(true);
        hit = pickSplatAlongRay(
          splatHandleRef.current.viewer,
          ray,
          sceneState.sceneGroup.matrixWorld,
        );
      }
      if (!hit && sparsePoints) {
        hit = intersectRayWithPointCloud(ray, sparsePoints);
      }
      if (cancelled) return;
      if (!hit) {
        setToast('Пересечение не найдено');
        clearPendingRaycast();
        return;
      }
      const scale = data.manifest?.scale_m_per_unit ?? manifest?.scale_m_per_unit;
      const scaleDir = data.manifest?.scale_reference?.scale_direction
        ?? manifest?.scale_reference?.scale_direction;
      const distM = distanceMeters(ray.origin, hit, scale);
      const az = azimuthDeg(ray.origin, hit, scaleDir);
      addRaycastMarker({
        id: `${pendingRaycast.detectionId}-${Date.now()}`,
        detectionId: pendingRaycast.detectionId,
        position: [hit.x, hit.y, hit.z],
        className: pendingRaycast.className,
        aiClassName: pendingRaycast.aiClassName,
        distanceM: distM,
        azimuthDeg: az,
      });
      setViewMode('scene');
      clearPendingRaycast();
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [
    pendingRaycast,
    sourcePath,
    sparsePoints,
    manifest,
    addRaycastMarker,
    clearPendingRaycast,
    setToast,
    setViewMode,
  ]);

  useEffect(() => {
    const el = mountRef.current;
    if (!el) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0e12);

    const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 50000);
    camera.position.set(80, 60, 80);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(el.clientWidth || 400, el.clientHeight || 300);
    el.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI * 0.49;

    scene.add(new THREE.HemisphereLight(0xb1c5d4, 0x1a1a1a, 0.85));
    const dir = new THREE.DirectionalLight(0xffffff, 0.65);
    dir.position.set(40, 80, 20);
    scene.add(dir);

    scene.add(new THREE.GridHelper(400, 40, 0x1e3a2f, 0x152028));

    const trackGroup = new THREE.Group();
    const targetsGroup = new THREE.Group();
    const sceneGroup = new THREE.Group();
    const raycastGroup = new THREE.Group();
    scene.add(trackGroup);
    scene.add(targetsGroup);
    scene.add(sceneGroup);
    scene.add(raycastGroup);

    const camMarker = new THREE.Group();
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(2.2, 5, 8),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0a3a55, emissiveIntensity: 0.4 }),
    );
    cone.rotation.x = Math.PI / 2;
    camMarker.add(new THREE.Mesh(
      new THREE.SphereGeometry(1.4, 12, 12),
      new THREE.MeshStandardMaterial({ color: 0xe2e8f0 }),
    ));
    camMarker.add(cone);
    cone.position.z = 3;
    scene.add(camMarker);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    const onClick = (ev: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

      if (viewModeRef.current === 'scene' && scalePickRef.current.length < 2 && sparseRef.current) {
        sceneGroup.updateMatrixWorld(true);
        const localRay = transformRay(
          { origin: raycaster.ray.origin, direction: raycaster.ray.direction.clone().normalize() },
          sceneGroup.matrixWorld.clone().invert(),
        );
        const hit = intersectRayWithPointCloud(
          localRay,
          sparseRef.current,
        );
        if (hit) {
          setScalePick((prev) => [...prev, hit.clone()].slice(0, 2));
        }
        return;
      }

      const hits = raycaster.intersectObjects(targetsGroup.children, true);
      if (!hits.length) return;
      let obj: THREE.Object3D | null = hits[0].object;
      while (obj && obj.userData?.detId == null) obj = obj.parent;
      const detId = obj?.userData?.detId as string | undefined;
      const t = obj?.userData?.timeSec as number | undefined;
      if (detId) setActiveDetectionId(detId);
      if (typeof t === 'number') seekTo(t);
    };
    renderer.domElement.addEventListener('pointerdown', onClick);

    const resize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth || 400;
      const h = mountRef.current.clientHeight || 300;
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    const state = {
      renderer,
      scene,
      camera,
      controls,
      trackLine: null as THREE.Line | null,
      trackGroup,
      targetsGroup,
      sceneGroup,
      raycastGroup,
      camMarker,
      origin: null as ReturnType<typeof makeOrigin>,
      track: [] as GeoPoint[],
      dets: [] as DetMarker[],
      raf: 0,
    };
    sceneRef.current = state;

    const animate = () => {
      state.raf = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(state.raf);
      renderer.domElement.removeEventListener('pointerdown', onClick);
      ro.disconnect();
      controls.dispose();
      if (splatHandleRef.current) {
        splatHandleRef.current.dispose();
        splatHandleRef.current = null;
      }
      disposeObject(scene);
      renderer.dispose();
      if (renderer.domElement.parentElement === el) el.removeChild(renderer.domElement);
      sceneRef.current = null;
    };
  }, [seekTo, setActiveDetectionId]);

  useEffect(() => {
    const st = sceneRef.current;
    if (!st) return;

    while (st.trackGroup.children.length) {
      const c = st.trackGroup.children[0];
      st.trackGroup.remove(c);
      disposeObject(c);
    }
    while (st.targetsGroup.children.length) {
      const c = st.targetsGroup.children[0];
      st.targetsGroup.remove(c);
      disposeObject(c);
    }
    st.trackLine = null;

    const origin = makeOrigin(track.length ? track : geoDets.map((d) => ({
      timestamp: d.time_sec,
      lat: d.lat,
      lon: d.lon,
      alt: d.alt,
    })));
    st.origin = origin;
    st.track = track;
    st.dets = geoDets;

    if (!origin) return;

    if (track.length >= 2) {
      const positions = new Float32Array(track.length * 3);
      track.forEach((p, i) => {
        const { x, y, z } = toLocal(p.lat, p.lon, p.alt ?? 0, origin);
        positions[i * 3] = x;
        positions[i * 3 + 1] = y;
        positions[i * 3 + 2] = z;
      });
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0x38bdf8 }));
      st.trackLine = line;
      st.trackGroup.add(line);
    }

    geoDets.forEach((d) => {
      const { x, y, z } = toLocal(d.lat, d.lon, d.alt, origin);
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(3.2, 3.2, 3.2),
        new THREE.MeshStandardMaterial({ color: 0x00ff88, emissive: 0x003322, emissiveIntensity: 0.35 }),
      );
      mesh.position.set(x, y + 1.6, z);
      mesh.userData = { detId: d.id, timeSec: d.time_sec };
      st.targetsGroup.add(mesh);
    });

    st.trackGroup.visible = viewMode === 'geo' && showTrack;
    st.targetsGroup.visible = viewMode === 'geo' && showTargets;
  }, [track, geoDets, showTrack, showTargets, viewMode]);

  useEffect(() => {
    const st = sceneRef.current;
    if (!st) return;

    let cancelled = false;
    const jobId = manifest?.job_id;
    const artifact = manifest?.artifact ?? null;
    const artifactKind = classifyArtifact(artifact);
    const frameKey = `${jobId ?? ''}:${artifact ?? 'sparse'}`;

    const clearScene = () => {
      if (splatHandleRef.current) {
        splatHandleRef.current.dispose();
        splatHandleRef.current = null;
      }
      disposeSceneChildren(st.sceneGroup);
    };

    const snapCamera = () => {
      if (!jobId) return;
      cameraSnapRef.current = {
        jobId,
        pos: st.camera.position.clone(),
        target: st.controls.target.clone(),
      };
    };

    const applyCamera = (obj: THREE.Object3D) => {
      const sameJob =
        cameraSnapRef.current &&
        jobId &&
        cameraSnapRef.current.jobId === jobId &&
        framedKeyRef.current !== '' &&
        framedKeyRef.current.split(':')[0] === jobId;
      if (sameJob && framedKeyRef.current !== frameKey && cameraSnapRef.current) {
        st.camera.position.copy(cameraSnapRef.current.pos);
        st.controls.target.copy(cameraSnapRef.current.target);
        st.controls.update();
      } else {
        frameObject(obj, st.camera, st.controls);
      }
      framedKeyRef.current = frameKey;
    };

    st.sceneGroup.visible = viewMode === 'scene';
    if (viewMode !== 'scene') {
      clearScene();
      setSceneKind('empty');
      setSceneError(null);
      setSceneLoading(false);
      return;
    }

    if (reconRunning || training) {
      clearScene();
      setSceneKind('empty');
      setSceneError(null);
      setSceneLoading(false);
      return;
    }

    const ready = isReconReady(manifest);

    if (!ready) {
      clearScene();
      setSceneKind('empty');
      setSceneError(
        manifest?.status === 'error'
          ? manifest.error || 'Ошибка построения 3D'
          : null,
      );
      setSceneLoading(false);
      return;
    }

    snapCamera();
    clearScene();
    setSceneError(null);
    setSceneLoading(true);

    const finishPoints = (pts: THREE.Points) => {
      if (cancelled) {
        pts.geometry.dispose();
        (pts.material as THREE.Material).dispose();
        setSceneLoading(false);
        return;
      }
      st.sceneGroup.add(pts);
      const box = new THREE.Box3().setFromObject(pts);
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z, 0.01);
      const center = box.getCenter(new THREE.Vector3());
      const grid = new THREE.GridHelper(maxDim * 2, 12, 0x334455, 0x223344);
      grid.position.y = center.y - size.y * 0.5;
      st.sceneGroup.add(grid);
      if (manifest?.rotation_x) st.sceneGroup.rotation.x = manifest.rotation_x;
      else st.sceneGroup.rotation.x = 0;
      applyCamera(pts);
      setSceneKind('points');
      setSceneLoading(false);
    };

    const run = async () => {
      try {
        if (artifactKind === 'splat' && jobId && artifact) {
          const blobUrl = await fetchAssetBlobUrl(jobId, artifact);
          if (cancelled) {
            URL.revokeObjectURL(blobUrl);
            setSceneLoading(false);
            return;
          }
          const hint = artifact.toLowerCase().endsWith('.ksplat')
            ? 'ksplat'
            : artifact.toLowerCase().endsWith('.splat')
              ? 'splat'
              : 'ply';
          const handle = await loadSplatDropIn(st.sceneGroup, blobUrl, hint);
          if (cancelled) {
            handle.dispose();
            setSceneLoading(false);
            return;
          }
          splatHandleRef.current = handle;
          if (manifest?.rotation_x) st.sceneGroup.rotation.x = manifest.rotation_x;
          else st.sceneGroup.rotation.x = 0;
          applyCamera(handle.viewer);
          setSceneKind('splat');
          setSceneLoading(false);
          return;
        }

        if (artifactKind === 'points' && jobId && artifact) {
          const blobUrl = await fetchAssetBlobUrl(jobId, artifact);
          try {
            const pts = await loadPlyAsPoints(blobUrl);
            finishPoints(pts);
          } finally {
            URL.revokeObjectURL(blobUrl);
          }
          return;
        }

        // Fallback: sparse_points.json already in store
        if (sparsePoints && sparsePoints.length >= 3) {
          finishPoints(pointsFromSparse(sparsePoints));
          return;
        }

        setSceneKind('empty');
        setSceneError(
          isReconReady(manifest)
            ? 'COLMAP готов, но нет точек / artifact'
            : '3D-модель не построена',
        );
        setSceneLoading(false);
      } catch (err) {
        if (cancelled) {
          setSceneLoading(false);
          return;
        }
        clearScene();
        setSceneKind('empty');
        setSceneError(err instanceof Error ? err.message : 'Ошибка загрузки 3D');
        setSceneLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
      setSceneLoading(false);
    };
  }, [
    viewMode,
    manifest?.job_id,
    manifest?.artifact,
    manifest?.status,
    manifest?.rotation_x,
    sparsePoints,
    reconRunning,
    training,
  ]);

  useEffect(() => {
    const st = sceneRef.current;
    if (!st) return;
    while (st.raycastGroup.children.length) {
      const c = st.raycastGroup.children[0];
      st.raycastGroup.remove(c);
      disposeObject(c);
    }
    st.raycastGroup.visible = viewMode === 'scene';
    st.raycastGroup.rotation.x = manifest?.rotation_x ?? 0;
    raycastMarkers.forEach((m) => {
      const g = new THREE.Group();
      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(0.35, 10, 10),
        new THREE.MeshStandardMaterial({ color: 0xff6644, emissive: 0x441100, emissiveIntensity: 0.5 }),
      );
      g.position.set(m.position[0], m.position[1], m.position[2]);
      g.add(sphere);
      const cross = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 1.2, 0.08),
        new THREE.MeshBasicMaterial({ color: 0xffaa00 }),
      );
      g.add(cross);
      g.userData = { marker: m };
      st.raycastGroup.add(g);
    });
  }, [raycastMarkers, viewMode, manifest?.rotation_x]);

  useEffect(() => {
    const st = sceneRef.current;
    if (!st?.origin || !st.track.length || viewMode !== 'geo') {
      if (viewMode !== 'geo') setCamAlt(null);
      return;
    }
    const pt = interpolateTrack(st.track, playheadPosition);
    if (!pt) return;
    const { x, y, z } = toLocal(pt.lat, pt.lon, pt.alt ?? 0, st.origin);
    st.camMarker.position.set(x, y, z);
    st.camMarker.visible = viewMode === 'geo';
    setCamAlt(pt.alt ?? 0);
  }, [playheadPosition, track, viewMode]);

  useEffect(() => {
    const st = sceneRef.current;
    if (st) st.camMarker.visible = viewMode === 'geo';
  }, [viewMode]);

  useEffect(() => {
    if (viewMode === 'scene' && manifest) {
      const nPts = sparsePoints ? sparsePoints.length / 3 : 0;
      const seg = `${formatTimecode(manifest.t_start)}–${formatTimecode(manifest.t_end)}`;
      const ok = manifest.status === 'colmap_done' || manifest.status === 'done';
      const art = manifest.artifact ? ` · ${manifest.artifact}` : '';
      const kind =
        sceneKind === 'splat' ? 'Gaussian splat' : sceneKind === 'points' ? `${nPts || 'PLY'} точек` : 'нет облака';
      setStatus(
        ok
          ? `Сцена: ${manifest.status} · ${manifest.job_id}${art} · ${kind} · сегмент ${seg}`
          : `Сцена: ${manifest.status}${manifest.job_id ? ` · ${manifest.job_id}` : ''}`,
      );
    }
  }, [viewMode, manifest, sparsePoints, sceneKind]);

  const applyScale = async () => {
    if (!manifest?.job_id || scalePick.length !== 2) return;
    const a = scalePick[0];
    const b = scalePick[1];
    const distScene = a.distanceTo(b);
    const distM = parseFloat(scaleMeters);
    if (!distScene || !distM || distM <= 0) return;
    const dir = b.clone().sub(a).normalize();
    const body = {
      scale_m_per_unit: distM / distScene,
      scale_reference: {
        point_a: [a.x, a.y, a.z],
        point_b: [b.x, b.y, b.z],
        distance_m: distM,
        scale_direction: [dir.x, dir.y, dir.z],
      },
    };
    await fetch(`/api/recon/manifest/${manifest.job_id}`, {
      method: 'PATCH',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    setScalePick([]);
    void loadManifest();
    setToast(`Масштаб: ${(distM / distScene).toFixed(4)} м/ед.`);
  };

  return (
    <div className="h-full flex flex-col min-h-0 bg-[var(--dv-deep)]">
      <div className="px-2 py-1.5 border-b border-[var(--dv-border)] flex flex-wrap items-center gap-2 text-[10px] flex-shrink-0">
        <span className="text-[var(--dv-text-muted)] truncate max-w-[30%]" title={sourcePath || ''}>
          3D: {fileLabel}
        </span>
        <div className="flex rounded-sm overflow-hidden border border-[var(--dv-border)]">
          <button
            type="button"
            className={`px-2 py-0.5 ${viewMode === 'geo' ? 'bg-[var(--dv-accent)] text-black' : 'bg-[var(--dv-bg-deep)]'}`}
            onClick={() => setViewMode('geo')}
          >
            Гео
          </button>
          <button
            type="button"
            className={`px-2 py-0.5 ${viewMode === 'scene' ? 'bg-[var(--dv-accent)] text-black' : 'bg-[var(--dv-bg-deep)]'}`}
            onClick={() => setViewMode('scene')}
          >
            Сцена
          </button>
        </div>
        <button
          type="button"
          disabled={!sourcePath || reconRunning || training}
          className="px-2 py-0.5 bg-[var(--dv-surface)] hover:bg-[var(--dv-hover)] disabled:opacity-40 rounded-sm"
          onClick={() => runBuild3d()}
          title={training ? 'Дождитесь завершения обучения' : undefined}
        >
          {reconRunning ? 'Строим…' : 'Построить 3D'}
        </button>
        {reconRunning && (
          <button
            type="button"
            className="px-2 py-0.5 bg-[var(--dv-surface)] hover:bg-[var(--dv-hover)] rounded-sm"
            onClick={() => void stopRecon()}
          >
            Стоп
          </button>
        )}
        {viewMode === 'scene' && manifest && (
          <span className="font-mono text-[var(--dv-text-muted)]">
            Сегмент: {formatTimecode(manifest.t_start)}–{formatTimecode(manifest.t_end)}
          </span>
        )}
        {playheadOutsideSegment && (
          <span className="text-amber-400 font-mono" title="Raycast и poses доступны только внутри сегмента COLMAP">
            playhead вне сегмента
          </span>
        )}
        {reconRunning && (
          <span className="font-mono text-[var(--dv-accent)]">{reconPct}%</span>
        )}
        <span className="font-mono text-[var(--dv-text)]">{formatTimecode(playheadPosition)}</span>
        {camAlt != null && viewMode === 'geo' && (
          <span className="text-[#38bdf8] font-mono">alt {camAlt.toFixed(1)} m</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {viewMode === 'geo' && (
            <>
              <label className="inline-flex items-center gap-1 cursor-pointer text-[var(--dv-muted)]">
                <input type="checkbox" checked={showTrack} onChange={(e) => setShowTrack(e.target.checked)} className="accent-[var(--dv-accent)]" />
                Траектория
              </label>
              <label className="inline-flex items-center gap-1 cursor-pointer text-[var(--dv-muted)]">
                <input type="checkbox" checked={showTargets} onChange={(e) => setShowTargets(e.target.checked)} className="accent-[var(--dv-accent)]" />
                Цели
              </label>
            </>
          )}
          {viewMode === 'scene' && manifest && (
            <>
              <input
                className="w-12 bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-1 font-mono"
                value={scaleMeters}
                onChange={(e) => setScaleMeters(e.target.value)}
                title="Метры между 2 точками"
              />
              <button
                type="button"
                className="px-1.5 py-0.5 bg-[var(--dv-surface)] rounded-sm"
                onClick={() => void applyScale()}
                disabled={scalePick.length !== 2}
              >
                Масштаб ({scalePick.length}/2)
              </button>
            </>
          )}
        </div>
      </div>
      <div className="px-2 py-0.5 text-[10px] text-[var(--dv-text-muted)] border-b border-[var(--dv-border)] flex-shrink-0">
        {reconRunning
          ? reconMessage
          : sceneLoading
            ? 'Загрузка 3D-сцены…'
            : busy
              ? 'Загрузка…'
              : status}
        <OpsStatusBar sourcePath={sourcePath} />
        {viewMode === 'scene' && (
          <span className="opacity-60">
            {' '}
            ·{' '}
            {sceneKind === 'splat'
              ? 'Gaussian splat'
              : sceneKind === 'points'
                ? 'point cloud'
                : manifest?.status === 'error'
                  ? 'ошибка'
                  : 'нет сцены'}
            {manifest?.job_id ? ` · raycast из Inspector (sparse)` : ''}
          </span>
        )}
        {sceneError && <span className="ml-2 text-[var(--dv-danger)]">{sceneError}</span>}
        {toast && <span className="ml-2 text-[var(--dv-accent)]">{toast}</span>}
      </div>
      {viewMode === 'scene' && manifest?.job_id && (
        <div className="px-2 py-1 border-b border-[var(--dv-border)] flex flex-col gap-1 text-[10px] flex-shrink-0">
          {needsTrainBanner && (
            <div className="text-amber-300 bg-amber-950/40 border border-amber-700/50 rounded-sm px-2 py-1">
              COLMAP завершён. Выберите профиль обучения для фотореалистичной сцены.
            </div>
          )}
          {train.status === 'error' && (
            <div className="text-red-300 bg-red-950/40 border border-red-700/50 rounded-sm px-2 py-1">
              Обучение не удалось: {train.error || train.message || 'ошибка'}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[var(--dv-text-muted)] font-mono">
              train: {train.status}
              {manifest.artifact ? ` · ${manifest.artifact}` : ' · artifact: null'}
            </span>
            {trainPresets.map((p) => (
              <button
                key={p.id}
                type="button"
                disabled={
                  training ||
                  reconRunning ||
                  trainSeesColmap ||
                  p.disabled ||
                  !isReconReady(manifest)
                }
                title={
                  trainSeesColmap || reconRunning
                    ? 'Дождитесь завершения COLMAP'
                    : p.disabled
                      ? p.disabled_reason
                      : p.eta
                }
                className="px-2 py-0.5 bg-[var(--dv-surface)] hover:bg-[var(--dv-hover)] disabled:opacity-40 rounded-sm"
                onClick={() =>
                  void startTrain(p.id, () => {
                    void loadManifest();
                  })
                }
              >
                {p.label}
                {p.eta ? ` (${p.eta})` : ''}
              </button>
            ))}
            {training && (
              <button
                type="button"
                className="px-2 py-0.5 bg-[var(--dv-surface)] hover:bg-[var(--dv-hover)] rounded-sm"
                onClick={() => void stopTrain()}
              >
                Стоп train
              </button>
            )}
          </div>
          {training && (
            <div className="font-mono text-[var(--dv-accent)]">
              {(train.steps ?? 0)}/{(train.max_steps ?? 0)} steps
              {train.loss != null ? ` · loss ${train.loss.toFixed(4)}` : ''}
              {train.psnr != null ? ` · PSNR ${train.psnr.toFixed(1)}` : ''}
              {` · VRAM ${(train.vram_used_gb ?? 0).toFixed(1)}/${(train.vram_total_gb ?? 0).toFixed(1)} GB`}
              {train.eta_seconds != null ? ` · ETA ~${Math.round(train.eta_seconds / 60)}м` : ''}
              <div className="mt-0.5 h-1 bg-[var(--dv-bg-deep)] rounded-sm overflow-hidden">
                <div
                  className="h-full bg-[var(--dv-accent)]"
                  style={{
                    width: `${Math.min(
                      100,
                      Math.round(
                        ((train.steps ?? 0) / Math.max(1, train.max_steps ?? 1)) * 100,
                      ),
                    )}%`,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}
      {reconRunning && (
        <div className="h-1 bg-[var(--dv-bg-deep)] flex-shrink-0">
          <div
            className="h-full bg-[var(--dv-accent)] transition-all"
            style={{ width: `${reconPct}%` }}
          />
        </div>
      )}
      <div ref={mountRef} className="flex-1 min-h-0 relative">
        {viewMode === 'scene' && !sceneLoading && sceneKind === 'empty' && !reconRunning && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
            <div className="px-3 py-2 rounded-sm bg-black/70 text-[11px] text-[var(--dv-text-muted)] text-center max-w-[80%]">
              {manifest?.status === 'error' &&
              colmapAvailable &&
              manifest.error?.includes('COLMAP не найден')
                ? 'Предыдущая попытка: COLMAP не был доступен. Нажмите «Построить 3D» ещё раз.'
                : manifest?.status === 'error' && manifest.error
                  ? manifest.error
                  : sceneError || '3D-модель не построена'}
              {manifest?.status !== 'error' && (
                <div className="opacity-70 mt-1">Нажмите «Построить 3D» (сегмент ≤120 с)</div>
              )}
            </div>
          </div>
        )}
        {viewMode === 'scene' && sceneKind === 'points' && sparseWeak && !reconRunning && (
          <div className="absolute top-2 left-2 right-2 pointer-events-none z-10">
            <div className="px-2 py-1 rounded-sm bg-amber-950/80 text-[10px] text-amber-200 border border-amber-700/50">
              Слабая 3D-модель: точки сгруппированы (мало parallax). Попробуйте другой сегмент или
              больше перекрытия кадров. gsplat мог не завершиться — см. logs/recon.log
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Flight3D;
