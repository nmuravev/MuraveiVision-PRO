import { expect, test } from '@playwright/test';

/**
 * Phase 1.2 / Phase 2.3 — Detection config UI toggles (engineer AdminPanel).
 *
 * Verifies the round-trip: toggle "SAHI по умолчанию" in the UI → save →
 * persists to SQLite via PUT /api/system/detect-config → reflected by
 * GET /api/system/detect-config → survives a page reload (F5).
 */
test('Detection config toggles persist via API and survive reload', async ({ page, request }) => {
  // Engineer login (PIN 0000000 per backend/scripts/smoke_phase4.py defaults).
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  await page.addInitScript((token) => {
    localStorage.setItem('muravei-token', token);
    localStorage.setItem('muravei-splash-done-v1', '1');
  }, auth.token);
  await page.goto('/');

  // Open the "Система" workspace tab (renders AdminPanel).
  await page.getByRole('button', { name: 'Система', exact: true }).click();

  // The detection config block must mount.
  const cfgBlock = page.getByTestId('detect-config');
  await expect(cfgBlock).toBeVisible({ timeout: 15_000 });

  const sahiCheckbox = page.getByTestId('cfg-use-sahi');
  await expect(sahiCheckbox).toBeVisible();

  // Capture the initial value from the API (source of truth) so the test is
  // independent of whatever a previous run left in SQLite.
  const before = (await (
    await request.get('http://127.0.0.1:8000/api/system/detect-config', {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
  ).json()) as { use_sahi_default: boolean };

  const initialValue = before.use_sahi_default;
  // Sanity: the checkbox reflects the API value on mount.
  await expect(sahiCheckbox).toBeChecked({ checked: initialValue });

  // Toggle to the opposite and save.
  const toggledValue = !initialValue;
  if (toggledValue) {
    await sahiCheckbox.check();
  } else {
    await sahiCheckbox.uncheck();
  }
  await expect(sahiCheckbox).toBeChecked({ checked: toggledValue });

  await cfgBlock.getByRole('button', { name: 'Сохранить', exact: true }).click();

  // The API must reflect the toggled value.
  await expect
    .poll(
      async () =>
        (
          (await (
            await request.get('http://127.0.0.1:8000/api/system/detect-config', {
              headers: { Authorization: `Bearer ${auth.token}` },
            })
          ).json()) as { use_sahi_default: boolean }
        ).use_sahi_default,
      { timeout: 10_000 },
    )
    .toBe(toggledValue);

  // Reload (F5) — the checkbox must rehydrate from the persisted SQLite value.
  await page.reload();
  await page.getByRole('button', { name: 'Система', exact: true }).click();
  await expect(page.getByTestId('cfg-use-sahi')).toBeChecked({ checked: toggledValue });

  // Restore the original value so the test is idempotent.
  await page.getByTestId('cfg-use-sahi').click(); // toggle back
  await page.getByTestId('detect-config').getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect
    .poll(
      async () =>
        (
          (await (
            await request.get('http://127.0.0.1:8000/api/system/detect-config', {
              headers: { Authorization: `Bearer ${auth.token}` },
            })
          ).json()) as { use_sahi_default: boolean }
        ).use_sahi_default,
      { timeout: 10_000 },
    )
    .toBe(initialValue);
});
