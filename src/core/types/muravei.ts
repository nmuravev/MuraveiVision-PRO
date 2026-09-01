// src/core/types/muravei.ts
// Собственные типы MuraveiVision PRO — вдохновлены openreel, но адаптированы под военные задачи

// === БАЗОВЫЕ ТИПЫ ТАЙМЛАЙНА ===

export interface Clip {
  id: string;
  type: 'video' | 'audio' | 'image' | 'detection';
  name: string;
  startTime: number;      // секунды от начала таймлайна
  duration: number;       // секунды
  sourcePath?: string;    // путь к файлу на диске
  thumbnail?: string;     // base64 превью
  trackId: string;        // ID дорожки
  mediaId?: string;       // ID в медиабиблиотеке
  inPoint?: number;       // точка входа (для trim)
  outPoint?: number;      // точка выхода
  volume?: number;        // 0..1
  speed?: number;         // 0.25..4.0
  effects?: Effect[];
  keyframes?: Keyframe[];
  metadata?: Record<string, any>;
}

export interface Effect {
  id: string;
  type: string;
  params: Record<string, any>;
}

export interface Keyframe {
  time: number;
  property: string;
  value: any;
  easing?: 'linear' | 'ease-in' | 'ease-out' | 'ease-in-out';
}

export interface Track {
  id: string;
  name: string;
  type: 'video' | 'audio' | 'detections' | 'ai-analysis';
  clips: Clip[];
  visible: boolean;
  locked: boolean;
  muted?: boolean;       // для аудио
  solo?: boolean;        // для аудио
  hidden?: boolean;      // альтернатива visible
  color?: string;        // цвет дорожки в UI
  transitions?: Transition[];
}

export interface Transition {
  id: string;
  type: 'cut' | 'fade' | 'dissolve' | 'wipe';
  startTime: number;
  duration: number;
}

export interface Timeline {
  id: string;
  name: string;
  tracks: Track[];
  duration: number;       // общая длительность в секундах
  currentTime: number;    // текущая позиция playhead
  fps: number;
  resolution?: {
    width: number;
    height: number;
  };
  inPoint?: number;       // точка входа для рендера
  outPoint?: number;      // точка выхода для рендера
}

// === ТИПЫ ДЕЙСТВИЙ (ACTIONS) ===

export type Action =
  | { type: 'clip/add'; payload: { trackId: string; clip: Clip } }
  | { type: 'clip/remove'; payload: { trackId: string; clipId: string } }
  | { type: 'clip/move'; payload: { trackId: string; clipId: string; newStartTime: number } }
  | { type: 'clip/resize'; payload: { trackId: string; clipId: string; newDuration: number } }
  | { type: 'clip/split'; payload: { trackId: string; clipId: string; splitTime: number } }
  | { type: 'clip/trim'; payload: { trackId: string; clipId: string; inPoint?: number; outPoint?: number } }
  | { type: 'clip/rippleDelete'; payload: { trackId: string; clipId: string } }
  | { type: 'track/add'; payload: { track: Track } }
  | { type: 'track/remove'; payload: { trackId: string } }
  | { type: 'track/reorder'; payload: { trackId: string; newIndex: number } }
  | { type: 'track/lock'; payload: { trackId: string; locked: boolean } }
  | { type: 'track/hide'; payload: { trackId: string; hidden: boolean } }
  | { type: 'track/mute'; payload: { trackId: string; muted: boolean } }
  | { type: 'track/solo'; payload: { trackId: string; solo: boolean } }
  | { type: 'timeline/setCurrentTime'; payload: { time: number } }
  | { type: 'timeline/setInPoint'; payload: { time: number } }
  | { type: 'timeline/setOutPoint'; payload: { time: number } }
  | { type: 'timeline/clearInOutPoints' };

// === ТИПЫ ПРОЕКТА ===

export interface MediaItem {
  id: string;
  name: string;
  type: 'video' | 'audio' | 'image';
  path: string;
  duration?: number;
  thumbnail?: string;
  width?: number;
  height?: number;
  fps?: number;
  codec?: string;
}

export interface Project {
  id: string;
  name: string;
  timeline: Timeline;
  mediaItems: MediaItem[];
  createdAt: string;      // ISO timestamp
  updatedAt: string;      // ISO timestamp
  settings?: {
    theme?: 'premiere' | 'cyber-neon';
    autoSave?: boolean;
    autoSaveInterval?: number;  // секунды
  };
}

// === ВОЕННЫЕ ТИПЫ (специфичные для MuraveiVision) ===

export interface BoundingBox {
  x1: number;  // normalized 0..1
  y1: number;
  x2: number;
  y2: number;
}

export interface DetectedObject {
  id: string;
  class_ru: string;
  class_en: string;
  confidence: number;
  bbox: BoundingBox;
  color?: string;
  notes?: string;
}

export interface DetectionMoment {
  id: string;
  timestamp: string;    // "0:00:13"
  timeSec: number;
  frameIdx: number;
  objects: DetectedObject[];
  imageUrl?: string;
  cropAnalysis?: string;
  isFlagged?: boolean;
}

export type MilitaryClass =
  | 'tank'
  | 'armored_vehicle'
  | 'uav'
  | 'soldier'
  | 'artillery'
  | 'military_truck'
  | 'helicopter'
  | 'boat'
  | string;  // расширяемый список

export type ViewMode =
  | 'mini'
  | 'pro'
  | 'training'
  | 'merge'
  | 'gallery'
  | 'report'
  | 'diagnostics'
  | 'portable';

export type UiTheme = 'premiere' | 'cyber-neon';

export type UserRole = 'operator' | 'engineer' | 'master';