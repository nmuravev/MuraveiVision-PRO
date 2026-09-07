import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Network, Plug, PlugZap, RefreshCw } from 'lucide-react';
import { authHeaders } from '../../store/useMuraveiStore';

export type OllamaState = 'disconnected' | 'searching' | 'connected' | 'degraded';

type OllamaStatus = {
  state: OllamaState;
  base_url?: string;
  host?: string;
  port?: number;
  model?: string;
  timeout_sec?: number;
  models?: { name: string }[];
  message?: string;
  error_kind?: string;
  available?: boolean;
  auto_reconnect?: boolean;
};

type ScanHost = {
  host: string;
  port: number;
  base_url: string;
  ok?: boolean;
};

const STATE_LABEL: Record<OllamaState, string> = {
  disconnected: 'отключена',
  searching: 'поиск',
  connected: 'подключена',
  degraded: 'деградация',
};

function badgeClass(state: OllamaState): string {
  if (state === 'connected') return 'text-emerald-400';
  if (state === 'degraded') return 'text-amber-400';
  if (state === 'searching') return 'text-sky-400';
  return 'text-dv-muted';
}

export const OllamaSettingsCard: React.FC = () => {
  const [status, setStatus] = useState<OllamaStatus>({ state: 'disconnected' });
  const [host, setHost] = useState('127.0.0.1');
  const [port, setPort] = useState(11434);
  const [model, setModel] = useState('');
  const [timeoutSec, setTimeoutSec] = useState(60);
  const [busy, setBusy] = useState(false);
  const [scanBusy, setScanBusy] = useState(false);
  const [hosts, setHosts] = useState<ScanHost[]>([]);
  const [banner, setBanner] = useState<string | null>(null);

  const applyStatus = useCallback((data: OllamaStatus) => {
    setStatus(data);
    if (data.host) setHost(String(data.host));
    if (data.port) setPort(Number(data.port));
    if (data.model != null) setModel(String(data.model));
    if (data.timeout_sec) setTimeoutSec(Number(data.timeout_sec));
    if (data.message) setBanner(data.message);
    else if (data.state === 'connected' || data.state === 'disconnected') setBanner(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/ai/ollama/status', { headers: authHeaders() });
      if (!res.ok) return;
      const data = (await res.json()) as OllamaStatus;
      applyStatus(data);
    } catch {
      /* calm */
    }
  }, [applyStatus]);

  useEffect(() => {
    void refresh();
    const ms = status.state === 'connected' || status.state === 'degraded' ? 30000 : 60000;
    const t = window.setInterval(() => void refresh(), ms);
    return () => window.clearInterval(t);
  }, [refresh, status.state]);

  const connectLadder = async () => {
    setBusy(true);
    setBanner(null);
    try {
      const res = await fetch('/api/ai/ollama/connect', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({}),
      });
      const data = (await res.json()) as OllamaStatus;
      applyStatus(data);
      if (!data.available && data.message) setBanner(data.message);
    } catch {
      setBanner('Не удалось выполнить подключение');
    } finally {
      setBusy(false);
    }
  };

  const saveAndConnect = async () => {
    setBusy(true);
    setBanner(null);
    try {
      const res = await fetch('/api/ai/ollama/settings', {
        method: 'PUT',
        headers: authHeaders(),
        body: JSON.stringify({
          host,
          port,
          model: model || null,
          timeout_sec: timeoutSec,
          connect_now: true,
        }),
      });
      const data = (await res.json()) as OllamaStatus;
      applyStatus(data);
      if (data.message) setBanner(data.message);
    } catch {
      setBanner('Не удалось сохранить настройки');
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      const res = await fetch('/api/ai/ollama/disconnect', {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = (await res.json()) as OllamaStatus;
      applyStatus(data);
      setBanner(null);
    } catch {
      setBanner('Ошибка отключения');
    } finally {
      setBusy(false);
    }
  };

  const scanLan = async () => {
    setScanBusy(true);
    setBanner(null);
    try {
      const res = await fetch('/api/ai/ollama/scan', {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = (await res.json()) as { hosts?: ScanHost[]; count?: number };
      const list = Array.isArray(data.hosts) ? data.hosts : [];
      setHosts(list);
      if (!list.length) setBanner('В локальной сети ничего не найдено на порту 11434');
    } catch {
      setBanner('Сканирование сети не удалось');
    } finally {
      setScanBusy(false);
    }
  };

  const pickHost = async (h: ScanHost) => {
    setBusy(true);
    try {
      const res = await fetch('/api/ai/ollama/connect', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ base_url: h.base_url }),
      });
      const data = (await res.json()) as OllamaStatus;
      applyStatus(data);
      if (data.message) setBanner(data.message);
    } catch {
      setBanner('Не удалось подключиться к выбранному хосту');
    } finally {
      setBusy(false);
    }
  };

  const state = status.state || 'disconnected';
  const models = status.models || [];

  return (
    <div
      className="rounded-sm border border-dv-border/70 bg-dv-panel/40 p-3 space-y-3"
      data-testid="ollama-settings-card"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <PlugZap size={14} className={badgeClass(state)} />
          <span className="text-dv-text font-medium">Ollama</span>
          <span className={`font-mono text-[10px] ${badgeClass(state)}`}>
            {STATE_LABEL[state]}
          </span>
          {status.base_url ? (
            <span className="text-[10px] text-dv-muted font-mono truncate max-w-[220px]">
              {status.base_url}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            disabled={busy || state === 'searching'}
            onClick={() => void connectLadder()}
            className="inline-flex items-center gap-1 px-2 py-1 text-[10px] rounded-sm border border-dv-border bg-dv-deep hover:bg-dv-panel disabled:opacity-50"
          >
            {busy || state === 'searching' ? <Loader2 size={11} className="animate-spin" /> : <Plug size={11} />}
            Подключить
          </button>
          <button
            type="button"
            disabled={scanBusy}
            onClick={() => void scanLan()}
            className="inline-flex items-center gap-1 px-2 py-1 text-[10px] rounded-sm border border-dv-border bg-dv-deep hover:bg-dv-panel disabled:opacity-50"
          >
            {scanBusy ? <Loader2 size={11} className="animate-spin" /> : <Network size={11} />}
            Найти в сети
          </button>
          <button
            type="button"
            disabled={busy || state === 'disconnected'}
            onClick={() => void disconnect()}
            className="inline-flex items-center gap-1 px-2 py-1 text-[10px] rounded-sm border border-dv-border text-dv-muted hover:text-dv-text disabled:opacity-40"
          >
            Отключить
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            className="inline-flex items-center gap-1 px-2 py-1 text-[10px] rounded-sm border border-dv-border/50 text-dv-muted"
            title="Обновить статус"
          >
            <RefreshCw size={11} />
          </button>
        </div>
      </div>

      {banner ? (
        <div className="text-[11px] text-dv-muted border border-dv-border/40 rounded-sm px-2 py-1.5 bg-dv-deep/50" role="status">
          {banner}
        </div>
      ) : null}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
        <label className="space-y-0.5">
          <span className="text-dv-muted">Host</span>
          <input
            className="w-full px-2 py-1 rounded-sm bg-dv-deep border border-dv-border font-mono text-[11px]"
            value={host}
            onChange={(e) => setHost(e.target.value)}
          />
        </label>
        <label className="space-y-0.5">
          <span className="text-dv-muted">Port</span>
          <input
            type="number"
            className="w-full px-2 py-1 rounded-sm bg-dv-deep border border-dv-border font-mono text-[11px]"
            value={port}
            onChange={(e) => setPort(Number(e.target.value) || 11434)}
          />
        </label>
        <label className="space-y-0.5">
          <span className="text-dv-muted">Model</span>
          <select
            className="w-full px-2 py-1 rounded-sm bg-dv-deep border border-dv-border text-[11px]"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="">— авто —</option>
            {models.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-0.5">
          <span className="text-dv-muted">Timeout (с)</span>
          <input
            type="number"
            className="w-full px-2 py-1 rounded-sm bg-dv-deep border border-dv-border font-mono text-[11px]"
            value={timeoutSec}
            onChange={(e) => setTimeoutSec(Number(e.target.value) || 60)}
          />
        </label>
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={() => void saveAndConnect()}
        className="px-3 py-1.5 text-[11px] rounded-sm bg-[var(--dv-accent-hot,#e87d0d)]/90 text-white disabled:opacity-50"
      >
        Сохранить и подключить
      </button>

      {hosts.length > 0 ? (
        <div className="space-y-1">
          <div className="text-[10px] text-dv-muted">Найдено в сети:</div>
          <ul className="max-h-28 overflow-auto space-y-0.5">
            {hosts.map((h) => (
              <li key={h.base_url}>
                <button
                  type="button"
                  className="w-full text-left text-[11px] font-mono px-2 py-1 rounded-sm border border-dv-border/50 hover:bg-dv-deep"
                  onClick={() => void pickHost(h)}
                >
                  {h.base_url} {h.ok ? '✓' : ''}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
};

export default OllamaSettingsCard;
