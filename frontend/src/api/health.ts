export interface HealthResponse {
  status: 'ok';
  service: 'freight-ecommerce-test';
}

export async function getHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('API local indisponível.');
  const data: unknown = await response.json();
  if (
    typeof data !== 'object' ||
    data === null ||
    !('status' in data) ||
    data.status !== 'ok' ||
    !('service' in data) ||
    data.service !== 'freight-ecommerce-test'
  ) {
    throw new Error('Resposta inválida da API local.');
  }
  return { status: data.status, service: data.service };
}
