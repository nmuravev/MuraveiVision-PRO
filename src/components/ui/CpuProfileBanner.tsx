import React, { useCallback, useEffect, useState } from 'react';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';
import { addEvent } from '../../debug/sessionTrace';

type AccelOffer = {
  show?: boolean;
  kind?: string;
  message_ru?: string;
  action?: string;
};

type HardwarePayload = {
  accelerator_kind?: string;
  cpu_profile?: boolean;
  banner?: string;
  directml_available?: boolean;
  system_badge_ru?: string;
  portable_mismatch?: { level?: string; message_ru?: string } | null;
  accel_offer?: AccelOffer | null;
};

/**
 * Non-blocking banner: portable build/tier badge + CPU profile + C2 accel offer.
 */
export const CpuProfileBanner: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const [banner, setBanner] = useState<string>('');
  const [badge, setBadge] = useState<string>('');
  const [offer, setOffer] = useState<AccelOffer | null>(null);
  const [busy, setBusy] = useState(false);
  const [restartHint, setRestartHint] = useState('');
  const [logged, setLogged] = useState(false);

  const fetchHw = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/system/hardware', { headers: authHeaders() });
      if (!res.ok) return;
      const data = (await res.json()) as HardwarePayload;
      if (data.system_badge_ru) {
        setBadge(data.system_badge_ru);
      }
      const mismatch = data.portable_mismatch?.message_ru;
      if (data.accel_offer?.show && data.accel_offer.message_ru) {
        setOffer(data.accel_offer);
      } else {
        setOffer(null);
      }
      if (data.cpu_profile || data.accelerator_kind === 'cpu') {
        const text =
          mismatch ||
          data.banner ||
          'Нет NVIDIA GPU — режим CPU + DirectML (если доступен)';
        setBanner(text);
        if (!logged) {
          addEvent('note', `accelerator profile: cpu`, {
            accelerator_kind: data.accelerator_kind,
            directml_available: data.directml_available,
            system_badge_ru: data.system_badge_ru,
          });
          setLogged(true);
        }
      } else {
        setBanner(mismatch || '');
        if (!logged && data.accelerator_kind === 'cuda') {
          addEvent('note', `accelerator profile: cuda`, {
            accelerator_kind: 'cuda',
            system_badge_ru: data.system_badge_ru,
          });
          setLogged(true);
        }
      }
    } catch {
      /* ignore */
    }
  }, [isAuthenticated, logged]);

  useEffect(() => {
    if (!isAuthenticated) {
      setBanner('');
      setBadge('');
      setOffer(null);
      setRestartHint('');
      setLogged(false);
      return;
    }
    void fetchHw();
  }, [isAuthenticated, fetchHw]);

  const onAcceptUpgrade = async () => {
    setBusy(true);
    try {
      const res = await fetch('/api/system/accel-upgrade', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ accept: true }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        restart_required?: boolean;
        message_ru?: string;
      };
      if (data.restart_required) {
        setRestartHint(
          data.message_ru ||
            'Ускорение установлено. Перезапустите приложение — значок обновится.',
        );
        setOffer(null);
      } else if (data.message_ru) {
        setRestartHint(data.message_ru);
      }
      await fetchHw();
    } finally {
      setBusy(false);
    }
  };

  const onDismissOffer = async () => {
    try {
      await fetch('/api/system/accel-upgrade', {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ accept: false, dismiss: true }),
      });
    } catch {
      /* ignore */
    }
    setOffer(null);
  };

  if (!banner && !badge && !offer && !restartHint) return null;

  return (
    <div
      className="px-3 py-1.5 text-[11px] text-amber-200/95 bg-amber-950/40 border-b border-amber-800/40 text-center"
      data-testid="cpu-profile-banner"
      role="status"
    >
      {badge ? <span data-testid="system-build-badge">{badge}</span> : null}
      {badge && (banner || offer) ? <span className="mx-2 opacity-50">·</span> : null}
      {banner ? <span>{banner}</span> : null}
      {offer?.message_ru ? (
        <span className="ml-2 inline-flex items-center gap-2" data-testid="accel-upgrade-offer">
          <span>{offer.message_ru}</span>
          <button
            type="button"
            className="underline hover:text-white disabled:opacity-50"
            disabled={busy}
            data-testid="accel-upgrade-yes"
            onClick={() => void onAcceptUpgrade()}
          >
            {busy ? '…' : 'Да'}
          </button>
          <button
            type="button"
            className="opacity-70 underline hover:text-white"
            disabled={busy}
            data-testid="accel-upgrade-no"
            onClick={() => void onDismissOffer()}
          >
            Нет
          </button>
        </span>
      ) : null}
      {restartHint ? (
        <span className="ml-2 text-sky-200" data-testid="accel-restart-hint">
          {restartHint}
        </span>
      ) : null}
    </div>
  );
};

export default CpuProfileBanner;
