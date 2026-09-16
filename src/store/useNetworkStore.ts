import { create } from 'zustand';
import { authHeaders, authToken } from './useMuraveiStore';
import { logger } from '../services/logger';

const CHAT_WS_BACKOFF_MAX_MS = 60_000;
let chatWsSocket: WebSocket | null = null;
let chatWsReconnectTimer: ReturnType<typeof setTimeout> | null = null;
let chatWsBackoffMs = 1000;

const CHAT_SEEN_KEY = 'muravei_chat_last_seen_at';

export interface NetworkConfig {
  mode: 'off' | 'server' | 'client';
  server_ip: string;
  port: number;
  base_name: string;
  base_id?: string;
  has_hub_pin?: boolean;
  lan_beacon_enabled?: boolean;
  lan_beacon_port?: number;
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
  ws_peer?: 'connected' | 'down' | string;
  ws_peer_last_error?: string | null;
  lan_beacon_enabled?: boolean;
  lan_beacon_port?: number;
  lan_beacon_peers?: number;
}

export interface NetworkBeaconPeer {
  base_id: string;
  base_name: string;
  ip: string;
  port: number;
  ts: number;
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
  attachment_id?: string | null;
}

interface NetworkState {
  config: NetworkConfig;
  status: NetworkStatus | null;
  bases: NetworkBase[];
  targets: NetworkTarget[];
  lanPeers: NetworkBeaconPeer[];
  messages: NetworkMessage[];
  unreadCount: number;
  lastChatSeenAt: number;
  error: string | null;
  loadConfig: () => Promise<void>;
  saveConfig: (patch: Partial<NetworkConfig> & { hub_pin?: string }) => Promise<void>;
  fetchStatus: () => Promise<void>;
  fetchBases: () => Promise<void>;
  fetchTargets: () => Promise<void>;
  fetchLanPeers: () => Promise<void>;
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
  sendMessage: (body: string, attachmentId?: string) => Promise<void>;
  sendAttachment: (file: File, caption?: string) => Promise<void>;
  offerReconPackage: (jobId: string, artifacts: string[]) => Promise<void>;
  acceptReconPackage: (
    packageId: string,
    selected: string[],
  ) => Promise<{ job_id: string; unpacked: string[] }>;
  connectChatSocket: () => void;
  disconnectChatSocket: () => void;
  mergeChatMessage: (msg: NetworkMessage) => void;
}

export function networkAttachmentSrc(attachmentId: string): string {
  const token = encodeURIComponent(authToken());
  return `/api/network/attachments/${encodeURIComponent(attachmentId)}/bytes?token=${token}`;
}

async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function chatWsLocalUrl(): string {
  const token = authToken();
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/chat?token=${encodeURIComponent(token)}`;
}

function mergeMessagesList(
  existing: NetworkMessage[],
  msg: NetworkMessage,
): NetworkMessage[] {
  if (existing.some((m) => m.id === msg.id)) return existing;
  return [...existing, msg];
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
  lanPeers: [],
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
          lan_beacon_enabled: Boolean(data.lan_beacon_enabled),
          lan_beacon_port: Number(data.lan_beacon_port) || 8001,
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
      lan_beacon_enabled: next.lan_beacon_enabled ?? false,
      lan_beacon_port: next.lan_beacon_port ?? 8001,
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
        lan_beacon_enabled: Boolean(data.lan_beacon_enabled),
        lan_beacon_port: Number(data.lan_beacon_port) || 8001,
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
        ws_peer: data.ws_peer || 'down',
        ws_peer_last_error: data.ws_peer_last_error ?? null,
        lan_beacon_enabled: Boolean(data.lan_beacon_enabled),
        lan_beacon_port: Number(data.lan_beacon_port) || 8001,
        lan_beacon_peers: Number(data.lan_beacon_peers) || 0,
      },
    });
  },

  mergeChatMessage: (msg) => {
    const since = get().lastChatSeenAt;
    set((state) => ({
      messages: mergeMessagesList(state.messages, msg),
      unreadCount:
        msg.direction === 'in' && Number(msg.created_at) > since
          ? state.unreadCount + 1
          : state.unreadCount,
    }));
  },

  disconnectChatSocket: () => {
    if (chatWsReconnectTimer != null) {
      clearTimeout(chatWsReconnectTimer);
      chatWsReconnectTimer = null;
    }
    chatWsBackoffMs = 1000;
    if (chatWsSocket) {
      chatWsSocket.onclose = null;
      chatWsSocket.close();
      chatWsSocket = null;
    }
  },

  connectChatSocket: () => {
    const { config } = get();
    if (config.mode === 'off' || !authToken()) {
      get().disconnectChatSocket();
      return;
    }
    if (
      chatWsSocket &&
      (chatWsSocket.readyState === WebSocket.OPEN ||
        chatWsSocket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    get().disconnectChatSocket();
    const url = chatWsLocalUrl();
    try {
      const ws = new WebSocket(url);
      chatWsSocket = ws;
      ws.onopen = () => {
        chatWsBackoffMs = 1000;
        logger.debug('network', 'Chat WS connected (local)');
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(String(ev.data)) as {
            type?: string;
            message?: NetworkMessage;
          };
          if (data.type === 'chat.message' && data.message?.id) {
            get().mergeChatMessage(data.message);
          }
        } catch {
          /* ignore malformed */
        }
      };
      ws.onclose = () => {
        chatWsSocket = null;
        const mode = get().config.mode;
        if (mode === 'off' || !authToken()) return;
        const jitter = Math.floor(Math.random() * 500);
        const delay = Math.min(CHAT_WS_BACKOFF_MAX_MS, chatWsBackoffMs) + jitter;
        chatWsBackoffMs = Math.min(CHAT_WS_BACKOFF_MAX_MS, chatWsBackoffMs * 2);
        chatWsReconnectTimer = setTimeout(() => {
          chatWsReconnectTimer = null;
          get().connectChatSocket();
        }, delay);
      };
      ws.onerror = () => {
        /* onclose handles reconnect */
      };
    } catch (e) {
      logger.warn('network', e instanceof Error ? e.message : 'Chat WS failed');
    }
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

  fetchLanPeers: async () => {
    const res = await fetch('/api/network/beacon/peers', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    set({ lanPeers: Array.isArray(data.peers) ? data.peers : [] });
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

  sendMessage: async (body, attachmentId) => {
    const payload: Record<string, unknown> = { body };
    if (attachmentId) payload.attachment_id = attachmentId;
    const res = await fetch('/api/network/messages', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка сообщения');
    if (data.message?.id) {
      get().mergeChatMessage(data.message as NetworkMessage);
    } else {
      await get().fetchMessages();
    }
  },

  sendAttachment: async (file, caption) => {
    const maxBytes = 8 * 1024 * 1024;
    if (file.size <= 0 || file.size > maxBytes) {
      throw new Error('Файл до 8 МБ');
    }
    const buf = await file.arrayBuffer();
    const digest = await sha256Hex(buf);
    const initRes = await fetch('/api/network/attachments', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        filename: file.name || 'screenshot.jpg',
        content_type: file.type || 'image/jpeg',
        size: file.size,
        sha256: digest,
      }),
    });
    const initData = await initRes.json().catch(() => ({}));
    if (!initRes.ok) {
      throw new Error(
        typeof initData.detail === 'string' ? initData.detail : 'Ошибка вложения',
      );
    }
    const att = initData.attachment || {};
    const aid = String(att.id || '');
    const chunkSize = Number(att.chunk_size) || 256 * 1024;
    const total = Number(att.total_chunks) || Math.ceil(file.size / chunkSize);
    if (!aid) throw new Error('Нет attachment_id');
    if (!att.complete) {
      const bytes = new Uint8Array(buf);
      for (let i = 0; i < total; i += 1) {
        const start = i * chunkSize;
        const end = Math.min(bytes.length, start + chunkSize);
        const slice = bytes.subarray(start, end);
        const put = await fetch(`/api/network/attachments/${encodeURIComponent(aid)}/chunks/${i}`, {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${authToken()}`,
            'Content-Type': 'application/octet-stream',
          },
          body: slice,
        });
        if (!put.ok) {
          const err = await put.json().catch(() => ({}));
          throw new Error(typeof err.detail === 'string' ? err.detail : `Чанк ${i}`);
        }
      }
      const fin = await fetch(`/api/network/attachments/${encodeURIComponent(aid)}/finalize`, {
        method: 'POST',
        headers: authHeaders(),
        body: '{}',
      });
      const finData = await fin.json().catch(() => ({}));
      if (!fin.ok) {
        throw new Error(
          typeof finData.detail === 'string' ? finData.detail : 'Ошибка сборки вложения',
        );
      }
    }
    const text = (caption || '').trim() || file.name || 'вложение';
    await get().sendMessage(text, aid);
  },

  offerReconPackage: async (jobId, artifacts) => {
    const res = await fetch('/api/network/recon-packages', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ job_id: jobId, artifacts }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Ошибка пакета 3D');
    }
    if (data.message?.id) get().mergeChatMessage(data.message as NetworkMessage);
    logger.info('network', `Пакет 3D предложен: ${jobId}`);
  },

  acceptReconPackage: async (packageId, selected) => {
    const res = await fetch(
      `/api/network/recon-packages/${encodeURIComponent(packageId)}/pull`,
      {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ selected }),
      },
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(
        typeof data.detail === 'string' ? data.detail : 'Не удалось принять пакет 3D',
      );
    }
    logger.info('network', `Пакет 3D принят: ${data.job_id || packageId}`);
    return {
      job_id: String(data.job_id || ''),
      unpacked: Array.isArray(data.unpacked) ? data.unpacked : selected,
    };
  },
}));
