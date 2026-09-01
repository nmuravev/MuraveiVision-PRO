/** Централизованный логгер для DebugPanel и системных событий. */

export type LogLevel = 'error' | 'warn' | 'info' | 'debug' | 'verbose';

export interface LogEntry {
  id: string;
  ts: number;
  level: LogLevel;
  source: string;
  message: string;
}

const LEVEL_ORDER: Record<LogLevel, number> = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3,
  verbose: 4,
};

const MAX = 1000;
const entries: LogEntry[] = [];
const listeners = new Set<(e: LogEntry) => void>();
let seq = 0;

function push(level: LogLevel, source: string, message: string) {
  const entry: LogEntry = {
    id: `log-${Date.now()}-${++seq}`,
    ts: Date.now(),
    level,
    source,
    message,
  };
  entries.push(entry);
  if (entries.length > MAX) entries.splice(0, entries.length - MAX);
  for (const fn of listeners) {
    try {
      fn(entry);
    } catch {
      /* ignore subscriber errors */
    }
  }
  const prefix = `[${level.toUpperCase()}][${source}]`;
  if (level === 'error') console.error(prefix, message);
  else if (level === 'warn') console.warn(prefix, message);
  else if (level === 'debug' || level === 'verbose') console.debug(prefix, message);
  else console.info(prefix, message);
}

export const logger = {
  error: (source: string, message: string) => push('error', source, message),
  warn: (source: string, message: string) => push('warn', source, message),
  info: (source: string, message: string) => push('info', source, message),
  debug: (source: string, message: string) => push('debug', source, message),
  verbose: (source: string, message: string) => push('verbose', source, message),

  getEntries: (maxLevel: LogLevel = 'verbose'): LogEntry[] => {
    const cap = LEVEL_ORDER[maxLevel];
    return entries.filter((e) => LEVEL_ORDER[e.level] <= cap);
  },

  clear: () => {
    entries.length = 0;
  },

  subscribe: (fn: (e: LogEntry) => void): (() => void) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },

  exportText: (maxLevel: LogLevel = 'verbose'): string => {
    return logger
      .getEntries(maxLevel)
      .map(
        (e) =>
          `${new Date(e.ts).toISOString()} [${e.level}] [${e.source}] ${e.message}`,
      )
      .join('\n');
  },
};

export default logger;
