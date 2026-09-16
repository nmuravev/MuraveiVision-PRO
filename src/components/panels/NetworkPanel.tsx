import React, { useEffect, useState } from 'react';
import { Network, RefreshCw } from 'lucide-react';
import {
  useNetworkStore,
  type NetworkConfig,
} from '../../store/useNetworkStore';
import { useMuraveiStore, detectionCropSrc } from '../../store/useMuraveiStore';

export const NetworkPanel: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const userRole = useMuraveiStore((s) => s.userRole);
  const active = useMuraveiStore((s) => s.activeDetection);
  const detections = useMuraveiStore((s) => s.detections);
  const activeId = useMuraveiStore((s) => s.activeDetectionId);

  const config = useNetworkStore((s) => s.config);
  const status = useNetworkStore((s) => s.status);
  const bases = useNetworkStore((s) => s.bases);
  const targets = useNetworkStore((s) => s.targets);
  const error = useNetworkStore((s) => s.error);
  const loadConfig = useNetworkStore((s) => s.loadConfig);
  const saveConfig = useNetworkStore((s) => s.saveConfig);
  const fetchStatus = useNetworkStore((s) => s.fetchStatus);
  const fetchBases = useNetworkStore((s) => s.fetchBases);
  const fetchTargets = useNetworkStore((s) => s.fetchTargets);
  const sendTarget = useNetworkStore((s) => s.sendTarget);
  const offerReconPackage = useNetworkStore((s) => s.offerReconPackage);
  const acceptReconPackage = useNetworkStore((s) => s.acceptReconPackage);

  const [draft, setDraft] = useState(config);
  const [hubPin, setHubPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [reconJobId, setReconJobId] = useState('');
  const [reconKinds, setReconKinds] = useState<Record<string, boolean>>({
    sparse: true,
    dense: true,
    mesh: false,
    splat: false,
  });
  const [acceptPkgId, setAcceptPkgId] = useState('');
  const [reconProgress, setReconProgress] = useState<string | null>(null);

  const canEditConfig = userRole === 'engineer' || userRole === 'master';

  useEffect(() => {
    setDraft(config);
  }, [config]);

  useEffect(() => {
    if (!isAuthenticated) return;
    void loadConfig();
    void fetchStatus();
    void fetchBases();
    void fetchTargets();
    const t = window.setInterval(() => {
      void fetchBases();
      void fetchTargets();
    }, 8000);
    const st = window.setInterval(() => {
      void fetchStatus();
    }, 5000);
    return () => {
      window.clearInterval(t);
      window.clearInterval(st);
    };
  }, [isAuthenticated, loadConfig, fetchStatus, fetchBases, fetchTargets]);

  const refreshAll = () => {
    void loadConfig();
    void fetchStatus();
    void fetchBases();
    void fetchTargets();
  };

  const persist = async () => {
    setBusy(true);
    setLocalErr(null);
    try {
      await saveConfig({ ...draft, hub_pin: hubPin || undefined });
      setHubPin('');
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  const activeRow = detections.find((d) => d.id === activeId);

  const buildTargetPayload = () => {
    const className = activeRow?.class_name || active?.class_en;
    if (!className) return null;
    const gpsLat = activeRow?.gps_lat ?? null;
    const gpsLon = activeRow?.gps_lon ?? null;
    const detId = activeRow?.id || active?.id || '';
    const notesParts = [
      activeRow?.user_notes || '',
      detId ? `detection_id=${detId}` : '',
    ].filter(Boolean);
    return {
      class_name: className,
      confidence: activeRow?.confidence ?? active?.confidence ?? 0,
      notes: notesParts.join(' · ') || undefined,
      crop_path: activeRow?.crop_path || undefined,
      source_video: activeRow?.source_video || active?.source_video || undefined,
      gps_lat: gpsLat,
      gps_lon: gpsLon,
    };
  };

  const onSendTarget = async () => {
    const payload = buildTargetPayload();
    if (!payload) {
      setLocalErr('Выберите детекцию в Inspector / Viewer');
      return;
    }
    setBusy(true);
    setLocalErr(null);
    try {
      await sendTarget(payload);
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  const onShareLocation = async () => {
    const payload = buildTargetPayload();
    if (!payload) {
      setLocalErr('Выберите детекцию в Inspector / Viewer');
      return;
    }
    const hasGps = payload.gps_lat != null && payload.gps_lon != null;
    if (!hasGps) {
      const ok = window.confirm('GPS отсутствует — отправить без координат?');
      if (!ok) return;
    }
    setBusy(true);
    setLocalErr(null);
    try {
      await sendTarget(payload);
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  const onOfferRecon = async () => {
    const jid = reconJobId.trim().replace(/\s+/g, '');
    if (!jid) {
      setLocalErr('Укажите job_id (12 hex)');
      return;
    }
    const kinds = Object.entries(reconKinds)
      .filter(([, on]) => on)
      .map(([k]) => k);
    if (!kinds.length) {
      setLocalErr('Выберите хотя бы один артефакт');
      return;
    }
    setBusy(true);
    setLocalErr(null);
    setReconProgress('Создание пакета…');
    try {
      await offerReconPackage(jid, kinds);
      setReconProgress('Пакет предложен (см. Чат)');
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка');
      setReconProgress(null);
    } finally {
      setBusy(false);
    }
  };

  const onAcceptRecon = async () => {
    const pid = acceptPkgId.trim().toLowerCase();
    if (!pid) {
      setLocalErr('Укажите package id из чата (recon_package:…)');
      return;
    }
    const kinds = Object.entries(reconKinds)
      .filter(([, on]) => on)
      .map(([k]) => k);
    setBusy(true);
    setLocalErr(null);
    setReconProgress('Приём пакета…');
    try {
      const out = await acceptReconPackage(pid, kinds.length ? kinds : ['sparse', 'dense', 'mesh', 'splat']);
      setReconProgress(`Готово → archive/recon/${out.job_id} (${out.unpacked.join(', ') || '—'})`);
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка приёма');
      setReconProgress(null);
    } finally {
      setBusy(false);
    }
  };

  const incoming = targets.filter((t) => t.direction === 'in');

  return (
    <div className="h-full flex flex-col bg-[var(--dv-panel)] text-xs overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--dv-border)] flex items-center gap-2 flex-shrink-0">
        <Network size={14} className="text-[var(--dv-accent)]" />
        <span className="font-semibold text-[11px]">Сеть баз</span>
        <button
          type="button"
          className="ml-auto p-1 rounded-sm hover:bg-[#333] text-[var(--dv-text-muted)]"
          onClick={refreshAll}
          title="Обновить"
        >
          <RefreshCw size={12} />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-4">
        {(error || localErr) && (
          <div className="text-amber-300 text-[11px] border border-amber-800/50 bg-amber-950/30 px-2 py-1.5 rounded-sm">
            {localErr || error}
          </div>
        )}

        <section className="space-y-2">
          <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
            Настройки
          </div>
          <label className="block space-y-1">
            <span className="text-[var(--dv-text-muted)]">Режим</span>
            <select
              className="w-full bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1.5 rounded-sm"
              disabled={!canEditConfig}
              value={draft.mode}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  mode: e.target.value as NetworkConfig['mode'],
                }))
              }
            >
              <option value="off">Выкл</option>
              <option value="server">Сервер</option>
              <option value="client">Клиент</option>
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block space-y-1">
              <span className="text-[var(--dv-text-muted)]">IP сервера</span>
              <input
                className="w-full bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1 rounded-sm"
                disabled={!canEditConfig}
                value={draft.server_ip}
                onChange={(e) => setDraft((d) => ({ ...d, server_ip: e.target.value }))}
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[var(--dv-text-muted)]">Порт</span>
              <input
                type="number"
                className="w-full bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1 rounded-sm"
                disabled={!canEditConfig}
                value={draft.port}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, port: Number(e.target.value) || 8000 }))
                }
              />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="text-[var(--dv-text-muted)]">Имя базы</span>
            <input
              className="w-full bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1 rounded-sm"
              disabled={!canEditConfig}
              value={draft.base_name}
              onChange={(e) => setDraft((d) => ({ ...d, base_name: e.target.value }))}
            />
          </label>
          {canEditConfig && (
            <label className="block space-y-1">
              <span className="text-[var(--dv-text-muted)]">PIN хаба (клиент)</span>
              <input
                type="password"
                autoComplete="off"
                className="w-full bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1 rounded-sm"
                value={hubPin}
                placeholder={config.has_hub_pin ? '••••••• (сохранён)' : 'PIN оператора хаба'}
                onChange={(e) => setHubPin(e.target.value)}
              />
            </label>
          )}
          {canEditConfig && (
            <button
              type="button"
              disabled={busy}
              className="w-full py-1.5 rounded-sm bg-[var(--dv-accent)] text-black font-medium disabled:opacity-40"
              onClick={() => void persist()}
            >
              Сохранить настройки
            </button>
          )}
          {!canEditConfig && (
            <div className="text-[10px] text-[var(--dv-text-muted)]">
              Смена режима — только engineer / master
            </div>
          )}
        </section>

        <section className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
            Синхронизация
          </div>
          <div className="border border-[var(--dv-border)] rounded-sm px-2 py-1.5 bg-[var(--dv-bg-deep)] space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[var(--dv-text-muted)]">Хаб</span>
              <span className={status?.hub_reachable ? 'text-emerald-400' : 'text-red-400'}>
                {status?.hub_reachable ? 'online' : 'offline'}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-[var(--dv-text-muted)]">Worker</span>
              <span className={status?.worker_alive ? 'text-emerald-400' : 'text-slate-500'}>
                {status?.worker_alive ? 'alive' : '—'}
              </span>
            </div>
            {config.mode === 'client' && (
              <div className="flex items-center justify-between gap-2">
                <span className="text-[var(--dv-text-muted)]" title="Ускорение чата до хаба (REST — запасной путь)">
                  WS peer
                </span>
                <span
                  className={
                    status?.ws_peer === 'connected' ? 'text-emerald-400' : 'text-amber-500/90'
                  }
                  title={status?.ws_peer_last_error || undefined}
                >
                  {status?.ws_peer === 'connected' ? 'connected' : 'down'}
                </span>
              </div>
            )}
            <div className="text-[10px] text-[var(--dv-text-muted)]">
              Последняя синхронизация:{' '}
              {status?.last_sync_ts
                ? new Date(status.last_sync_ts * 1000).toLocaleTimeString()
                : 'ещё не было'}
            </div>
            {status?.advertise_ip && (
              <div className="text-[10px] text-[var(--dv-text-muted)]">
                LAN IP: {status.advertise_ip}
              </div>
            )}
            {config.base_id && (
              <div className="text-[9px] truncate text-[var(--dv-text-muted)]" title={config.base_id}>
                base_id: {config.base_id}
              </div>
            )}
            {status?.last_error && (
              <div className="text-red-400 text-[10px] break-words">{status.last_error}</div>
            )}
          </div>
        </section>

        <section className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
            Подключённые базы
          </div>
          {bases.length === 0 && (
            <div className="text-[var(--dv-text-muted)]">Пока нет heartbeat</div>
          )}
          {bases.map((b) => (
            <div
              key={b.id}
              className="flex justify-between gap-2 border border-[var(--dv-border)] rounded-sm px-2 py-1 bg-[var(--dv-bg-deep)]"
            >
              <span className="truncate">
                {b.base_name} · {b.ip}
              </span>
              <span className={b.status === 'online' ? 'text-emerald-400' : 'text-slate-500'}>
                {b.status}
              </span>
            </div>
          ))}
        </section>

        <section className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
            Пакет 3D (recon)
          </div>
          <div className="border border-[var(--dv-border)] rounded-sm px-2 py-1.5 bg-[var(--dv-bg-deep)] space-y-1.5">
            <input
              className="w-full bg-[var(--dv-panel)] border border-[var(--dv-border)] px-2 py-1 rounded-sm"
              placeholder="job_id (12 hex)"
              value={reconJobId}
              disabled={config.mode === 'off'}
              onChange={(e) => setReconJobId(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              {(['sparse', 'dense', 'mesh', 'splat'] as const).map((k) => (
                <label key={k} className="flex items-center gap-1 text-[10px]">
                  <input
                    type="checkbox"
                    checked={Boolean(reconKinds[k])}
                    disabled={config.mode === 'off'}
                    onChange={(e) =>
                      setReconKinds((prev) => ({ ...prev, [k]: e.target.checked }))
                    }
                  />
                  {k}
                </label>
              ))}
            </div>
            <button
              type="button"
              disabled={busy || config.mode === 'off'}
              className="w-full py-1 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
              onClick={() => void onOfferRecon()}
            >
              Предложить пакет
            </button>
            <input
              className="w-full bg-[var(--dv-panel)] border border-[var(--dv-border)] px-2 py-1 rounded-sm"
              placeholder="package id для приёма"
              value={acceptPkgId}
              disabled={config.mode === 'off'}
              onChange={(e) => setAcceptPkgId(e.target.value)}
            />
            <button
              type="button"
              disabled={busy || config.mode === 'off'}
              className="w-full py-1 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
              onClick={() => void onAcceptRecon()}
            >
              Принять / докачать
            </button>
            {reconProgress && (
              <div className="text-[10px] text-emerald-400/90 break-words">{reconProgress}</div>
            )}
          </div>
        </section>

        <section className="space-y-1.5">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
              Входящие цели
            </div>
            <div className="flex gap-1">
              <button
                type="button"
                disabled={busy || config.mode === 'off'}
                className="text-[10px] px-2 py-0.5 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
                onClick={() => void onSendTarget()}
              >
                Отправить текущую цель
              </button>
              <button
                type="button"
                disabled={busy || config.mode === 'off'}
                className="text-[10px] px-2 py-0.5 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
                onClick={() => void onShareLocation()}
                title="GPS-цель с detection_id в notes"
              >
                Поделиться локацией
              </button>
            </div>
          </div>
          {incoming.length === 0 && (
            <div className="text-[var(--dv-text-muted)]">Лента пуста</div>
          )}
          {incoming.slice(0, 20).map((t) => (
            <div
              key={t.id}
              className="border border-[var(--dv-border)] rounded-sm p-2 bg-[var(--dv-bg-deep)] space-y-1"
            >
              <div className="flex gap-2">
                {t.crop_path ? (
                  <img
                    src={detectionCropSrc(t.id, t.crop_path)}
                    alt=""
                    className="w-12 h-12 object-cover rounded-sm bg-black"
                  />
                ) : (
                  <div className="w-12 h-12 bg-[#222] rounded-sm" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{t.class_name}</div>
                  <div className="text-[10px] text-[var(--dv-text-muted)]">
                    {t.source_base || '—'} · {(t.confidence * 100).toFixed(0)}%
                    {t.gps_lat != null && t.gps_lon != null
                      ? ` · ${t.gps_lat.toFixed(5)}, ${t.gps_lon.toFixed(5)}`
                      : ''}
                  </div>
                  {t.source_video && (
                    <div
                      className="text-[9px] truncate text-[var(--dv-text-muted)]"
                      title={t.source_video}
                    >
                      {t.source_video.replace(/^.*[/\\]/, '')}
                    </div>
                  )}
                  {t.notes && (
                    <div className="text-[10px] truncate text-[var(--dv-text-muted)]">{t.notes}</div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </section>

        <div className="text-[10px] text-[var(--dv-text-muted)]">
          Чат перенесён в окно «Чат» (Система / Окна → Чат).
        </div>
      </div>
    </div>
  );
};

export default NetworkPanel;
