import React from 'react';
import { batchScanProgressPct, useBatchScanStore } from '../store/useBatchScanStore';
import { useReconStore } from '../store/useReconStore';
import { mediaPathsMatch } from '../lib/mediaPaths';
import { reconTerminalLabel } from '../hooks/useReconBuild';

type Props = {
  sourcePath: string | null | undefined;
  className?: string;
};

function fileLabel(path: string | null | undefined): string {
  if (!path) return '';
  return path.replace(/^.*[/\\]/, '');
}

export const OpsStatusBar: React.FC<Props> = ({ sourcePath, className = '' }) => {
  const scanStatus = useBatchScanStore((s) => s.status);
  const scanMessage = useBatchScanStore((s) => s.message);
  const scanProcessed = useBatchScanStore((s) => s.processed);
  const scanSampleTotal = useBatchScanStore((s) => s.sampleTotal);
  const scanFound = useBatchScanStore((s) => s.found);
  const scanVideoPath = useBatchScanStore((s) => s.videoPath);
  const scanPhase = useBatchScanStore((s) => s.phase);

  const reconRunning = useReconStore((s) => s.reconRunning);
  const reconMessage = useReconStore((s) => s.reconMessage);
  const reconProgress = useReconStore((s) => s.reconProgress);
  const reconPhase = useReconStore((s) => s.reconPhase);
  const lastReconMessage = useReconStore((s) => s.lastReconMessage);
  const manifest = useReconStore((s) => s.manifest);

  const scanForThis =
    sourcePath && scanVideoPath && mediaPathsMatch(sourcePath, scanVideoPath);
  const scanOnOther =
    scanStatus === 'running' && scanVideoPath && sourcePath && !scanForThis;

  const scanPct = batchScanProgressPct({
    status: scanStatus,
    processed: scanProcessed,
    sampleTotal: scanSampleTotal,
  });

  let scanLine: React.ReactNode = null;
  if (scanOnOther) {
    scanLine = (
      <span className="text-[var(--dv-text-muted)]">
        {' '}
        · Анализ: другой ролик ({fileLabel(scanVideoPath)}) {scanPct}%
      </span>
    );
  } else if (scanForThis && scanStatus === 'running') {
    scanLine = (
      <span className="text-[#38bdf8]">
        {' '}
        · Анализ: {scanPhase || 'scanning'} {scanPct}% · {scanProcessed}
        {scanSampleTotal > 0 ? `/${scanSampleTotal}` : ''} кадров · {scanFound} целей
        {scanMessage ? ` · ${scanMessage}` : ''}
      </span>
    );
  } else if (scanForThis && scanStatus === 'done') {
    scanLine = (
      <span className="text-emerald-400"> · Анализ: готово · {scanFound} целей</span>
    );
  } else if (scanForThis && scanStatus === 'error') {
    scanLine = (
      <span className="text-red-400"> · Анализ: ошибка — {scanMessage}</span>
    );
  }

  const reconPct = Math.round(reconProgress * 100);
  let reconLine: React.ReactNode = null;
  if (reconRunning) {
    reconLine = (
      <span className="text-[var(--dv-accent)]">
        {' '}
        · 3D: {reconPhase || 'running'} {reconPct}% · {reconMessage}
      </span>
    );
  } else if (
    sourcePath &&
    manifest &&
    mediaPathsMatch(manifest.video_path || '', sourcePath) &&
    (manifest.status === 'colmap_done' || manifest.status === 'done' || manifest.status === 'error')
  ) {
    const msg = reconTerminalLabel(manifest.status, manifest.error);
    const cls =
      manifest.status === 'error' ? 'text-red-400' : 'text-[var(--dv-text-muted)] opacity-80';
    reconLine = <span className={cls}> · 3D: {msg}</span>;
  } else if (
    lastReconMessage &&
    lastReconMessage !== 'Реконструкция уже выполняется' &&
    !/feature extract/i.test(lastReconMessage)
  ) {
    reconLine = (
      <span className="text-[var(--dv-text-muted)] opacity-70"> · 3D: {lastReconMessage}</span>
    );
  }

  if (!scanLine && !reconLine) return null;

  return <span className={className}>{scanLine}{reconLine}</span>;
};
