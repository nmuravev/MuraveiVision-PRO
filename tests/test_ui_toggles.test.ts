import { expect, test } from '@playwright/test';

/**
 * Phase 1.2 / Phase 2.3 — Detection config UI toggles (engineer AdminPanel).
 *
 * Verifies: toggle SAHI in the UI → PUT /api/system/detect-config (direct API,
 * same payload the Сохранить button would send) → survives reload.
 *
 * Browser fetch to Vite-proxied /api can stall under heavy hardware polling
 * (2–4s / call); Playwright request goes straight to :8000.
 */
test('Detection config toggles persist via API and survive reload', async ({ page, request }) => {
  test.setTimeout(180_000);
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };
  const headers = { Authorization: `Bearer ${auth.token}` };

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

  const cfgBlock = page.getByTestId('detect-config');
  await expect(cfgBlock).toBeVisible({ timeout: 45_000 });

  const sahiCheckbox = page.getByTestId('cfg-use-sahi');
  await expect(sahiCheckbox).toBeVisible({ timeout: 45_000 });

  const before = (await (
    await request.get('http://127.0.0.1:8000/api/system/detect-config', { headers })
  ).json()) as Record<string, unknown> & { use_sahi_default: boolean };

  const initialValue = before.use_sahi_default;
  await expect(sahiCheckbox).toBeChecked({ checked: initialValue });

  const toggledValue = !initialValue;
  await sahiCheckbox.setChecked(toggledValue, { force: true });
  await expect(sahiCheckbox).toBeChecked({ checked: toggledValue });

  const put = await request.put('http://127.0.0.1:8000/api/system/detect-config', {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: { ...before, use_sahi_default: toggledValue },
  });
  expect(put.ok()).toBeTruthy();

  const mid = (await (
    await request.get('http://127.0.0.1:8000/api/system/detect-config', { headers })
  ).json()) as { use_sahi_default: boolean };
  expect(mid.use_sahi_default).toBe(toggledValue);

  await page.reload();
  await expect(page.getByRole('button', { name: 'Инженер', exact: true })).toBeVisible({
    timeout: 45_000,
  });
  await page.getByRole('button', { name: 'Система', exact: true }).click();
  await expect(page.getByTestId('detect-config')).toBeVisible({ timeout: 45_000 });
  await expect(page.getByTestId('cfg-use-sahi')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId('cfg-use-sahi')).toBeChecked({ checked: toggledValue });

  const restore = await request.put('http://127.0.0.1:8000/api/system/detect-config', {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: { ...before, use_sahi_default: initialValue },
  });
  expect(restore.ok()).toBeTruthy();
});
