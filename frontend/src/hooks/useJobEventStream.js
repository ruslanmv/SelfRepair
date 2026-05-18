import { useEffect, useRef, useState } from "react";

import { openJobEventStream } from "../api/jobsStream.js";

/**
 * Live tail of job_event rows.
 *
 * Seeds the buffer with whatever historical events the caller has
 * already loaded via `useJobEvents`, then opens an SSE stream from
 * the highest event id forward. Reconnects are handled by the browser
 * (EventSource native), which re-sends Last-Event-ID so we don't get
 * duplicate or missed events.
 *
 * Returns `{ events, connected, error }`. Consumers concatenate with
 * the historical page; this hook only owns the live tail.
 */
export function useJobEventStream(jobId, { since } = {}) {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    if (!jobId) return undefined;
    setEvents([]);
    setError(null);
    const es = openJobEventStream(jobId, { lastEventId: since });
    sourceRef.current = es;
    es.onopen = () => setConnected(true);
    es.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        setEvents((prev) => prev.concat(parsed));
      } catch {
        // Ignore malformed payloads; the server-side serialiser is
        // canonical, so this would be a noisy network glitch.
      }
    };
    es.onerror = (e) => {
      setConnected(false);
      // Browser reconnects on its own; surface the last error so the
      // UI can flag a stale-stream banner if it stays disconnected.
      setError(e);
    };
    return () => {
      setConnected(false);
      es.close();
      sourceRef.current = null;
    };
  }, [jobId, since]);

  return { events, connected, error };
}
