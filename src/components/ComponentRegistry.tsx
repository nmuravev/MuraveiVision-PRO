import React, { Suspense, lazy } from 'react';
import type { ViewId } from '../layout/initialLayout';
import { MediaPool } from './panels/MediaPool';
import { Viewer } from './panels/Viewer';
import { Inspector } from './panels/Inspector';
import { TimelinePanel } from './panels/TimelinePanel';
import { EventTimeline } from './panels/EventTimeline';

const BattleGallery = lazy(() =>
  import('./panels/BattleGallery').then((m) => ({ default: m.BattleGallery })),
);
const UpdatePanel = lazy(() =>
  import('./panels/UpdatePanel').then((m) => ({ default: m.UpdatePanel })),
);
const AdminPanel = lazy(() =>
  import('./panels/AdminPanel').then((m) => ({ default: m.AdminPanel })),
);
const AiAnalysisPanel = lazy(() =>
  import('./panels/AiAnalysisPanel').then((m) => ({ default: m.AiAnalysisPanel })),
);
const DebugPanel = lazy(() =>
  import('./panels/DebugPanel').then((m) => ({ default: m.DebugPanel })),
);
const NetworkPanel = lazy(() =>
  import('./panels/NetworkPanel').then((m) => ({ default: m.NetworkPanel })),
);
const Flight3D = lazy(() =>
  import('./panels/Flight3D').then((m) => ({ default: m.Flight3D })),
);

const PanelLoader: React.FC = () => (
  <div className="h-full w-full flex items-center justify-center bg-[var(--dv-bg-deep)] text-[11px] text-[var(--dv-text-muted)]">
    Загрузка панели…
  </div>
);

const registry: Record<ViewId, React.FC> = {
  'media-pool': MediaPool,
  'viewer-1': () => <Viewer viewerId="viewer-1" />,
  'viewer-2': () => <Viewer viewerId="viewer-2" />,
  'viewer-3': () => <Viewer viewerId="viewer-3" />,
  'viewer-4': () => <Viewer viewerId="viewer-4" />,
  inspector: Inspector,
  timeline: TimelinePanel,
  queue: () => (
    <div className="p-4 text-[12px] text-[var(--dv-text-muted)]">
      Панель «Очередь» удалена. Пакетный анализ — кнопка «Сканировать» во Viewer.
    </div>
  ),
  gallery: BattleGallery,
  update: UpdatePanel,
  admin: AdminPanel,
  aiAnalysis: AiAnalysisPanel,
  debug: DebugPanel,
  network: NetworkPanel,
  flight3d: Flight3D,
  events: EventTimeline,
};

export const ComponentForId: React.FC<{ id: ViewId }> = ({ id }) => {
  const Comp = registry[id];
  if (!Comp) {
    return <div className="p-4 text-sm text-[var(--dv-text-muted)]">Unknown: {id}</div>;
  }
  return (
    <Suspense fallback={<PanelLoader />}>
      <Comp />
    </Suspense>
  );
};

export default ComponentForId;
