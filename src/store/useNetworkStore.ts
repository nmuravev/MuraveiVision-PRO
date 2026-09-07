import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';
import { logger } from '../services/logger';

const CHAT_SEEN_KEY = 'muravei_chat_last_seen_at';

export interface NetworkConfig {
  mode: 'off' | 'server' | 'client';
  server_ip: string;
  port: number;
  base_name: string;
  base_id?: string;
  has_hub_pin?: boolean;
}

export interface NetworkStatus {
  mode: string;
  base_id: string;
  last_sync_ts: number | null;
  last_error: string | null;
  hub_reachable: boolean;
  worker_alive: boolean;
  advertise_ip?: string;
  sync_interval_sec?: number;
}

export interface NetworkBase {
  id: string;
  base_name: string;
  ip: string;
  last_seen: number;
  status: string;
}

export interface NetworkTarget {
  id: string;
  created_at: number;
  direction: string;
  class_name: string;
  confidence: number;
  gps_lat?: number | null;
  gps_lon?: number | null;
  crop_path?: string | null;
  source_base?: string | null;
  source_video?: string | null;
  notes?: string | null;
}

export interface NetworkMessage {
  id: string;
  created_at: number;
  direction: string;
  sender: string;
  body: string;
  synced_at?: number | null;
}

interface NetworkState {
  config: NetworkConfig;
  status: NetworkStatus | null;
  bases: NetworkBase[];
  targets: NetworkTarget[];
  messages: NetworkMessage[];
  unreadCount: number;
  lastChatSeenAt: number;
  error: string | null;
  loadConfig: () => Promise<void>;
  saveConfig: (patch: Partial<NetworkConfig> & { hub_pin?: string }) => Promise<void>;
  fetchStatus: () => Promise<void>;
  fetchBases: () => Promise<void>;
  fetchTargets: () => Promise<void>;
  fetchMessages: () => Promise<void>;
  refreshUnread: () => Promise<void>;
  markChatSeen: () => void;
  sendTarget: (payload: {
    class_name: string;
    confidence?: number;
    notes?: string;
    crop_path?: string;
    source_video?: string;
    gps_lat?: number | null;
    gps_lon?: number | null;
  }) => Promise<void>;
  sendMessage: (body: string) => Promise<void>;
}

function readLastSeen(): number {
  try {
    const raw = localStorage.getItem(CHAT_SEEN_KEY);
    const n = raw != null ? Number(raw) : 0;
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

const defaultConfig: NetworkConfig = {
  mode: 'off',
  server_ip: '127.0.0.1',
  port: 8000,
  base_name: 'База-1',
};

export const useNetworkStore = create<NetworkState>((set, get) => ({
  config: defaultConfig,
  status: null,
  bases: [],
  targets: [],
  messages: [],
  unreadCount: 0,
  lastChatSeenAt: readLastSeen(),
  error: null,

  loadConfig: async () => {
    try {
      const res = await fetch('/api/network/config', { headers: authHeaders() });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Ошибка конфигурации сети');
      set({
        config: {
          mode: data.mode || 'off',
          server_ip: data.server_ip || '127.0.0.1',
          port: data.port || 8000,
          base_name: data.base_name || 'База-1',
          base_id: data.base_id || '',
          has_hub_pin: Boolean(data.has_hub_pin),
        },
        error: null,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Сеть недоступна';
      set({ error: msg });
      logger.warn('network', msg);
    }
  },

  saveConfig: async (patch) => {
    const { hub_pin, ...rest } = patch;
    const next = { ...get().config, ...rest };
    const body: Record<string, unknown> = {
      mode: next.mode,
      server_ip: next.server_ip,
      port: next.port,
      base_name: next.base_name,
    };
    if (hub_pin && hub_pin.trim()) body.hub_pin = hub_pin.trim();
    const res = await fetch('/api/network/config', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка сохранения');
    set({
      config: {
        mode: data.mode,
        server_ip: data.server_ip,
        port: data.port,
        base_name: data.base_name,
        base_id: data.base_id || next.base_id,
        has_hub_pin: Boolean(data.has_hub_pin),
      },
    });
    logger.info('network', `Режим сети: ${data.mode}`);
  },

  fetchStatus: async () => {
    const res = await fetch('/api/network/status', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    set({
      status: {
        mode: data.mode || '',
        base_id: data.base_id || '',
        last_sync_ts: data.last_sync_ts ?? null,
        last_error: data.last_error ?? null,
        hub_reachable: Boolean(data.hub_reachable),
        worker_alive: Boolean(data.worker_alive),
        advertise_ip: data.advertise_ip || '',
        sync_interval_sec: data.sync_interval_sec,
      },
    });
  },

  fetchBases: async () => {
    const res = await fetch('/api/network/bases', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    set({ bases: Array.isArray(data.bases) ? data.bases : [] });
  },

  fetchTargets: async () => {
    const res = await fetch('/api/network/targets', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    set({ targets: Array.isArray(data.targets) ? data.targets : [] });
  },

  fetchMessages: async () => {
    const res = await fetch('/api/network/messages', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    set({ messages: Array.isArray(data.messages) ? data.messages : [] });
    await get().refreshUnread();
  },

  refreshUnread: async () => {
    const since = get().lastChatSeenAt;
    const res = await fetch(
      `/api/network/messages/unread?since=${encodeURIComponent(String(since))}`,
      { headers: authHeaders() },
    );
    if (!res.ok) {
      // Fallback: local count
      const n = get().messages.filter(
        (m) => m.direction === 'in' && Number(m.created_at) > since,
      ).length;
      set({ unreadCount: n });
      return;
    }
    const data = await res.json();
    set({ unreadCount: Number(data.count) || 0 });
  },

  markChatSeen: () => {
    const now = Date.now() / 1000;
    try {
      localStorage.setItem(CHAT_SEEN_KEY, String(now));
    } catch {
      /* ignore */
    }
    set({ lastChatSeenAt: now, unreadCount: 0 });
  },

  sendTarget: async (payload) => {
    const res = await fetch('/api/network/targets', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка отправки цели');
    await get().fetchTargets();
    logger.info('network', `Цель отправлена: ${payload.class_name}`);
  },

  sendMessage: async (body) => {
    const res = await fetch('/api/network/messages', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ body }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка сообщения');
    await get().fetchMessages();
  },
}));
