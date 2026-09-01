import React, { memo, useEffect, useState } from 'react';
import { yoloDebug } from '../../debug/yoloDebug';

const INACTIVITY_MS = 5_000;

export const YoloDebugOverlay = memo(function YoloDebugOverlay() {
  const [enabled, setEnabled] = useState(true);
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const update = () => setTick((value) => value + 1);
    const unsubscribe = yoloDebug.subscribe(update);
    const timer = window.setInterval(update, 100);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.ctrlKey && event.shiftKey && event.code === 'KeyD') {
        event.preventDefault();
        setEnabled((value) => !value);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      unsubscribe();
      window.clearInterval(timer);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  if (!import.meta.env.DEV || !enabled) return null;

  const state = yoloDebug.getState();
  if (
    state.lastActivityAt <= 0 ||
    performance.now() - state.lastActivityAt > INACTIVITY_MS
  ) {
    return null;
  }

  return (
    <aside
      aria-label="YOLO debug statistics"
      className="pointer-events-none absolute right-2 top-12 z-50 min-w-[190px] border border-sky-400/60 bg-black/85 px-3 py-2 font-mono text-[10px] leading-4 text-sky-100"
    >
      <div className="mb-1 font-bold tracking-wider text-sky-300">YOLO DEBUG</div>
      <div>Scrub: {state.scrubEvents}</div>
      <div>WS blocked: {state.wsMessagesBlocked}</div>
      <div>
        Infer: {state.yoloInferCalls} | Skip: {state.yoloSkipCalls}
      </div>
      <div>
        Suspend: {state.suspendActive ? 'ON' : 'OFF'} ({state.cooldownRemaining}ms)
      </div>
    </aside>
  );
});
