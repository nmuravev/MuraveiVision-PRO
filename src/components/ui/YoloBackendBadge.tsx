import React, { useCallback, useEffect, useState } from 'react';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';

type DetectStatus = {
  yolo_badge?: string;
  yolo_label?: string;
  device_backend?: string;
  degraded?: boolean;
};

/** Compact badge: YOLO: CUDA | DirectML | CPU */
export const YoloBackendBadge: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const [label, setLabel] = useState<string>('');

  const fetchStatus = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/detect/status', { headers: authHeaders() });
      if (!res.ok) return;
      const data = (await res.json()) as DetectStatus;
      const text =
        data.yolo_badge ||
        (data.yolo_label ? `YOLO: ${data.yolo_label}` : '') ||
        '';
      setLabel(text);
    } catch {
      /* ignore */
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setLabel('');
      return;
    }
    void fetchStatus();
    const t = setInterval(() => void fetchStatus(), 8000);
    return () => clearInterval(t);
  }, [isAuthenticated, fetchStatus]);

  if (!isAuthenticated || !label) return null;

  return (
    <span
      className="text-[10px] font-mono tabular-nums shrink-0 text-dv-muted max-w-[120px] truncate"
      title="YOLO inference backend"
      data-testid="yolo-backend-badge"
    >
      {label}
    </span>
  );
};

export default YoloBackendBadge;
