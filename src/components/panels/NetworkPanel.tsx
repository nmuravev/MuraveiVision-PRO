import React, { useEffect, useState } from 'react';
import { Network, RefreshCw, Send } from 'lucide-react';
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
  const messages = useNetworkStore((s) => s.messages);
  const error = useNetworkStore((s) => s.error);
  const loadConfig = useNetworkStore((s) => s.loadConfig);
  const saveConfig = useNetworkStore((s) => s.saveConfig);
  const fetchStatus = useNetworkStore((s) => s.fetchStatus);
  const fetchBases = useNetworkStore((s) => s.fetchBases);
  const fetchTargets = useNetworkStore((s) => s.fetchTargets);
  const fetchMessages = useNetworkStore((s) => s.fetchMessages);
  const sendTarget = useNetworkStore((s) => s.sendTarget);
  const sendMessage = useNetworkStore((s) => s.sendMessage);

  const [draft, setDraft] = useState(config);
  const [hubPin, setHubPin] = useState('');
  const [chat, setChat] = useState('');
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

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
    void fetchMessages();
    const t = window.setInterval(() => {
      void fetchBases();
      void fetchTargets();
      void fetchMessages();
    }, 8000);
    const st = window.setInterval(() => {
      void fetchStatus();
    }, 5000);
    return () => {
      window.clearInterval(t);
      window.clearInterval(st);
    };
  }, [isAuthenticated, loadConfig, fetchStatus, fetchBases, fetchTargets, fetchMessages]);

  const refreshAll = () => {
    void loadConfig();
    void fetchStatus();
    void fetchBases();
    void fetchTargets();
    void fetchMessages();
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

  const onSendTarget = async () => {
    const row = detections.find((d) => d.id === activeId);
    const className = row?.class_name || active?.class_en;
    if (!className) {
      setLocalErr('Выберите детекцию в Inspector / Viewer');
      return;
    }
    setBusy(true);
    setLocalErr(null);
    try {
      await sendTarget({
        class_name: className,
        confidence: row?.confidence ?? active?.confidence ?? 0,
        notes: row?.user_notes || undefined,
        crop_path: row?.crop_path || undefined,
        source_video: row?.source_video || active?.source_video || undefined,
      });
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  const onSendChat = async () => {
    if (!chat.trim()) return;
    setBusy(true);
    setLocalErr(null);
    try {
      await sendMessage(chat.trim());
      setChat('');
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка');
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
            <div className="text-[10px] text-[var(--dv-text-muted)]">
              Последняя синхронизация:{' '}
              {status?.last_sync_ts
                ? new Date(status.last_sync_ts * 1000).toLocaleTimeString()
                : 'ещё не было'}
            </div>
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
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
              Входящие цели
            </div>
            <button
              type="button"
              disabled={busy || config.mode === 'off'}
              className="text-[10px] px-2 py-0.5 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
              onClick={() => void onSendTarget()}
            >
              Отправить текущую цель
            </button>
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

        <section className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">Чат</div>
          <div className="max-h-40 overflow-auto space-y-1 border border-[var(--dv-border)] rounded-sm p-2 bg-[var(--dv-bg-deep)]">
            {messages.length === 0 && (
              <div className="text-[var(--dv-text-muted)]">Нет сообщений</div>
            )}
            {[...messages].reverse().map((m) => (
              <div key={m.id} className="leading-snug">
                <span className="text-[var(--dv-text-muted)]">{m.sender}: </span>
                {m.body}
              </div>
            ))}
          </div>
          <div className="flex gap-1">
            <input
              className="flex-1 bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1 rounded-sm"
              value={chat}
              placeholder="Сообщение…"
              disabled={config.mode === 'off'}
              onChange={(e) => setChat(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void onSendChat();
              }}
            />
            <button
              type="button"
              disabled={busy || config.mode === 'off' || !chat.trim()}
              className="px-2 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
              onClick={() => void onSendChat()}
            >
              <Send size={12} />
            </button>
          </div>
        </section>
      </div>
    </div>
  );
};

export default NetworkPanel;
