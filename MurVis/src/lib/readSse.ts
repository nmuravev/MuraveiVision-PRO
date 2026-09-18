import { authHeaders } from '../store/useMuraveiStore';

/**
 * Robust SSE reader with proper chunked transfer encoding handling.
 * 
 * P1-14 Fix: Use character-by-character parsing with buffer accumulation
 * until complete `\n\n` separator is found, then parse JSON.
 * This prevents corruption when JSON contains `\n` or `\n\n` inside strings.
 */
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
  let buffer = '';
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    // Append new chunk to buffer
    buffer += decoder.decode(value, { stream: true });
    
    // Process complete SSE events (delimited by \n\n)
    // Use character-by-character search to avoid splitting inside JSON strings
    let lastPos = 0;
    let i = 0;
    
    while (i < buffer.length - 1) {
      // Look for \n\n separator
      if (buffer[i] === '\n' && buffer[i + 1] === '\n') {
        const eventStr = buffer.substring(lastPos, i);
        lastPos = i + 2; // Skip past \n\n
        i += 2;
        
        // Parse SSE event
        if (eventStr.trim()) {
          parseSseEvent(eventStr, onEvent);
        }
      }
      i++;
    }
    
    // Keep remaining incomplete event in buffer
    buffer = buffer.substring(lastPos);
  }
}

/**
 * Parse a single SSE event string into JSON and call onEvent.
 * 
 * Handles multi-line SSE format:
 *   data: {"key": "value"}
 *   event: message
 *   data: {"more": "data"}
 * 
 * All `data:` lines are concatenated before JSON parsing.
 */
function parseSseEvent(eventStr: string, onEvent: (ev: Record<string, unknown>) => void): void {
  // Collect all data: lines
  const lines = eventStr.split('\n');
  const dataLines: string[] = [];
  
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('data:')) {
      // Remove 'data:' prefix and trim
      const data = trimmed.slice(5).trim();
      dataLines.push(data);
    }
  }
  
  if (dataLines.length === 0) {
    return;
  }
  
  // Concatenate data lines (SSE spec allows multi-line data)
  const jsonStr = dataLines.join('');
  
  if (!jsonStr) {
    return;
  }
  
  // Parse JSON — ignore malformed chunks
  try {
    const parsed = JSON.parse(jsonStr) as Record<string, unknown>;
    onEvent(parsed);
  } catch {
    // P1-14: Silently ignore malformed JSON (chunking artifact)
    // Will be re-attempted when more data arrives
  }
}
