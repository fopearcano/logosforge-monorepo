const inFlightLoads = new Map<string, Promise<unknown>>();

/**
 * Deduplicate the complete initial LIST -> optional CREATE -> GET transaction.
 *
 * Sharing only CREATE is insufficient: a delayed StrictMode replay can receive
 * an earlier empty LIST after the first CREATE has already completed and then
 * create a second document. Sharing the whole transaction closes that window.
 */
export function loadInitialDocumentOnce<T>(
  baseUrl: string,
  load: () => Promise<T>,
): Promise<T> {
  const existing = inFlightLoads.get(baseUrl) as Promise<T> | undefined;
  if (existing) return existing;
  const request = Promise.resolve().then(load).finally(() => {
    if (inFlightLoads.get(baseUrl) === request) inFlightLoads.delete(baseUrl);
  });
  inFlightLoads.set(baseUrl, request);
  return request;
}
