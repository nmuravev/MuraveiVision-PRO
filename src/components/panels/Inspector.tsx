import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box,
  Brain,
  ChevronDown,
  ChevronRight,
  Flag,
  Images,
  Search,
  Trash2,
} from 'lucide-react';
import {
  authHeaders,
  detectionCropSrc,
  toDetectedObject,
  useMuraveiStore,
  xyxyFromRow,
} from '../../store/useMuraveiStore';
import { useReconStore } from '../../store/useReconStore';
import { bboxCenterPixels } from '../../lib/reconRaycast';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import {
  useChangeDetectionStore,
  type ChangeItem,
  type ChangeMatch,
} from '../../store/useChangeDetectionStore';
import { usePanelLayoutStore } from '../../store/usePanelLayoutStore';
import { classDisplayLine, classLabelRu } from '../../lib/classLabels';
import { fetchDetectionCropBase64 } from '../../lib/aiVision';
import { computeReconSegment, useReconBuild } from '../../hooks/useReconBuild';
import { mediaPathsMatch } from '../../lib/mediaPaths';
import type { ClassCatalogItem, PersistedDetection } from '../../types/muravei';

const AI_UNAVAILABLE = 'ИИ недоступен. Проверьте запуск Ollama';
const FOLDS_KEY = 'muravei-inspector-folds';

type SimilarHit = {
  id: string;
  class_name: string;
  class_id?: number;
  similarity: number;
  time_sec: number;
  source_video: string;
  crop_path?: string | null;
};

type FoldKey = 'active' | 'recon' | 'similar' | 'ai' | 'detections' | 'changes';

type FoldState = Record<FoldKey, boolean>;

const DEFAULT_FOLDS: FoldState = {
  active: true,
  recon: false,
  similar: false,
  ai: false,
  detections: true,
  changes: true,
};

function loadFolds(): FoldState {
  try {
    const raw = localStorage.getItem(FOLDS_KEY);
    if (!raw) return { ...DEFAULT_FOLDS };
    const parsed = JSON.parse(raw) as Partial<FoldState>;
    return { ...DEFAULT_FOLDS, ...parsed };
  } catch {
    return { ...DEFAULT_FOLDS };
  }
}

function FoldSection({
  open,
  onToggle,
  title,
  icon,
  status,
  children,
  bodyClassName = 'px-2 pb-2.5 space-y-2',
  className = 'border-b border-dv-border flex-shrink-0',
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  icon?: React.ReactNode;
  status?: string;
  children?: React.ReactNode;
  bodyClassName?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <button
        type="button"
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-left hover:bg-dv-surface flex-shrink-0"
        onClick={onToggle}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown size={12} className="text-dv-muted shrink-0" />
        ) : (
          <ChevronRight size={12} className="text-dv-muted shrink-0" />
        )}
        {icon}
        <span className="dv-section-title flex-1 truncate">{title}</span>
        {!open && status ? (
          <span className="text-[10px] text-dv-muted font-mono truncate max-w-[45%]">{status}</span>
        ) : null}
      </button>
      {open ? <div className={bodyClassName}>{children}</div> : null}
    </div>
  );
}

function originLabel(origin?: string | null): string {
  switch (origin) {
    case 'batch_scan':
      return 'пакетный скан';
    case 'operator':
    case 'manual':
      return 'оператор';
    case 'auto':
      return 'авто';
    case 'live':
      return 'live YOLO';
    default:
      return origin ? origin.replace(/_/g, ' ') : 'live YOLO';
  }
}

function ChangeList({
  title,
  empty,
  items,
  kind,
  active,
  onPick,
}: {
  title: string;
  empty: string;
  items: ChangeItem[];
  kind: 'new' | 'removed';
  active: { kind: string; id: string } | null;
  onPick: (id: string) => void;
}) {
  return (
    <div>
      <div className="dv-section-label mb-0.5">{title}</div>
      {items.length === 0 ? (
        <div className="text-[10px] text-dv-muted">{empty}</div>
      ) : (
        <ul className="space-y-0.5">
          {items.map((item) => {
            const selected = active?.kind === kind && active.id === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className={`w-full text-left px-1 py-0.5 rounded-sm text-[10px] truncate ${
                    selected ? 'bg-dv-accent/20 text-dv-accent' : 'hover:bg-dv-surface'
                  }`}
                  onClick={() => onPick(item.id)}
                >
                  {item.class_name || '?'}
                  {typeof item.confidence === 'number'
                    ? ` · ${(item.confidence * 100).toFixed(0)}%`
                    : ''}
                  {item.gps_lat != null && item.gps_lon != null
                    ? ` · GPS ${item.gps_lat.toFixed(5)},${item.gps_lon.toFixed(5)}`
                    : ''}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ChangeMovedList({
  matches,
  active,
  onPick,
}: {
  matches: ChangeMatch[];
  active: { kind: string; id: string } | null;
  onPick: (id: string) => void;
}) {
  return (
    <div>
      <div className="dv-section-label mb-0.5">Перемещены</div>
      {matches.length === 0 ? (
        <div className="text-[10px] text-dv-muted">нет</div>
      ) : (
        <ul className="space-y-0.5">
          {matches.map((m) => {
            const selected = active?.kind === 'moved' && active.id === m.before_id;
            return (
              <li key={m.before_id}>
                <button
                  type="button"
                  className={`w-full text-left px-1 py-0.5 rounded-sm text-[10px] truncate ${
                    selected ? 'bg-dv-accent/20 text-dv-accent' : 'hover:bg-dv-surface'
                  }`}
                  onClick={() => onPick(m.before_id)}
                >
                  {m.class_name || '?'} · {m.distance_m.toFixed(1)} m
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function formatTs(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

const ClassCombobox: React.FC<{
  catalog: ClassCatalogItem[];
  valueId: number | undefined;
  valueName: string;
  disabled?: boolean;
  onSelect: (item: ClassCatalogItem) => void;
  onCustomLabel?: (label: string) => void;
}> = ({ catalog, valueId, valueName, disabled, onSelect, onCustomLabel }) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return catalog.slice(0, 238);
    return catalog.filter((c) => {
      const id = String(c.id);
      const ru = (c.name_ru || classLabelRu(c.id, c.name_en, catalog)).toLowerCase();
      return (
        id === q ||
        c.name_en.toLowerCase().includes(q) ||
        c.name_raw.toLowerCase().includes(q) ||
        ru.includes(q) ||
        c.name_en.replace(/_/g, ' ').includes(q)
      );
    });
  }, [catalog, query]);

  const current = catalog.find((c) => c.id === valueId);
  const currentLabel = current
    ? classDisplayLine(current.id, current.name_en, catalog)
    : valueName
      ? classLabelRu(valueId, valueName, catalog)
      : 'Выберите класс';

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        className="w-full text-left px-2 py-1 bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] rounded-sm flex items-center gap-1 disabled:opacity-40"
        onClick={() => {
          setQuery('');
          setOpen((v) => !v);
        }}
      >
        <Search size={11} className="text-[var(--dv-text-muted)] shrink-0" />
        <span className="truncate">{currentLabel}</span>
      </button>
      {open && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-dv-panel border border-dv-border shadow-xl">
          <input
            autoFocus
            className="w-full bg-dv-deep border-b border-dv-border px-2 py-1 text-[11px]"
            placeholder="Поиск по 238 классам…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="max-h-48 overflow-auto">
            {filtered.length === 0 && query.trim() && onCustomLabel ? (
              <button
                type="button"
                className="w-full text-left px-2 py-2 text-[11px] hover:bg-dv-hover text-dv-accent"
                onClick={() => {
                  onCustomLabel(query.trim());
                  setOpen(false);
                }}
              >
                Своя метка: «{query.trim()}»
              </button>
            ) : filtered.length === 0 ? (
              <div className="px-2 py-2 text-[10px] text-dv-muted">Нет совпадений</div>
            ) : null}
            {filtered.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`w-full text-left px-2 py-1 text-[11px] hover:bg-dv-hover ${
                  c.id === valueId ? 'bg-dv-surface text-dv-accent' : ''
                }`}
                onClick={() => {
                  onSelect(c);
                  setOpen(false);
                }}
              >
                <span className="font-mono text-[10px] text-dv-muted mr-1">{c.id}</span>
                {classDisplayLine(c.id, c.name_en, catalog)}
                {c.is_model_class ? (
                  <span className="ml-1 text-[9px] text-dv-accent">модель</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export const Inspector: React.FC = () => {
  const detections = useMuraveiStore((s) => s.detections);
  const active = useMuraveiStore((s) => s.activeDetection);
  const activeDetectionId = useMuraveiStore((s) => s.activeDetectionId);
  const classCatalog = useMuraveiStore((s) => s.classCatalog);
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const setActiveDetection = useMuraveiStore((s) => s.setActiveDetection);
  const setActiveDetectionId = useMuraveiStore((s) => s.setActiveDetectionId);
  const hydrateDetections = useMuraveiStore((s) => s.hydrateDetections);
  const clearDetections = useMuraveiStore((s) => s.clearDetections);
  const deleteAllForSource = useMuraveiStore((s) => s.deleteAllForSource);
  const loadClassCatalog = useMuraveiStore((s) => s.loadClassCatalog);
  const patchDetection = useMuraveiStore((s) => s.patchDetection);
  const deleteDetection = useMuraveiStore((s) => s.deleteDetection);
  const dismissDetection = useMuraveiStore((s) => s.dismissDetection);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const setSource = useViewerStore((s) => s.setSource);
  const [notes, setNotes] = useState('');
  const [listQuery, setListQuery] = useState('');
  const notesTimer = useRef<number | null>(null);
  const notesTargetIdRef = useRef<string | null>(null);
  const [aiModels, setAiModels] = useState<{ name: string }[]>([]);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [aiModel, setAiModel] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiText, setAiText] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [autolabelBusy, setAutolabelBusy] = useState(false);
  const [autolabelProposal, setAutolabelProposal] = useState<{
    class_id: number;
    class_name: string;
    name_ru: string;
    confidence: number;
    reason: string;
  } | null>(null);
  const [similarBusy, setSimilarBusy] = useState(false);
  const [similar, setSimilar] = useState<SimilarHit[]>([]);
  const [similarMethod, setSimilarMethod] = useState<string | null>(null);
  const [similarError, setSimilarError] = useState<string | null>(null);
  const [show3dBusy, setShow3dBusy] = useState(false);
  const [folds, setFolds] = useState<FoldState>(() => loadFolds());
  const requestRaycast = useReconStore((s) => s.requestRaycast);
  const setViewMode = useReconStore((s) => s.setViewMode);
  const openPanel = usePanelLayoutStore((s) => s.openPanel);
  const isPanelVisible = usePanelLayoutStore((s) => s.isPanelVisible);
  const sourcePath = useViewerStore((s) => s.viewers[focusedViewerId]?.sourcePath);
  const compareMode = useViewerStore((s) => s.compareMode);
  const cdResult = useChangeDetectionStore((s) => s.result);
  const cdError = useChangeDetectionStore((s) => s.error);
  const cdLoading = useChangeDetectionStore((s) => s.loading);
  const cdActiveHighlight = useChangeDetectionStore((s) => s.activeHighlight);
  const setCdHighlight = useChangeDetectionStore((s) => s.setActiveHighlight);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const mediaDuration = useTimelineStore((s) => s.mediaDuration);
  const {
    manifest: reconManifest,
    hasRecon,
    reconMessage,
    reconRunning,
    pct: reconPct,
    startRecon,
    stopRecon,
  } = useReconBuild(sourcePath, isAuthenticated);
  const persisted: PersistedDetection | undefined = detections.find((d) => d.id === activeDetectionId);
  const canEdit = Boolean(persisted);
  notesTargetIdRef.current = persisted?.id ?? null;

  const toggleFold = useCallback((key: FoldKey) => {
    setFolds((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(FOLDS_KEY, JSON.stringify(next));
      } catch {
        /* ignore quota */
      }
      return next;
    });
  }, []);

  const reconAnchorSec = persisted?.time_sec ?? playheadPosition;
  const plannedSegment = computeReconSegment(reconAnchorSec, mediaDuration);

  const detectionOutsideRecon =
    Boolean(persisted && reconManifest) &&
    (persisted!.time_sec < (reconManifest!.t_start - 0.5) ||
      persisted!.time_sec > (reconManifest!.t_end + 0.5));

  const showIn3D = async () => {
    if (!persisted || !sourcePath) return;
    if (reconManifest) {
      const { t_start, t_end } = reconManifest;
      if (persisted.time_sec < t_start - 0.5 || persisted.time_sec > t_end + 0.5) {
        setSimilarError(
          `Детекция вне сегмента 3D (${formatTs(t_start)}–${formatTs(t_end)}). ` +
            'Переместите playhead в сегмент или постройте 3D для этого участка.',
        );
        return;
      }
    }
    setShow3dBusy(true);
    try {
      const res = await fetch(
        `/api/recon/poses?video_path=${encodeURIComponent(sourcePath)}&time_sec=${persisted.time_sec}`,
        { headers: authHeaders() },
      );
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { detail?: string };
        setSimilarError(
          err.detail || 'Нет 3D-сцены — нажмите «Построить 3D» в Inspector',
        );
        return;
      }
      const data = (await res.json()) as {
        pose: { image_size: { width: number; height: number } };
      };
      const { u, v } = bboxCenterPixels(xyxyFromRow(persisted), data.pose.image_size);
      if (!isPanelVisible('flight3d')) openPanel('flight3d');
      setViewMode('scene');
      requestRaycast({
        detectionId: persisted.id,
        timeSec: persisted.time_sec,
        u,
        v,
        className: persisted.class_name,
        aiClassName: persisted.ai_class_name ?? undefined,
      });
    } catch (err: unknown) {
      setSimilarError(err instanceof Error ? err.message : 'Ошибка 3D');
    } finally {
      setShow3dBusy(false);
    }
  };

  const runAutolabel = async () => {
    if (!persisted) return;
    setAutolabelBusy(true);
    setAiError(null);
    setAutolabelProposal(null);
    try {
      const res = await fetch('/api/ai/autolabel', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          detection_id: persisted.id,
          model: aiModel || undefined,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        detail?: string;
        proposal?: typeof autolabelProposal;
      };
      if (!res.ok || !data.proposal) {
        throw new Error(data.detail || 'Ollama не вернула предложение');
      }
      setAutolabelProposal(data.proposal);
    } catch (error) {
      setAiError(error instanceof Error ? error.message : 'Ошибка автоклассификации');
    } finally {
      setAutolabelBusy(false);
    }
  };

  const acceptAutolabel = async () => {
    if (!persisted || !autolabelProposal) return;
    await patchDetection(persisted.id, {
      class_id: autolabelProposal.class_id,
      class_name: autolabelProposal.class_name,
      confidence: autolabelProposal.confidence,
    });
    setAutolabelProposal(null);
  };

  useEffect(() => {
    if (!isAuthenticated) return;
    void loadClassCatalog();
  }, [isAuthenticated, loadClassCatalog]);

  useEffect(() => {
    setAutolabelProposal(null);
  }, [activeDetectionId]);

  useEffect(() => {
    if (!isAuthenticated) return;
    if (!sourcePath) {
      clearDetections();
      return;
    }
    void hydrateDetections(sourcePath);
  }, [isAuthenticated, sourcePath, hydrateDetections, clearDetections]);

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    void fetch('/api/ai/models', { headers: authHeaders() })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data: { available?: boolean; models?: { name: string }[]; message?: string }) => {
        if (cancelled) return;
        const models = Array.isArray(data.models) ? data.models : [];
        setAiAvailable(Boolean(data.available) && models.length > 0);
        setAiModels(models);
        setAiModel(models[0]?.name || '');
        if (!data.available) setAiError(data.message || AI_UNAVAILABLE);
        else setAiError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setAiAvailable(false);
        setAiModels([]);
        setAiError(AI_UNAVAILABLE);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    if (notesTimer.current) {
      window.clearTimeout(notesTimer.current);
      notesTimer.current = null;
    }
    setNotes(persisted?.user_notes ?? active?.notes ?? '');
    setAiText(null);
    setSimilar([]);
    setSimilarError(null);
  }, [persisted?.id, persisted?.user_notes, active?.id, active?.notes]);

  useEffect(() => {
    return () => {
      if (notesTimer.current) {
        window.clearTimeout(notesTimer.current);
        notesTimer.current = null;
      }
    };
  }, []);

  const onNotesChange = (value: string) => {
    setNotes(value);
    if (!persisted) return;
    if (notesTimer.current) window.clearTimeout(notesTimer.current);
    notesTimer.current = window.setTimeout(() => {
      const id = notesTargetIdRef.current;
      if (!id) return;
      void patchDetection(id, { user_notes: value });
    }, 400);
  };

  const removeActive = () => {
    if (persisted) {
      void deleteDetection(persisted.id);
      return;
    }
    if (!active) return;
    void dismissDetection(active, active.source_video || 'local', active.time_sec ?? 0);
  };

  const runFindSimilar = async () => {
    if (!persisted?.id) {
      setSimilarError('Сначала зафиксируйте детекцию');
      return;
    }
    setSimilarBusy(true);
    setSimilarError(null);
    try {
      const res = await fetch('/api/detections/find-similar', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ detection_id: persisted.id, top_k: 12, same_class: true }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setSimilarError(typeof data.detail === 'string' ? data.detail : 'find-similar failed');
        setSimilar([]);
        setSimilarMethod(null);
        return;
      }
      setSimilar(Array.isArray(data.results) ? data.results : []);
      setSimilarMethod(typeof data.method === 'string' ? data.method : null);
    } catch {
      setSimilarError('find-similar failed');
    } finally {
      setSimilarBusy(false);
    }
  };

  const jumpToDetection = (row: PersistedDetection) => {
    const needsSource =
      row.source_video &&
      !mediaPathsMatch(
        useViewerStore.getState().viewers[focusedViewerId]?.sourcePath ?? '',
        row.source_video,
      );
    if (needsSource && row.source_video) {
      setSource(focusedViewerId, row.source_video, null);
    }
    useViewerStore.getState().setFocusedViewer(focusedViewerId);
    useTimelineStore.getState().pause();
    useTimelineStore.getState().setPendingJump(row.time_sec);
    seekTo(row.time_sec);
    setActiveDetection(toDetectedObject(row, classCatalog));
  };

  const jumpToSimilar = async (row: SimilarHit) => {
    const stub: PersistedDetection = {
      id: row.id,
      created_at: 0,
      source_video: row.source_video || '',
      time_sec: row.time_sec,
      frame_idx: 0,
      class_id: row.class_id ?? 0,
      class_name: row.class_name,
      confidence: 0,
      bbox_x: 0,
      bbox_y: 0,
      bbox_w: 0.1,
      bbox_h: 0.1,
      crop_path: row.crop_path,
      is_edited: false,
      user_notes: '',
      is_deleted: false,
      origin: 'auto',
    };
    jumpToDetection(stub);
    if (row.source_video) {
      await hydrateDetections(row.source_video);
      setActiveDetectionId(row.id);
    }
  };

  const runAnalyze = async () => {
    setAiBusy(true);
    setAiText(null);
    setAiError(null);
    try {
      const aiGuess = persisted?.ai_class_name || active?.ai_class_name;
      const operatorClass = persisted?.class_name || active?.class_en;
      const confPct = (((active?.confidence ?? persisted?.confidence) || 0) * 100).toFixed(1);
      const prompt = [
        '1) Опиши, что видно на приложенном изображении (форма, цвет, материал, контекст).',
        '2) Согласуется ли это с метками ниже?',
        '3) Что проверить оператору на месте?',
        aiGuess
          ? `Метка YOLO (может быть неверной): ${classLabelRu(undefined, aiGuess, classCatalog)} (${aiGuess}), ${confPct}%`
          : `Уверенность детекции: ${confPct}%`,
        operatorClass && operatorClass !== aiGuess
          ? `Метка оператора: ${classLabelRu(persisted?.class_id, operatorClass, classCatalog)}`
          : '',
        notes ? `Заметки: ${notes}` : '',
        'Не выдумывай то, чего нет на кадре.',
      ]
        .filter(Boolean)
        .join('\n');

      let imageBase64: string | undefined;
      if (persisted?.id) {
        imageBase64 = (await fetchDetectionCropBase64(persisted.id)) ?? undefined;
      }

      const res = await fetch('/api/ai/analyze', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          prompt,
          model: aiModel || undefined,
          detection_id: persisted?.id,
          image_base64: imageBase64,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        analysis?: string;
        had_image?: boolean;
        detail?: string;
      };
      if (!res.ok) {
        setAiError(data.detail || AI_UNAVAILABLE);
        return;
      }
      const text = typeof data.analysis === 'string' ? data.analysis.trim() : '';
      if (!text) {
        setAiError(AI_UNAVAILABLE);
        return;
      }
      if (data.had_image === false) {
        setAiError('Кроп не найден — ответ только по тексту меток (без просмотра кадра).');
      }
      setAiText(text);
    } catch {
      setAiError(AI_UNAVAILABLE);
    } finally {
      setAiBusy(false);
    }
  };

  useEffect(() => {
    // Delete / Backspace soft-delete of active detection is handled globally
    // in src/hooks/useHotkeys.ts, which dispatches 'muravei:delete-active'.
    const onDelete = () => removeActive();
    window.addEventListener('muravei:delete-active', onDelete);
    return () => window.removeEventListener('muravei:delete-active', onDelete);
  }, [active, persisted]);

  const recent = useMemo(() => {
    const q = listQuery.trim().toLowerCase();
    const scoped = sourcePath
      ? detections.filter((row) => mediaPathsMatch(row.source_video || '', sourcePath))
      : [];
    const rows = [...scoped].reverse();
    if (!q) return rows;
    return rows.filter((row) => {
      const notesText = (row.user_notes || '').toLowerCase();
      const name = row.class_name.toLowerCase();
      const spaced = name.replace(/_/g, ' ');
      return name.includes(q) || spaced.includes(q) || notesText.includes(q) || String(row.class_id) === q;
    });
  }, [detections, listQuery, sourcePath]);

  const clearAllForVideo = () => {
    if (!sourcePath) return;
    if (!window.confirm('Удалить все детекции этого видео?')) return;
    void deleteAllForSource(sourcePath);
  };

  const activeStatus = active
    ? classLabelRu(active.class_id, active.class_en || active.class_ru, classCatalog)
    : 'нет';
  const reconStatus = reconRunning
    ? `${reconPct}%`
    : reconManifest
      ? reconManifest.status
      : 'нет сцены';
  const similarStatus =
    similar.length > 0
      ? `${similar.length}${similarMethod === 'clip' ? ' · CLIP' : similarMethod === 'hist+class' ? ' · гист.' : ''}`
      : similarMethod === 'clip'
        ? 'CLIP'
        : similarMethod === 'hist+class'
          ? 'гист.'
          : undefined;
  const aiStatus = aiBusy ? '…' : aiText ? 'готово' : undefined;

  return (
    <div className="h-full flex flex-col text-xs min-h-0">
      <div className="flex-shrink-0 max-h-[55%] overflow-auto border-b border-dv-border">
        <FoldSection
          open={folds.active}
          onToggle={() => toggleFold('active')}
          title="Активная детекция"
          status={activeStatus}
        >
          {active ? (
            <div className="space-y-2.5">
              {canEdit && persisted?.crop_path ? (
                <div>
                  <div className="dv-section-label mb-1">Кроп</div>
                  <img
                    src={detectionCropSrc(persisted.id, persisted.crop_path)}
                    alt={persisted.class_name}
                    className="w-full max-h-28 object-contain bg-dv-deep border border-dv-border"
                  />
                </div>
              ) : null}
              <div>
                <div className="dv-section-label mb-1">Класс</div>
                <ClassCombobox
                  catalog={classCatalog}
                  valueId={persisted?.class_id ?? active.class_id}
                  valueName={active.class_en || active.class_ru}
                  disabled={!canEdit}
                  onSelect={(item) => {
                    if (!persisted) return;
                    void patchDetection(persisted.id, { class_id: item.id, class_name: item.name_en });
                  }}
                  onCustomLabel={(label) => {
                    if (!persisted) return;
                    void patchDetection(persisted.id, {
                      user_notes: notes ? `${notes}\nМетка: ${label}` : `Метка: ${label}`,
                    });
                  }}
                />
              </div>
              {persisted?.ai_class_name && persisted.ai_class_name !== persisted.class_name ? (
                <div className="text-[10px] text-dv-muted">
                  ИИ: {classLabelRu(undefined, persisted.ai_class_name, classCatalog)} · Оператор:{' '}
                  {classLabelRu(persisted.class_id, persisted.class_name, classCatalog)}
                </div>
              ) : null}
              {canEdit && (
                <div className="space-y-1">
                  <button
                    type="button"
                    disabled={autolabelBusy || !persisted?.crop_path || !aiAvailable}
                    className="w-full px-2 py-1 bg-dv-surface hover:bg-dv-hover rounded-sm disabled:opacity-40 text-[10px]"
                    onClick={() => void runAutolabel()}
                  >
                    {autolabelBusy ? 'Ollama анализирует…' : 'Предложить класс через Ollama'}
                  </button>
                  {autolabelProposal && (
                    <div className="border border-dv-border bg-dv-deep p-1.5 text-[10px] space-y-1">
                      <div>
                        {autolabelProposal.name_ru || autolabelProposal.class_name} ·{' '}
                        {(autolabelProposal.confidence * 100).toFixed(0)}%
                      </div>
                      {autolabelProposal.reason && (
                        <div className="text-dv-muted">{autolabelProposal.reason}</div>
                      )}
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="text-emerald-400"
                          onClick={() => void acceptAutolabel()}
                        >
                          Принять
                        </button>
                        <button
                          type="button"
                          className="text-red-400"
                          onClick={() => setAutolabelProposal(null)}
                        >
                          Отклонить
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
              <div>
                <div className="dv-section-label mb-1">Уверенность</div>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-dv-deep rounded-sm overflow-hidden border border-dv-border">
                    <div
                      className="h-full bg-dv-accent"
                      style={{ width: `${Math.min(100, active.confidence * 100)}%` }}
                    />
                  </div>
                  <span className="font-mono text-[10px] text-dv-muted w-12 text-right">
                    {(active.confidence * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="text-[10px] text-dv-muted mt-0.5">
                  {originLabel(active.origin ?? persisted?.origin)}
                  {active.is_edited ? ' · правлен' : ''}
                </div>
              </div>
              {canEdit && (
                <div>
                  <div className="dv-section-label mb-1">GPS</div>
                  {persisted?.gps_lat != null && persisted?.gps_lon != null ? (
                    <div className="font-mono text-[10px] text-dv-text space-y-0.5">
                      <div>
                        {persisted.gps_lat.toFixed(6)}, {persisted.gps_lon.toFixed(6)}
                      </div>
                      {persisted.gps_alt != null ? (
                        <div className="text-dv-muted">alt {persisted.gps_alt.toFixed(1)} m</div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="text-[10px] text-dv-muted">нет телеметрии</div>
                  )}
                </div>
              )}
              {!canEdit && (
                <div className="text-[10px] text-dv-accent">
                  Зафиксируйте кадр, чтобы сохранить объект в SQLite
                </div>
              )}
              <div>
                <label className="dv-section-label block mb-1">Заметки</label>
                <textarea
                  disabled={!canEdit}
                  className="w-full h-16 bg-dv-deep border border-dv-border px-2 py-1 text-[11px] resize-none disabled:opacity-40"
                  value={notes}
                  onChange={(e) => onNotesChange(e.target.value)}
                  placeholder={canEdit ? 'Заметки оператора…' : 'Зафиксируйте кадр для правок'}
                />
              </div>
              <button
                type="button"
                onClick={removeActive}
                className="px-2 py-1 bg-dv-surface hover:bg-[#4a2222] rounded-sm flex items-center gap-1 text-dv-danger"
              >
                <Trash2 size={12} />
                Удалить
              </button>
            </div>
          ) : (
            <div className="text-dv-muted text-[11px] py-1">
              Выберите bbox во вьюере или зафиксируйте кадр
            </div>
          )}
        </FoldSection>

        <FoldSection
          open={folds.recon}
          onToggle={() => toggleFold('recon')}
          title="3D реконструкция"
          icon={<Box size={12} className="text-dv-accent shrink-0" />}
          status={reconStatus}
        >
          <div className="text-[10px] text-dv-muted leading-snug">
            {reconRunning ? (
              <>
                Сегмент: {formatTs(plannedSegment.tStart)}–{formatTs(plannedSegment.tEnd)}
              </>
            ) : reconManifest ? (
              <>
                Готово · {formatTs(reconManifest.t_start)}–{formatTs(reconManifest.t_end)} ·{' '}
                {reconManifest.status}
              </>
            ) : (
              <>
                Сегмент для построения: {formatTs(plannedSegment.tStart)}–
                {formatTs(plannedSegment.tEnd)}
                {persisted ? ' (вокруг детекции)' : ' (от playhead)'}
              </>
            )}
          </div>
          {detectionOutsideRecon && !reconRunning && (
            <div className="text-[10px] text-dv-danger leading-snug">
              Детекция вне текущего 3D-сегмента. Постройте 3D для участка{' '}
              {formatTs(plannedSegment.tStart)}–{formatTs(plannedSegment.tEnd)}.
            </div>
          )}
          {reconRunning ? (
            <>
              <div className="flex items-center justify-between gap-2 text-[10px]">
                <span className="text-dv-text truncate" title={reconMessage}>
                  {reconMessage || 'Обработка…'}
                </span>
                <span className="font-mono text-dv-accent shrink-0">{reconPct}%</span>
              </div>
              <div className="h-2 bg-dv-deep border border-dv-border rounded-sm overflow-hidden">
                <div
                  className="h-full bg-dv-accent transition-[width] duration-300"
                  style={{ width: `${reconPct}%` }}
                />
              </div>
              <button
                type="button"
                className="px-2 py-1 bg-dv-surface hover:bg-dv-hover rounded-sm text-[10px]"
                onClick={() => void stopRecon()}
              >
                Остановить
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={!sourcePath || !isAuthenticated}
              className="w-full px-2 py-1.5 bg-dv-accent text-black font-medium rounded-sm disabled:opacity-40 text-[11px]"
              onClick={() =>
                void startRecon({
                  tStart: plannedSegment.tStart,
                  tEnd: plannedSegment.tEnd,
                  openSceneOnDone: true,
                })
              }
            >
              Построить 3D
            </button>
          )}
          {!reconRunning && reconPct === 100 && reconMessage && (
            <div className="text-[10px] text-emerald-400">{reconMessage}</div>
          )}
          <button
            type="button"
            disabled={!hasRecon || show3dBusy || !canEdit}
            title={hasRecon ? 'Raycast в 3D-сцену' : 'Сначала постройте 3D'}
            className="w-full px-2 py-1 bg-dv-surface hover:bg-dv-hover rounded-sm flex items-center justify-center gap-1 disabled:opacity-40 text-[11px]"
            onClick={() => void showIn3D()}
          >
            <Box size={12} />
            {show3dBusy ? '3D…' : 'Показать в 3D'}
          </button>
        </FoldSection>

        <FoldSection
          open={folds.similar}
          onToggle={() => toggleFold('similar')}
          title="Похожие"
          icon={<Images size={12} className="text-dv-accent shrink-0" />}
          status={similarStatus}
        >
          <button
            type="button"
            disabled={similarBusy || !canEdit}
            className="px-2 py-1 bg-dv-surface hover:bg-dv-hover rounded-sm flex items-center gap-1 disabled:opacity-40"
            onClick={() => void runFindSimilar()}
          >
            <Images size={12} />
            {similarBusy ? 'Поиск…' : 'Найти похожие'}
          </button>
          {similarMethod ? (
            <div className="text-[10px] text-dv-muted">
              Метод: {similarMethod === 'clip' ? 'CLIP (изображение)' : 'гистограмма'}
            </div>
          ) : null}
          {similarError && <div className="text-[10px] text-dv-danger">{similarError}</div>}
          {similar.length > 0 && (
            <div className="max-h-40 overflow-auto space-y-0.5">
              {similar.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className="w-full text-left text-[10px] px-1 py-0.5 hover:bg-dv-surface rounded-sm flex items-center gap-1.5"
                  onClick={() => void jumpToSimilar(row)}
                >
                  <img
                    src={detectionCropSrc(row.id, row.crop_path)}
                    alt=""
                    className="w-8 h-8 object-cover bg-dv-deep border border-dv-border shrink-0"
                  />
                  <span className="min-w-0 truncate">
                    <span className="font-mono text-dv-muted mr-1">
                      {(row.similarity * 100).toFixed(0)}%
                    </span>
                    {classLabelRu(undefined, row.class_name, classCatalog)} · {formatTs(row.time_sec)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </FoldSection>

        <FoldSection
          open={folds.ai}
          onToggle={() => toggleFold('ai')}
          title="Анализ ИИ"
          icon={<Brain size={12} className="text-dv-accent shrink-0" />}
          status={aiStatus}
        >
          {aiAvailable && aiModels.length > 0 && (
            <select
              className="w-full bg-dv-deep border border-dv-border px-1 py-1 text-[10px]"
              value={aiModel}
              onChange={(e) => setAiModel(e.target.value)}
            >
              {aiModels.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            disabled={aiBusy || !aiAvailable || !persisted?.id}
            title={
              !persisted?.id
                ? 'Сначала зафиксируйте детекцию (кнопка «Кадр» во Viewer)'
                : 'Vision-анализ кропа через Ollama'
            }
            className="px-2 py-1 bg-dv-surface hover:bg-dv-hover rounded-sm flex items-center gap-1 disabled:opacity-40"
            onClick={() => void runAnalyze()}
          >
            <Brain size={12} />
            {aiBusy ? 'Запрос…' : 'Анализ ИИ'}
          </button>
          {aiError && <div className="text-[10px] text-dv-danger">{aiError}</div>}
          {aiText && (
            <pre className="whitespace-pre-wrap text-[10px] text-dv-text bg-dv-deep border border-dv-border p-1.5 max-h-36 overflow-auto">
              {aiText}
            </pre>
          )}
        </FoldSection>

        {compareMode && (cdResult || cdLoading || cdError) ? (
          <FoldSection
            open={folds.changes}
            onToggle={() => toggleFold('changes')}
            title="Изменения (Compare)"
            status={
              cdResult
                ? `+${cdResult.summary.new} −${cdResult.summary.removed} ↔${cdResult.summary.moved}`
                : cdLoading
                  ? '…'
                  : 'ошибка'
            }
          >
            {cdLoading && !cdResult ? (
              <div className="text-[10px] text-dv-muted px-1">Анализ…</div>
            ) : null}
            {cdError ? <div className="text-[10px] text-dv-danger px-1">{cdError}</div> : null}
            {cdResult ? (
              <div className="space-y-2 px-1">
                <div className="text-[10px] text-dv-muted font-mono">
                  {cdResult.summary.total_before} → {cdResult.summary.total_after} obj · {cdResult.method}
                  {cdResult.message ? ` · ${cdResult.message}` : ''}
                </div>
                <ChangeList
                  title="Новые"
                  empty="нет"
                  items={cdResult.new}
                  kind="new"
                  active={cdActiveHighlight}
                  onPick={(id) => setCdHighlight({ kind: 'new', id })}
                />
                <ChangeList
                  title="Исчезли"
                  empty="нет"
                  items={cdResult.removed}
                  kind="removed"
                  active={cdActiveHighlight}
                  onPick={(id) => setCdHighlight({ kind: 'removed', id })}
                />
                <ChangeMovedList
                  matches={cdResult.matches.filter((m) => m.status === 'moved')}
                  active={cdActiveHighlight}
                  onPick={(id) => setCdHighlight({ kind: 'moved', id })}
                />
              </div>
            ) : null}
          </FoldSection>
        ) : null}
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        <FoldSection
          open={folds.detections}
          onToggle={() => toggleFold('detections')}
          title={`Детекции (${recent.length}/${detections.length})`}
          status={`${recent.length}/${detections.length}`}
          className={`border-b border-dv-border flex flex-col min-h-0 ${folds.detections ? 'flex-1' : 'flex-shrink-0'}`}
          bodyClassName="flex flex-col min-h-0 flex-1"
        >
          <div className="px-2 pb-1.5">
            <div className="flex items-center gap-1 bg-dv-deep border border-dv-border px-1.5 py-1">
              <Search size={11} className="text-dv-muted shrink-0" />
              <input
                className="w-full bg-transparent text-[11px] outline-none"
                placeholder="поиск класса…"
                value={listQuery}
                onChange={(e) => setListQuery(e.target.value)}
              />
              <button
                type="button"
                className="shrink-0 px-1.5 py-0.5 text-[10px] text-dv-danger hover:bg-dv-hover rounded-sm disabled:opacity-40"
                title="Очистить все детекции этого видео"
                disabled={!sourcePath || recent.length === 0}
                onClick={clearAllForVideo}
              >
                Очистить
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-auto min-h-0">
            {recent.length === 0 && (
              <div className="p-3 text-dv-muted text-[11px]">
                Зафиксируйте кадр на паузе или нарисуйте рамку в режиме «Правка»
              </div>
            )}
            {recent.map((row) => {
              const on = row.id === activeDetectionId;
              return (
                <button
                  key={row.id}
                  type="button"
                  className={`w-full text-left px-2 py-1.5 border-b border-dv-soft hover:bg-dv-surface ${
                    on ? 'bg-dv-header shadow-[inset_2px_0_0_var(--dv-accent)]' : ''
                  }`}
                  onClick={() => jumpToDetection(row)}
                >
                  <div className="flex items-center gap-1">
                    <Flag size={10} className="text-dv-accent" />
                    <span className="font-mono text-[10px]">{formatTs(row.time_sec)}</span>
                    <span className="truncate text-dv-text flex-1">
                      {classLabelRu(row.class_id, row.class_name, classCatalog)}
                      {row.ai_class_name && row.ai_class_name !== row.class_name
                        ? ` (ИИ: ${classLabelRu(undefined, row.ai_class_name, classCatalog)})`
                        : ''}
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      className="p-0.5 rounded hover:bg-[#4a2222] text-dv-muted hover:text-dv-danger"
                      title="Удалить метку"
                      onClick={(e) => {
                        e.stopPropagation();
                        void deleteDetection(row.id);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void deleteDetection(row.id);
                      }}
                    >
                      <Trash2 size={11} />
                    </span>
                  </div>
                  {row.user_notes ? (
                    <div className="text-[10px] text-dv-muted truncate pl-4">{row.user_notes}</div>
                  ) : null}
                </button>
              );
            })}
          </div>
        </FoldSection>
      </div>
    </div>
  );
};

export default Inspector;
