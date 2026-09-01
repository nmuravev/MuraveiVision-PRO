import { useEffect } from 'react';
import { useTimelineStore } from '../store/timeline-store';
import { useViewerStore } from '../store/useViewerStore';
import { useMuraveiStore } from '../store/useMuraveiStore';

/**
 * Global operator hotkeys. Attached once at the app root (see App.tsx).
 *
 * Conflict policy (per user decision): preventDefault only when acting on a
 * hotkey; never fire while the user is typing in a form field. Space / arrow
 * frame-step additionally require a focused viewer and that the active
 * element is not a button/link (so we don't hijack button activation).
 *
 * Consolidates the previously inline I/O (TimelinePanel) and Delete
 * (Inspector) listeners — those were removed to avoid double-handling.
 */
function isFormField(el: EventTarget | null): boolean {
  const t = el as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || t.isContentEditable;
}

function isActivatable(el: EventTarget | null): boolean {
  const t = el as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  return tag === 'BUTTON' || tag === 'A' || t.getAttribute('role') === 'button';
}

/** Dispatch a freeze-frame request to the focused Viewer (which owns the
 *  video element and local freezeFrame()). The Viewer listens for this. */
function requestFreezeFrame(viewerId: string): void {
  window.dispatchEvent(new CustomEvent('muravei:freeze-frame', { detail: { viewerId } }));
}

export function useHotkeys(): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isFormField(e.target)) return;

      const timeline = useTimelineStore.getState();
      const viewers = useViewerStore.getState();
      const muravei = useMuraveiStore.getState();
      const focused = viewers.focusedViewerId;

      // Ctrl+Z — undo last detection edit (patch-only in v1).
      if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault();
        void muravei.undoLastEdit();
        return;
      }

      // Ctrl+S — freeze/commit focused viewer frame (prevent browser save).
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        if (focused) requestFreezeFrame(focused);
        return;
      }

      // Space — play/pause. Only when a viewer is focused and not on a button/link.
      if (e.key === ' ' || e.code === 'Space') {
        if (!focused || isActivatable(e.target)) return;
        e.preventDefault();
        timeline.togglePlayback();
        return;
      }

      // 1-4 — switch focused viewer.
      if (['1', '2', '3', '4'].includes(e.key)) {
        const n = Number(e.key);
        if (viewers.viewers[`viewer-${n}`]) {
          e.preventDefault();
          viewers.setFocusedViewer(`viewer-${n}`);
        }
        return;
      }

      // I / O — mark in / out.
      if (e.key === 'i' || e.key === 'I') {
        e.preventDefault();
        timeline.markIn();
        return;
      }
      if (e.key === 'o' || e.key === 'O') {
        e.preventDefault();
        timeline.markOut();
        return;
      }

      // F — freeze/commit focused frame.
      if (e.key === 'f' || e.key === 'F') {
        if (!focused) return;
        e.preventDefault();
        requestFreezeFrame(focused);
        return;
      }

      // Arrow Left/Right — frame step (Shift = x10). Requires focused viewer.
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        if (!focused || isActivatable(e.target)) return;
        e.preventDefault();
        const dir = e.key === 'ArrowRight' ? 1 : -1;
        const mag = e.shiftKey ? 10 : 1;
        timeline.stepFrame(dir * mag);
        return;
      }

      // Delete / Backspace — soft-delete active detection. Delegate to Inspector's
      // removeActive() (handles both persisted and live/non-persisted) via a
      // CustomEvent, so we don't duplicate that logic here.
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const activeId = muravei.activeDetectionId;
        if (!activeId && !muravei.activeDetection) return;
        e.preventDefault();
        window.dispatchEvent(new CustomEvent('muravei:delete-active'));
        return;
      }
    };

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
}
