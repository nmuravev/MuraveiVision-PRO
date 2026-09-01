import { expect, test } from '@playwright/test';

const SOURCE =
  process.env.MURAVEI_TEST_SOURCE ??
  'D:\\LLM\\MuraveiVision-PRO\\archive\\video_2026-08-25_09-17-15.mp4';

test('scoped detections, playback rate and dead Live status remain consistent', async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: process.env.MURAVEI_TEST_PIN ?? '1234567' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const { token } = (await authResponse.json()) as { token: string };
  const headers = { Authorization: `Bearer ${token}` };

  const streamUrl = new URL('http://127.0.0.1:8000/api/media/stream');
  streamUrl.searchParams.set('path', SOURCE);
  const ranged = await request.get(streamUrl.toString(), {
    headers: { ...headers, Range: 'bytes=0-99' },
  });
  expect(ranged.status()).toBe(206);
  expect((await ranged.body()).byteLength).toBe(100);
  expect(ranged.headers()['content-range']).toMatch(/^bytes 0-99\//);

  const unscoped = await request.get('http://127.0.0.1:8000/api/detections', { headers });
  expect(unscoped.ok()).toBeTruthy();
  expect(((await unscoped.json()) as { detections: unknown[] }).detections).toEqual([]);

  const createdResponse = await request.post('http://127.0.0.1:8000/api/detections', {
    headers,
    data: {
      source_video: SOURCE,
      time_sec: 1.25,
      frame_idx: 1,
      class_id: 0,
      class_name: 'tank',
      confidence: 0.42,
      bbox: { x1: 0.1, y1: 0.1, x2: 0.3, y2: 0.3 },
      user_notes: 'field-regression fixture',
      origin: 'manual',
    },
  });
  expect(createdResponse.ok()).toBeTruthy();
  const created = (await createdResponse.json()) as { id: string };

  const scopedUrl = new URL('http://127.0.0.1:8000/api/detections');
  scopedUrl.searchParams.set('source_video', SOURCE);
  scopedUrl.searchParams.set('include_deleted', 'true');
  const scoped = await request.get(scopedUrl.toString(), { headers });
  const scopedRows = ((await scoped.json()) as { detections: Array<{ id: string }> }).detections;
  expect(scopedRows.some((row) => row.id === created.id)).toBe(true);

  const collected = await request.post(
    'http://127.0.0.1:8000/api/active-learning/collect',
    {
      headers,
      data: { source_video: SOURCE, max_confidence: 0.5 },
    },
  );
  expect(collected.ok()).toBeTruthy();
  const samples = (
    (await collected.json()) as {
      samples: Array<{ id: string; detection_id: string }>;
    }
  ).samples;
  const sample = samples.find((row) => row.detection_id === created.id);
  expect(sample).toBeTruthy();
  const rejected = await request.post(
    `http://127.0.0.1:8000/api/active-learning/${encodeURIComponent(sample!.id)}/decision`,
    { headers, data: { status: 'rejected', class_name: 'tank' } },
  );
  expect(rejected.ok()).toBeTruthy();
  const afterDelete = await request.get(scopedUrl.toString(), { headers });
  const deletedRows = (
    (await afterDelete.json()) as {
      detections: Array<{ id: string; is_deleted: boolean }>;
    }
  ).detections;
  expect(deletedRows.find((row) => row.id === created.id)?.is_deleted).toBe(true);

  const engineerLogin = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: process.env.MURAVEI_ENGINEER_PIN ?? '0000000' },
  });
  expect(engineerLogin.ok()).toBeTruthy();
  const engineerToken = ((await engineerLogin.json()) as { token: string }).token;
  const engineerHeaders = { Authorization: `Bearer ${engineerToken}` };
  const previousNetwork = await request.get('http://127.0.0.1:8000/api/network/config', {
    headers,
  });
  const previousConfig = (await previousNetwork.json()) as {
    mode: 'off' | 'server' | 'client';
    server_ip: string;
    port: number;
    base_name: string;
  };
  const networkOn = await request.post('http://127.0.0.1:8000/api/network/config', {
    headers: engineerHeaders,
    data: { ...previousConfig, mode: 'server' },
  });
  expect(networkOn.ok()).toBeTruthy();
  const sentTarget = await request.post('http://127.0.0.1:8000/api/network/targets', {
    headers,
    data: { class_name: 'tank', confidence: 0.8, source_video: SOURCE },
  });
  expect(sentTarget.ok()).toBeTruthy();
  const target = ((await sentTarget.json()) as { target: { source_video?: string } }).target;
  expect(target.source_video).toBe(SOURCE);
  const networkRestore = await request.post('http://127.0.0.1:8000/api/network/config', {
    headers: engineerHeaders,
    data: previousConfig,
  });
  expect(networkRestore.ok()).toBeTruthy();

  const scopedRequests: string[] = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/detections?')) scopedRequests.push(req.url());
  });
  await page.addInitScript((authToken) => {
    localStorage.setItem('muravei-token', authToken);
    localStorage.setItem('muravei-splash-done-v1', '1');
  }, token);
  await page.goto('/');
  await page.getByText('archive', { exact: true }).first().click();
  const media = page.locator('[data-media-path$=".mp4"]').filter({ hasText: /.+/ }).first();
  await expect(media).toBeVisible();
  await media.dblclick();
  await page.waitForFunction(
    () => (document.querySelector('video')?.readyState ?? 0) >= HTMLMediaElement.HAVE_CURRENT_DATA,
  );
  await expect
    .poll(() => scopedRequests.some((url) => url.includes('source_video=')))
    .toBe(true);

  await page.getByLabel('Скорость воспроизведения').selectOption('2');
  await expect
    .poll(() => page.locator('video').first().evaluate((video) => video.playbackRate))
    .toBe(2);
  const before = await page.locator('video').first().evaluate((video) => video.currentTime);
  await page.getByRole('button', { name: 'Пуск' }).click();
  await page.waitForTimeout(700);
  const after = await page.locator('video').first().evaluate((video) => video.currentTime);
  expect(after).toBeGreaterThan(before + 0.5);
  await page.getByRole('button', { name: 'Пауза' }).click();

  await page.getByRole('button', { name: 'Монтаж', exact: true }).click();
  const viewer1 = page.getByTestId('viewer-1');
  const viewer2 = page.getByTestId('viewer-2');
  await expect(viewer2).toBeVisible();
  await viewer2.click({ position: { x: 20, y: 60 } });
  await media.dblclick();
  await expect(viewer2.locator('video')).toHaveCount(1);
  await expect
    .poll(() => viewer2.locator('video').evaluate((video) => video.readyState))
    .toBeGreaterThanOrEqual(1);
  await viewer1.click({ position: { x: 20, y: 60 } });
  await viewer1.getByRole('button', { name: 'Было/Стало' }).click();
  await expect(viewer1.getByRole('button', { name: 'Sync' })).toBeVisible();
  const compareScrub = viewer1.getByTestId('viewer-scrub');
  const compareBox = await compareScrub.boundingBox();
  expect(compareBox).not.toBeNull();
  await page.mouse.click(compareBox!.x + compareBox!.width * 0.45, compareBox!.y + 4);
  await page.waitForTimeout(900);
  const compareTimes = await page.locator('video').evaluateAll((videos) =>
    videos.map((video) => video.currentTime),
  );
  expect(Math.abs(compareTimes[0] - compareTimes[1])).toBeLessThan(0.6);

  await page.getByRole('button', { name: 'AI-анализ', exact: true }).click();
  await expect(page.getByText('Правила и тревоги')).toBeVisible();
  await page.getByLabel('Минимальная уверенность').fill('0.8');
  await page.getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText(/любой класс ≥ 0\.80/)).toBeVisible();

  const liveOpen = await request.post('http://127.0.0.1:8000/api/live/open', {
    headers,
    data: { viewer_id: 'field-dead-live', url: 'rtsp://127.0.0.1:1/no-stream' },
  });
  expect(liveOpen.ok()).toBeTruthy();
  await expect
    .poll(
      async () => {
        const status = await request.get(
          'http://127.0.0.1:8000/api/live/field-dead-live/status',
          { headers },
        );
        return ((await status.json()) as { active?: boolean }).active;
      },
      { timeout: 15_000 },
    )
    .toBe(false);
});
