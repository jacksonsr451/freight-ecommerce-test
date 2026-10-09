import { z } from 'zod';
import { requestInternal } from './http';

const runtimeSchema = z.object({
  freight_mode: z.enum(['mock', 'real']),
  purchases_simulated: z.literal(true),
});
export type RuntimeInfo = z.infer<typeof runtimeSchema>;

export function getRuntime(signal?: AbortSignal): Promise<RuntimeInfo> {
  return requestInternal('/api/runtime', runtimeSchema, { signal });
}
