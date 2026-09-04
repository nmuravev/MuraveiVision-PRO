import { expect, test } from '@playwright/test';

/**
 * Step 3.2 — 4×Live preset + Event Timeline.
 * Mocks GET /api/events/timeline so the panel can render without seeding SQLite.
 */
test('4xLive preset shows four viewers and EventTimeline seeks on local click', async ({
  page,
  request,
}) => {
  const pin = process.env.MURAVEI_TEST_PIN ?? '1234567';
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  const mockEvents = {
    events: [
      {
        id: 'local-1',
        type: 'local_detection',
        time_sec: 12.5,
        class_name: 'tank',
        confidence: 0.91,
        source_video: 'clip.mp4',
        source_base: null,
        created_at: 1700000001,
      },
      {
        id: 'net-1',
        type: 'network_target',
        time_sec: null,
        class_name: 'military_truck',
        confidence: 0.7,
        source_video: null,
        source_base: 'Baza-1',
        created_at: 1700000000,
        gps_lat: 50.1,
        gps_lon: 30.2,
        notes: 'from hub',
      },
    ],
  };

  await page.route('**/api/events/timeline**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockEvents),
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
  await page.getByRole('button', { name: '4×Live', exact: true }).click();

  await expect(page.getByTestId('viewer-1')).toBeVisible();
  await expect(page.getByTestId('viewer-2')).toBeVisible();
  await expect(page.getByTestId('viewer-3')).toBeVisible();
  await expect(page.getByTestId('viewer-4')).toBeVisible();
  await expect(page.getByTestId('event-timeline')).toBeVisible();
  await expect(page.getByTestId('event-local-1')).toBeVisible();
  await expect(page.getByTestId('event-net-1')).toBeVisible();

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
    w.__muraveiStores?.viewer?.getState().setSource('viewer-1', 'archive/clip.mp4');
  });

  await page.getByTestId('event-local-1').click();

  await expect
    .poll(async () =>
      page.evaluate(() => {
        const w = window as unknown as {
          __muraveiStores?: {
            timeline?: { getState: () => { playheadPosition: number } };
            viewer?: { getState: () => { focusedViewerId: string } };
          };
        };
        return {
          playhead: w.__muraveiStores?.timeline?.getState().playheadPosition ?? -1,
          focused: w.__muraveiStores?.viewer?.getState().focusedViewerId ?? '',
        };
      }),
    )
    .toEqual({ playhead: 12.5, focused: 'viewer-1' });
});
