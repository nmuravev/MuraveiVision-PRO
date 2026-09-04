import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';
import { logger } from '../services/logger';

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
}

interface NetworkState {
  config: NetworkConfig;
  status: NetworkStatus | null;
  bases: NetworkBase[];
  targets: NetworkTarget[];
  messages: NetworkMessage[];
  error: string | null;
  loadConfig: () => Promise<void>;
  saveConfig: (patch: Partial<NetworkConfig> & { hub_pin?: string }) => Promise<void>;
  fetchStatus: () => Promise<void>;
  fetchBases: () => Promise<void>;
  fetchTargets: () => Promise<void>;
  fetchMessages: () => Promise<void>;
  sendTarget: (payload: {
    class_name: string;
    confidence?: number;
    notes?: string;
    crop_path?: string;
    source_video?: string;
  }) => Promise<void>;
  sendMessage: (body: string) => Promise<void>;
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
