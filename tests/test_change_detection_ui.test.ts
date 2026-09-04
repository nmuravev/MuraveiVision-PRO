import { expect, test } from '@playwright/test';

/**
 * P3.15 — Change Detection UI: Compare mode analyze → Inspector summary/lists
 * (POST /api/change-detection/analyze mocked; no real GPS/ORB work).
 *
 * Source paths are set via __muraveiStores so the analyze button enables without
 * waiting on real dual-video decode (same introspection pattern as event timeline).
 */
test('Change Detection analyze flow', async ({ page, request }) => {
  const pin = process.env.MURAVEI_TEST_PIN ?? '1234567';
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  const mockResult = {
    method: 'gps',
    aligned: true,
    message: null,
    summary: {
      total_before: 2,
      total_after: 2,
      matched: 0,
      stable: 0,
      moved: 0,
      new: 1,
      removed: 1,
    },
    matches: [],
    new: [
      {
        id: 'n1',
        class_name: 'truck',
        bbox: { x1: 0.1, y1: 0.1, x2: 0.3, y2: 0.3 },
      },
    ],
    removed: [
      {
        id: 'r1',
        class_name: 'car',
        bbox: { x1: 0.4, y1: 0.4, x2: 0.6, y2: 0.6 },
      },
    ],
    image_diff: null,
  };

  await page.route('**/api/change-detection/analyze**', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockResult),
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
  await expect(page.getByTestId('viewer-1')).toBeVisible({ timeout: 15_000 });

  await page.getByRole('button', { name: 'Монтаж', exact: true }).click();
  const viewer1 = page.getByTestId('viewer-1');
  const viewer2 = page.getByTestId('viewer-2');
  await expect(viewer2).toBeVisible();

  await page.evaluate(() => {
    const w = window as unknown as {
      __muraveiStores?: {
        viewer?: {
          getState: () => {
            setSource: (id: string, path: string | null) => void;
          };
        };
      };
    };
    const setSource = w.__muraveiStores?.viewer?.getState().setSource;
    setSource?.('viewer-1', 'archive/before.mp4');
    setSource?.('viewer-2', 'archive/after.mp4');
  });

  await expect
    .poll(() =>
      page.evaluate(() => {
        const w = window as unknown as {
          __muraveiStores?: {
            viewer?: {
              getState: () => {
                viewers: Record<string, { sourcePath?: string | null }>;
              };
            };
          };
        };
        const viewers = w.__muraveiStores?.viewer?.getState().viewers ?? {};
        return Boolean(viewers['viewer-1']?.sourcePath && viewers['viewer-2']?.sourcePath);
      }),
    )
    .toBe(true);

  await viewer1.getByRole('button', { name: 'Было/Стало' }).click();

  const analyzeBtn = viewer1.getByRole('button', { name: 'Анализ изменений' });
  await expect(analyzeBtn).toBeVisible();
  await expect(analyzeBtn).toBeEnabled();
  await analyzeBtn.click();

  const changesSection = page.getByText('Изменения (Compare)');
  await expect(changesSection).toBeVisible({ timeout: 10_000 });
  await changesSection.scrollIntoViewIfNeeded();

  // Fold is open by default → summary lives in the body (not the collapsed status chip).
  await expect(page.getByText('2 → 2 obj · gps')).toBeVisible();
  await expect(page.getByText('Новые', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'truck' })).toBeVisible();
  await expect(page.getByText('Исчезли', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'car' })).toBeVisible();

  // Viewer-2 compare strip also reflects summary counts.
  await expect(viewer2.getByText('Изменения', { exact: true })).toBeVisible();
  await expect(viewer2.locator('span[title="новые"]')).toHaveText('+ 1');
  await expect(viewer2.locator('span[title="исчезли"]')).toHaveText('− 1');
});

/** Tiny 1×1 PNG (valid base64) for heatmap overlay E2E. */
const TINY_PNG_B64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

test('Heatmap toggle shows/hides overlay', async ({ page, request }) => {
  const pin = process.env.MURAVEI_TEST_PIN ?? '1234567';
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  const mockResult = {
    method: 'image',
    aligned: true,
    message: null,
    summary: {
      total_before: 0,
      total_after: 0,
      matched: 0,
      stable: 0,
      moved: 0,
      new: 0,
      removed: 0,
    },
    matches: [],
    new: [],
    removed: [],
    image_diff: {
      inlier_ratio: 0.85,
      regions: [],
      heatmap_b64: TINY_PNG_B64,
    },
  };

  await page.route('**/api/change-detection/analyze**', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockResult),
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
  await expect(page.getByTestId('viewer-1')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Монтаж', exact: true }).click();

  const viewer1 = page.getByTestId('viewer-1');
  await expect(page.getByTestId('viewer-2')).toBeVisible();

  await page.evaluate(() => {
    const w = window as unknown as {
      __muraveiStores?: {
        viewer?: {
          getState: () => {
            setSource: (id: string, path: string | null) => void;
          };
        };
      };
    };
    const setSource = w.__muraveiStores?.viewer?.getState().setSource;
    setSource?.('viewer-1', 'archive/before.mp4');
    setSource?.('viewer-2', 'archive/after.mp4');
  });

  await viewer1.getByRole('button', { name: 'Было/Стало' }).click();
  await viewer1.getByRole('button', { name: 'Анализ изменений' }).click();

  const heatBtn = viewer1.getByRole('button', { name: 'Теплокарта' });
  await expect(heatBtn).toBeVisible({ timeout: 10_000 });
  await heatBtn.click();
  await expect(page.getByTestId('change-heatmap').first()).toBeVisible();
  await heatBtn.click();
  await expect(page.getByTestId('change-heatmap')).toHaveCount(0);
});
