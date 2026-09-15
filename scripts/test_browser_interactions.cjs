const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const page = await browser.newPage();
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('[BROWSER CONSOLE ERROR]:', msg.text());
    }
  });

  page.on('pageerror', err => {
    console.log('[PAGE ERROR MESSAGE]:', err.message);
    console.log('[PAGE ERROR STACK]:', err.stack);
  });

  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  // Close splash if present
  try {
    const splash = await page.locator('text=Запустить MuraveiVision').or(page.locator('text=Продолжить')).first();
    if (await splash.isVisible()) {
      await splash.click();
      await page.waitForTimeout(500);
    }
  } catch (e) {}

  // Test tabs
  const tabs = ['Медиа', 'Монтаж', 'AI-анализ', 'Обучение', '4×Live', 'Система'];
  for (const tab of tabs) {
    console.log('Testing tab:', tab);
    try {
      const tabEl = page.getByRole('button', { name: tab });
      if (await tabEl.count() > 0) {
        await tabEl.first().click();
        await page.waitForTimeout(1000);
      }
    } catch (e) {
      console.log('Failed clicking tab', tab, e.message);
    }
  }

  // Test switching to flight3d
  console.log('Testing layout switch to mediaGeo (flight3d)...');
  await page.evaluate(() => {
    const stores = window.__muraveiStores;
    if (window.usePanelLayoutStore) {
      // test
    }
    // Let's trigger timeline operations
    if (stores && stores.timeline) {
      console.log('Simulating timeline states...');
      stores.timeline.getState().setMediaDuration(0);
      stores.timeline.getState().setMediaDuration(-1);
      stores.timeline.getState().setMediaDuration(NaN);
      stores.timeline.getState().setMediaDuration(Infinity);
      stores.timeline.getState().setMediaDuration(120);
    }
  });
  await page.waitForTimeout(1000);

  await browser.close();
  console.log('Test completed successfully.');
})();
