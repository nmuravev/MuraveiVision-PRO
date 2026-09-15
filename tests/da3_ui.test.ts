import { expect, test } from '@playwright/test';

/**
 * P5 — DA3 Dense UI audit (all-variants + NC badge + Mesh toggle).
 * Requires backend on :8000 (engineer PIN 0000000).
 */
test.describe('DA3 Dense UI audit', () => {
  test.beforeEach(async ({ page, request }) => {
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
  });

  test('Dense selector has 4 DA3 options, no AliceVision MVS by default', async ({ page }) => {
    await page.getByRole('button', { name: /Гео 3D/i }).click();
    const select = page.getByTestId('dense-backend-select');
    await expect(select).toBeVisible({ timeout: 20_000 });

    const values = await select.locator('option').evaluateAll((opts) =>
      opts.map((o) => (o as HTMLOptionElement).value),
    );
    expect(values).toEqual([
      'da3_dense_base',
      'da3_dense_large',
      'da3_dense_metric',
      'da3_dense_giant',
    ]);
    expect(values.some((v) => v.includes('alicevision') || v === 'dense')).toBeFalsy();
  });

  test('NC badge appears for LARGE and GIANT with CC BY-NC tooltip', async ({ page }) => {
    await page.getByRole('button', { name: /Гео 3D/i }).click();
    const select = page.getByTestId('dense-backend-select');
    await expect(select).toBeVisible({ timeout: 20_000 });

    await select.selectOption('da3_dense_large');
    const badge = page.getByTestId('da3-nc-badge');
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText(/Non-Commercial Only/i);
    const title = (await badge.getAttribute('title')) || '';
    expect(title).toMatch(/creativecommons\.org\/licenses\/by-nc\/4\.0/);
    expect(title).toMatch(/NOTICE_CC-BY-NC-4\.0/);

    await select.selectOption('da3_dense_base');
    await expect(page.getByTestId('da3-nc-badge')).toHaveCount(0);

    await select.selectOption('da3_dense_giant');
    await expect(page.getByTestId('da3-nc-badge')).toBeVisible();
  });

  test('Система → Конфигурация 3D has alicevision_enabled toggle', async ({ page }) => {
    await page.getByRole('button', { name: 'Система', exact: true }).click();
    const recon = page.getByTestId('recon-config');
    await expect(recon).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('cfg-alicevision-enabled')).toBeVisible();
    await expect(recon).toContainText(/Dense = DA3/i);
  });

  test('presets API exposes da3 family + mesh disabled_reason fields', async ({ request }) => {
    const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
      data: { pin: '0000000', role: 'engineer' },
    });
    const auth = (await authResponse.json()) as { token: string };
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
    // AliceVision MVS dense must not be a default preset id
    expect(ids).not.toContain('dense');
    const giant = body.presets.find((p) => p.id === 'da3_dense_giant');
    expect(giant).toBeTruthy();
    if (giant?.disabled) {
      expect(String(giant.disabled_reason || '')).toMatch(/VRAM|16/i);
    }
  });
});
