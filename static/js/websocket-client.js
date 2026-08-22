/**
 * Parse and validate one raw WebSocket text frame from the server, per the
 * protocol in WEB_DESIGN.md section 6.3. Throws on anything malformed or
 * unrecognized.
 */
export function parseServerMessage(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(`invalid JSON from server: ${raw}`);
  }

  if (
    data &&
    data.type === "session_start" &&
    typeof data.tempo_bpm === "number" &&
    typeof data.key === "string" &&
    typeof data.seed === "number" &&
    typeof data.modulation === "boolean"
  ) {
    return data;
  }
  if (
    data &&
    data.type === "bar" &&
    typeof data.bar_index === "number" &&
    typeof data.key === "string" &&
    Array.isArray(data.notes) &&
    data.notes.every(
      (note) =>
        note &&
        typeof note.pitch === "number" &&
        typeof note.start_beat === "number" &&
        typeof note.duration_beat === "number" &&
        typeof note.velocity === "number" &&
        typeof note.channel === "number"
    )
  ) {
    return data;
  }
  if (data && data.type === "error" && typeof data.message === "string") {
    return data;
  }
  throw new Error(`unrecognized server message: ${raw}`);
}

/**
 * Open a WebSocket connection to /ws with the given (optional) query
 * parameters, dispatching parsed messages to the given callbacks. A parse
 * failure for one message is logged and skipped rather than closing the
 * connection (WEB_DESIGN.md doesn't specify this case; failing open on a
 * single bad frame is safer than tearing down an otherwise-healthy session).
 */
export function connect({ tempo, key, seed, modulation, onSessionStart, onBar, onError, onClose }) {
  const params = new URLSearchParams();
  if (tempo) params.set("tempo", tempo);
  if (key) params.set("key", key);
  if (seed) params.set("seed", seed);
  if (modulation !== undefined) params.set("modulation", modulation ? "true" : "false");
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const query = params.toString();
  const url = `${protocol}//${location.host}/ws${query ? "?" + query : ""}`;

  const ws = new WebSocket(url);
  ws.addEventListener("message", (event) => {
    let message;
    try {
      message = parseServerMessage(event.data);
    } catch (error) {
      console.error(error);
      return;
    }
    if (message.type === "session_start") onSessionStart(message);
    else if (message.type === "bar") onBar(message);
    else if (message.type === "error") onError(message);
  });
  ws.addEventListener("error", (event) => {
    console.warn("WebSocket error (see subsequent close event for details)", event);
  });
  ws.addEventListener("close", onClose);
  return ws;
}
