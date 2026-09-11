/** Extract an actionable message from FastAPI/core error envelopes. */
export async function responseError(res: Response, fallback: string): Promise<Error> {
  let message = '';
  try {
    const data = (await res.clone().json()) as unknown;
    if (data && typeof data === 'object') {
      const record = data as Record<string, unknown>;
      const error = record.error;
      const detail = record.detail;
      if (error && typeof error === 'object') {
        const nested = (error as Record<string, unknown>).message;
        if (typeof nested === 'string') message = nested.trim();
      } else if (typeof error === 'string') {
        message = error.trim();
      }
      if (!message && typeof detail === 'string') message = detail.trim();
      if (!message && detail && typeof detail === 'object') {
        const nested = (detail as Record<string, unknown>).message;
        if (typeof nested === 'string') message = nested.trim();
      }
    }
  } catch {
    try {
      message = (await res.text()).trim();
    } catch {
      /* Keep the caller's stable fallback. */
    }
  }
  return new Error(`${message || fallback} (HTTP ${res.status})`);
}
