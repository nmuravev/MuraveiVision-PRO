/** Parse and split chat bodies with detection:<id> tokens. */

const DETECTION_REF_RE = /detection:([a-fA-F0-9]{8,64})\b/g;

export type ChatBodyPart =
  | { kind: 'text'; text: string }
  | { kind: 'detection'; id: string; raw: string };

export function formatDetectionRef(detId: string): string {
  return `detection:${(detId || '').trim().toLowerCase()}`;
}

export function extractDetectionIds(body: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const re = new RegExp(DETECTION_REF_RE.source, 'g');
  let m: RegExpExecArray | null;
  while ((m = re.exec(body || '')) !== null) {
    const id = m[1].toLowerCase();
    if (!seen.has(id)) {
      seen.add(id);
      out.push(id);
    }
  }
  return out;
}

export function splitChatBody(body: string): ChatBodyPart[] {
  const parts: ChatBodyPart[] = [];
  const re = new RegExp(DETECTION_REF_RE.source, 'g');
  let last = 0;
  let m: RegExpExecArray | null;
  const text = body || '';
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      parts.push({ kind: 'text', text: text.slice(last, m.index) });
    }
    parts.push({ kind: 'detection', id: m[1].toLowerCase(), raw: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    parts.push({ kind: 'text', text: text.slice(last) });
  }
  return parts.length ? parts : [{ kind: 'text', text }];
}
