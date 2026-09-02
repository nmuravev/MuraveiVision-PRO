import type { MosaicNode } from 'react-mosaic-component';

export type ViewId =
  | 'media-pool'
  | 'viewer-1'
  | 'viewer-2'
  | 'viewer-3'
  | 'viewer-4'
  | 'inspector'
  | 'timeline'
  | 'queue'
  | 'gallery'
  | 'update'
  | 'admin'
  | 'aiAnalysis'
  | 'debug'
  | 'network'
  | 'flight3d'
  | 'events';

/** TopBar workspace modes (functional tabs, not just mosaic cosmetics). */
export type WorkspaceMode =
  | 'mediaView'
  | 'editDefault'
  | 'aiAnalysis'
  | 'training'
  | 'system'
  | 'liveQuad';

/** Stable tab ids (also used as display labels — Russian). */
export const WORKSPACE_TABS = [
  'Медиа',
  'Монтаж',
  'AI-анализ',
  'Обучение',
  '4×Live',
  'Система',
] as const;

export type WorkspaceTab = (typeof WORKSPACE_TABS)[number];

export const TAB_TO_MODE: Record<string, WorkspaceMode> = {
  Медиа: 'mediaView',
  Монтаж: 'editDefault',
  'AI-анализ': 'aiAnalysis',
  Обучение: 'training',
  '4×Live': 'liveQuad',
  Система: 'system',
  // Legacy English keys (layout migrate / deep links)
  MEDIA: 'mediaView',
  EDIT: 'editDefault',
  'AI ANALYSIS': 'aiAnalysis',
  TRAINING: 'training',
  SYSTEM: 'system',
  '4xLive': 'liveQuad',
};

export const MODE_TO_TAB: Record<WorkspaceMode, WorkspaceTab> = {
  mediaView: 'Медиа',
  editDefault: 'Монтаж',
  aiAnalysis: 'AI-анализ',
  training: 'Обучение',
  liveQuad: '4×Live',
  system: 'Система',
};

export const VIEW_TITLES: Record<ViewId, string> = {
  'media-pool': 'Медиапул',
  'viewer-1': 'Вьюер 1 (1)',
  'viewer-2': 'Вьюер 2 (2)',
  'viewer-3': 'Вьюер 3 (3)',
  'viewer-4': 'Вьюер 4 (4)',
  inspector: 'Инспектор',
  timeline: 'Таймлайн',
  queue: 'Очередь',
  gallery: 'Галерея',
  update: 'Обновление',
  admin: 'Система',
  aiAnalysis: 'AI-анализ',
  debug: 'Отладка',
  network: 'Сеть',
  flight3d: 'Гео 3D',
  events: 'События',
};

export const ALL_VIEW_IDS: ViewId[] = [
  'media-pool',
  'viewer-1',
  'viewer-2',
  'viewer-3',
  'viewer-4',
  'inspector',
  'timeline',
  'gallery',
  'update',
  'admin',
  'aiAnalysis',
  'debug',
  'network',
  'flight3d',
  'events',
];

export const MIN_SIZES: Partial<Record<ViewId, { width: number; height: number }>> = {
  'viewer-1': { width: 400, height: 300 },
  'viewer-2': { width: 400, height: 300 },
  'viewer-3': { width: 400, height: 300 },
  'viewer-4': { width: 400, height: 300 },
  timeline: { width: 200, height: 120 },
  queue: { width: 180, height: 120 },
  'media-pool': { width: 180, height: 120 },
  inspector: { width: 180, height: 120 },
  gallery: { width: 200, height: 120 },
  update: { width: 280, height: 200 },
  admin: { width: 320, height: 240 },
  aiAnalysis: { width: 280, height: 220 },
  debug: { width: 280, height: 200 },
  network: { width: 300, height: 240 },
  flight3d: { width: 320, height: 240 },
  events: { width: 280, height: 140 },
};

/** MEDIA — archive browse: MediaPool + 1 Viewer + Timeline */
export const mediaViewLayout: MosaicNode<ViewId> = {
  type: 'split',
  direction: 'row',
  splitPercentages: [24, 76],
  children: [
    'media-pool',
    {
      type: 'split',
      direction: 'column',
      splitPercentages: [72, 28],
      children: ['viewer-1', 'timeline'],
    },
  ],
};

/** EDIT — primary operator markup: pool + viewers + inspector + timeline */
export const editDefaultLayout: MosaicNode<ViewId> = {
  type: 'split',
  direction: 'row',
  splitPercentages: [18, 82],
  children: [
    'media-pool',
    {
      type: 'split',
      direction: 'column',
      splitPercentages: [62, 38],
      children: [
        {
          type: 'split',
          direction: 'row',
          splitPercentages: [55, 45],
          children: ['viewer-1', 'viewer-2'],
        },
        {
          type: 'split',
          direction: 'row',
          splitPercentages: [35, 65],
          children: ['inspector', 'timeline'],
        },
      ],
    },
  ],
};

/** AI ANALYSIS — VLM panel + inspector + viewer (binary nested splits) */
export const aiAnalysisLayout: MosaicNode<ViewId> = {
  type: 'split',
  direction: 'row',
  // 32 | (40+28=68) → inner 40:28 ≈ 58.8:41.2 of remaining
  splitPercentages: [32, 68],
  children: [
    'aiAnalysis',
    {
      type: 'split',
      direction: 'row',
      splitPercentages: [58.82, 41.18],
      children: ['viewer-1', 'inspector'],
    },
  ],
};

/** TRAINING — UpdatePanel dominant + narrow pool + preview viewer */
export const trainingLayout: MosaicNode<ViewId> = {
  type: 'split',
  direction: 'row',
  // 16 | (52+32=84) → inner 52:32 ≈ 61.9:38.1
  splitPercentages: [16, 84],
  children: [
    'media-pool',
    {
      type: 'split',
      direction: 'row',
      splitPercentages: [61.9, 38.1],
      children: ['update', 'viewer-1'],
    },
  ],
};

/** SYSTEM — admin + network */
export const systemLayout: MosaicNode<ViewId> = {
  type: 'split',
  direction: 'row',
  splitPercentages: [55, 45],
  children: ['admin', 'network'],
};

/** MEDIA + Flight3D — viewer 60% / geo 40% + timeline */
export const mediaGeoLayout: MosaicNode<ViewId> = {
  type: 'split',
  direction: 'column',
  splitPercentages: [72, 28],
  children: [
    {
      type: 'split',
      direction: 'row',
      splitPercentages: [60, 40],
      children: ['viewer-1', 'flight3d'],
    },
    'timeline',
  ],
};

/** 4×Live — 2×2 viewers + event log (does not replace layout-menu «4 вьюера»). */
export const liveQuadLayout: MosaicNode<ViewId> = {
  type: 'split',
  direction: 'column',
  splitPercentages: [78, 22],
  children: [
    {
      type: 'split',
      direction: 'row',
      splitPercentages: [50, 50],
      children: [
        {
          type: 'split',
          direction: 'column',
          splitPercentages: [50, 50],
          children: ['viewer-1', 'viewer-3'],
        },
        {
          type: 'split',
          direction: 'column',
          splitPercentages: [50, 50],
          children: ['viewer-2', 'viewer-4'],
        },
      ],
    },
    'events',
  ],
};

/** Default workspace = EDIT (main operator mode) */
export const initialLayout: MosaicNode<ViewId> = editDefaultLayout;

export const layoutPresets: Record<WorkspaceMode | string, MosaicNode<ViewId>> = {
  mediaView: mediaViewLayout,
  editDefault: editDefaultLayout,
  aiAnalysis: aiAnalysisLayout,
  training: trainingLayout,
  system: systemLayout,
  liveQuad: liveQuadLayout,
  mediaGeo: mediaGeoLayout,
  // Legacy aliases (Layout menu / old code)
  default: editDefaultLayout,
  dualViewer: editDefaultLayout,
  singleViewer: {
    type: 'split',
    direction: 'row',
    splitPercentages: [18, 82],
    children: [
      'media-pool',
      {
        type: 'split',
        direction: 'column',
        splitPercentages: [70, 30],
        children: [
          'viewer-1',
          {
            type: 'split',
            direction: 'row',
            splitPercentages: [34, 66],
            children: ['inspector', 'timeline'],
          },
        ],
      },
    ],
  },
  quadViewer: {
    type: 'split',
    direction: 'row',
    splitPercentages: [14, 86],
    children: [
      'media-pool',
      {
        type: 'split',
        direction: 'column',
        splitPercentages: [68, 32],
        children: [
          {
            type: 'split',
            direction: 'row',
            splitPercentages: [50, 50],
            children: [
              {
                type: 'split',
                direction: 'column',
                splitPercentages: [50, 50],
                children: ['viewer-1', 'viewer-3'],
              },
              {
                type: 'split',
                direction: 'column',
                splitPercentages: [50, 50],
                children: ['viewer-2', 'viewer-4'],
              },
            ],
          },
          {
            type: 'split',
            direction: 'row',
            splitPercentages: [35, 65],
            children: ['inspector', 'timeline'],
          },
        ],
      },
    ],
  },
};
