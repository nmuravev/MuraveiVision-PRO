import { expect, test } from '@playwright/test';

/**
 * P3.13 — Segmentation UI: archive SEG toggle and «Сегментировать кадр»
 * enablement driven by GET /api/seg/status (mocked; no real VRAM load).
 */
test('Segmentation UI toggles and button state', async ({ page, request }) => {
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  let segStatus: {
    ready: boolean;
    loaded: boolean;
    weight: string | null;
    available: string[];
  } = {
    ready: true,
    loaded: false,
    weight: null,
    available: ['yolo26n-seg.pt'],
  };

  await page.route('**/api/seg/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(segStatus),
    });
  });

  await page.addInitScript((token) => {
    localStorage.setItem('muravei-token', token);
    localStorage.setItem('muravei-splash-done-v1', '1');
    localStorage.removeItem('muraveivision-layout-v3');
    localStorage.removeItem('muraveivision-layout-v2');
    localStorage.removeItem('muraveivision-layout-v1');
  }, auth.token);

  await page.goto('/');
  const viewer1 = page.getByTestId('viewer-1');
  await expect(viewer1).toBeVisible({ timeout: 15_000 });

  await viewer1.getByRole('button', { name: 'Сегментация' }).click();

  const segmentBtn = viewer1.getByRole('button', { name: 'Сегментировать кадр' });
  await expect(segmentBtn).toBeVisible();
  await expect(segmentBtn).toBeDisabled();
  await expect(segmentBtn).toHaveAttribute('title', 'загрузите модель (Система)');
  await expect(viewer1.getByText('загрузите модель (Система)')).toBeVisible();

  segStatus = {
    ready: true,
    loaded: true,
    weight: 'yolo26n-seg.pt',
    available: ['yolo26n-seg.pt'],
  };

  // Status is fetched only when overlayMode changes — re-enter SEG mode.
  await viewer1.getByRole('button', { name: 'Детекция' }).click();
  await viewer1.getByRole('button', { name: 'Сегментация' }).click();

  await expect(segmentBtn).toBeEnabled();
  await expect(segmentBtn).toHaveAttribute('title', 'Сегментировать текущий кадр');
});
