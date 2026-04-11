/* Thin wrapper for Daily's remote video tile in the hosted call UI. */

import { DailyVideo } from "@daily-co/daily-react";

export default function AgentVideoTile({ id }) {
  /* Render the currently selected remote avatar participant video track. */
  return (
    <div className="relative h-[560px] w-[368px]">
      <DailyVideo sessionId={id} type="video" />
    </div>
  );
}
