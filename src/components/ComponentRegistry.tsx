import React from 'react';
import type { ViewId } from '../layout/initialLayout';
import { MediaPool } from './panels/MediaPool';
import { Viewer } from './panels/Viewer';
import { Inspector } from './panels/Inspector';
import { TimelinePanel } from './panels/TimelinePanel';
import { BattleGallery } from './panels/BattleGallery';
import { UpdatePanel } from './panels/UpdatePanel';
import { AdminPanel } from './panels/AdminPanel';
import { AiAnalysisPanel } from './panels/AiAnalysisPanel';
import { DebugPanel } from './panels/DebugPanel';
import { NetworkPanel } from './panels/NetworkPanel';
import { Flight3D } from './panels/Flight3D';

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
      Панель «Очередь» удалена. Анализ видео запускается автоматически при открытии файла во вьюере.
    </div>
  ),
  gallery: BattleGallery,
  update: UpdatePanel,
  admin: AdminPanel,
  aiAnalysis: AiAnalysisPanel,
  debug: DebugPanel,
  network: NetworkPanel,
  flight3d: Flight3D,
};

export const ComponentForId: React.FC<{ id: ViewId }> = ({ id }) => {
  const Comp = registry[id];
  return Comp ? <Comp /> : <div className="p-4 text-sm text-[var(--dv-text-muted)]">Unknown: {id}</div>;
};

export default ComponentForId;
