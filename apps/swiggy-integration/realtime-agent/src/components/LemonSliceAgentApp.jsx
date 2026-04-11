/* Hosted LemonSlice call container plus the browser-to-Swiggy transcript bridge. */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  useDailyEvent,
  useDaily,
  DailyAudio,
  useAppMessage,
  useMeetingState,
} from "@daily-co/daily-react";

import api from "../api";
import { useAgentState } from "../providers/AgentStateProvider";
import HomeScreen from "./HomeScreen";
import AgentCall from "./AgentCall";
import Tray from "./Tray";

const STATE_IDLE = "STATE_IDLE";
const STATE_JOINING = "STATE_JOINING";
const STATE_JOINED = "STATE_JOINED";
const STATE_ERROR = "STATE_ERROR";

function normalizeBridgeText(value) {
  /* Normalize whitespace so echoed relay messages can be matched reliably. */
  return value.trim().replace(/\s+/g, " ");
}

function extractTranscriptText(data) {
  /* Tolerate slightly different transcript payload shapes from the hosted room. */
  if (!data || typeof data !== "object") return "";
  return normalizeBridgeText(
    data.transcription ?? data.transcript ?? data.message ?? data.text ?? "",
  );
}

function isFinalUserTranscription(data) {
  /* Only finalized user turns should enter the sidecar planner path. */
  if (data?.type !== "user_transcription") return false;
  if (typeof data?.is_final === "boolean") return data.is_final;
  if (typeof data?.final === "boolean") return data.final;
  if (typeof data?.transcription_complete === "boolean") {
    return data.transcription_complete;
  }
  return true;
}

export default function LemonSliceAgentApp() {
  const callObject = useDaily();
  const sendAppMessage = useAppMessage();
  const meetingState = useMeetingState();
  const [appState, setAppState] = useState(STATE_IDLE);
  const [hasError, setHasError] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [roomSession, setRoomSession] = useState(null);
  const { setHasAgentJoinedRoom, setIsAgentReady } = useAgentState();
  const roomSessionRef = useRef(null);
  const pendingEchoesRef = useRef(new Map());

  useEffect(() => {
    /* Keep the current room/session payload accessible inside async callbacks. */
    roomSessionRef.current = roomSession;
  }, [roomSession]);

  const rememberPendingEcho = useCallback((message) => {
    /* Store injected relay messages so they can be ignored if they echo back. */
    const normalized = normalizeBridgeText(message);
    if (!normalized) return;
    pendingEchoesRef.current.set(normalized, Date.now());
  }, []);

  const consumePendingEcho = useCallback((message) => {
    /* Drop expired echo entries and report whether this transcript is one of ours. */
    const normalized = normalizeBridgeText(message);
    if (!normalized) return false;

    const now = Date.now();
    for (const [key, timestamp] of pendingEchoesRef.current.entries()) {
      if (now - timestamp > 120000) {
        pendingEchoesRef.current.delete(key);
      }
    }

    if (!pendingEchoesRef.current.has(normalized)) {
      return false;
    }

    pendingEchoesRef.current.delete(normalized);
    return true;
  }, []);

  const handleBridgeResponse = useCallback(
    async (transcript) => {
      /* Forward the user's finalized transcript to the Swiggy sidecar backend. */
      const sessionId = roomSessionRef.current?.session_id;
      if (!sessionId) return;

      const result = await api.submitSwiggyTranscript({
        session_id: sessionId,
        transcription: transcript,
        event_type: "user_transcription",
        client_timestamp: new Date().toISOString(),
      });

      if (result?.action !== "inject_message" || !result?.chat_message) {
        return;
      }

      /* Relay the backend's commerce update back into the same hosted room. */
      rememberPendingEcho(result.chat_message);
      sendAppMessage(
        {
          event: "chat-msg",
          message: result.chat_message,
          name: "Swiggy",
        },
        "*",
      );
    },
    [rememberPendingEcho, sendAppMessage],
  );

  /**
   * Handle when the agent leaves the call
   */
  useDailyEvent(
    "participant-left",
    useCallback(() => {
      setHasError(true);
      setErrorMessage("Agent left the call");
    }, []),
  );

  /*
   * Handle Daily webRTC Errors
   */
  useDailyEvent(
    "error",
    useCallback(() => {
      setHasError(true);
      setErrorMessage("An error occurred. Please try again.");
    }, []),
  );

  /**
   * Handle Lemon Slice specific events
   */
  useDailyEvent(
    "app-message",
    useCallback((ev) => {
      if (ev?.data?.type === "bot_ready") {
        setIsAgentReady(true);
      }
      if (ev?.data?.type === "idle_timeout") {
        setHasError(true);
        setErrorMessage("Agent has hit idle timeout");
      }
      if (ev?.data?.type === "daily_error") {
        setHasError(true);
        setErrorMessage(
          "A pipeline error occurred. " +
            ev?.data?.error +
            " fatal:" +
            ev?.data?.fatal?.toString(),
        );
      }
      if (ev?.data?.type === "video_generation_error") {
        setHasError(true);
        setErrorMessage("A video generation error occurred.");
      }
      if (!isFinalUserTranscription(ev?.data)) {
        return;
      }

      const transcript = extractTranscriptText(ev?.data);
      // Ignore empty turns and the sidecar's own relay text when it comes back
      // through the hosted transcription stream.
      if (!transcript || consumePendingEcho(transcript)) {
        return;
      }

      handleBridgeResponse(transcript).catch((error) => {
        console.error("Error submitting Swiggy transcript", error);
      });
    }, [consumePendingEcho, handleBridgeResponse, setIsAgentReady]),
  );

  /**
   * Reset state so a new call can be created
   */
  const resetDailyState = useCallback(() => {
    /* Reset local hosted session state so the next join starts from a clean slate. */
    if (callObject) {
      try {
        const meetingState = callObject.meetingState();
        if (
          meetingState === "joined-meeting" ||
          meetingState === "joining-meeting"
        ) {
          // Force stop the Lemon Slice Agent instead of waiting for the idle timeout trigger
          sendAppMessage({ event: "force-end" }, "*");
        }
      } catch (error) {
        // If there is an error, we're not in a meeting, so skip sendAppMessage
      }
    }
    roomSessionRef.current = null;
    pendingEchoesRef.current.clear();
    setRoomSession(null);
    setIsAgentReady(false);
    setHasAgentJoinedRoom(false);
    setAppState(STATE_IDLE);
    setHasError(false);
  }, [callObject, sendAppMessage, setHasAgentJoinedRoom, setIsAgentReady]);

  /**
   * Reset state when the page is unloaded
   */
  useEffect(() => {
    /* Keep the hosted room from lingering if the browser tab is closed mid-call. */
    const handleBeforeUnload = () => {
      resetDailyState();
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      resetDailyState();
    };
  }, [resetDailyState]);

  /**
   * Call your API to create a Daily room
   * and then join that Daily room
   */
  const createCall = useCallback(() => {
    /* Create the LemonSlice room first, then join Daily with the returned token. */
    setAppState(STATE_JOINING);
    return api
      .createRoom()
      .then((room) => {
        setRoomSession(room);
        return callObject
          .join({
            url: room.room_url,
            token: room.token,
            audioSource: true,
            videoSource: false,
            startAudioOff: true,
          })
          .then(() => {
            // Agent has joined the call but has not sent down a/v yet
            setHasAgentJoinedRoom(true);
          });
      })
      .catch((error) => {
        console.error("Error creating or joining room", error);
        setRoomSession(null);
        setAppState(STATE_IDLE);
        setHasError(true);
        setErrorMessage("Error creating room");
      });
  }, [callObject, setHasAgentJoinedRoom]);

  /**
   * Leave the call and reset state
   */
  const leaveCall = useCallback(() => {
    /* Leave Daily and drop all sidecar bridge state for the current room. */
    resetDailyState();
    if (callObject && appState !== STATE_ERROR) {
      callObject.leave();
    }
  }, [appState, callObject, resetDailyState]);

  /**
   * Update app state based on reported meeting state changes.
   */
  useEffect(() => {
    /* Mirror Daily's meeting state into the local view state machine. */
    if (!meetingState) return;

    switch (meetingState) {
      case "joined-meeting":
        setAppState(STATE_JOINED);
        break;
      case "left-meeting":
        resetDailyState();
        break;
      case "error":
        setAppState(STATE_ERROR);
        setHasError(true);
        setErrorMessage("Daily call error");
        break;
      default:
        break;
    }
  }, [meetingState, resetDailyState]);

  const showCall = !hasError && [STATE_JOINED, STATE_ERROR].includes(appState);

  const renderLemonSliceAgentApp = () => {
    /* Render the join screen, active call, or error state from one state machine. */
    // If something goes wrong with creating the room.
    if (hasError) {
      return (
        <div className="flex min-h-screen w-full items-center justify-center p-4">
          <div className="bg-dark-blue box-border flex w-full max-w-[480px] flex-col rounded-lg p-12 text-center shadow-lg">
            <h1 className="text-turquoise m-0 mb-4 p-0 text-2xl font-semibold">
              Notification
            </h1>
            <p className="text-grey-light mb-6 text-base">{errorMessage}</p>
            <Tray leaveCall={leaveCall} />
          </div>
        </div>
      );
    }

    if (showCall) {
      return (
        <>
          <AgentCall />
          <Tray leaveCall={leaveCall} />
          <DailyAudio />
        </>
      );
    } else {
      return (
        <HomeScreen
          createCall={createCall}
          creatingRoom={appState === STATE_JOINING}
        />
      );
    }
  };

  return renderLemonSliceAgentApp();
}
