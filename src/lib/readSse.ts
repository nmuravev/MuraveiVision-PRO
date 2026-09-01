import { authHeaders } from '../store/useMuraveiStore';

export async function readSse(
  url: string,
  onEvent: (ev: Record<string, unknown>) => void,
  abort?: AbortController,
): Promise<void> {
  const streamRes = await fetch(url, {
    headers: authHeaders(),
    signal: abort?.signal,
  });
  if (!streamRes.ok || !streamRes.body) {
    throw new Error('SSE stream unavailable');
  }
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
        onEvent(JSON.parse(line) as Record<string, unknown>);
      } catch {
        /* ignore malformed chunk */
      }
    }
  }
}
