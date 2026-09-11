import { responseError } from './responseError';
import { backendFetch } from './backendAuth';

export interface RecoveryNotice {
  id: string;
  label: string;
  message: string;
  recovered_from: string;
  quarantined_path: string;
  recovered_at: string;
}

/** Consume any successful backend recovery notices not shown in this session. */
export async function getRecoveryNotices(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<RecoveryNotice[]> {
  const res = await backendFetch(`${baseUrl}/api/recovery/notices`, { signal });
  if (!res.ok) throw await responseError(res, 'Could not check recovery status');
  const data = (await res.json()) as { notices?: unknown };
  return Array.isArray(data.notices) ? (data.notices as RecoveryNotice[]) : [];
}
