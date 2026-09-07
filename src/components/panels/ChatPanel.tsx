import React, { useEffect, useState } from 'react';
import { MessageSquare, RefreshCw, Send } from 'lucide-react';
import { useNetworkStore } from '../../store/useNetworkStore';
import { useMuraveiStore } from '../../store/useMuraveiStore';

function formatTs(epoch: number): string {
  try {
    return new Date(epoch * 1000).toLocaleTimeString();
  } catch {
    return '';
  }
}

export const ChatPanel: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const config = useNetworkStore((s) => s.config);
  const messages = useNetworkStore((s) => s.messages);
  const bases = useNetworkStore((s) => s.bases);
  const unreadCount = useNetworkStore((s) => s.unreadCount);
  const error = useNetworkStore((s) => s.error);
  const fetchMessages = useNetworkStore((s) => s.fetchMessages);
  const fetchBases = useNetworkStore((s) => s.fetchBases);
  const sendMessage = useNetworkStore((s) => s.sendMessage);
  const markChatSeen = useNetworkStore((s) => s.markChatSeen);

  const [chat, setChat] = useState('');
  const [busy, setBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);

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

  const ordered = [...messages].sort((a, b) => a.created_at - b.created_at);

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
              <div className="mt-0.5 leading-snug whitespace-pre-wrap break-words">{m.body}</div>
            </div>
          );
        })}
      </div>

      <div className="p-2 border-t border-[var(--dv-border)] flex gap-1 flex-shrink-0">
        <input
          className="flex-1 bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1.5 rounded-sm"
          value={chat}
          placeholder={config.mode === 'off' ? 'Сеть выключена' : 'Сообщение…'}
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
