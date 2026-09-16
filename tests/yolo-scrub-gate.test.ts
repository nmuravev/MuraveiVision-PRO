import { expect, test } from '@playwright/test';

type YOLODebugStats = {
  scrubEvents: number;
  wsMessagesBlocked: number;
  wsMessagesAllowed: number;
  yoloInferCalls: number;
  yoloSkipCalls: number;
  lastScrubTime: number | null;
  suspendActive: boolean;
  cooldownRemaining: number;
};

test('YOLO stays suspended throughout scrub and cooldown', async ({ page, request }, testInfo) => {
  test.setTimeout(120_000);
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

  await page.getByText('archive', { exact: true }).first().click();
  const media = page.locator('[data-media-path$=".mp4"]').filter({ hasText: /.+/ }).first();
  await expect(media).toBeVisible({ timeout: 30_000 });
  await media.dblclick();

  await page.waitForFunction(
    () => {
      const video = document.querySelector('video');
      return Boolean(video && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA);
    },
    undefined,
    { timeout: 90_000 },
  );
  await page.evaluate(() => window.resetYOLOStats());

  const scrub = page.getByTestId('viewer-scrub');
  await expect(scrub).toBeVisible();
  const box = await scrub.boundingBox();
  expect(box).not.toBeNull();
  if (!box) return;

  const y = box.y + box.height / 2;
  await page.mouse.move(box.x + box.width * 0.1, y);
  await page.mouse.down();
  for (let index = 1; index <= 10; index += 1) {
    await page.mouse.move(box.x + box.width * (0.1 + index * 0.075), y);
    await page.waitForTimeout(50);
  }
  await page.mouse.up();

  const duringCooldown = await page.evaluate(() => window.getYOLOStats());
  expect(duringCooldown.scrubEvents).toBeGreaterThanOrEqual(10);
  expect(duringCooldown.suspendActive).toBe(true);
  expect(duringCooldown.yoloInferCalls).toBe(0);
  expect(duringCooldown.yoloSkipCalls).toBeGreaterThan(0);

  // Discrete seek is debounced by 100 ms; slow media/keyframe decode can move
  // the 400 ms cooldown start, so poll the observable state instead of racing it.
  await page.waitForTimeout(500);
  await expect
    .poll(() => page.evaluate(() => window.getYOLOStats().suspendActive), {
      timeout: 5_000,
    })
    .toBe(false);
  const stats = await page.evaluate<YOLODebugStats>(() => window.getYOLOStats());
  const events = await page.evaluate(() => window.muraveiDebug.events);
  await testInfo.attach('yolo-scrub-stats', {
    body: JSON.stringify({ stats, events }, null, 2),
    contentType: 'application/json',
  });

  expect(stats.scrubEvents).toBeGreaterThanOrEqual(10);
  expect(stats.yoloInferCalls).toBe(0);
  expect(stats.yoloSkipCalls).toBeGreaterThan(0);
  expect(stats.suspendActive).toBe(false);
  expect(stats.cooldownRemaining).toBe(0);

  const scrubEnd = events.find((event) => event.type === 'scrub_end');
  const suspendOff = events.find((event) => event.type === 'suspend_off');
  expect(scrubEnd).toBeTruthy();
  expect(suspendOff).toBeTruthy();
  expect((suspendOff?.time ?? 0) - (scrubEnd?.time ?? 0)).toBeGreaterThanOrEqual(390);

  await page.evaluate(() => window.printYOLOReport());
});
