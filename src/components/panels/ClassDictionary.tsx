import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, Save } from 'lucide-react';
import { authHeaders } from '../../store/useMuraveiStore';
import type { ClassCatalogItem } from '../../types/muravei';

/** SYSTEM dictionary editor — engineer/master. */
export const ClassDictionary: React.FC = () => {
  const [classes, setClasses] = useState<ClassCatalogItem[]>([]);
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [nameRu, setNameRu] = useState('');
  const [aliasesText, setAliasesText] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [inPrompt, setInPrompt] = useState(false);
  const [confidenceThreshold, setConfidenceThreshold] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch('/api/classes/catalog', { headers: authHeaders() });
    if (!res.ok) throw new Error('catalog failed');
    const data = await res.json();
    setClasses(Array.isArray(data.classes) ? data.classes : []);
  }, []);

  useEffect(() => {
    void load().catch((e) => setErr(String(e)));
  }, [load]);

  const selected = useMemo(
    () => classes.find((c) => c.id === selectedId) || null,
    [classes, selectedId],
  );

  useEffect(() => {
    if (!selected) return;
    setNameRu(selected.name_ru || '');
    setAliasesText((selected.aliases || []).join(', '));
    setEnabled(selected.enabled !== false);
    setInPrompt(Boolean(selected.in_prompt));
    setConfidenceThreshold(
      selected.confidence_threshold != null
        ? String(selected.confidence_threshold)
        : '',
    );
  }, [selected]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return classes;
    return classes.filter(
      (c) =>
        String(c.id) === q ||
        c.name_en.toLowerCase().includes(q) ||
        c.name_raw.toLowerCase().includes(q) ||
        (c.name_ru || '').toLowerCase().includes(q),
    );
  }, [classes, query]);

  const save = async () => {
    if (selectedId == null) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const aliases = aliasesText
        .split(/[,;\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await fetch(`/api/classes/overrides/${selectedId}`, {
        method: 'PUT',
        headers: authHeaders(),
        body: JSON.stringify({
          name_ru: nameRu,
          aliases,
          enabled,
          in_prompt: inPrompt,
          confidence_threshold: confidenceThreshold
            ? Number(confidenceThreshold)
            : undefined,
          clear_confidence_threshold: !confidenceThreshold,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'save failed');
      if (Array.isArray(data.classes)) setClasses(data.classes);
      else await load();
      setMsg('Сохранено');
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const resetOverride = async () => {
    if (selectedId == null) return;
    if (!confirm('Сбросить override для этого класса?')) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/classes/overrides/${selectedId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'delete failed');
      if (Array.isArray(data.classes)) setClasses(data.classes);
      else await load();
      setMsg('Override сброшен');
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
      <div className="font-semibold flex items-center gap-2">
        <BookOpen size={14} /> Словарь классов
      </div>
      <input
        className="w-full bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 text-[11px]"
        placeholder="Поиск класса…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="grid grid-cols-2 gap-2 min-h-[180px]">
        <div className="max-h-48 overflow-auto border border-[var(--dv-border)] bg-black/30">
          {filtered.slice(0, 120).map((c) => (
            <button
              key={c.id}
              type="button"
              className={`w-full text-left px-1.5 py-0.5 text-[10px] hover:bg-[#333] ${
                c.id === selectedId ? 'bg-[#333] text-[var(--dv-accent)]' : ''
              } ${c.enabled === false ? 'opacity-40 line-through' : ''}`}
              onClick={() => setSelectedId(c.id)}
            >
              <span className="font-mono text-[9px] text-[var(--dv-text-muted)] mr-1">{c.id}</span>
              {c.name_en}
              {c.has_override ? <span className="ml-1 text-[8px] text-[var(--dv-accent)]">●</span> : null}
            </button>
          ))}
        </div>
        <div className="space-y-1.5 text-[11px]">
          {selected ? (
            <>
              <div className="text-[10px] text-[var(--dv-text-muted)] truncate" title={selected.name_raw}>
                {selected.name_raw}
              </div>
              <label className="block text-[10px] text-[var(--dv-text-muted)]">RU имя</label>
              <input
                className="w-full bg-[#1a1a1a] border border-[var(--dv-border)] px-1.5 py-0.5"
                value={nameRu}
                onChange={(e) => setNameRu(e.target.value)}
              />
              <label className="block text-[10px] text-[var(--dv-text-muted)]">
                Алиасы (через запятую)
              </label>
              <textarea
                className="w-full h-14 bg-[#1a1a1a] border border-[var(--dv-border)] px-1.5 py-0.5 resize-none"
                value={aliasesText}
                onChange={(e) => setAliasesText(e.target.value)}
                placeholder="car, truck, …"
              />
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                Включён в каталог / детекцию
              </label>
              <label className="flex items-center gap-1.5">
                <input type="checkbox" checked={inPrompt} onChange={(e) => setInPrompt(e.target.checked)} />
                YOLOE live-prompt
              </label>
              <label className="block text-[10px] text-[var(--dv-text-muted)]">
                Порог confidence для класса (0.01–1.00)
              </label>
              <input
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                className="w-full bg-[#1a1a1a] border border-[var(--dv-border)] px-1.5 py-0.5"
                value={confidenceThreshold}
                onChange={(e) => setConfidenceThreshold(e.target.value)}
                placeholder="общий порог"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  className="px-2 py-1 bg-[#333] rounded-sm inline-flex items-center gap-1 disabled:opacity-40"
                  onClick={() => void save()}
                >
                  <Save size={12} /> Сохранить
                </button>
                <button
                  type="button"
                  disabled={busy || !selected.has_override}
                  className="px-2 py-1 bg-[#333] rounded-sm disabled:opacity-40"
                  onClick={() => void resetOverride()}
                >
                  Сброс
                </button>
              </div>
            </>
          ) : (
            <div className="text-[10px] text-[var(--dv-text-muted)]">Выберите класс слева</div>
          )}
        </div>
      </div>
      {msg && <div className="text-[10px] text-[var(--dv-accent)]">{msg}</div>}
      {err && <div className="text-[10px] text-red-400">{err}</div>}
    </div>
  );
};

export default ClassDictionary;
