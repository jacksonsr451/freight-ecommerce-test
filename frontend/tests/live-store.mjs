import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';

/* global document, window -- page.evaluate runs in the browser, not Node. */

const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const writes = [];
  const checkoutWrites = [];
  const external = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.hostname !== '127.0.0.1') external.push(request.url());
    if (url.pathname.endsWith('/checkout-details') && request.method() === 'PUT') {
      const body = request.postDataJSON();
      checkoutWrites.push(body);
      assert.deepEqual(Object.keys(body).sort(), ['address', 'buyer', 'expected_revision']);
    }
    if (url.pathname.endsWith('/orders') && request.method() === 'POST') {
      const body = request.postDataJSON();
      assert.deepEqual(Object.keys(body).sort(), ['expected_revision', 'submission_key']);
      assert.match(body.submission_key, /^[0-9a-f-]{36}$/i);
    }
    if (url.pathname.endsWith('/confirm') && request.method() === 'POST') {
      const body = request.postDataJSON();
      assert.deepEqual(Object.keys(body).sort(), ['expected_cart_revision', 'outcome']);
      assert.equal(body.outcome, 'approved');
    }
    if (url.pathname.endsWith('/cancel') && request.method() === 'POST') {
      const body = request.postDataJSON();
      assert.deepEqual(Object.keys(body), ['expected_cart_revision']);
    }
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
  await page.goto(`${process.env.LIVE_STORE_URL}/catalogo`);
  await page.getByRole('link', { name: 'Livro sintético de demonstração', exact: true }).click();
  await page.getByLabel('Quantidade', { exact: true }).fill('2');
  const addSecondOrder = page.getByRole('button', { name: 'Adicionar ao carrinho' });
  await expect(addSecondOrder).toBeEnabled();
  await addSecondOrder.click();
  await page.getByRole('link', { name: 'Ver carrinho', exact: true }).click();
  await expect(page.getByRole('complementary', { name: 'Resumo do carrinho' })).toContainText(
    '91,80',
  );
  await page.goto(`${process.env.LIVE_STORE_URL}/checkout`);
  for (const [label, value] of [
    ['Nome do comprador', 'Comprador sintético'],
    ['E-mail', 'buyer@example.com'],
    ['CEP de destino', '01001000'],
    ['Rua', 'Rua sintética'],
    ['Número', '1'],
    ['Bairro', 'Centro'],
    ['Cidade', 'São Paulo'],
  ])
    await page.getByLabel(label).fill(value);
  await page.getByLabel('UF').selectOption('SP');
  await page.getByRole('button', { name: 'Salvar dados e cotar' }).click();
  await expect(page.getByText('Transportadora sintética')).toBeVisible();
  const offeredOption = page.getByRole('button', { name: /Selecionar oferta 1/ });
  await expect(offeredOption).toBeEnabled();
  await offeredOption.click();
  await expect(
    page.getByText(
      'Oferta selecionada somente na loja. Nenhuma contratação ou pagamento externo foi realizado.',
    ),
  ).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Resumo do checkout' })).toContainText(
    '25,90',
  );
  await page.getByRole('button', { name: 'Criar pedido local simulado' }).click();
  await expect(page.getByRole('heading', { name: 'Resumo do pedido' })).toBeVisible();
  await expect(page.getByText('Aguardando decisão do simulador')).toBeVisible();
  await expect(page.getByText(/Gateway inexistente/)).toBeVisible();
  await page.getByRole('button', { name: 'Simular aprovado' }).click();
  await expect(page.getByText('Pagamento aprovado (simulação local)')).toBeVisible();
  await expect(page.getByText('pago simulado · evento de origem simulated')).toBeVisible();
  const orderId = page.url().split('/').at(-1);
  assert.match(orderId, /^[0-9a-f-]{36}$/i);
  await page.goto(`${process.env.LIVE_STORE_URL}/admin/pedidos`);
  await page.getByLabel('Chave administrativa local').fill(process.env.LOCAL_ADMIN_KEY);
  await page.getByRole('button', { name: new RegExp(`Pedido · ${orderId.slice(0, 8)}`) }).click();
  await page.getByRole('button', { name: 'Separando' }).click();
  await page.getByRole('button', { name: 'Embalado' }).click();
  await page.getByRole('button', { name: 'Pronto para importação' }).click();
  await page.getByRole('button', { name: 'Importação pendente (local)' }).click();
  await page.getByRole('button', { name: 'Expedido (simulação local)' }).click();
  await page.getByRole('button', { name: 'Entregue (simulação local)' }).click();
  await expect(page.getByText('Sem status externo vinculado')).toBeVisible();
  await page.goto(`${process.env.LIVE_STORE_URL}/pedidos/${orderId}`);
  await expect(page.getByText('entregue simulado · evento de origem simulated')).toBeVisible();
  await expect(page.getByText(/Este estado é simulado/)).toBeVisible();
  await page.getByRole('link', { name: 'Ver histórico local' }).click();
  await expect(page.getByRole('link', { name: /Pedido local/ })).toBeVisible();
  assert(checkoutWrites.some((body) => body.buyer.email === 'buyer@example.com'));
  await page.screenshot({
    path: process.env.LIVE_STORE_SCREENSHOT.replace('cart-live-mobile', 'checkout-live-mobile'),
    fullPage: true,
  });
  console.log(
    'PASS: real browser -> local API -> PostgreSQL catalog/cart/checkout/mock quote/simulated payment/order/fulfillment/tracking; no external calls',
  );
} finally {
  await browser.close();
}
