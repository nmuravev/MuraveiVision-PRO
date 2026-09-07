import React, { useState, useRef, useEffect } from 'react';
import {
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
  Terminal,
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
import { useNetworkStore } from '../store/useNetworkStore';
import { useViewerStore } from '../store/useViewerStore';
import { downloadAuthorized } from '../lib/download';
import { logger } from '../services/logger';
import { Button, Menu, MenuItem, Modal, VramIndicator, YoloBackendBadge } from './ui';

interface TopBarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  isDefaultLayout?: boolean;
  onResetLayout?: () => void;
  traceDockOpen?: boolean;
  onToggleTraceDock?: () => void;
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
  traceDockOpen,
  onToggleTraceDock,
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
  const [ollamaState, setOllamaState] = useState<string>('disconnected');
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
  const chatUnreadBadge = useNetworkStore((s) => s.unreadCount);

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
      setOllamaState('disconnected');
      return;
    }
    let cancelled = false;
    const poll = () => {
      const token = localStorage.getItem('muravei-token');
      void fetch('/api/ai/ollama/status', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((res) => (res.ok ? res.json() : Promise.reject()))
        .then((data: { state?: string }) => {
          if (!cancelled) setOllamaState(String(data.state || 'disconnected'));
        })
        .catch(() => {
          if (!cancelled) setOllamaState('disconnected');
        });
    };
    poll();
    const connected = ollamaState === 'connected' || ollamaState === 'degraded';
    const t = window.setInterval(poll, connected ? 30000 : 60000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [isAuthenticated, ollamaState]);

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
    userRole === 'master'
      ? 'Мастер'
      : userRole === 'engineer'
        ? 'Инженер'
        : userRole === 'operator'
          ? 'Оператор'
          : null;
  const focusedSourcePath = useViewerStore((s) => s.viewers[s.focusedViewerId]?.sourcePath);

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
      url =
        kind === 'kml' ? `/api/export/kml?source_video=${q}` : `/api/export/geojson?source_video=${q}`;
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

  const LAYOUT_PRESETS = [
    ['singleViewer', '1 вьюер'],
    ['dualViewer', '2 вьюера'],
    ['quadViewer', '4 вьюера'],
    ['liveQuad', '4×Live'],
    ['editDefault', 'Монтаж по умолчанию'],
    ['mediaGeo', 'Медиа + Гео 3D'],
  ] as const;

  const toggleGeo3d = () => {
    if (isPanelVisible('flight3d')) {
      closePanel('flight3d');
    } else {
      applyPreset('mediaGeo');
      logger.info('ui', 'Открыта панель Гео 3D');
    }
  };

  const toggleDebug = () => {
    if (isPanelVisible('debug')) closePanel('debug');
    else {
      openPanel('debug');
      logger.info('ui', 'Открыта панель отладки');
    }
  };

  const closeStripMenus = () => {
    setWindowOpen(false);
    setLayoutOpen(false);
    setExportOpen(false);
    setSessionOpen(false);
  };

  const stripBtn = (active: boolean) =>
    `h-7 px-2 text-[11px] font-medium rounded-sm transition-all duration-150 inline-flex items-center gap-1 shrink-0 whitespace-nowrap ${
      active
        ? 'bg-dv-accent text-black shadow-sm'
        : 'text-dv-muted hover:text-dv-text hover:bg-dv-hover'
    }`;

  const stripMenuOpen = exportOpen || layoutOpen || windowOpen;

  return (
    <>
      <div
        ref={menuRef}
        className="h-12 bg-dv-header border-b border-dv-border flex items-center px-3 flex-shrink-0 relative z-[100] gap-2 min-w-0 overflow-visible"
      >
        <div className="flex items-center gap-2 mr-2 shrink-0">
          <div className="w-7 h-7 bg-dv-hot rounded-sm flex items-center justify-center text-white font-bold text-xs">
            M
          </div>
          <div className="leading-tight hidden sm:block">
            <div className="text-dv-text font-semibold text-sm tracking-wide">MuraveiVision</div>
            <div className="text-[9px] text-dv-muted tracking-wider uppercase">PRO</div>
          </div>
        </div>

        <div
          className={`flex-1 min-w-0 flex items-center gap-0.5 p-0.5 bg-dv-deep rounded-sm border border-dv-border/60 ${
            stripMenuOpen ? 'overflow-visible' : 'overflow-x-auto'
          }`}
        >
          {WORKSPACE_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              aria-label={tab}
              onClick={() => onTabChange(tab)}
              className={stripBtn(activeTab === tab)}
            >
              {TAB_ICONS[tab]}
              <span className="hidden md:inline">{tab}</span>
            </button>
          ))}

          <div className="w-px h-4 bg-dv-border/70 mx-0.5 shrink-0 self-center" aria-hidden />

          {isAuthenticated && (
            <div className="relative shrink-0">
              <button
                type="button"
                className={stripBtn(exportOpen)}
                disabled={reportBusy}
                title="Экспорт: HTML / PDF / KML / GeoJSON"
                onClick={() => {
                  setExportOpen((v) => !v);
                  setWindowOpen(false);
                  setLayoutOpen(false);
                  setSessionOpen(false);
                }}
              >
                <FileText size={12} />
                <span className="hidden md:inline">{reportBusy ? 'Экспорт…' : 'Экспорт'}</span>
              </button>
              <Menu open={exportOpen} className="w-52 z-[110]" align="left">
                <MenuItem onClick={() => runExport('html')}>HTML-отчёт</MenuItem>
                <MenuItem onClick={() => runExport('pdf')}>PDF (схема карты)</MenuItem>
                <MenuItem onClick={() => runExport('kml')}>KML (Google Earth)</MenuItem>
                <MenuItem onClick={() => runExport('geojson')}>GeoJSON (QGIS)</MenuItem>
              </Menu>
            </div>
          )}

          <div className="relative shrink-0">
            <button
              type="button"
              className={stripBtn(layoutOpen)}
              title="Раскладка"
              onClick={() => {
                setLayoutOpen((v) => !v);
                setWindowOpen(false);
                setSessionOpen(false);
                setExportOpen(false);
              }}
            >
              <LayoutGrid size={12} />
              <span className="hidden md:inline">Раскладка</span>
            </button>
            <Menu open={layoutOpen} className="z-[110]" align="left">
              {LAYOUT_PRESETS.map(([key, label]) => (
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

          <div className="relative shrink-0">
            <button
              type="button"
              className={stripBtn(windowOpen)}
              title="Окна"
              onClick={() => {
                setWindowOpen((v) => !v);
                setLayoutOpen(false);
                setSessionOpen(false);
                setExportOpen(false);
              }}
            >
              <Monitor size={12} />
              <span className="hidden md:inline">Окна</span>
            </button>
            <Menu open={windowOpen} className="max-h-96 overflow-auto w-56 z-[110]" align="left">
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
                    {id === 'chat' && chatUnreadBadge > 0 ? (
                      <span className="ml-auto text-[10px] text-amber-400">
                        {chatUnreadBadge > 99 ? '99+' : chatUnreadBadge}
                      </span>
                    ) : null}
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

          <button
            type="button"
            className={stripBtn(isPanelVisible('flight3d'))}
            title="3D-траектория полёта (SRT/CSV)"
            onClick={() => {
              closeStripMenus();
              toggleGeo3d();
            }}
          >
            <Globe2 size={12} />
            <span className="hidden md:inline">Гео 3D</span>
          </button>

          <button
            type="button"
            className={stripBtn(Boolean(traceDockOpen))}
            title="Session Trace dock (FE+BE). Код не удалять без явного приказа."
            onClick={() => {
              closeStripMenus();
              onToggleTraceDock?.();
            }}
          >
            <Bug size={12} />
            <span className="hidden md:inline">Трассировка</span>
          </button>

          <button
            type="button"
            className={stripBtn(isPanelVisible('debug'))}
            title="Панель отладки"
            onClick={() => {
              closeStripMenus();
              toggleDebug();
            }}
          >
            <Terminal size={12} />
            <span className="hidden md:inline">Отладка</span>
          </button>

          {reportError && (
            <span
              className="text-[10px] text-dv-danger max-w-[100px] truncate shrink-0 px-1"
              title={reportError}
            >
              {reportError}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {isAuthenticated && <YoloBackendBadge />}
          {isAuthenticated && <VramIndicator />}

          <div className="relative">
            <button
              type="button"
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors shrink-0 ${
                isAuthenticated
                  ? 'bg-dv-accent/20 ring-1 ring-dv-accent/40'
                  : 'bg-dv-surface hover:bg-dv-hover'
              }`}
              onClick={() => {
                if (isAuthenticated) {
                  setSessionOpen((v) => !v);
                  setLayoutOpen(false);
                  setWindowOpen(false);
                  setExportOpen(false);
                } else {
                  setLoginOpen(true);
                }
              }}
              title={isAuthenticated ? roleLabel || 'Сессия' : 'Войти'}
            >
              <User size={14} className="text-dv-text" />
            </button>
            <Menu open={sessionOpen && isAuthenticated} className="w-56 p-0 z-[110]" align="right">
              <div className="px-3 py-2 text-[10px] text-dv-muted border-b border-dv-border space-y-1.5">
                <div>
                  Сессия:{' '}
                  <span className="text-dv-text">{roleLabel ?? userRole ?? '—'}</span>
                </div>
                <div className="flex items-center gap-1.5 font-mono">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      yoloReady ? 'bg-dv-success' : yoloMode ? 'bg-amber-400' : 'bg-dv-muted'
                    }`}
                  />
                  <span className="text-dv-text">YOLO {yoloMode ?? '—'}</span>
                </div>
                <div className="flex items-center gap-1.5 font-mono">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      ollamaState === 'connected'
                        ? 'bg-dv-success'
                        : ollamaState === 'degraded'
                          ? 'bg-amber-400'
                          : ollamaState === 'searching'
                            ? 'bg-sky-400'
                            : 'bg-dv-muted'
                    }`}
                  />
                  <span className="text-dv-text">
                    Ollama{' '}
                    {ollamaState === 'connected'
                      ? 'подключена'
                      : ollamaState === 'degraded'
                        ? 'деградация'
                        : ollamaState === 'searching'
                          ? 'поиск'
                          : 'отключена'}
                  </span>
                </div>
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
