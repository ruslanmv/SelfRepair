import { apiBase } from "./client.js";

/**
 * Open the SSE event stream for a job.
 *
 * EventSource doesn't allow custom request headers, so we rely on the
 * session cookie (sent via `withCredentials`) and the standard
 * `Last-Event-ID` header that the browser re-sends on reconnect.
 * Caller passes the highest event id they have so the server replays
 * everything strictly after that.
 */
export function openJobEventStream(jobId, { lastEventId } = {}) {
  const params = new URLSearchParams();
  if (lastEventId !== undefined && lastEventId !== null) {
    params.set("lastEventId", String(lastEventId));
  }
  const query = params.toString() ? `?${params}` : "";
  return new EventSource(
    `${apiBase}/v1/jobs/${jobId}/events/stream${query}`,
    { withCredentials: true },
  );
}
