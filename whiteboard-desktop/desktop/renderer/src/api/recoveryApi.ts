import { responseError } from './responseError';
import { backendFetch } from './backendAuth';
import { validateRecoveryNoticesResponse } from './runtimeDtoValidation';

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
  return validateRecoveryNoticesResponse(await res.json()).notices;
}
