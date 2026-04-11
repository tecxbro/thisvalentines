/* Root app switch between hosted avatar mode and Swiggy text debug mode. */

import React, { useEffect, useRef } from "react";
import DailyIframe from "@daily-co/daily-js";
import { DailyProvider } from "@daily-co/daily-react";

import { AgentStateProvider } from "./providers/AgentStateProvider";
import LemonSliceAgentApp from "./components/LemonSliceAgentApp";
import SwiggyDebugHarness from "./components/SwiggyDebugHarness";

export default function App() {
  // Query-param debug mode bypasses Daily/LemonSlice entirely so the current
  // Swiggy sidecar can be exercised directly from a text-only UI.
  const debugMode =
    new URLSearchParams(window.location.search).get("debug") === "swiggy";
  const callObjectRef = useRef(null);

  /**
   * Create a barebones call object to use for the DailyProvider
   */
  if (!debugMode && !callObjectRef.current) {
    callObjectRef.current = DailyIframe.createCallObject({
      videoSource: false,
      audioSource: true,
    });
  }

  const callObject = callObjectRef.current;

  /**
   * Cleanup the call object when the component unmounts
   * This is important to prevent hanging calls
   */
  useEffect(() => {
    if (debugMode) {
      return undefined;
    }

    return () => {
      const callObj = callObjectRef.current;
      if (callObj) {
        try {
          // Leave any active calls first
          const meetingState = callObj.meetingState();
          if (
            meetingState === "joined-meeting" ||
            meetingState === "joining-meeting"
          ) {
            callObj.leave();
          }
        } catch (error) {
          console.error("Error leaving call object:", error);
        }

        // Destroy the call object
        try {
          callObj.destroy();
        } catch (error) {
          console.error("Error destroying call object:", error);
        } finally {
          callObjectRef.current = null;
        }
      }
    };
  }, [debugMode]);

  if (debugMode) {
    return (
      <div className="bg-darkest-blue min-h-screen w-full">
        <SwiggyDebugHarness />
      </div>
    );
  }

  const renderApp = () => {
    // The hosted runtime only needs Daily when the avatar experience is active.
    return (
      <DailyProvider callObject={callObject}>
        <AgentStateProvider>
          <LemonSliceAgentApp />
        </AgentStateProvider>
      </DailyProvider>
    );
  };

  return (
    <div className="bg-darkest-blue min-h-screen w-full">{renderApp()}</div>
  );
}
