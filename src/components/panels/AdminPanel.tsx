import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Eye, KeyRound, RefreshCw, Upload, Cpu, Usb } from 'lucide-react';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';
import { ClassDictionary } from './ClassDictionary';
import { Modal } from '../ui';

type Hw = Record<string, unknown>;

export const AdminPanel: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const userRole = useMuraveiStore((s) => s.userRole);
  const isEng = userRole === 'engineer' || userRole === 'master';
  const isMaster = userRole === 'master';

  const [hw, setHw] = useState<Hw | null>(null);
  const [selftest, setSelftest] = useState<string | null>(null);
  const [sim, setSim] = useState<string | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importLog, setImportLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [peek, setPeek] = useState<{ role: string; pin: string } | null>(null);
  const [newPin, setNewPin] = useState('');
  const [pinRole, setPinRole] = useState('operator');
  const [masterPin, setMasterPin] = useState('');
  const [info, setInfo] = useState<string | null>(null);
  const [usbBusy, setUsbBusy] = useState(false);
  const [usbDrives, setUsbDrives] = useState<
    Array<{
      letter: string;
      label: string;
      files: Array<{
        path: string;
        name: string;
        type: 'model' | 'classes';
        size_mb: number;
        valid: boolean;
        nc?: number | null;
        count?: number | null;
        error?: string | null;
      }>;
    }>
  >([]);
  const [usbErrors, setUsbErrors] = useState<string[]>([]);
  const [usbPending, setUsbPending] = useState<{
    path: string;
    type: 'model' | 'classes';
    dest?: string;
    message?: string;
  } | null>(null);
  const [usbResult, setUsbResult] = useState<string | null>(null);

  // Detection inference config (SAHI + Response Validator)
  type DetectCfg = {
    use_sahi_default: boolean;
    slice_height: number;
    slice_width: number;
    overlap_ratio: number;
    validator_enabled: boolean;
    validator_min_bbox_area: number;
    validator_max_bbox_area: number;
    validator_min_confidence: number;
  };
  const [detectCfg, setDetectCfg] = useState<DetectCfg | null>(null);
  const [detectCfgSaved, setDetectCfgSaved] = useState<string | null>(null);
  const [segStatus, setSegStatus] = useState<{
    ready: boolean;
    loaded: boolean;
    weight: string | null;
    available: string[];
  } | null>(null);
  const [segWeightPick, setSegWeightPick] = useState('yolo26n-seg.pt');
  const [segBusy, setSegBusy] = useState(false);
  const [segMsg, setSegMsg] = useState<string | null>(null);

  const loadDetectCfg = useCallback(async () => {
    if (!isEng) return;
    const res = await fetch('/api/system/detect-config', { headers: authHeaders() });
    if (!res.ok) throw new Error('detect-config load failed');
    setDetectCfg(await res.json());
  }, [isEng]);

  const saveDetectCfg = useCallback(
    async (next: DetectCfg) => {
      const res = await fetch('/api/system/detect-config', {
        method: 'PUT',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((data as { detail?: string }).detail || 'detect-config save failed');
      setDetectCfg(data as DetectCfg);
      setDetectCfgSaved('Сохранено');
      window.setTimeout(() => setDetectCfgSaved(null), 2000);
    },
    [],
  );

  useEffect(() => {
    if (!isAuthenticated || !isEng) return;
    void loadDetectCfg().catch((e) => setError(String(e)));
  }, [isAuthenticated, isEng, loadDetectCfg]);

  const refreshSegStatus = useCallback(async () => {
    const res = await fetch('/api/seg/status', { headers: authHeaders() });
    if (!res.ok) return;
    const data = (await res.json()) as {
      ready?: boolean;
      loaded?: boolean;
      weight?: string | null;
      available?: string[];
    };
    const available = Array.isArray(data.available) ? data.available : [];
    setSegStatus({
      ready: Boolean(data.ready),
      loaded: Boolean(data.loaded),
      weight: data.weight ?? null,
      available,
    });
    setSegWeightPick((prev) => (available.includes(prev) ? prev : available[0] || prev));
  }, []);

  useEffect(() => {
    if (!isAuthenticated || !isEng) return;
    void refreshSegStatus().catch(() => undefined);
  }, [isAuthenticated, isEng, refreshSegStatus]);

  const refreshHw = useCallback(async () => {
    if (!isEng) return;
    const res = await fetch('/api/system/hardware', { headers: authHeaders() });
    if (!res.ok) throw new Error('hardware failed');
    setHw(await res.json());
  }, [isEng]);

  useEffect(() => {
    if (!isAuthenticated || !isEng) return;
    void refreshHw().catch((e) => setError(String(e)));
    const id = window.setInterval(() => {
      void refreshHw().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(id);
  }, [isAuthenticated, isEng, refreshHw]);

  useEffect(() => {
    if (!peek) return;
    const t = window.setTimeout(() => setPeek(null), 4000);
    return () => window.clearTimeout(t);
  }, [peek]);

  if (!isAuthenticated) {
    return <div className="p-4 text-xs text-[var(--dv-text-muted)]">Войдите как engineer/master</div>;
  }
  if (!isEng) {
    return (
      <div className="p-4 text-xs text-[var(--dv-text-muted)]">
        Панель SYSTEM доступна инженеру и мастеру. Ваша роль: {userRole || '—'}
      </div>
    );
  }

  const runSelftest = async () => {
    setError(null);
    const res = await fetch('/api/system/selftest', { method: 'POST', headers: authHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'selftest failed');
    setSelftest(
      (data.checks as { name: string; ok: boolean; detail: string }[])
        .map((c) => `${c.ok ? 'OK' : 'FAIL'} ${c.name}: ${c.detail}`)
        .join('\n'),
    );
  };

  const simulate = async (type: string) => {
    const res = await fetch('/api/system/simulate-failure', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ type }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'simulate failed');
    setSim(data.active);
    await runSelftest();
  };

  const onImport = async (file: File | null) => {
    if (!file) return;
    setError(null);
    setImportMsg('Uploading…');
    setImportLog([]);
    const fd = new FormData();
    fd.append('file', file);
    const token = localStorage.getItem('muravei-token');
    const res = await fetch('/api/models/import', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setImportMsg(null);
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Import failed');
    }
    setImportMsg(data.message || 'Validating…');
    const streamRes = await fetch('/api/models/import/stream', { headers: authHeaders() });
    if (!streamRes.body) return;
    const reader = streamRes.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop() || '';
      for (const chunk of parts) {
        const line = chunk
          .split('\n')
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).trim())
          .join('');
        if (!line) continue;
        try {
          const ev = JSON.parse(line) as Record<string, unknown>;
          if (typeof ev.message === 'string') {
            setImportMsg(ev.message);
            setImportLog((p) => [...p.slice(-30), String(ev.stage || '') + ': ' + ev.message]);
          }
          if (ev.status === 'error') setError(String(ev.error || ev.message));
          if (ev.status === 'done') setInfo('Модель установлена (best.pt)');
        } catch {
          /* ignore */
        }
      }
    }
  };

  const scanUsb = async () => {
    setError(null);
    setUsbResult(null);
    setUsbBusy(true);
    try {
      const res = await fetch('/api/models/usb-scan', { headers: authHeaders() });
      const data = (await res.json()) as {
        drives?: typeof usbDrives;
        errors?: string[];
        detail?: string;
      };
      if (!res.ok) throw new Error(data.detail || 'USB scan failed');
      setUsbDrives(data.drives || []);
      setUsbErrors(data.errors || []);
    } finally {
      setUsbBusy(false);
    }
  };

  const previewUsb = async (file: { path: string; type: 'model' | 'classes' }) => {
    setError(null);
    const res = await fetch('/api/models/usb-import', {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_path: file.path,
        target_type: file.type,
        confirm: false,
      }),
    });
    const data = (await res.json()) as {
      dest_path?: string;
      message?: string;
      detail?: string;
      valid?: boolean;
      error?: string;
    };
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'preview failed');
    if (data.valid === false) throw new Error(data.error || 'Файл невалиден');
    setUsbPending({
      path: file.path,
      type: file.type,
      dest: data.dest_path,
      message: data.message,
    });
  };

  const confirmUsb = async () => {
    if (!usbPending) return;
    setUsbBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/models/usb-import', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_path: usbPending.path,
          target_type: usbPending.type,
          confirm: true,
        }),
      });
      const data = (await res.json()) as {
        success?: boolean;
        message?: string;
        detail?: string;
      };
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'import failed');
      setUsbResult(data.message || (data.success ? 'Импортировано' : 'Ошибка'));
      setUsbPending(null);
    } finally {
      setUsbBusy(false);
    }
  };

  const changePin = async () => {
    const res = await fetch('/api/auth/change-pin', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        role: pinRole,
        pin: newPin,
        current_master_pin: pinRole === 'master' ? masterPin : undefined,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'change-pin failed');
    setInfo(`PIN ${pinRole} обновлён`);
    setNewPin('');
  };

  const peekPin = async (role: string) => {
    const res = await fetch(`/api/auth/peek-pin/${role}`, { headers: authHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'peek failed');
    setPeek({ role, pin: data.pin });
  };

  const factoryReset = async () => {
    if (!confirm('Сбросить все PIN к заводским?')) return;
    const res = await fetch('/api/auth/factory-reset', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ current_master_pin: masterPin }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'reset failed');
    setInfo('Factory reset: PIN восстановлены');
  };

  return (
    <div className="h-full overflow-auto p-4 space-y-4 text-[12px]">
      <div className="flex items-center gap-2">
        <Cpu size={14} className="text-[var(--dv-accent)]" />
        <span className="uppercase tracking-wider text-[var(--dv-text-muted)] font-semibold">
          SYSTEM / Engineer
        </span>
        <button type="button" className="ml-auto px-2 py-1 bg-[#333] rounded-sm" onClick={() => void refreshHw()}>
          <RefreshCw size={12} />
        </button>
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 grid grid-cols-2 gap-2 text-[11px]">
        <div>CPU: {String(hw?.cpu_percent ?? '—')}% × {String(hw?.cpu_count ?? '')}</div>
        <div>
          RAM: {String(hw?.ram_available_mb ?? '—')} / {String(hw?.ram_total_mb ?? '—')} MB free/total
        </div>
        <div className="col-span-2">GPU: {String(hw?.gpu ?? '—')}</div>
        <div>VRAM used: {String(hw?.vram_used_mb ?? '—')} MB</div>
        <div>Temp: {String(hw?.gpu_temp_c ?? '—')} °C</div>
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="font-semibold">Самодиагностика / симуляция сбоев</div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="px-2 py-1 bg-[#333] rounded-sm" onClick={() => void runSelftest().catch((e) => setError(String(e)))}>
            Self-test
          </button>
          {(['gpu_oom', 'model_missing', 'ollama_offline', 'clear'] as const).map((t) => (
            <button
              key={t}
              type="button"
              className="px-2 py-1 bg-[#333] rounded-sm"
              onClick={() => void simulate(t).catch((e) => setError(String(e)))}
            >
              {t}
            </button>
          ))}
        </div>
        {sim && <div className="text-[10px] text-[var(--dv-accent)]">active sim: {sim}</div>}
        {selftest && <pre className="text-[10px] whitespace-pre-wrap bg-black/30 p-2 border border-[var(--dv-border)]">{selftest}</pre>}
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2" data-testid="detect-config">
        <div className="font-semibold flex items-center gap-2">
          <Cpu size={14} /> Конфигурация детекции
        </div>
        {!detectCfg ? (
          <div className="text-[10px] text-[var(--dv-text-muted)]">Загрузка…</div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  data-testid="cfg-use-sahi"
                  checked={detectCfg.use_sahi_default}
                  onChange={(e) =>
                    setDetectCfg({ ...detectCfg, use_sahi_default: e.target.checked })
                  }
                />
                <span>SAHI по умолчанию (нарезка слайсов)</span>
              </label>
              <label className="flex items-center gap-1 cursor-pointer ml-4">
                <input
                  type="checkbox"
                  data-testid="cfg-validator"
                  checked={detectCfg.validator_enabled}
                  onChange={(e) =>
                    setDetectCfg({ ...detectCfg, validator_enabled: e.target.checked })
                  }
                />
                <span>Валидатор ответов</span>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <label className="flex items-center gap-1">
                <span className="text-[var(--dv-text-muted)]">slice_h</span>
                <input
                  type="number"
                  min={128}
                  max={2048}
                  step={64}
                  className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-20"
                  value={detectCfg.slice_height}
                  onChange={(e) =>
                    setDetectCfg({ ...detectCfg, slice_height: Number(e.target.value) || 512 })
                  }
                />
              </label>
              <label className="flex items-center gap-1">
                <span className="text-[var(--dv-text-muted)]">slice_w</span>
                <input
                  type="number"
                  min={128}
                  max={2048}
                  step={64}
                  className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-20"
                  value={detectCfg.slice_width}
                  onChange={(e) =>
                    setDetectCfg({ ...detectCfg, slice_width: Number(e.target.value) || 512 })
                  }
                />
              </label>
              <label className="flex items-center gap-1">
                <span className="text-[var(--dv-text-muted)]">overlap</span>
                <input
                  type="number"
                  min={0}
                  max={0.5}
                  step={0.05}
                  className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-20"
                  value={detectCfg.overlap_ratio}
                  onChange={(e) =>
                    setDetectCfg({ ...detectCfg, overlap_ratio: Number(e.target.value) || 0.2 })
                  }
                />
              </label>
              <label className="flex items-center gap-1">
                <span className="text-[var(--dv-text-muted)]">v_min_area</span>
                <input
                  type="number"
                  min={0}
                  max={0.9}
                  step={0.0001}
                  className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-20"
                  value={detectCfg.validator_min_bbox_area}
                  onChange={(e) =>
                    setDetectCfg({
                      ...detectCfg,
                      validator_min_bbox_area: Number(e.target.value) || 0.0001,
                    })
                  }
                />
              </label>
              <label className="flex items-center gap-1">
                <span className="text-[var(--dv-text-muted)]">v_max_area</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-20"
                  value={detectCfg.validator_max_bbox_area}
                  onChange={(e) =>
                    setDetectCfg({
                      ...detectCfg,
                      validator_max_bbox_area: Number(e.target.value) || 0.9,
                    })
                  }
                />
              </label>
              <label className="flex items-center gap-1">
                <span className="text-[var(--dv-text-muted)]">v_min_conf</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-20"
                  value={detectCfg.validator_min_confidence}
                  onChange={(e) =>
                    setDetectCfg({
                      ...detectCfg,
                      validator_min_confidence: Number(e.target.value) || 0.01,
                    })
                  }
                />
              </label>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                className="px-2 py-1 bg-[#333] rounded-sm"
                onClick={() => void saveDetectCfg(detectCfg).catch((e) => setError(String(e)))}
              >
                Сохранить
              </button>
              <button
                type="button"
                className="px-2 py-1 bg-[#333] rounded-sm"
                onClick={() => void loadDetectCfg().catch((e) => setError(String(e)))}
              >
                Сбросить
              </button>
              {detectCfgSaved && (
                <span className="text-[10px] text-[var(--dv-accent)]">{detectCfgSaved}</span>
              )}
            </div>
          </>
        )}
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2" data-testid="seg-config">
        <div className="font-semibold">Сегментация (архив)</div>
        <p className="text-[10px] text-[var(--dv-text-muted)]">
          Только yolo26n-seg / yolo26s-seg. Не держите seg и detect вместе на 8 ГБ VRAM. Live не сегментируется.
        </p>
        {segStatus && (
          <div className="text-[10px] font-mono text-[var(--dv-text-muted)]">
            ready={segStatus.ready ? '1' : '0'} loaded={segStatus.loaded ? '1' : '0'}
            {segStatus.weight ? ` · ${segStatus.weight}` : ''}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="bg-[#1a1a1a] border border-[var(--dv-border)] text-[11px] px-1 py-0.5"
            value={segWeightPick}
            onChange={(e) => setSegWeightPick(e.target.value)}
            disabled={segBusy}
          >
            {(segStatus?.available?.length ? segStatus.available : ['yolo26n-seg.pt', 'yolo26s-seg.pt']).map(
              (name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ),
            )}
          </select>
          <button
            type="button"
            className="px-2 py-1 bg-[#333] rounded-sm disabled:opacity-40"
            disabled={segBusy || !(segStatus?.available?.length)}
            onClick={() => {
              setSegBusy(true);
              setSegMsg(null);
              void fetch('/api/seg/load', {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({ weight: segWeightPick }),
              })
                .then(async (res) => {
                  const data = await res.json().catch(() => ({}));
                  if (!res.ok) throw new Error((data as { detail?: string }).detail || 'load failed');
                  setSegMsg(`Загружено: ${(data as { weight?: string }).weight || segWeightPick}`);
                  await refreshSegStatus();
                })
                .catch((err) => setError(String(err)))
                .finally(() => setSegBusy(false));
            }}
          >
            {segBusy ? '…' : 'Загрузить'}
          </button>
          <button
            type="button"
            className="px-2 py-1 bg-[#333] rounded-sm disabled:opacity-40"
            disabled={segBusy || !segStatus?.loaded}
            onClick={() => {
              setSegBusy(true);
              setSegMsg(null);
              void fetch('/api/seg/unload', { method: 'POST', headers: authHeaders() })
                .then(async (res) => {
                  if (!res.ok) throw new Error('unload failed');
                  setSegMsg('Выгружено');
                  await refreshSegStatus();
                })
                .catch((err) => setError(String(err)))
                .finally(() => setSegBusy(false));
            }}
          >
            Выгрузить
          </button>
        </div>
        {segMsg && <div className="text-[10px] text-[var(--dv-accent)]">{segMsg}</div>}
        {segStatus && !segStatus.ready && (
          <div className="text-[10px] text-red-400">Нет yolo26n-seg.pt / yolo26s-seg.pt в assets/models/</div>
        )}
      </div>

      <ClassDictionary />

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="font-semibold flex items-center gap-2">
          <Upload size={14} /> Импорт модели (.pt)
        </div>
        <input
          type="file"
          accept=".pt"
          className="text-[11px]"
          onChange={(e) => void onImport(e.target.files?.[0] || null).catch((err) => setError(String(err)))}
        />
        {importMsg && <div className="text-[10px] text-[var(--dv-text-muted)]">{importMsg}</div>}
        {importLog.length > 0 && (
          <pre className="max-h-24 overflow-auto text-[10px] bg-black/40 p-2">{importLog.join('\n')}</pre>
        )}
      </div>

      <div data-testid="usb-import" className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="font-semibold flex items-center gap-2">
          <Usb size={14} /> Импорт с USB
        </div>
        <p className="text-[10px] text-[var(--dv-text-muted)]">
          Съёмный диск: .pt (nc 12 или 238) и словарь классов YAML. Текущий файл сохраняется как .backup.
          Модель подхватывается без перезапуска.
        </p>
        <button
          type="button"
          className="px-2 py-1 bg-[#333] rounded-sm disabled:opacity-40"
          disabled={usbBusy}
          onClick={() => void scanUsb().catch((e) => setError(String(e)))}
        >
          {usbBusy ? 'Сканирование…' : 'Сканировать USB'}
        </button>
        {usbErrors.map((e) => (
          <div key={e} className="text-[10px] text-[var(--dv-text-muted)]">
            {e}
          </div>
        ))}
        {usbDrives.map((drive) => (
          <div key={drive.letter} className="border border-[var(--dv-border)]/60 p-2 space-y-1">
            <div className="text-[11px] font-semibold">
              {drive.letter} {drive.label ? `· ${drive.label}` : ''}
            </div>
            {drive.files.length === 0 && (
              <div className="text-[10px] text-[var(--dv-text-muted)]">Нет .pt / .yaml</div>
            )}
            {drive.files.map((file) => (
              <div
                key={file.path}
                className="flex flex-wrap items-center gap-2 text-[10px] py-0.5 border-t border-[var(--dv-border)]/40"
              >
                <span className="truncate max-w-[14rem]" title={file.path}>
                  {file.name}
                </span>
                <span className="text-[var(--dv-text-muted)]">{file.size_mb} MB</span>
                <span className={file.valid ? 'text-emerald-400' : 'text-red-400'}>
                  {file.valid ? 'валиден' : 'невалиден'}
                </span>
                {file.type === 'model' && file.nc != null && <span>nc={file.nc}</span>}
                {file.type === 'classes' && file.count != null && <span>{file.count} классов</span>}
                {file.error && (
                  <span className="text-[var(--dv-text-muted)] truncate max-w-[12rem]">{file.error}</span>
                )}
                <button
                  type="button"
                  className="px-1.5 py-0.5 bg-[#333] rounded-sm disabled:opacity-40"
                  disabled={!file.valid || usbBusy}
                  onClick={() => void previewUsb(file).catch((e) => setError(String(e)))}
                >
                  Предпросмотр
                </button>
              </div>
            ))}
          </div>
        ))}
        {usbResult && <div className="text-[11px] text-[var(--dv-accent)]">{usbResult}</div>}
        <Modal
          open={Boolean(usbPending)}
          title="Импорт с USB"
          onClose={() => setUsbPending(null)}
          footer={
            <>
              <button type="button" className="px-2 py-1 bg-[#333] rounded-sm" onClick={() => setUsbPending(null)}>
                Отмена
              </button>
              <button
                type="button"
                className="px-2 py-1 bg-[var(--dv-accent)] text-black rounded-sm disabled:opacity-40"
                disabled={usbBusy}
                onClick={() => void confirmUsb().catch((e) => setError(String(e)))}
              >
                Да, импортировать
              </button>
            </>
          }
        >
          {usbPending && (
            <div className="space-y-1 text-[12px]">
              <p>{usbPending.message || `Импортировать ${usbPending.path}?`}</p>
              {usbPending.dest && (
                <p className="text-[10px] text-[var(--dv-text-muted)] font-mono break-all">{usbPending.dest}</p>
              )}
              <p className="text-[10px] text-[var(--dv-text-muted)]">
                Текущий файл будет сохранён как .backup
              </p>
            </div>
          )}
        </Modal>
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="font-semibold flex items-center gap-2">
          <KeyRound size={14} /> PIN
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <select
            className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1"
            value={pinRole}
            onChange={(e) => setPinRole(e.target.value)}
          >
            <option value="operator">operator</option>
            {isMaster && <option value="engineer">engineer</option>}
            {isMaster && <option value="master">master</option>}
          </select>
          <input
            className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-28 font-mono"
            placeholder="новый PIN"
            value={newPin}
            maxLength={7}
            onChange={(e) => setNewPin(e.target.value.replace(/\D/g, '').slice(0, 7))}
          />
          {pinRole === 'master' && (
            <input
              className="bg-[#1a1a1a] border border-[var(--dv-border)] px-2 py-1 w-28 font-mono"
              placeholder="текущий master"
              value={masterPin}
              maxLength={7}
              onChange={(e) => setMasterPin(e.target.value.replace(/\D/g, '').slice(0, 7))}
            />
          )}
          <button
            type="button"
            className="px-2 py-1 bg-[#333] rounded-sm"
            onClick={() => void changePin().catch((e) => setError(String(e)))}
          >
            Сменить
          </button>
          <button
            type="button"
            className="px-2 py-1 bg-[#333] rounded-sm inline-flex items-center gap-1"
            onClick={() => void peekPin(pinRole).catch((e) => setError(String(e)))}
          >
            <Eye size={12} /> Показать
          </button>
        </div>
        {peek && (
          <div className="text-[12px] font-mono text-[var(--dv-accent)]">
            {peek.role}: {peek.pin} (скрывается через 4с)
          </div>
        )}
        {isMaster && (
          <button
            type="button"
            className="px-2 py-1 bg-red-900/60 rounded-sm"
            onClick={() => void factoryReset().catch((e) => setError(String(e)))}
          >
            Factory reset PIN
          </button>
        )}
      </div>

      {info && <div className="text-[11px] text-[var(--dv-accent)]">{info}</div>}
      {error && (
        <div className="text-[11px] text-red-400 flex items-center gap-1">
          <AlertTriangle size={12} /> {error}
        </div>
      )}
    </div>
  );
};

export default AdminPanel;
