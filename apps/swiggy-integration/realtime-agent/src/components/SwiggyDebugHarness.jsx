/* Text-only browser harness for exercising the current Swiggy sidecar directly. */

import React, { useMemo, useState } from "react";

import api from "../api";

function createSyntheticSessionId() {
  /* Generate a stable synthetic session so multi-turn sidecar state can be tested. */
  const randomId =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `swiggy-debug-${randomId}`;
}

function prettyJson(value) {
  /* Keep the debug trace readable without introducing any custom formatter state. */
  return JSON.stringify(value, null, 2);
}

export default function SwiggyDebugHarness() {
  const [sessionId, setSessionId] = useState(createSyntheticSessionId);
  const [transcript, setTranscript] = useState("");
  const [turns, setTurns] = useState([]);
  const [isSending, setIsSending] = useState(false);

  const warning = useMemo(
    () =>
      "Fully live test mode. Explicit confirmations can place real Swiggy orders or bookings on the authenticated account.",
    [],
  );

  const handleSubmit = async (event) => {
    /* Send the typed transcript straight to the sidecar debug endpoint. */
    event.preventDefault();
    const normalized = transcript.trim();
    if (!normalized || isSending) return;

    setIsSending(true);
    try {
      const response = await api.submitSwiggyDebugTranscript({
        session_id: sessionId,
        transcription: normalized,
        event_type: "user_transcription",
        client_timestamp: new Date().toISOString(),
      });

      setTurns((currentTurns) => [
        ...currentTurns,
        {
          id: `${Date.now()}-${currentTurns.length}`,
          sessionId,
          input: normalized,
          response,
          error: null,
        },
      ]);
      setTranscript("");
    } catch (error) {
      setTurns((currentTurns) => [
        ...currentTurns,
        {
          id: `${Date.now()}-${currentTurns.length}`,
          sessionId,
          input: normalized,
          response: null,
          error: error instanceof Error ? error.message : String(error),
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const resetSession = () => {
    /* Start a fresh synthetic session while keeping the existing log for comparison. */
    setSessionId(createSyntheticSessionId());
  };

  const clearLog = () => {
    /* Clear the local transcript/trace history without touching backend state. */
    setTurns([]);
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-8 text-grey-light">
      <div className="flex flex-col gap-3 rounded-xl border border-dark-blue-border bg-dark-blue p-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="m-0 text-3xl font-semibold text-grey-light">
              Swiggy Debug Harness
            </h1>
            <p className="m-0 mt-2 text-sm text-grey-light/80">
              Text-only tester for the Swiggy sidecar. No LemonSlice. No Daily.
            </p>
          </div>
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {warning}
          </div>
        </div>

        <div className="flex flex-col gap-3 rounded-lg border border-dark-blue-border bg-darkest-blue p-4">
          <div className="text-xs uppercase tracking-[0.2em] text-turquoise">
            Current Session
          </div>
          <code className="overflow-x-auto text-sm text-grey-light">
            {sessionId}
          </code>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={resetSession}
              className="rounded-lg bg-turquoise px-4 py-2 text-sm font-semibold text-darkest-blue transition-colors hover:bg-turquoise-hover"
            >
              Reset Session
            </button>
            <button
              type="button"
              onClick={clearLog}
              className="rounded-lg border border-dark-blue-border px-4 py-2 text-sm font-semibold text-grey-light transition-colors hover:bg-darkest-blue"
            >
              Clear Log
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="text-sm font-semibold text-grey-light" htmlFor="debug-transcript">
            Transcript
          </label>
          <textarea
            id="debug-transcript"
            rows={4}
            value={transcript}
            onChange={(event) => setTranscript(event.target.value)}
            placeholder='Type a transcript like "order biryani from Biryani Blues"'
            className="w-full rounded-xl border border-dark-blue-border bg-darkest-blue px-4 py-3 text-sm text-grey-light outline-none ring-0"
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={isSending || !transcript.trim()}
              className="rounded-lg bg-turquoise px-5 py-2 text-sm font-semibold text-darkest-blue transition-colors hover:bg-turquoise-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSending ? "Sending..." : "Send Transcript"}
            </button>
          </div>
        </form>
      </div>

      <div className="flex flex-col gap-4 pb-8">
        {turns.length === 0 ? (
          <div className="rounded-xl border border-dashed border-dark-blue-border bg-dark-blue p-6 text-sm text-grey-light/80">
            No turns yet. Send a transcript to inspect the sidecar decision path.
          </div>
        ) : null}

        {turns.map((turn, index) => (
          <article
            key={turn.id}
            className="rounded-xl border border-dark-blue-border bg-dark-blue p-5"
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-turquoise">
                Turn {index + 1}
              </div>
              <div className="text-xs uppercase tracking-[0.16em] text-grey-light/60">
                Session {turn.sessionId}
              </div>
            </div>

            <div className="mb-4 rounded-lg border border-dark-blue-border bg-darkest-blue p-4">
              <div className="mb-2 text-xs uppercase tracking-[0.16em] text-grey-light/60">
                User Transcript
              </div>
              <div className="whitespace-pre-wrap text-sm text-grey-light">
                {turn.input}
              </div>
            </div>

            {turn.error ? (
              <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-100">
                {turn.error}
              </div>
            ) : null}

            {turn.response ? (
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
                <section className="rounded-lg border border-dark-blue-border bg-darkest-blue p-4">
                  <div className="mb-2 text-xs uppercase tracking-[0.16em] text-grey-light/60">
                    Sidecar Result
                  </div>
                  <dl className="grid gap-2 text-sm text-grey-light">
                    <div>
                      <dt className="inline text-grey-light/60">action:</dt>{" "}
                      <dd className="inline">{turn.response.action}</dd>
                    </div>
                    <div>
                      <dt className="inline text-grey-light/60">reason:</dt>{" "}
                      <dd className="inline">{turn.response.reason}</dd>
                    </div>
                    <div>
                      <dt className="inline text-grey-light/60">service:</dt>{" "}
                      <dd className="inline">{turn.response.service ?? "null"}</dd>
                    </div>
                    <div>
                      <dt className="inline text-grey-light/60">flow_open:</dt>{" "}
                      <dd className="inline">
                        {String(turn.response.flow_open ?? false)}
                      </dd>
                    </div>
                  </dl>
                  {turn.response.message ? (
                    <div className="mt-4">
                      <div className="mb-2 text-xs uppercase tracking-[0.16em] text-grey-light/60">
                        Message
                      </div>
                      <div className="whitespace-pre-wrap rounded-md bg-dark-blue p-3 text-sm text-grey-light">
                        {turn.response.message}
                      </div>
                    </div>
                  ) : null}
                  {turn.response.chat_message ? (
                    <div className="mt-4">
                      <div className="mb-2 text-xs uppercase tracking-[0.16em] text-grey-light/60">
                        Hosted Relay Message
                      </div>
                      <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-dark-blue p-3 text-xs text-grey-light">
                        {turn.response.chat_message}
                      </pre>
                    </div>
                  ) : null}
                </section>

                <section className="rounded-lg border border-dark-blue-border bg-darkest-blue p-4">
                  <div className="mb-2 text-xs uppercase tracking-[0.16em] text-grey-light/60">
                    Debug Trace
                  </div>
                  <pre className="max-h-[520px] overflow-auto whitespace-pre-wrap rounded-md bg-dark-blue p-3 text-xs text-grey-light">
                    {prettyJson(turn.response.debug_trace ?? {})}
                  </pre>
                </section>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}
