import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Folder,
  File,
  ChevronRight,
  ChevronDown,
  Trash2,
  RefreshCw,
  RotateCcw,
  X,
} from 'lucide-react';
import { useViewerStore } from '../../store/useViewerStore';
import { useMuraveiStore } from '../../store/useMuraveiStore';
import { usePanelLayoutStore } from '../../store/usePanelLayoutStore';
import { formatMediaTime, mediaPathsMatch } from '../../lib/mediaPaths';
import { Button } from '../ui';

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children?: FileNode[];
  size?: number;
  mtime?: number;
  duration_sec?: number;
}

type SortMode = 'name' | 'mtime' | 'duration';
type LayoutMode = 'tree' | 'list';

interface TrashItem {
  name: string;
  original?: string;
  trash_path: string;
  deleted_at?: number;
  size?: number;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('muravei-token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function formatBytes(n?: number): string {
  if (n == null || Number.isNaN(n)) return '';
  if (n < 1024) return `${n} Б`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} КБ`;
  return `${(n / (1024 * 1024)).toFixed(1)} МБ`;
}

export const MediaPool: React.FC = () => {
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTrash, setShowTrash] = useState(false);
  const [trashItems, setTrashItems] = useState<TrashItem[]>([]);
  const [trashLoading, setTrashLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<{ path: string; name: string } | null>(null);
  const [confirmPermanent, setConfirmPermanent] = useState<TrashItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [sortMode, setSortMode] = useState<SortMode>('name');
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('tree');

  const sortedTree = useMemo(() => {
    const sortNodes = (nodes: FileNode[]): FileNode[] =>
      [...nodes]
        .sort((a, b) => {
          if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
          if (sortMode === 'mtime') return (b.mtime || 0) - (a.mtime || 0);
          if (sortMode === 'duration') return (b.duration_sec || 0) - (a.duration_sec || 0);
          return a.name.localeCompare(b.name, 'ru');
        })
        .map((n) =>
          n.type === 'folder' && n.children?.length
            ? { ...n, children: sortNodes(n.children) }
            : n,
        );
    return sortNodes(fileTree);
  }, [fileTree, sortMode]);

  const flatFiles = useMemo(() => {
    const out: FileNode[] = [];
    const walk = (nodes: FileNode[]) => {
      for (const n of nodes) {
        if (n.type === 'file') out.push(n);
        else if (n.children) walk(n.children);
      }
    };
    walk(sortedTree);
    return out.sort((a, b) => {
      if (sortMode === 'mtime') return (b.mtime || 0) - (a.mtime || 0);
      if (sortMode === 'duration') return (b.duration_sec || 0) - (a.duration_sec || 0);
      return a.name.localeCompare(b.name, 'ru');
    });
  }, [sortedTree, sortMode]);

  const setSource = useViewerStore((s) => s.setSource);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const workspaceMode = usePanelLayoutStore((s) => s.workspaceMode);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/media/tree', { headers: authHeaders() });
      if (res.status === 401 || res.status === 403) {
        setFileTree([]);
        setError(res.status === 401 ? 'Войдите, чтобы открыть архив' : 'Доступ запрещён');
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setFileTree(data.tree ?? []);
      setError(null);
    } catch {
      setFileTree([]);
      setError('API медиа недоступен');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadTrash = useCallback(async () => {
    try {
      setTrashLoading(true);
      const res = await fetch('/api/media/trash', { headers: authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTrashItems(data.items ?? []);
    } catch {
      setTrashItems([]);
    } finally {
      setTrashLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [isAuthenticated, load]);

  // Auto-refresh when returning to MEDIA tab (not full F5)
  useEffect(() => {
    if (workspaceMode === 'mediaView') {
      void load();
    }
  }, [workspaceMode, load]);

  useEffect(() => {
    if (showTrash) void loadTrash();
  }, [showTrash, loadTrash]);

  const toggle = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const openInViewer = (path: string) => {
    setSource(focusedViewerId, path, null);
  };

  const moveToTrash = async () => {
    if (!confirmDelete) return;
    setBusy(true);
    try {
      const res = await fetch('/api/media/trash', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: confirmDelete.path }),
      });
      if (!res.ok) {
        const detail = await res.text();
        setError(detail || 'Не удалось переместить в корзину');
      } else {
        const trashed = confirmDelete.path;
        const focused = useViewerStore.getState().focusedViewerId;
        const current =
          useViewerStore.getState().viewers[focused]?.sourcePath ??
          useViewerStore.getState().viewers['viewer-1']?.sourcePath;
        if (current && mediaPathsMatch(current, trashed)) {
          useMuraveiStore.getState().clearDetections();
        }
        setConfirmDelete(null);
        await load();
        if (showTrash) await loadTrash();
      }
    } catch {
      setError('Ошибка при удалении');
    } finally {
      setBusy(false);
    }
  };

  const restoreItem = async (item: TrashItem) => {
    setBusy(true);
    try {
      const res = await fetch('/api/media/restore', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: item.trash_path }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(typeof data.detail === 'string' ? data.detail : 'Не удалось восстановить');
      } else {
        await loadTrash();
        await load();
      }
    } catch {
      setError('Ошибка восстановления');
    } finally {
      setBusy(false);
    }
  };

  const permanentDelete = async () => {
    if (!confirmPermanent) return;
    setBusy(true);
    try {
      const res = await fetch(
        `/api/media/permanent?path=${encodeURIComponent(confirmPermanent.trash_path)}`,
        { method: 'DELETE', headers: authHeaders() },
      );
      if (!res.ok) {
        setError('Не удалось удалить навсегда');
      } else {
        setConfirmPermanent(null);
        await loadTrash();
      }
    } catch {
      setError('Ошибка удаления');
    } finally {
      setBusy(false);
    }
  };

  const renderNode = (node: FileNode, depth = 0): React.ReactNode => {
    const pad = depth * 14;
    if (node.type === 'folder') {
      const open = expanded.has(node.path);
      return (
        <div key={node.path}>
          <div
            className="flex items-center gap-1.5 py-1 px-2 hover:bg-dv-hover cursor-pointer text-dv-text"
            style={{ paddingLeft: pad }}
            onClick={() => toggle(node.path)}
          >
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <Folder size={12} className="text-[var(--dv-accent)]" />
            <span className="text-xs truncate">{node.name}</span>
          </div>
          {open && node.children?.map((c) => renderNode(c, depth + 1))}
        </div>
      );
    }
    return (
      <div
        key={node.path}
        data-media-path={node.path}
        className="flex items-center gap-1.5 py-1 px-2 hover:bg-dv-hover cursor-pointer text-dv-text group"
        style={{ paddingLeft: pad + 14 }}
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData('text/plain', node.path);
          e.dataTransfer.effectAllowed = 'copy';
        }}
        onDoubleClick={() => openInViewer(node.path)}
      >
        <File size={12} className="text-[#6ea8fe]" />
        <span className="text-xs flex-1 truncate">{node.name}</span>
        {node.duration_sec != null && node.duration_sec > 0 ? (
          <span className="text-[9px] font-mono text-dv-muted shrink-0">
            {formatMediaTime(node.duration_sec)}
          </span>
        ) : null}
        {node.size ? (
          <span className="text-[9px] text-dv-muted shrink-0">{formatBytes(node.size)}</span>
        ) : null}
        <button
          type="button"
          title="В корзину"
          className="text-dv-muted hover:text-dv-hot opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => {
            e.stopPropagation();
            setConfirmDelete({ path: node.path, name: node.name });
          }}
        >
          <Trash2 size={11} />
        </button>
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col relative">
      <div className="flex items-center gap-1 px-2 py-1 border-b border-dv-border shrink-0">
        <Button size="sm" title="Обновить" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          Обновить
        </Button>
        <Button size="sm" active={showTrash} title="Корзина" onClick={() => setShowTrash((v) => !v)}>
          <Trash2 size={11} />
          Корзина
        </Button>
        <select
          className="bg-dv-deep border border-dv-border text-[10px] px-1 py-0.5 rounded-sm"
          value={sortMode}
          onChange={(e) => setSortMode(e.target.value as SortMode)}
          title="Сортировка"
        >
          <option value="name">Имя</option>
          <option value="mtime">Дата</option>
          <option value="duration">Длительность</option>
        </select>
        <select
          className="bg-dv-deep border border-dv-border text-[10px] px-1 py-0.5 rounded-sm"
          value={layoutMode}
          onChange={(e) => setLayoutMode(e.target.value as LayoutMode)}
          title="Вид"
        >
          <option value="tree">Дерево</option>
          <option value="list">Список</option>
        </select>
      </div>

      {error && (
        <div className="px-2 py-1 text-[10px] text-dv-accent border-b border-dv-border flex items-center gap-2">
          <span className="flex-1 truncate">{error}</span>
          <button type="button" className="shrink-0" onClick={() => setError(null)}>
            <X size={10} />
          </button>
        </div>
      )}

      {showTrash ? (
        <div className="flex-1 overflow-auto">
          {trashLoading ? (
            <div className="p-3 text-xs text-dv-muted">Загрузка корзины…</div>
          ) : trashItems.length === 0 ? (
            <div className="p-4 text-xs text-dv-muted text-center space-y-1">
              <div className="text-dv-text text-[12px] font-medium">Корзина пуста</div>
              <div>Удалённые файлы хранятся здесь до 30 дней</div>
            </div>
          ) : (
            trashItems.map((item) => (
              <div
                key={item.trash_path}
                className="flex items-center gap-1.5 py-1.5 px-2 hover:bg-dv-hover text-dv-text border-b border-dv-border/40"
              >
                <File size={12} className="text-dv-muted shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs truncate">{item.name}</div>
                  <div className="text-[9px] text-dv-muted truncate">
                    {formatBytes(item.size)}
                    {item.deleted_at
                      ? ` · ${new Date(item.deleted_at * 1000).toLocaleString('ru-RU')}`
                      : ''}
                  </div>
                </div>
                <Button size="sm" disabled={busy} onClick={() => void restoreItem(item)}>
                  <RotateCcw size={10} />
                  Восстановить
                </Button>
                <Button size="sm" variant="danger" disabled={busy} onClick={() => setConfirmPermanent(item)}>
                  Удалить
                </Button>
              </div>
            ))
          )}
        </div>
      ) : loading && fileTree.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-dv-muted text-xs">
          Загрузка…
        </div>
      ) : fileTree.length === 0 ||
        (fileTree.length === 1 &&
          fileTree[0].type === 'folder' &&
          !(fileTree[0].children && fileTree[0].children.length > 0)) ? (
        <div className="flex-1 flex flex-col items-center justify-center p-4 text-center gap-1">
          <Folder size={28} className="text-dv-muted mb-1 opacity-60" />
          <div className="text-[12px] font-medium text-dv-text">Архив пуст</div>
          <div className="text-[11px] text-dv-muted max-w-[220px]">
            Скопируйте ролики в папку archive/ и нажмите «Обновить»
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          {layoutMode === 'tree'
            ? sortedTree.map((n) => renderNode(n))
            : flatFiles.map((node) => (
                <div
                  key={node.path}
                  className="flex items-center gap-1.5 py-1 px-2 hover:bg-dv-hover cursor-pointer text-dv-text group"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData('text/plain', node.path);
                    e.dataTransfer.effectAllowed = 'copy';
                  }}
                  onDoubleClick={() => openInViewer(node.path)}
                >
                  <File size={12} className="text-[#6ea8fe]" />
                  <span className="text-xs flex-1 truncate">{node.name}</span>
                  {node.duration_sec != null && node.duration_sec > 0 ? (
                    <span className="text-[9px] font-mono text-dv-muted shrink-0">
                      {formatMediaTime(node.duration_sec)}
                    </span>
                  ) : null}
                  {node.mtime ? (
                    <span className="text-[9px] text-dv-muted shrink-0 hidden sm:inline">
                      {new Date(node.mtime * 1000).toLocaleDateString('ru-RU')}
                    </span>
                  ) : null}
                </div>
              ))}
        </div>
      )}

      {confirmDelete && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/60 p-3">
          <div className="bg-dv-panel border border-dv-border rounded-sm p-3 max-w-[280px] w-full shadow-xl">
            <p className="text-xs text-dv-text mb-3">
              Удалить файл «{confirmDelete.name}»? Файл будет перемещён в корзину.
            </p>
            <div className="flex justify-end gap-2">
              <Button size="sm" disabled={busy} onClick={() => setConfirmDelete(null)}>
                Отмена
              </Button>
              <Button size="sm" variant="danger" disabled={busy} onClick={() => void moveToTrash()}>
                Удалить
              </Button>
            </div>
          </div>
        </div>
      )}

      {confirmPermanent && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/60 p-3">
          <div className="bg-dv-panel border border-dv-border rounded-sm p-3 max-w-[280px] w-full shadow-xl">
            <p className="text-xs text-dv-text mb-3">
              Удалить «{confirmPermanent.name}» навсегда? Это действие необратимо.
            </p>
            <div className="flex justify-end gap-2">
              <Button size="sm" disabled={busy} onClick={() => setConfirmPermanent(null)}>
                Отмена
              </Button>
              <Button
                size="sm"
                variant="danger"
                disabled={busy}
                onClick={() => void permanentDelete()}
              >
                Удалить навсегда
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MediaPool;
