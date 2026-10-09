import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/products?*', (route) =>
    route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 6, total_pages: 0 } }),
  );
  // Explicitly synthetic responses to the local public runtime/health contract.
  await page.route('**/api/health', (route) =>
    route.fulfill({ json: { status: 'ok', service: 'freight-ecommerce-test' } }),
  );
  await page.route('**/api/runtime', (route) =>
    route.fulfill({ json: { freight_mode: 'mock', purchases_simulated: true } }),
  );
});

for (const width of [320, 390, 768, 1280]) {
  test(`shell and checkout have no horizontal overflow at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const external: string[] = [];
    page.on('request', (request) => {
      if (new URL(request.url()).hostname !== '127.0.0.1') external.push(request.url());
    });
    await page.goto('/catalogo');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(
      'Uma compra de teste. Tudo às claras.',
    );
    await expect(page.getByText('Mock · cotação sintética')).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    if (width < 600) {
      const toggle = page.getByRole('button', { name: 'Abrir menu' });
      await toggle.click();
      await expect(page.getByRole('navigation', { name: 'Principal' })).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(toggle).toBeFocused();
      await toggle.click();
    }
    await page.getByRole('link', { name: 'Checkout', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Checkout de teste');
    await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.getByLabel('CEP de destino').fill('123');
    await page.getByRole('button', { name: 'Validar CEP' }).click();
    await expect(page.getByRole('alert')).toContainText('8 dígitos');
    await page.getByLabel('CEP de destino').fill('01001000');
    await page.getByLabel('CEP de destino').press('Enter');
    await expect(
      page.getByText('CEP validado localmente. Nenhuma cotação foi enviada.'),
    ).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`checkout-${width}.png`), fullPage: true });
    expect(external).toEqual([]);
  });
}

test('keyboard skip link reaches main content and Real mode is disclosed as simulated purchase', async ({
  page,
}, testInfo) => {
  await page.route('**/api/runtime', (route) =>
    route.fulfill({ json: { freight_mode: 'real', purchases_simulated: true } }),
  );
  await page.goto('/catalogo');
  await expect(page.getByText('Real · compra simulada')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('catalog-desktop.png'), fullPage: true });
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Pular para o conteúdo' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath('keyboard-main-focus.png'), fullPage: true });
});
