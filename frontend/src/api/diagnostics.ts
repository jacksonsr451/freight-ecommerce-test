import { z } from 'zod';
import { requestInternal } from './http';

const nullableInteger = z.number().int().nonnegative().nullable();
const check = z.object({
  name: z.string(),
  status: z.enum(['ok', 'unavailable', 'configured', 'not_configured', 'not_checked']),
  latency_ms: nullableInteger.optional(),
  details: z.record(z.string(), z.json()),
});
const operation = z.object({
  correlation_id: z.uuid(),
  operation: z.string(),
  mode: z.enum(['mock', 'real']),
  outcome: z.enum(['started', 'succeeded', 'failed', 'uncertain']),
  occurred_at: z.iso.datetime({ offset: true }),
  http_status: nullableInteger,
  latency_ms: nullableInteger,
  request_key: z.uuid().nullable(),
  quote_id: z.uuid().nullable(),
  external_quote_id: z.uuid().nullable(),
  import_batch_id: z.uuid().nullable(),
  error_code: z.string().nullable(),
  retry_after_seconds: z.number().nonnegative().nullable(),
  redacted_details: z.record(z.string(), z.json()),
  snapshot_summary: z.record(z.string(), z.json()).nullable(),
});
export const diagnosticReportSchema = z.object({
  generated_at: z.iso.datetime({ offset: true }),
  freight_mode: z.enum(['mock', 'real']).nullable(),
  purchases_simulated: z.literal(true),
  checks: z.array(check),
  operations: z.array(operation),
  pending_import_batches: z.number().int().nonnegative().nullable(),
  pending_webhook_receipts: z.number().int().nonnegative().nullable(),
});
export type DiagnosticReport = z.infer<typeof diagnosticReportSchema>;

export function diagnosticReportJson(report: DiagnosticReport): string {
  return JSON.stringify(diagnosticReportSchema.parse(report), null, 2);
}

export function getDiagnostics(signal?: AbortSignal): Promise<DiagnosticReport> {
  return requestInternal('/api/diagnostics', diagnosticReportSchema, { signal });
}

export function exportDiagnosticReport(report: DiagnosticReport): void {
  const blob = new Blob([diagnosticReportJson(report)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `freight-lab-diagnostic-${new Date(report.generated_at).toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}
