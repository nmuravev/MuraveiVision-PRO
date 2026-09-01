export interface YOLODebugStats {
  scrubEvents: number;
  wsMessagesBlocked: number;
  wsMessagesAllowed: number;
  yoloInferCalls: number;
  yoloSkipCalls: number;
  lastScrubTime: number | null;
  suspendActive: boolean;
  cooldownRemaining: number;
}

export type YOLODebugEventType =
  | 'scrub_start'
  | 'scrub_move'
  | 'scrub_end'
  | 'ws_blocked'
  | 'ws_allowed'
  | 'yolo_infer'
  | 'yolo_skip'
  | 'suspend_on'
  | 'suspend_off';

export interface YOLODebugEvent {
  time: number;
  type: YOLODebugEventType;
  message?: string;
}

export interface YOLODebugState extends YOLODebugStats {
  events: YOLODebugEvent[];
  lastActivityAt: number;
}

declare global {
  interface Window {
    muraveiDebug: YOLODebugState;
    getYOLOStats: () => YOLODebugStats;
    resetYOLOStats: () => void;
    printYOLOReport: () => YOLODebugStats;
    exportDebugLog: () => void;
  }
}

const MAX_EVENTS = 2_000;
const listeners = new Set<() => void>();
let cooldownUntil = 0;

const initialStats = (): YOLODebugState => ({
  scrubEvents: 0,
  wsMessagesBlocked: 0,
  wsMessagesAllowed: 0,
  yoloInferCalls: 0,
  yoloSkipCalls: 0,
  lastScrubTime: null,
  suspendActive: false,
  cooldownRemaining: 0,
  events: [],
  lastActivityAt: 0,
});

const state = initialStats();

function notify() {
  for (const listener of listeners) listener();
}

function push(type: YOLODebugEventType, message?: string) {
  const now = performance.now();
  state.lastActivityAt = now;
  state.events.push({ time: now, type, message });
  if (state.events.length > MAX_EVENTS) {
    state.events.splice(0, state.events.length - MAX_EVENTS);
  }
  notify();
}

function snapshot(): YOLODebugStats {
  state.cooldownRemaining = Math.max(0, Math.ceil(cooldownUntil - performance.now()));
  return {
    scrubEvents: state.scrubEvents,
    wsMessagesBlocked: state.wsMessagesBlocked,
    wsMessagesAllowed: state.wsMessagesAllowed,
    yoloInferCalls: state.yoloInferCalls,
    yoloSkipCalls: state.yoloSkipCalls,
    lastScrubTime: state.lastScrubTime,
    suspendActive: state.suspendActive,
    cooldownRemaining: state.cooldownRemaining,
  };
}

export const yoloDebug = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  getState() {
    snapshot();
    return state;
  },

  noteScrub(kind: 'start' | 'move' | 'end') {
    state.scrubEvents += 1;
    state.lastScrubTime = performance.now();
    push(`scrub_${kind}`);
  },

  setSuspend(active: boolean, cooldownMs = 0) {
    state.suspendActive = active;
    cooldownUntil = Math.max(cooldownUntil, performance.now() + cooldownMs);
    push(active ? 'suspend_on' : 'suspend_off');
  },

  noteWsBlocked(reason: string) {
    state.wsMessagesBlocked += 1;
    push('ws_blocked', reason);
  },

  noteWsAllowed() {
    state.wsMessagesAllowed += 1;
    push('ws_allowed');
  },

  noteInfer() {
    // This counter intentionally measures illegal inference requests made inside
    // the protected scrub/suspend/cooldown window. Allowed post-cooldown sends
    // remain observable through wsMessagesAllowed and the event log.
    if (state.suspendActive || performance.now() < cooldownUntil) {
      state.yoloInferCalls += 1;
    }
    push('yolo_infer');
  },

  noteSkip(reason: string) {
    state.yoloSkipCalls += 1;
    push('yolo_skip', reason);
  },
};

function reset() {
  Object.assign(state, initialStats());
  cooldownUntil = 0;
  notify();
}

function printReport() {
  const stats = snapshot();
  const pass =
    stats.scrubEvents >= 3 &&
    stats.yoloInferCalls === 0 &&
    stats.yoloSkipCalls > 0 &&
    !stats.suspendActive &&
    stats.cooldownRemaining === 0;
  console.group('=== YOLO SCRUB GATE TEST ===');
  console.log(`Scrub events: ${stats.scrubEvents}`);
  console.log(`WS blocked before parse: ${stats.wsMessagesBlocked}`);
  console.log(`WS allowed: ${stats.wsMessagesAllowed}`);
  console.log(`YOLO infer during protected window: ${stats.yoloInferCalls}`);
  console.log(`YOLO skip: ${stats.yoloSkipCalls}`);
  console.log(
    `Suspend: ${stats.suspendActive ? 'ON' : 'OFF'} (${stats.cooldownRemaining}ms)`,
  );
  console.log(`${pass ? 'PASS' : 'FAIL'}: ${pass ? 'All criteria met' : 'See counters above'}`);
  console.groupEnd();
  return stats;
}

function exportLog() {
  const stats = snapshot();
  const payload = {
    testRun: new Date().toISOString(),
    events: state.events.map((event) => ({ ...event })),
    summary: {
      ...stats,
      pass:
        stats.scrubEvents >= 3 &&
        stats.yoloInferCalls === 0 &&
        stats.yoloSkipCalls > 0 &&
        !stats.suspendActive &&
        stats.cooldownRemaining === 0,
    },
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `yolo-scrub-debug-${Date.now()}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

if (typeof window !== 'undefined') {
  const consoleWithDebugHook = console as Console & { __muraveiYoloDebugHook?: boolean };
  if (!consoleWithDebugHook.__muraveiYoloDebugHook) {
    const originalLog = console.log.bind(console);
    const originalDebug = console.debug.bind(console);
    const inspect = (args: unknown[]) => {
      const message = args.map(String).join(' ');
      if (message.includes('[YOLO] skip:')) {
        yoloDebug.noteSkip(message.split('[YOLO] skip:')[1]?.trim() || 'console');
      } else if (message.includes('[YOLO] infer')) {
        yoloDebug.noteInfer();
      }
    };
    console.log = (...args: unknown[]) => {
      inspect(args);
      originalLog(...args);
    };
    console.debug = (...args: unknown[]) => {
      inspect(args);
      originalDebug(...args);
    };
    consoleWithDebugHook.__muraveiYoloDebugHook = true;
  }
  window.muraveiDebug = state;
  window.getYOLOStats = snapshot;
  window.resetYOLOStats = reset;
  window.printYOLOReport = printReport;
  window.exportDebugLog = exportLog;
}
