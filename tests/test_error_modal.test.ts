import { expect, test } from '@playwright/test';

/**
 * Error reference UI: structured API error → ErrorDetailsModal with causes/solutions.
 */
test('ErrorDetailsModal shows causes and solutions from API error', async ({ page }) => {
  await page.route('**/api/media/frame**', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'File not found',
        error: {
          code: 404,
          name: 'NOT_FOUND',
          title: 'Ресурс не найден',
          message: 'File not found',
          causes: ['Видео удалено или перемещено из archive/', 'Неверный путь к файлу'],
          solutions: [
            'Проверьте существование файла в archive/ (Медиапул → Обновить)',
            'Убедитесь, что путь указан правильно (без лишних спецсимволов)',
          ],
          docs_url:
            'https://github.com/nmuravev/MuraveiVision-PRO/blob/main/docs/ERROR_REFERENCE.md#404',
        },
      }),
    });
  });

  await page.addInitScript(() => {
    localStorage.setItem('muravei-splash-done-v1', '1');
    localStorage.removeItem('muraveivision-layout-v3');
    localStorage.removeItem('muraveivision-layout-v2');
    localStorage.removeItem('muraveivision-layout-v1');
  });

  await page.goto('/');
  await expect(page.getByTestId('viewer-1')).toBeVisible({ timeout: 15_000 });

  await page.evaluate(() => {
    void fetch('/api/media/frame?path=missing.mp4');
  });

  const modal = page.getByTestId('error-details-modal');
  await expect(modal).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText('Ошибка 404: Ресурс не найден')).toBeVisible();
  await expect(modal.getByText('Видео удалено или перемещено из archive/')).toBeVisible();
  await expect(modal.getByText('Что сделать')).toBeVisible();
  await expect(
    modal.getByText('Проверьте существование файла в archive/ (Медиапул → Обновить)'),
  ).toBeVisible();
  await expect(modal.getByRole('link', { name: /Подробнее в документации/ })).toBeVisible();

  await page.getByRole('button', { name: 'Понятно' }).click();
  await expect(modal).toHaveCount(0);
});
