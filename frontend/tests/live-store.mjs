import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';

/* global document, window -- page.evaluate runs in the browser, not Node. */

const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const writes = [];
  const external = [];
  page.on('requestfailed', (request) => {
    console.error(
      'Local request failed:',
      new URL(request.url()).pathname,
      request.failure()?.errorText,
    );
  });
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') external.push(request.url());
    if (url.pathname.includes('/items') && request.method() !== 'GET') {
      const body = request.postDataJSON();
      writes.push({ method: request.method(), body });
      if (body)
        assert(
          Object.keys(body).every((key) =>
            ['expected_revision', 'product_id', 'quantity'].includes(key),
          ),
        );
    }
    assert(!Object.keys(request.headers()).includes('authorization'));
  });
  await page.goto(`${process.env.LIVE_STORE_URL}/catalogo`);
  await expect(page.getByText('Mock · cotação sintética')).toBeVisible();
  await page.getByRole('link', { name: 'Livro sintético de demonstração', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Livro sintético de demonstração',
  );
  await page.getByLabel('Quantidade', { exact: true }).fill('2');
  await page.getByRole('button', { name: 'Adicionar ao carrinho' }).click();
  await page.getByRole('link', { name: 'Ver carrinho', exact: true }).click();
  const summary = page.getByRole('complementary', { name: 'Resumo do carrinho' });
  await expect(summary).toContainText('91,80');
  await expect(summary).toContainText('0,9 kg');
  await page.reload(); // only the cart UUID survives; data is read again from the actual API
  await expect(summary).toContainText('91,80');
  const quantity = page.getByLabel('Quantidade de Livro sintético de demonstração');
  await quantity.fill('3');
  await expect(summary).toContainText('91,80');
  await page.getByRole('button', { name: 'Atualizar quantidade' }).click();
  await expect(summary).toContainText('137,70');
  await expect(summary).toContainText('1,35 kg');
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await page.screenshot({ path: process.env.LIVE_STORE_SCREENSHOT, fullPage: true });
  await page
    .getByRole('button', { name: 'Remover Livro sintético de demonstração', exact: true })
    .click();
  await expect(page.getByRole('heading', { name: 'Seu carrinho está vazio' })).toBeVisible();
  assert.deepEqual(
    writes.map((write) => write.method),
    ['POST', 'PATCH', 'DELETE'],
  );
  assert.deepEqual(external, []);
  console.log(
    'PASS: real browser -> local API -> PostgreSQL add/update/remove, authoritative totals and no reservation',
  );
} finally {
  await browser.close();
}
