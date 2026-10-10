import { expect, test } from '@playwright/test';

const CART_ID = '00000000-0000-4000-8000-000000000100';

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
  await page.addInitScript(
    (cartId) => localStorage.setItem('freight-lab.cart-id', cartId),
    CART_ID,
  );
  await page.route(`**/api/carts/${CART_ID}`, (route) =>
    route.fulfill({
      json: {
        id: CART_ID,
        status: 'active',
        revision: 2,
        delivery_address: null,
        buyer_details: null,
        items: [
          {
            id: '00000000-0000-4000-8000-000000000101',
            product_id: '00000000-0000-4000-8000-000000000102',
            sku: 'SYNTHETIC-E2E',
            name: 'Produto sintético visual',
            quantity: 1,
            unit_price_cents: 2590,
            line_total_cents: 2590,
            weight_grams: 1000,
            line_weight_grams: 1000,
            length_cm: 20,
            width_cm: 15,
            height_cm: 10,
            available_quantity: 5,
            problem: null,
          },
        ],
        subtotal_cents: 2590,
        total_weight_grams: 1000,
        total_quantity: 1,
        editable: true,
        checkout_ready: false,
        has_current_quote: false,
      },
    }),
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
    const overflow = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('*')]
        .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
        .map((element) => ({
          tag: element.tagName,
          className: String(element.className),
          right: element.getBoundingClientRect().right,
          width: element.getBoundingClientRect().width,
          text: element.innerText.slice(0, 80),
        })),
    );
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      JSON.stringify(overflow),
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
    const checkoutOverflow = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('*')]
        .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
        .map((element) => ({
          tag: element.tagName,
          className: String(element.className),
          right: element.getBoundingClientRect().right,
          width: element.getBoundingClientRect().width,
          text: element.innerText.slice(0, 80),
        })),
    );
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      JSON.stringify(checkoutOverflow),
    ).toBe(true);
    await expect(page.getByRole('textbox', { name: 'CEP de destino' })).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Nome do comprador' })).toBeVisible();
    await page.getByRole('button', { name: 'Salvar dados e cotar' }).click();
    await expect(page.getByText('Informe o nome com ao menos 2 caracteres.')).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Nome do comprador' })).toBeFocused();
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
