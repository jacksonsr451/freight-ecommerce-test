import { z } from 'zod';
import { requestInternal } from './http';

const integer = z.number().int().nonnegative();
const localBatch = z.object({
  id: z.uuid(),
  filename: z.string(),
  local_status: z.string(),
  external_status: z.string().nullable(),
  total: integer,
  valid: integer,
  invalid: integer,
  imported: integer,
  duplicates: integer,
  processed: integer,
  created_at: z.iso.datetime({ offset: true }),
});
const localPage = z.object({ items: z.array(localBatch), total: integer });
const availability = z.object({
  mode: z.enum(['mock', 'real']),
  upload_enabled: z.boolean(),
  company_configured: z.boolean(),
  location_configured: z.boolean(),
});
const exportReadiness = z.object({
  can_export: z.literal(false),
  missing_fields: z.array(z.string()),
});
const importDetail = z.object({
  batch: localBatch,
  external_status: z.string(),
  issue: z.json().nullable(),
  dispatch: z.json().nullable(),
  items: z.array(z.record(z.string(), z.json())),
  has_more: z.boolean(),
  next_cursor: integer.nullable(),
});
export type LocalImportBatch = z.infer<typeof localBatch>;
export type ImportDetail = z.infer<typeof importDetail>;

export function getImportAvailability(key: string, signal?: AbortSignal) {
  return requestInternal('/api/admin/imports/availability', availability, {
    signal,
    headers: { 'X-Local-Admin-Key': key },
  });
}

export function getImportExportReadiness(key: string, signal?: AbortSignal) {
  return requestInternal('/api/admin/imports/export-readiness', exportReadiness, {
    signal,
    headers: { 'X-Local-Admin-Key': key },
  });
}

export function listImportBatches(key: string, signal?: AbortSignal) {
  return requestInternal('/api/admin/imports', localPage, {
    signal,
    headers: { 'X-Local-Admin-Key': key },
  });
}

export function uploadImportFile(key: string, file: File) {
  const body = new FormData();
  body.set('file', file);
  return requestInternal('/api/admin/imports', localBatch, {
    method: 'POST',
    body,
    headers: { 'X-Local-Admin-Key': key },
  });
}

export function getImportBatch(
  key: string,
  batchId: string,
  cursor = 0,
  errorsOnly = false,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ cursor: String(cursor) });
  if (errorsOnly) params.set('errors_only', 'true');
  return requestInternal(`/api/admin/imports/${z.uuid().parse(batchId)}?${params}`, importDetail, {
    signal,
    headers: { 'X-Local-Admin-Key': key },
  });
}

export function confirmImportBatch(key: string, batchId: string) {
  return requestInternal(`/api/admin/imports/${z.uuid().parse(batchId)}/confirm`, localBatch, {
    method: 'POST',
    body: { confirm_valid_rows: true, operator_reviewed: true },
    headers: { 'X-Local-Admin-Key': key },
  });
}
