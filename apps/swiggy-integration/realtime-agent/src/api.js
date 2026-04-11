/* Small browser API wrapper for the hosted Swiggy and LemonSlice backend. */

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3000";

async function request(path, init = {}) {
  /* Centralize fetch error handling so components get plain JSON or exceptions. */
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (response.ok) {
    return response.json();
  }

  const errorText = await response.text();
  throw new Error(`API request failed: ${errorText}`);
}

async function createRoom() {
  /* Create a LemonSlice hosted room for the live avatar runtime. */
  return request("/create-room", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
}

async function submitSwiggyTranscript(payload) {
  /* Send a normal hosted transcript turn to the Swiggy sidecar bridge. */
  return request("/swiggy/transcript", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

async function submitSwiggyDebugTranscript(payload) {
  /* Send a transcript turn to the debug endpoint with planner trace data. */
  return request("/swiggy/debug-transcript", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export default { createRoom, submitSwiggyTranscript, submitSwiggyDebugTranscript };
