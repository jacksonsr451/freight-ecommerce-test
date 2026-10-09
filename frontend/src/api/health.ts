import { z } from 'zod';
import { requestInternal } from './http';

const healthSchema = z.object({
  status: z.literal('ok'),
  service: z.literal('freight-ecommerce-test'),
});
export type HealthResponse = z.infer<typeof healthSchema>;

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return requestInternal('/api/health', healthSchema, { signal });
}
