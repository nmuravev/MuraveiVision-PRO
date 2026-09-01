export async function downloadAuthorized(
  url: string,
  opts?: { method?: string; body?: unknown; filename?: string },
): Promise<Blob> {
  const token = localStorage.getItem('muravei-token');
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts?.body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(url, {
    method: opts?.method || 'GET',
    headers,
    body: opts?.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = typeof data?.detail === 'string' ? data.detail : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  const blob = await res.blob();
  const name =
    opts?.filename ||
    res.headers.get('content-disposition')?.match(/filename="?([^"]+)"?/)?.[1] ||
    'download.bin';
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
  return blob;
}
