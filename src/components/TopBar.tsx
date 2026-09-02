import React, { useState, useRef, useEffect } from 'react';
import {
  AlertTriangle,
  Brain,
  Bug,
  Clapperboard,
  FileText,
  Film,
  Globe2,
  GraduationCap,
  LayoutGrid,
  Monitor,
  Radio,
  Settings,
  User,
} from 'lucide-react';
import {
  ALL_VIEW_IDS,
  VIEW_TITLES,
  WORKSPACE_TABS,
  type ViewId,
} from '../layout/initialLayout';
import { usePanelLayoutStore } from '../store/usePanelLayoutStore';
import { useMuraveiStore } from '../store/useMuraveiStore';
import { useViewerStore } from '../store/useViewerStore';
import { downloadAuthorized } from '../lib/download';
import { logger } from '../services/logger';
import { Button, Menu, MenuItem, Modal } from './ui';

interface TopBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  isDefaultLayout?: boolean;
  onResetLayout?: () => void;
}

function parseDetail(body: unknown): string {
  if (!body || typeof body !== 'object') return 'Ошибка входа';
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  return 'Ошибка входа';
}

const TAB_ICONS: Record<string, React.ReactNode> = {
  Медиа: <Film size={12} />,
  Монтаж: <Clapperboard size={12} />,
  'AI-анализ': <Brain size={12} />,
  Обучение: <GraduationCap size={12} />,
  '4×Live': <Radio size={12} />,
  Система: <Settings size={12} />,
};

export const TopBar: React.FC<TopBarProps> = ({
  activeTab,
  onTabChange,
  onResetLayout,
}) => {
  const [windowOpen, setWindowOpen] = useState(false);
  const [layoutOpen, setLayoutOpen] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [pin, setPin] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [ollamaOk, setOllamaOk] = useState<boolean | null>(null);
  const [yoloMode, setYoloMode] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const openPanel = usePanelLayoutStore((s) => s.openPanel);
  const closePanel = usePanelLayoutStore((s) => s.closePanel);
  const isPanelVisible = usePanelLayoutStore((s) => s.isPanelVisible);
  const applyPreset = usePanelLayoutStore((s) => s.applyPreset);
  const setAuthenticated = useMuraveiStore((s) => s.setAuthenticated);
  const setUserRole = useMuraveiStore((s) => s.setUserRole);
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const userRole = useMuraveiStore((s) => s.userRole);
  const hydrateDetections = useMuraveiStore((s) => s.hydrateDetections);
  const loadClassCatalog = useMuraveiStore((s) => s.loadClassCatalog);
  const resetSession = useMuraveiStore((s) => s.resetSession);

  useEffect(() => {
    const token = localStorage.getItem('muravei-token');
    if (!token) return;
    void fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => {
        setAuthenticated(true);
        setUserRole(data.role);
        void loadClassCatalog();
        const path = useViewerStore.getState().viewers[useViewerStore.getState().focusedViewerId]
          ?.sourcePath;
        if (path) void hydrateDetections(path);
      })
      .catch(() => {
        localStorage.removeItem('muravei-token');
      });
  }, [setAuthenticated, setUserRole, loadClassCatalog, hydrateDetections]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) {
        setWindowOpen(false);
        setLayoutOpen(false);
        setSessionOpen(false);
        setExportOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setOllamaOk(null);
      return;
    }
    let cancelled = false;
    const poll = () => {
      const token = localStorage.getItem('muravei-token');
      void fetch('/api/ai/models', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((res) => (res.ok ? res.json() : Promise.reject()))
        .then((data: { available?: boolean; models?: unknown[] }) => {
          if (cancelled) return;
          const models = Array.isArray(data.models) ? data.models : [];
          setOllamaOk(Boolean(data.available) && models.length > 0);
        })
        .catch(() => {
          if (!cancelled) setOllamaOk(false);
        });
    };
    poll();
    const t = window.setInterval(poll, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [isAuthenticated]);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      void fetch('/api/health')
        .then((res) => (res.ok ? res.json() : Promise.reject()))
        .then((data: { yolo_mode?: string }) => {
          if (!cancelled) setYoloMode(data.yolo_mode ?? null);
        })
        .catch(() => {
          if (!cancelled) setYoloMode(null);
        });
    };
    poll();
    const t = window.setInterval(poll, 20000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const togglePanel = (id: ViewId) => {
    if (isPanelVisible(id)) closePanel(id);
    else openPanel(id);
  };

  const login = async () => {
    setAuthError(null);
    if (!/^\d{7}$/.test(pin)) {
      setAuthError('PIN должен быть из 7 цифр');
      return;
    }
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(parseDetail(data));
      localStorage.setItem('muravei-token', data.token);
      setAuthenticated(true);
      setUserRole(data.role);
      void loadClassCatalog();
      const path = useViewerStore.getState().viewers[useViewerStore.getState().focusedViewerId]
        ?.sourcePath;
      if (path) void hydrateDetections(path);
      setPin('');
      setLoginOpen(false);
      logger.info('auth', `Вход: роль ${data.role}`);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Ошибка входа');
    }
  };

  const logout = () => {
    setAuthenticated(false);
    setUserRole(null);
    localStorage.removeItem('muravei-token');
    resetSession();
    setSessionOpen(false);
  };

  const yoloReady = yoloMode === 'ready' || yoloMode === 'gpu' || yoloMode === 'cpu';
  const roleLabel =
    userRole === 'master' ? 'Мастер' : userRole === 'engineer' ? 'Инженер' : userRole === 'operator' ? 'Оператор' : null;
  const focusedSourcePath = useViewerStore(
    (s) => s.viewers[s.focusedViewerId]?.sourcePath,
  );

  const runExport = (kind: 'html' | 'pdf' | 'kml' | 'geojson') => {
    setExportOpen(false);
    setReportBusy(true);
    setReportError(null);
    const stamp = Date.now();
    let url = '';
    let filename = '';
    if (kind === 'html') {
      url = '/api/report/html';
      filename = `muravei-report-${stamp}.html`;
    } else if (kind === 'pdf') {
      url = '/api/report/pdf';
      filename = `muravei-report-${stamp}.pdf`;
    } else {
      if (!focusedSourcePath) {
        setReportBusy(false);
        setReportError('Нет активного видео для экспорта');
        return;
      }
      const q = encodeURIComponent(focusedSourcePath);
      url = kind === 'kml' ? `/api/export/kml?source_video=${q}` : `/api/export/geojson?source_video=${q}`;
      filename = kind === 'kml' ? `muravei-${stamp}.kml` : `muravei-${stamp}.geojson`;
    }
    void downloadAuthorized(url, { filename })
      .then(() => {
        if (kind === 'html') {
          const token = localStorage.getItem('muravei-token') || '';
          window.open(
            `/api/report/html?token=${encodeURIComponent(token)}`,
            '_blank',
            'noopener',
          );
        }
      })
      .catch((err: unknown) => {
        setReportError(err instanceof Error ? err.message : 'Ошибка экспорта');
      })
      .finally(() => setReportBusy(false));
  };

  return (
    <>
      <div
        ref={menuRef}
        className="h-12 bg-dv-header border-b border-dv-border flex items-center px-3 flex-shrink-0 relative z-[100] gap-2"
      >
        <div className="flex items-center gap-2 mr-3 shrink-0">
          <div className="w-7 h-7 bg-dv-hot rounded-sm flex items-center justify-center text-white font-bold text-xs">
            M
          </div>
          <div className="leading-tight">
            <div className="text-dv-text font-semibold text-sm tracking-wide">MuraveiVision</div>
            <div className="text-[9px] text-dv-muted tracking-wider uppercase">PRO</div>
          </div>
        </div>

        <div className="flex gap-0.5 p-0.5 bg-dv-deep rounded-sm border border-dv-border/60">
          {WORKSPACE_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              aria-label={tab}
              onClick={() => onTabChange(tab)}
              className={`px-2.5 py-1.5 text-[11px] font-medium rounded-sm transition-all duration-150 inline-flex items-center gap-1.5 ${
                activeTab === tab
                  ? 'bg-dv-accent text-black shadow-sm'
                  : 'text-dv-muted hover:text-dv-text hover:bg-dv-hover'
              }`}
            >
              {TAB_ICONS[tab]}
              <span className="hidden md:inline">{tab}</span>
              {tab === 'AI-анализ' && ollamaOk === false && (
                <AlertTriangle
                  size={11}
                  className={activeTab === tab ? 'text-amber-900' : 'text-amber-400'}
                />
              )}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* Status strip */}
          <div
            className="hidden lg:flex items-center gap-2 text-[10px] text-dv-muted px-2 py-1 rounded-sm bg-dv-deep border border-dv-border/50 max-w-[280px]"
            title="Статус системы"
          >
            <span className="inline-flex items-center gap-1">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  yoloReady ? 'bg-dv-success' : yoloMode ? 'bg-amber-400' : 'bg-dv-muted'
                }`}
              />
              YOLO {yoloMode ?? '—'}
            </span>
            <span className="text-dv-border">|</span>
            <span className="inline-flex items-center gap-1">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  ollamaOk === true
                    ? 'bg-dv-success'
                    : ollamaOk === false
                      ? 'bg-amber-400'
                      : 'bg-dv-muted'
                }`}
              />
              Ollama {ollamaOk === true ? 'ок' : ollamaOk === false ? 'нет' : '—'}
            </span>
            {roleLabel && (
              <>
                <span className="text-dv-border">|</span>
                <span className="text-dv-text truncate">{roleLabel}</span>
              </>
            )}
          </div>

          {isAuthenticated && (
            <div className="relative">
              <Button
                size="md"
                disabled={reportBusy}
                active={exportOpen}
                title="Экспорт: HTML / PDF / KML / GeoJSON"
                onClick={() => {
                  setExportOpen((v) => !v);
                  setWindowOpen(false);
                  setLayoutOpen(false);
                  setSessionOpen(false);
                }}
              >
                <FileText size={13} />
                {reportBusy ? 'Экспорт…' : 'Экспорт'}
              </Button>
              <Menu open={exportOpen} className="w-52">
                <MenuItem onClick={() => runExport('html')}>HTML-отчёт</MenuItem>
                <MenuItem onClick={() => runExport('pdf')}>PDF (схема карты)</MenuItem>
                <MenuItem onClick={() => runExport('kml')}>KML (Google Earth)</MenuItem>
                <MenuItem onClick={() => runExport('geojson')}>GeoJSON (QGIS)</MenuItem>
              </Menu>
            </div>
          )}
          {reportError && (
            <span className="text-[10px] text-dv-danger max-w-[120px] truncate" title={reportError}>
              {reportError}
            </span>
          )}

          <div className="relative">
            <Button
              size="md"
              active={layoutOpen}
              onClick={() => {
                setLayoutOpen((v) => !v);
                setWindowOpen(false);
                setSessionOpen(false);
                setExportOpen(false);
              }}
            >
              <LayoutGrid size={13} />
              Раскладка
            </Button>
            <Menu open={layoutOpen}>
              {(
                [
                  ['singleViewer', '1 вьюер'],
                  ['dualViewer', '2 вьюера'],
                  ['quadViewer', '4 вьюера'],
                  ['liveQuad', '4×Live'],
                  ['editDefault', 'Монтаж по умолчанию'],
                  ['mediaGeo', 'Медиа + Гео 3D'],
                ] as const
              ).map(([key, label]) => (
                <MenuItem
                  key={key}
                  onClick={() => {
                    applyPreset(key);
                    setLayoutOpen(false);
                  }}
                >
                  {label}
                </MenuItem>
              ))}
              {onResetLayout && (
                <MenuItem
                  danger
                  className="border-t border-dv-border"
                  onClick={() => {
                    onResetLayout();
                    setLayoutOpen(false);
                  }}
                >
                  Сбросить раскладку
                </MenuItem>
              )}
            </Menu>
          </div>

          <div className="relative">
            <Button
              size="md"
              active={windowOpen}
              onClick={() => {
                setWindowOpen((v) => !v);
                setLayoutOpen(false);
                setSessionOpen(false);
                setExportOpen(false);
              }}
            >
              <Monitor size={13} />
              Окна
            </Button>
            <Menu open={windowOpen} className="max-h-96 overflow-auto w-56">
              {ALL_VIEW_IDS.map((id) => {
                const on = isPanelVisible(id);
                return (
                  <MenuItem key={id} onClick={() => togglePanel(id)}>
                    <span
                      className={`w-3 h-3 border border-dv-border rounded-sm shrink-0 ${
                        on ? 'bg-dv-accent' : ''
                      }`}
                    />
                    {VIEW_TITLES[id]}
                  </MenuItem>
                );
              })}
              <div className="px-3 py-2 text-[10px] text-dv-muted border-t border-dv-border font-mono leading-5">
                <div className="uppercase tracking-wider mb-1">Горячие клавиши</div>
                <div>Space — play/pause</div>
                <div>← / → — кадр (±10 с Shift)</div>
                <div>I / O — In / Out</div>
                <div>F / Ctrl+S — зафиксировать кадр</div>
                <div>1–4 — вьюер</div>
                <div>Ctrl+Z — отменить правку</div>
                <div>Del — удалить детекцию</div>
              </div>
            </Menu>
          </div>

          <Button
            size="md"
            title="3D-траектория полёта (SRT/CSV)"
            active={isPanelVisible('flight3d')}
            onClick={() => {
              if (isPanelVisible('flight3d')) {
                closePanel('flight3d');
              } else {
                applyPreset('mediaGeo');
                logger.info('ui', 'Открыта панель Гео 3D');
              }
            }}
          >
            <Globe2 size={13} />
            Гео 3D
          </Button>

          <Button
            size="md"
            title="Панель отладки"
            onClick={() => {
              if (isPanelVisible('debug')) closePanel('debug');
              else {
                openPanel('debug');
                logger.info('ui', 'Открыта панель отладки');
              }
            }}
          >
            <Bug size={13} />
            Отладка
          </Button>

          <div className="relative">
            <button
              type="button"
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
                isAuthenticated
                  ? 'bg-dv-accent/20 ring-1 ring-dv-accent/40'
                  : 'bg-dv-surface hover:bg-dv-hover'
              }`}
              onClick={() => {
                if (isAuthenticated) {
                  setSessionOpen((v) => !v);
                  setLayoutOpen(false);
                  setWindowOpen(false);
                } else {
                  setLoginOpen(true);
                }
              }}
              title={isAuthenticated ? roleLabel || 'Сессия' : 'Войти'}
            >
              <User size={14} className="text-dv-text" />
            </button>
            <Menu open={sessionOpen && isAuthenticated} className="w-48 p-0">
              <div className="px-3 py-2 text-[10px] text-dv-muted border-b border-dv-border">
                Сессия:{' '}
                <span className="text-dv-text">{roleLabel ?? userRole}</span>
              </div>
              <MenuItem
                onClick={() => {
                  setSessionOpen(false);
                  onTabChange('AI-анализ');
                }}
              >
                <Brain size={12} />
                AI-анализ
              </MenuItem>
              <MenuItem danger onClick={logout}>
                Выйти
              </MenuItem>
            </Menu>
          </div>
        </div>
      </div>

      <Modal
        open={loginOpen}
        title="Вход"
        onClose={() => {
          setLoginOpen(false);
          setAuthError(null);
          setPin('');
        }}
        footer={
          <>
            <Button
              size="md"
              onClick={() => {
                setLoginOpen(false);
                setAuthError(null);
                setPin('');
              }}
            >
              Отмена
            </Button>
            <Button
              size="md"
              variant="primary"
              disabled={pin.length !== 7}
              onClick={() => void login()}
            >
              Войти
            </Button>
          </>
        }
      >
        <p className="text-xs text-dv-muted mb-3">
          Введите 7-значный PIN оператора, инженера или мастера.
        </p>
        <label className="dv-section-label block mb-1">PIN</label>
        <input
          type="password"
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          maxLength={7}
          className="w-full bg-dv-deep border border-dv-border px-3 py-2 text-sm tracking-[0.35em] text-center rounded-sm text-dv-text"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 7))}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void login();
          }}
          placeholder="•••••••"
        />
        {authError && <div className="mt-2 text-[11px] text-dv-hot">{authError}</div>}
      </Modal>
    </>
  );
};

export default TopBar;
