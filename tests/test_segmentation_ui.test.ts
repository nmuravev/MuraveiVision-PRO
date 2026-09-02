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

test('Batch segmentation modal opens and shows progress', async ({ page, request }) => {
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  const taskId = 'e2e-batch-1';
  let pollCount = 0;

  await page.route('**/api/seg/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ready: true,
        loaded: true,
        weight: 'yolo26n-seg.pt',
        available: ['yolo26n-seg.pt'],
      }),
    });
  });

  await page.route('**/api/seg/batch**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (method === 'POST' && /\/api\/seg\/batch\/?$/.test(new URL(url).pathname)) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          task_id: taskId,
          status: 'running',
          progress: 0,
          processed: 0,
          sample_total: 10,
          mask_total: 0,
          message: 'Старт…',
          results: null,
        }),
      });
      return;
    }

    if (method === 'GET' && url.includes(`/api/seg/batch/${taskId}`)) {
      pollCount += 1;
      const done = pollCount >= 2;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          task_id: taskId,
          status: done ? 'done' : 'running',
          progress: done ? 1 : 0.5,
          processed: done ? 10 : 5,
          sample_total: 10,
          mask_total: done ? 3 : 1,
          message: done ? 'Готово' : 'В процессе',
          results: done
            ? [
                {
                  time_sec: 1.5,
                  masks: [
                    {
                      class: 'trench',
                      conf: 0.9,
                      polygon_norm: [
                        [0.1, 0.1],
                        [0.2, 0.1],
                        [0.15, 0.2],
                      ],
                    },
                  ],
                },
              ]
            : null,
        }),
      });
      return;
    }

    await route.continue();
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

  await viewer1.getByRole('button', { name: 'Сегментация' }).click();
  const batchBtn = viewer1.getByRole('button', { name: 'Batch сегментация' });
  await expect(batchBtn).toBeEnabled();
  await batchBtn.click();

  const modal = page.getByTestId('batch-seg-modal');
  await expect(modal).toBeVisible();
  await page.getByRole('button', { name: 'Старт' }).click();
  await expect(page.getByTestId('batch-seg-progress')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('batch-seg-summary')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('batch-seg-summary')).toContainText('Обработано 10 кадров');
  await expect(page.getByTestId('batch-seg-summary')).toContainText('найдено 3 масок');
});

test('SAM3 toolbar load and point tool', async ({ page, request }) => {
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  let samStatus = {
    ready: true,
    loaded: false,
    weight: null as string | null,
    available: ['sam3.pt'],
  };

  await page.route('**/api/seg/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ready: true,
        loaded: false,
        weight: null,
        available: ['yolo26n-seg.pt'],
      }),
    });
  });

  await page.route('**/api/seg/sam3/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(samStatus),
    });
  });

  await page.route('**/api/seg/sam3/load**', async (route) => {
    samStatus = {
      ready: true,
      loaded: true,
      weight: 'sam3.pt',
      available: ['sam3.pt'],
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        ...samStatus,
        yolo_seg_unloaded: false,
      }),
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
  const loadSam = viewer1.getByTestId('sam3-load');
  await expect(loadSam).toBeVisible();
  await loadSam.click();
  await expect(viewer1.getByTestId('sam3-tool-point')).toBeVisible();
  await expect(viewer1.getByTestId('sam3-from-detection')).toBeVisible();
  await expect(viewer1.getByTestId('sam3-hint')).toContainText('sam3');
});

test('SAM3 propagate modal progress', async ({ page, request }) => {
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  const taskId = 'e2e-prop-1';
  let pollCount = 0;

  await page.route('**/api/seg/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ready: true,
        loaded: false,
        weight: null,
        available: ['yolo26n-seg.pt'],
      }),
    });
  });

  await page.route('**/api/seg/sam3/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ready: true,
        loaded: true,
        weight: 'sam3.pt',
        available: ['sam3.pt'],
      }),
    });
  });

  await page.route('**/api/seg/sam3/propagate**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (method === 'POST' && /\/api\/seg\/sam3\/propagate\/?$/.test(new URL(url).pathname)) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          task_id: taskId,
          status: 'running',
          progress: 0,
          processed: 0,
          sample_total: 5,
          mask_total: 0,
          persisted: 0,
          message: 'Старт…',
          results: null,
        }),
      });
      return;
    }
    if (method === 'GET' && url.includes(`/api/seg/sam3/propagate/${taskId}`)) {
      pollCount += 1;
      const done = pollCount >= 2;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          task_id: taskId,
          status: done ? 'done' : 'running',
          progress: done ? 1 : 0.4,
          processed: done ? 5 : 2,
          sample_total: 5,
          mask_total: done ? 5 : 2,
          persisted: 0,
          message: done ? 'Готово' : 'В процессе',
          results: done
            ? [
                {
                  time_sec: 1.0,
                  frame_idx: 30,
                  masks: [
                    {
                      class: 'object',
                      conf: 1,
                      polygon_norm: [
                        [0.1, 0.1],
                        [0.2, 0.1],
                        [0.15, 0.2],
                      ],
                    },
                  ],
                },
              ]
            : null,
        }),
      });
      return;
    }
    await route.continue();
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

  await page.evaluate(() => {
    const w = window as unknown as {
      __muraveiStores?: {
        viewer?: {
          getState: () => {
            setSource: (id: string, path: string | null) => void;
          };
        };
        sam3?: {
          setState: (partial: Record<string, unknown>) => void;
        };
      };
    };
    w.__muraveiStores?.viewer?.getState().setSource('viewer-1', 'archive/clip.mp4');
    w.__muraveiStores?.sam3?.setState({
      ready: true,
      loaded: true,
      weight: 'sam3.pt',
      hint: 'sam3.pt',
      lastPrompt: { bboxes: [{ x1: 0.1, y1: 0.1, x2: 0.4, y2: 0.4 }] },
    });
  });

  await viewer1.getByRole('button', { name: 'Сегментация' }).click();
  const propBtn = viewer1.getByTestId('sam3-propagate');
  await expect(propBtn).toBeEnabled({ timeout: 10_000 });
  await propBtn.click();
  const modal = page.getByTestId('sam3-prop-modal');
  await expect(modal).toBeVisible();
  await page.getByTestId('sam3-prop-start').click();
  await expect(page.getByTestId('sam3-prop-progress')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('sam3-prop-summary')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('sam3-prop-summary')).toContainText('Обработано 5 кадров');
});

test('SAM3 text prompt UI and propagate seed', async ({ page, request }) => {
  const authResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { pin: '0000000', role: 'engineer' },
  });
  expect(authResponse.ok()).toBeTruthy();
  const auth = (await authResponse.json()) as { token: string };

  await page.route('**/api/seg/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ready: true,
        loaded: false,
        weight: null,
        available: ['yolo26n-seg.pt'],
      }),
    });
  });

  await page.route('**/api/seg/sam3/status**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ready: true,
        loaded: true,
        weight: 'sam3.pt',
        available: ['sam3.pt'],
      }),
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

  await page.evaluate(() => {
    const w = window as unknown as {
      __muraveiStores?: {
        viewer?: {
          getState: () => {
            setSource: (id: string, path: string | null) => void;
          };
        };
        sam3?: { setState: (s: Record<string, unknown>) => void };
      };
    };
    w.__muraveiStores?.viewer?.getState().setSource('viewer-1', 'archive/clip.mp4');
    w.__muraveiStores?.sam3?.setState({
      ready: true,
      loaded: true,
      weight: 'sam3.pt',
      hint: 'sam3.pt',
      lastPrompt: { text: ['trench'] },
      textPrompt: 'trench / окоп; person',
    });
  });

  await viewer1.getByRole('button', { name: 'Сегментация' }).click();

  const textInput = viewer1.getByTestId('sam3-text-input');
  await expect(textInput).toBeVisible({ timeout: 10_000 });
  await expect(textInput).toHaveAttribute(
    'placeholder',
    'trench / окоп; person; vehicle',
  );
  await expect(viewer1.getByTestId('sam3-text-infer')).toBeVisible();

  const propBtn = viewer1.getByTestId('sam3-propagate');
  await expect(propBtn).toBeEnabled({ timeout: 10_000 });
  await propBtn.click();
  await expect(page.getByTestId('sam3-prop-modal')).toBeVisible();
  await expect(page.getByTestId('sam3-prop-seed')).toContainText('text:');
  await expect(page.getByTestId('sam3-prop-seed')).toContainText('trench');
  await expect(page.getByTestId('sam3-prop-start')).toBeEnabled();
});
