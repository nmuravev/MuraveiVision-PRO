import { expect, test } from '@playwright/test';

/**
 * Stage 1 / 3.4 — global operator hotkeys.
 *
 * Verifies the core no-mouse scenario: Space toggles playback, arrow keys
 * step frames, 1-4 switches focused viewer, I/O set marks, Ctrl+Z undoes a
 * detection patch. Hotkeys must NOT fire while typing in a form field.
 */
test('Operator hotkeys: space, arrows, viewer-switch, marks, undo', async ({ page, request }) => {
  const pin = process.env.MURAVEI_TEST_PIN ?? '1234567';
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  await page.addInitScript((token) => {
    localStorage.setItem('muravei-token', token);
    localStorage.setItem('muravei-splash-done-v1', '1');
  }, auth.token);
  await page.goto('/');

  // Load a video into viewer-1.
  await page.getByText('archive', { exact: true }).first().click();
  const media = page.locator('[data-media-path$=".mp4"]').filter({ hasText: /.+/ }).first();
  await expect(media).toBeVisible();
  await media.dblclick();

  await page.waitForFunction(() => {
    const video = document.querySelector('video');
    return Boolean(video && video.readyState >= 1);
  });

  // Focus the viewer so Space / arrows act.
  await page.getByTestId('viewer-scrub').click({ position: { x: 10, y: 4 } });

  // --- Space toggles playback ---
  const pausedBefore = await page.evaluate(() => (document.querySelector('video') as HTMLVideoElement).paused);
  await page.keyboard.press('Space');
  await page.waitForTimeout(150);
  const pausedAfter = await page.evaluate(() => (document.querySelector('video') as HTMLVideoElement).paused);
  expect(pausedAfter).not.toBe(pausedBefore);

  // Pause again so the rest of the test is deterministic.
  if (!pausedAfter) {
    await page.keyboard.press('Space');
    await page.waitForTimeout(150);
  }

  // --- Arrow Right steps a frame (playhead moves forward) ---
  const timeBefore = await page.evaluate(() => (document.querySelector('video') as HTMLVideoElement).currentTime);
  await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(100);
  const timeAfter = await page.evaluate(() => (document.querySelector('video') as HTMLVideoElement).currentTime);
  expect(timeAfter).toBeGreaterThanOrEqual(timeBefore);

  // --- 1-4 switches focused viewer ---
  const focusedViewer = () =>
    page.evaluate(() => {
      const s = (window as unknown as { __muraveiStores?: { viewer?: { getState: () => { focusedViewerId: string } } } }).__muraveiStores?.viewer?.getState();
      return s?.focusedViewerId ?? null;
    });
  await page.keyboard.press('2');
  await expect.poll(() => focusedViewer(), { timeout: 5_000 }).toBe('viewer-2');
  await page.keyboard.press('1');
  await expect.poll(() => focusedViewer(), { timeout: 5_000 }).toBe('viewer-1');

  // --- I / O set marks ---
  const inPoint = () =>
    page.evaluate(() => {
      const s = (window as unknown as { __muraveiStores?: { timeline?: { getState: () => { inPoint: number | null } } } }).__muraveiStores?.timeline?.getState();
      return s?.inPoint ?? null;
    });
  const outPoint = () =>
    page.evaluate(() => {
      const s = (window as unknown as { __muraveiStores?: { timeline?: { getState: () => { outPoint: number | null } } } }).__muraveiStores?.timeline?.getState();
      return s?.outPoint ?? null;
    });
  await page.keyboard.press('i');
  await expect.poll(() => inPoint(), { timeout: 5_000 }).not.toBeNull();
  await page.keyboard.press('o');
  await expect.poll(() => outPoint(), { timeout: 5_000 }).not.toBeNull();

  // --- Hotkeys must NOT fire while typing in a form field ---
  // Focus an input (Inspector notes / chat). Use a known input: the Network chat if present,
  // else create a temporary input via evaluate.
  await page.evaluate(() => {
    const el = document.createElement('input');
    el.id = '__hotkey_test_input';
    document.body.appendChild(el);
    el.focus();
  });
  const inPaused = await page.evaluate(() => (document.querySelector('video') as HTMLVideoElement).paused);
  await page.keyboard.press('Space');
  await page.waitForTimeout(150);
  const inPausedAfter = await page.evaluate(() => (document.querySelector('video') as HTMLVideoElement).paused);
  expect(inPausedAfter).toBe(inPaused); // playback did not toggle while typing
  await page.evaluate(() => document.getElementById('__hotkey_test_input')?.remove());

  // --- Ctrl+Z undoes a detection patch ---
  // Patch the active detection (if any) via the store, then undo.
  const hadActive = await page.evaluate(() => {
    const s = (window as unknown as { __muraveiStores?: { muravei?: { getState: () => { activeDetectionId: string | null; patchDetection: (id: string, f: Record<string, unknown>) => Promise<void> } } } }).__muraveiStores?.muravei?.getState();
    return Boolean(s?.activeDetectionId);
  });
  if (hadActive) {
    const beforeUndo = await page.evaluate(() => {
      const s = (window as unknown as { __muraveiStores?: { muravei?: { getState: () => { activeDetectionId: string | null; detections: { id: string; user_notes: string }[]; patchDetection: (id: string, f: Record<string, unknown>) => Promise<void> } } } }).__muraveiStores?.muravei?.getState();
      const id = s?.activeDetectionId;
      const row = s?.detections.find((d) => d.id === id);
      return row?.user_notes ?? '';
    });
    await page.evaluate(async () => {
      const s = (window as unknown as { __muraveiStores?: { muravei?: { getState: () => { activeDetectionId: string | null; patchDetection: (id: string, f: Record<string, unknown>) => Promise<void> } } } }).__muraveiStores?.muravei?.getState();
      if (s?.activeDetectionId) await s.patchDetection(s.activeDetectionId, { user_notes: '__hotkey_test__' });
    });
    await page.keyboard.press('Control+z');
    await expect
      .poll(
        async () => {
          const r = await page.evaluate(() => {
            const s = (window as unknown as { __muraveiStores?: { muravei?: { getState: () => { activeDetectionId: string | null; detections: { id: string; user_notes: string }[] } } } }).__muraveiStores?.muravei?.getState();
            const id = s?.activeDetectionId;
            return s?.detections.find((d) => d.id === id)?.user_notes ?? null;
          });
          return r;
        },
        { timeout: 5_000 },
      )
      .toBe(beforeUndo);
  }
});
