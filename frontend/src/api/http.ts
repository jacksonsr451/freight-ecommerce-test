import type { ZodType } from 'zod';

export class ApiError extends Error {
  readonly code: 'http' | 'network' | 'invalid-response' | 'invalid-path';
  readonly status?: number;
  readonly domainCode?: string;
  readonly retryAfterSeconds?: number;
  constructor(
    code: 'http' | 'network' | 'invalid-response' | 'invalid-path',
    message: string,
    status?: number,
    domainCode?: string,
    retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.domainCode = domainCode;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function internalPath(path: string): string {
  let valid: boolean;
  try {
    const url = new URL(path, window.location.origin);
    const pathname = decodeURIComponent(url.pathname);
    valid =
      path.startsWith('/api/') &&
      !path.includes('\\') &&
      url.origin === window.location.origin &&
      !url.hash &&
      pathname.startsWith('/api/') &&
      !pathname.startsWith('/api/v1/freight');
  } catch {
    valid = false;
  }
  if (!valid) throw new ApiError('invalid-path', 'Use apenas a API interna da loja.');
  return path;
}

function httpMessage(status: number): string {
  if (status === 422 || status === 400) return 'Confira os dados informados e tente novamente.';
  if (status === 401 || status === 403) return 'Não foi possível autorizar esta ação na loja.';
  if (status === 404) return 'Conteúdo não encontrado na API local.';
  if (status === 409) return 'Os dados mudaram. Atualize e tente novamente.';
  if (status === 429) return 'Muitas tentativas. Aguarde antes de tentar novamente.';
  return 'A API local está indisponível. Tente novamente.';
}

export async function requestInternal<T>(
  path: string,
  schema: ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  const target = internalPath(path);
  let response: Response;
  try {
    response = await fetch(target, {
      method: options.method ?? 'GET',
      credentials: 'same-origin',
      redirect: 'error',
      headers: {
        Accept: 'application/json',
        ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...options.headers,
      },
      signal: options.signal,
      ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
    });
  } catch (error) {
    if (
      typeof error === 'object' &&
      error !== null &&
      'name' in error &&
      error.name === 'AbortError'
    )
      throw error;
    throw new ApiError('network', 'Não foi possível conectar à API local.');
  }
  if (!response.ok) {
    let code: string | undefined;
    const known: Record<string, string> = {
      insufficient_stock: 'Estoque insuficiente. Confira a disponibilidade atual.',
      product_not_found: 'Produto indisponível ou não encontrado.',
      product_unavailable: 'O produto ficou indisponível. Atualize o catálogo.',
      cart_revision_conflict:
        'O carrinho mudou em outra operação. Os dados foram atualizados; revise antes de tentar novamente.',
      cart_commercial_changed: 'Preços ou disponibilidade mudaram. Revise o carrinho atualizado.',
      cart_locked: 'Este carrinho está encerrado e não pode ser alterado.',
      cart_item_not_found: 'O item não está mais neste carrinho.',
      item_quantity_limit: 'Limite de 1000 unidades por produto.',
      cart_item_limit: 'Limite de produtos distintos no carrinho atingido.',
      unequal_volumes:
        'Os volumes têm medidas diferentes. Use a estimativa por peso explicitamente ou revise os itens.',
      freight_unauthorized: 'Cotação não autorizada. Verifique a credencial no backend.',
      freight_forbidden: 'O backend não possui acesso autorizado para esta cotação.',
      freight_validation_error:
        'Os critérios foram recusados. Revise os dados do carrinho e endereço.',
      freight_rate_limited: 'Limite de cotações atingido. Aguarde o tempo informado.',
      freight_retry_wait: 'Aguarde antes de repetir a chamada de cotação.',
      freight_unavailable: 'O serviço de cotação está temporariamente indisponível.',
      freight_configuration_error: 'A configuração de frete do backend precisa ser revisada.',
      quote_criteria_changed:
        'Carrinho ou endereço mudaram. Recalcule o frete antes de selecionar.',
      quote_not_selectable: 'A cotação não possui ofertas utilizáveis para seleção.',
      estimate_not_selectable: 'Estimativa por peso não pode fechar pedido.',
    };
    try {
      const data: unknown = await response.json();
      if (
        typeof data === 'object' &&
        data !== null &&
        'detail' in data &&
        typeof data.detail === 'object' &&
        data.detail !== null &&
        'code' in data.detail &&
        typeof data.detail.code === 'string' &&
        Object.hasOwn(known, data.detail.code)
      ) {
        code = data.detail.code;
      }
    } catch {
      /* Never publish raw error bodies. */
    }
    throw new ApiError(
      'http',
      code ? known[code] : httpMessage(response.status),
      response.status,
      code,
      (() => {
        const value = response.headers.get('Retry-After');
        if (!value) return undefined;
        if (/^[0-9]+$/.test(value)) {
          const seconds = Number(value);
          return Number.isSafeInteger(seconds) ? seconds : undefined;
        }
        const time = Date.parse(value);
        return Number.isFinite(time)
          ? Math.max(0, Math.ceil((time - Date.now()) / 1000))
          : undefined;
      })(),
    );
  }
  try {
    return schema.parse(await response.json());
  } catch {
    throw new ApiError('invalid-response', 'A resposta da API local não pôde ser validada.');
  }
}
