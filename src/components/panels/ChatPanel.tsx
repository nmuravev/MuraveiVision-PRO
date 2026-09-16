import React, { useEffect, useRef, useState } from 'react';
import { Crosshair, ImagePlus, MessageSquare, RefreshCw, Send } from 'lucide-react';
import {
  networkAttachmentSrc,
  useNetworkStore,
} from '../../store/useNetworkStore';
import { useTimelineStore } from '../../store/timeline-store';
import {
  formatDetectionRef,
  splitChatBody,
} from '../../lib/chatDetectionRefs';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';

function formatTs(epoch: number): string {
  try {
    return new Date(epoch * 1000).toLocaleTimeString();
  } catch {
    return '';
  }
}

type RemoteCard = {
  id: string;
  class_name?: string;
  confidence?: number;
  gps_lat?: number | null;
  gps_lon?: number | null;
  source_video?: string | null;
  source_base?: string | null;
  notes?: string | null;
  missing?: boolean;
};

export const ChatPanel: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const detections = useMuraveiStore((s) => s.detections);
  const activeDetectionId = useMuraveiStore((s) => s.activeDetectionId);
  const setActiveDetectionId = useMuraveiStore((s) => s.setActiveDetectionId);
  const seekTo = useTimelineStore((s) => s.seekTo);

  const config = useNetworkStore((s) => s.config);
    const messages = useNetworkStore((s) => s.messages);
  const targets = useNetworkStore((s) => s.targets);
  const bases = useNetworkStore((s) => s.bases);
  const unreadCount = useNetworkStore((s) => s.unreadCount);
  const error = useNetworkStore((s) => s.error);
  const fetchMessages = useNetworkStore((s) => s.fetchMessages);
  const fetchBases = useNetworkStore((s) => s.fetchBases);
  const sendMessage = useNetworkStore((s) => s.sendMessage);
  const sendAttachment = useNetworkStore((s) => s.sendAttachment);
  const markChatSeen = useNetworkStore((s) => s.markChatSeen);
  const fileRef = useRef<HTMLInputElement>(null);

  const [chat, setChat] = useState('');
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [remoteCard, setRemoteCard] = useState<RemoteCard | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;
    markChatSeen();
    void fetchMessages();
    void fetchBases();
    const t = window.setInterval(() => {
      void fetchMessages();
      void fetchBases();
    }, 5000);
    return () => window.clearInterval(t);
  }, [isAuthenticated, fetchMessages, fetchBases, markChatSeen]);

  const onSend = async () => {
    if (!chat.trim()) return;
    setBusy(true);
    setLocalErr(null);
    try {
      await sendMessage(chat.trim());
      setChat('');
      markChatSeen();
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  const onPickFile = async (file: File | null) => {
    if (!file) return;
    setBusy(true);
    setLocalErr(null);
    try {
      await sendAttachment(file, chat.trim() || undefined);
      setChat('');
      markChatSeen();
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'Ошибка вложения');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const insertDetectionRef = () => {
    if (!activeDetectionId) {
      setLocalErr('Выберите детекцию в Viewer / Timeline');
      return;
    }
    const token = formatDetectionRef(activeDetectionId);
    setChat((prev) => (prev.trim() ? `${prev.trim()} ${token}` : token));
    setLocalErr(null);
  };

  const onDetectionClick = async (detId: string) => {
    const row = detections.find((d) => d.id === detId || d.id.toLowerCase() === detId);
    if (row) {
      setActiveDetectionId(row.id);
      if (typeof row.time_sec === 'number') seekTo(row.time_sec);
      setRemoteCard(null);
      return;
    }
    // Remote / missing locally — try API then show card
    try {
      const res = await fetch(`/api/detections/${encodeURIComponent(detId)}`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setRemoteCard({
          id: detId,
          class_name: data.class_name,
          confidence: data.confidence,
          gps_lat: data.gps_lat,
          gps_lon: data.gps_lon,
          source_video: data.source_video,
          notes: data.user_notes || data.notes,
          missing: false,
        });
        if (typeof data.time_sec === 'number') {
          setActiveDetectionId(data.id || detId);
          seekTo(data.time_sec);
        }
        return;
      }
    } catch {
      /* fall through */
    }
    // Look at shared network targets that reference this detection
    const netHit = targets.find(
      (t) =>
        (t.notes || '').toLowerCase().includes(`detection_id=${detId}`) ||
        (t.notes || '').toLowerCase().includes(`detection:${detId}`),
    );
    if (netHit) {
      setRemoteCard({
        id: detId,
        class_name: netHit.class_name,
        confidence: netHit.confidence,
        gps_lat: netHit.gps_lat,
        gps_lon: netHit.gps_lon,
        source_video: netHit.source_video,
        source_base: netHit.source_base,
        notes: netHit.notes,
        missing: false,
      });
      return;
    }
    setRemoteCard({
      id: detId,
      missing: true,
      source_base: 'удалённая база',
      notes: 'Детекция не найдена на этой машине — открыть на базе-источнике.',
    });
  };

  const ordered = [...messages].sort((a, b) => a.created_at - b.created_at);

  const renderBody = (body: string) =>
    splitChatBody(body).map((part, i) => {
      if (part.kind === 'text') {
        return (
          <span key={i} className="whitespace-pre-wrap break-words">
            {part.text}
          </span>
        );
      }
      return (
        <button
          key={i}
          type="button"
          className="inline text-sky-400 underline underline-offset-2 hover:text-sky-300 mx-0.5"
          title={`Открыть detection:${part.id}`}
          onClick={() => void onDetectionClick(part.id)}
        >
          {part.raw}
        </button>
      );
    });

  return (
    <div className="h-full flex flex-col bg-[var(--dv-panel)] text-xs overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--dv-border)] flex items-center gap-2 flex-shrink-0">
        <MessageSquare size={14} className="text-[var(--dv-accent)]" />
        <span className="font-semibold text-[11px]">Чат баз</span>
        {unreadCount > 0 && (
          <span
            className="min-w-[1.1rem] h-4 px-1 rounded-sm bg-amber-600 text-[10px] text-white flex items-center justify-center"
            title="Непрочитанные входящие"
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
        <button
          type="button"
          className="ml-auto p-1 rounded-sm hover:bg-[#333] text-[var(--dv-text-muted)]"
          onClick={() => {
            void fetchMessages();
            markChatSeen();
          }}
          title="Обновить"
        >
          <RefreshCw size={12} />
        </button>
      </div>

      <div className="px-3 py-1.5 border-b border-[var(--dv-border)] flex flex-wrap gap-1.5 text-[10px] text-[var(--dv-text-muted)]">
        {bases.length === 0 ? (
          <span>Нет heartbeat от других баз</span>
        ) : (
          bases.slice(0, 8).map((b) => (
            <span
              key={b.id}
              className={
                b.status === 'online'
                  ? 'px-1.5 py-0.5 rounded-sm border border-[var(--dv-border)] text-emerald-400'
                  : 'px-1.5 py-0.5 rounded-sm border border-[var(--dv-border)] text-slate-500'
              }
              title={`${b.ip} · ${b.status}`}
            >
              {b.base_name}
            </span>
          ))
        )}
      </div>

      {(error || localErr) && (
        <div className="mx-3 mt-2 text-amber-300 text-[11px] border border-amber-800/50 bg-amber-950/30 px-2 py-1.5 rounded-sm">
          {localErr || error}
        </div>
      )}

      {remoteCard && (
        <div className="mx-3 mt-2 border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] px-2 py-1.5 rounded-sm text-[10px] space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-sky-400 font-medium">detection:{remoteCard.id}</span>
            <button
              type="button"
              className="ml-auto text-[var(--dv-text-muted)] hover:text-white"
              onClick={() => setRemoteCard(null)}
            >
              закрыть
            </button>
          </div>
          {remoteCard.missing ? (
            <div className="text-amber-300">{remoteCard.notes}</div>
          ) : (
            <>
              {remoteCard.class_name && (
                <div>
                  Класс: {remoteCard.class_name}
                  {typeof remoteCard.confidence === 'number'
                    ? ` · ${(remoteCard.confidence * 100).toFixed(0)}%`
                    : ''}
                </div>
              )}
              {(remoteCard.gps_lat != null || remoteCard.gps_lon != null) && (
                <div>
                  GPS: {remoteCard.gps_lat ?? '—'}, {remoteCard.gps_lon ?? '—'}
                </div>
              )}
              {remoteCard.source_video && (
                <div className="truncate" title={remoteCard.source_video}>
                  Видео: {remoteCard.source_video}
                </div>
              )}
              {remoteCard.notes && <div className="text-[var(--dv-text-muted)]">{remoteCard.notes}</div>}
            </>
          )}
        </div>
      )}

      <div className="flex-1 overflow-auto p-3 space-y-1.5">
        {ordered.length === 0 && (
          <div className="text-[var(--dv-text-muted)]">Нет сообщений</div>
        )}
        {ordered.map((m) => {
          const incoming = m.direction === 'in';
          const rowClass = incoming
            ? 'rounded-sm px-2 py-1.5 border border-[var(--dv-border)] bg-[var(--dv-bg-deep)]'
            : 'rounded-sm px-2 py-1.5 border border-[var(--dv-border)] bg-emerald-950/40';
          return (
            <div key={m.id} className={rowClass}>
              <div className="flex items-baseline gap-2 text-[10px] text-[var(--dv-text-muted)]">
                <span className={incoming ? 'text-sky-400' : 'text-emerald-400'}>
                  {incoming ? 'вх' : 'исх'}
                </span>
                <span className="font-medium text-[var(--dv-text)] truncate">{m.sender}</span>
                <span className="ml-auto shrink-0">{formatTs(m.created_at)}</span>
              </div>
              <div className="mt-0.5 leading-snug">{renderBody(m.body)}</div>
              {m.attachment_id && (
                <a
                  href={networkAttachmentSrc(m.attachment_id)}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 block"
                  title="Открыть вложение"
                >
                  <img
                    src={networkAttachmentSrc(m.attachment_id)}
                    alt="вложение"
                    className="max-h-40 max-w-full rounded-sm border border-[var(--dv-border)] object-contain bg-black/30"
                  />
                </a>
              )}
            </div>
          );
        })}
      </div>

      <div className="p-2 border-t border-[var(--dv-border)] flex gap-1 flex-shrink-0">
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          className="hidden"
          onChange={(e) => void onPickFile(e.target.files?.[0] || null)}
        />
        <button
          type="button"
          disabled={busy || config.mode === 'off'}
          className="px-2 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
          onClick={() => fileRef.current?.click()}
          title="Прикрепить скриншот / кроп (до 8 МБ)"
        >
          <ImagePlus size={12} />
        </button>
        <button
          type="button"
          disabled={busy || config.mode === 'off' || !activeDetectionId}
          className="px-2 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
          onClick={insertDetectionRef}
          title="Вставить detection:<id> активной детекции"
        >
          <Crosshair size={12} />
        </button>
        <input
          className="flex-1 bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1.5 rounded-sm"
          value={chat}
          placeholder={config.mode === 'off' ? 'Сеть выключена' : 'Сообщение… detection:<id>'}
          disabled={config.mode === 'off'}
          onChange={(e) => setChat(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void onSend();
          }}
        />
        <button
          type="button"
          disabled={busy || config.mode === 'off' || !chat.trim()}
          className="px-2 rounded-sm bg-[#2e2e2e] disabled:opacity-40"
          onClick={() => void onSend()}
          title="Отправить"
        >
          <Send size={12} />
        </button>
      </div>
    </div>
  );
};

export default ChatPanel;
