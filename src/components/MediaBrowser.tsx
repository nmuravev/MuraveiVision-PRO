import React, { useEffect, useState } from 'react';
import { Folder, File, Trash2, ChevronRight, ChevronDown } from 'lucide-react';

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  children?: FileNode[];
  size?: number;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('muravei-token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Legacy media browser — same archive API as MediaPool (no mock tree). */
export const MediaBrowser: React.FC = () => {
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadFileTree = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/media/tree', { headers: authHeaders() });
      if (response.status === 401 || response.status === 403) {
        setFileTree([]);
        setError(response.status === 401 ? 'Sign in to browse archive' : 'Path forbidden');
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setFileTree(data.tree ?? []);
      setError(null);
    } catch (err) {
      setFileTree([]);
      setError('Не удалось загрузить файлы. Проверьте backend.');
      console.error('Failed to load file tree:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadFileTree();
  }, []);

  const toggleFolder = (path: string) => {
    const next = new Set(expandedFolders);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setExpandedFolders(next);
  };

  const handleDelete = async (path: string) => {
    if (!confirm(`Удалить файл? Он будет перемещён в корзину.`)) return;
    try {
      await fetch(`/api/media/delete?path=${encodeURIComponent(path)}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      await loadFileTree();
    } catch (e) {
      console.error(e);
    }
  };

  const renderNode = (node: FileNode, depth = 0): React.ReactNode => {
    const pad = depth * 16;
    if (node.type === 'folder') {
      const open = expandedFolders.has(node.path);
      return (
        <div key={node.path}>
          <button
            type="button"
            className="w-full flex items-center gap-1 py-1 px-2 text-left text-sm hover:bg-[#333]"
            style={{ paddingLeft: pad }}
            onClick={() => toggleFolder(node.path)}
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <Folder size={14} className="text-amber-400" />
            <span>{node.name}</span>
          </button>
          {open && node.children?.map((c) => renderNode(c, depth + 1))}
        </div>
      );
    }
    return (
      <div
        key={node.path}
        className="flex items-center gap-1 py-1 px-2 text-sm hover:bg-[#333] group"
        style={{ paddingLeft: pad + 18 }}
      >
        <File size={14} className="text-slate-400" />
        <span className="truncate flex-1">{node.name}</span>
        <button
          type="button"
          className="opacity-0 group-hover:opacity-100 text-red-400"
          onClick={() => void handleDelete(node.path)}
          title="Delete"
        >
          <Trash2 size={14} />
        </button>
      </div>
    );
  };

  if (loading) {
    return <div className="p-3 text-sm text-[var(--dv-text-muted)]">Загрузка…</div>;
  }
  if (error) {
    return <div className="p-3 text-sm text-red-400">{error}</div>;
  }
  return (
    <div className="h-full overflow-auto text-[var(--dv-text)]">
      {fileTree.length === 0 ? (
        <div className="p-3 text-sm text-[var(--dv-text-muted)]">Архив пуст</div>
      ) : (
        fileTree.map((n) => renderNode(n))
      )}
    </div>
  );
};

export default MediaBrowser;
