import type { ZodType } from 'zod';

export class ApiError extends Error {
  readonly code: 'http' | 'network' | 'invalid-response' | 'invalid-path';
  readonly status?: number;
  constructor(
    code: 'http' | 'network' | 'invalid-response' | 'invalid-path',
    message: string,
    status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
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
  if (!response.ok) throw new ApiError('http', httpMessage(response.status), response.status);
  try {
    return schema.parse(await response.json());
  } catch {
    throw new ApiError('invalid-response', 'A resposta da API local não pôde ser validada.');
  }
}
