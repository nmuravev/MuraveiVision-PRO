import { useEffect } from 'react';
import { useTimelineStore } from '../store/timeline-store';
import { useViewerStore } from '../store/useViewerStore';

/** Global keyboard shortcuts (F freeze, I/O marks, Delete active detection). */
export function useHotkeys(): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return;
      }

      const { focusedViewerId } = useViewerStore.getState();
      const { playheadPosition, markIn, markOut } = useTimelineStore.getState();

      if (e.key === 'f' || (e.key === 's' && e.ctrlKey)) {
        e.preventDefault();
        window.dispatchEvent(
          new CustomEvent('muravei:freeze-frame', { detail: { viewerId: focusedViewerId } }),
        );
        return;
      }
      if (e.key === 'i' || e.key === 'I') {
        markIn(playheadPosition);
        return;
      }
      if (e.key === 'o' || e.key === 'O') {
        markOut(playheadPosition);
        return;
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        window.dispatchEvent(new CustomEvent('muravei:delete-active'));
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
