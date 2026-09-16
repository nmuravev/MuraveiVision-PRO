import { expect, test } from '@playwright/test';

/**
 * P5 — DA3 Dense presets + engineer Mesh toggle (API + AdminPanel static copy).
 * Dense `<select data-testid="dense-backend-select">` mounts only after sparse COLMAP
 * (sceneKind=points); option list is asserted via presets API.
 */
async function engineerLogin(request: import('@playwright/test').APIRequestContext) {
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  return (await authResponse.json()) as { token: string };
}

test('presets API: 4 DA3 variants, no default AV MVS, mesh + giant fields', async ({ request }) => {
  const auth = await engineerLogin(request);
  const res = await request.get('http://127.0.0.1:8000/api/recon/train/presets', {
    headers: { Authorization: `Bearer ${auth.token}` },
  });
  expect(res.ok()).toBeTruthy();
  const body = (await res.json()) as {
    presets: Array<{ id: string; disabled?: boolean; disabled_reason?: string }>;
  };
  const ids = body.presets.map((p) => p.id);
  for (const need of [
    'da3_dense_base',
    'da3_dense_large',
    'da3_dense_metric',
    'da3_dense_giant',
    'mesh',
    'sparse',
    'splat',
  ]) {
    expect(ids).toContain(need);
  }
  expect(ids).not.toContain('dense');
  const giant = body.presets.find((p) => p.id === 'da3_dense_giant');
  expect(giant).toBeTruthy();
  if (giant?.disabled) {
    expect(String(giant.disabled_reason || '')).toMatch(/VRAM|16/i);
  }
});

test('recon-config API round-trip alicevision_enabled', async ({ request }) => {
  const auth = await engineerLogin(request);
  const headers = { Authorization: `Bearer ${auth.token}` };
  const before = (await (
    await request.get('http://127.0.0.1:8000/api/system/recon-config', { headers })
  ).json()) as { alicevision_enabled: boolean };
  expect(typeof before.alicevision_enabled).toBe('boolean');

  const flipped = !before.alicevision_enabled;
  const put = await request.put('http://127.0.0.1:8000/api/system/recon-config', {
    headers,
    data: { alicevision_enabled: flipped },
  });
  expect(put.ok()).toBeTruthy();
  const mid = (await put.json()) as { alicevision_enabled: boolean };
  expect(mid.alicevision_enabled).toBe(flipped);

  // restore
  const restore = await request.put('http://127.0.0.1:8000/api/system/recon-config', {
    headers,
    data: { alicevision_enabled: before.alicevision_enabled },
  });
  expect(restore.ok()).toBeTruthy();
});

test('Система AdminPanel shows Конфигурация 3D Dense=DA3 copy', async ({ page, request }) => {
  const auth = await engineerLogin(request);
  await page.addInitScript((token) => {
    localStorage.setItem('muravei-token', token);
    localStorage.setItem('muravei-splash-done-v1', '1');
    for (const k of Object.keys(localStorage)) {
      if (k.toLowerCase().includes('layout') || k.toLowerCase().includes('mosaic')) {
        localStorage.removeItem(k);
      }
    }
  }, auth.token);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Инженер', exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole('button', { name: 'Система', exact: true }).click();
  await expect(page.getByTestId('detect-config')).toBeVisible({ timeout: 45_000 });
  const recon = page.getByTestId('recon-config');
  await recon.scrollIntoViewIfNeeded();
  await expect(recon).toBeVisible();
  await expect(recon).toContainText(/Dense = DA3/i);
  await expect(recon).toContainText(/Конфигурация 3D/i);
});
