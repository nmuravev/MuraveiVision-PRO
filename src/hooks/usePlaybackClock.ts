import { useEffect } from 'react';
import { useTimelineStore } from '../store/timeline-store';

/** Advance playhead only when there is no loaded video (video is the clock otherwise). */
export function usePlaybackClock(): void {
  const playbackState = useTimelineStore((s) => s.playbackState);
  const playbackRate = useTimelineStore((s) => s.playbackRate);
  const setPlayheadPosition = useTimelineStore((s) => s.setPlayheadPosition);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const mediaDuration = useTimelineStore((s) => s.mediaDuration);

  useEffect(() => {
    if (mediaDuration > 0) return;
    if (playbackState !== 'playing') return;
    let raf = 0;
    let last = performance.now();
    let time = playheadPosition;

    const tick = (now: number) => {
      const dt = ((now - last) / 1000) * playbackRate;
      last = now;
      time += dt;
      setPlayheadPosition(time);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playbackState, playbackRate, setPlayheadPosition, mediaDuration]);
}
