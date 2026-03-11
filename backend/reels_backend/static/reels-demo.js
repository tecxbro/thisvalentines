import { Room, RoomEvent, Track } from "https://cdn.jsdelivr.net/npm/livekit-client@2.15.7/dist/livekit-client.esm.mjs";

const displayNameEl = document.getElementById("displayName");
const avatarIdEl = document.getElementById("avatarId");
const indexLabelEl = document.getElementById("indexLabel");
const statusEl = document.getElementById("status");
const stageEl = document.getElementById("stage");
const idleCtaEl = document.getElementById("idleCta");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");
const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");

const state = {
  avatars: [],
  index: 0,
  room: null,
  connected: false,
  wheelAt: 0,
  idleTimer: null,
};

function setStatus(message) {
  statusEl.textContent = message;
}

function currentAvatar() {
  return state.avatars[state.index];
}

function showIdleCta(message) {
  idleCtaEl.textContent = message;
  idleCtaEl.style.display = "block";
  if (state.idleTimer) {
    clearTimeout(state.idleTimer);
  }
  state.idleTimer = setTimeout(() => {
    idleCtaEl.style.display = "none";
  }, 4500);
}

function renderCard() {
  if (!state.avatars.length) {
    displayNameEl.textContent = "No avatars";
    avatarIdEl.textContent = "-";
    indexLabelEl.textContent = "0 / 0";
    return;
  }

  const avatar = currentAvatar();
  displayNameEl.textContent = avatar.display_name;
  avatarIdEl.textContent = avatar.avatar_id;
  indexLabelEl.textContent = `${state.index + 1} / ${state.avatars.length}`;
  stageEl.querySelectorAll("img,video,audio,.stage-placeholder").forEach((el) => el.remove());

  if (avatar.preview_image_url) {
    const img = document.createElement("img");
    img.src = avatar.preview_image_url;
    img.alt = avatar.display_name;
    stageEl.insertBefore(img, idleCtaEl);
  } else {
    const placeholder = document.createElement("div");
    placeholder.className = "stage-placeholder";
    placeholder.textContent = (avatar.display_name || avatar.avatar_id || "?").charAt(0).toUpperCase();
    placeholder.setAttribute("aria-hidden", "true");
    stageEl.insertBefore(placeholder, idleCtaEl);
  }
}

function clampIndex(value) {
  if (value < 0) return state.avatars.length - 1;
  if (value >= state.avatars.length) return 0;
  return value;
}

async function disconnectRoom() {
  if (!state.room) return;
  try {
    state.room.disconnect();
  } catch (_error) {
    // best-effort disconnect
  }
  state.room = null;
  state.connected = false;
  stageEl.querySelectorAll("video,audio").forEach((el) => el.remove());
}

function attachTrack(track) {
  const el = track.attach();
  if (track.kind === Track.Kind.Video) {
    stageEl.querySelectorAll("video").forEach((node) => node.remove());
    stageEl.insertBefore(el, idleCtaEl);
  } else if (track.kind === Track.Kind.Audio) {
    el.autoplay = true;
    el.style.display = "none";
    stageEl.appendChild(el);
  }
}

function wireRoomEvents(room) {
  room.on(RoomEvent.TrackSubscribed, (track) => {
    attachTrack(track);
    if (track.kind === Track.Kind.Video) {
      setStatus(`Connected: video track subscribed for ${currentAvatar().display_name}`);
    }
  });

  room.on(RoomEvent.TrackUnsubscribed, (track) => {
    track.detach().forEach((el) => el.remove());
  });

  room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
    if (topic !== "reels.events") return;
    try {
      const decoded = new TextDecoder().decode(payload);
      const event = JSON.parse(decoded);
      if (event.type === "reels.idle_suggest_next") {
        showIdleCta(`No speech for ${event.idle_seconds}s. Swipe to next reel.`);
      }
    } catch (_error) {
      // ignore invalid event payloads
    }
  });

  room.on(RoomEvent.Disconnected, () => {
    state.connected = false;
    setStatus("Disconnected");
  });
}

async function connectCurrentAvatar() {
  const avatar = currentAvatar();
  if (!avatar) return;

  await disconnectRoom();
  setStatus(`Requesting token for ${avatar.display_name}...`);

  const tokenRes = await fetch("/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ avatar_id: avatar.avatar_id }),
  });
  if (!tokenRes.ok) {
    const text = await tokenRes.text();
    throw new Error(`Token request failed (${tokenRes.status}): ${text}`);
  }

  const conn = await tokenRes.json();
  const room = new Room({
    adaptiveStream: true,
    dynacast: true,
  });

  wireRoomEvents(room);
  await room.connect(conn.serverUrl, conn.participantToken);
  await room.localParticipant.setMicrophoneEnabled(true);

  state.room = room;
  state.connected = true;
  setStatus(`Live with ${avatar.display_name}. You can talk now.`);
}

async function move(delta) {
  if (!state.avatars.length) return;
  state.index = clampIndex(state.index + delta);
  renderCard();

  if (state.connected) {
    try {
      await connectCurrentAvatar();
    } catch (error) {
      setStatus(`Reconnect failed: ${error.message}`);
    }
  }
}

async function loadAvatars() {
  const res = await fetch("/avatars");
  if (!res.ok) {
    throw new Error(`Failed to load avatars (${res.status})`);
  }
  const payload = await res.json();
  state.avatars = (payload.avatars || []).filter((avatar) => avatar.is_active);
  if (!state.avatars.length) {
    throw new Error("No active avatars in registry");
  }
  renderCard();
  setStatus("Ready. Click Join & Talk.");
}

prevBtn.addEventListener("click", () => move(-1));
nextBtn.addEventListener("click", () => move(1));

connectBtn.addEventListener("click", async () => {
  try {
    await connectCurrentAvatar();
  } catch (error) {
    setStatus(`Connect failed: ${error.message}`);
  }
});

disconnectBtn.addEventListener("click", async () => {
  await disconnectRoom();
});

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown") {
    move(1);
  } else if (event.key === "ArrowUp") {
    move(-1);
  }
});

window.addEventListener("wheel", (event) => {
  const now = Date.now();
  if (now - state.wheelAt < 600) return;
  if (Math.abs(event.deltaY) < 40) return;
  state.wheelAt = now;
  move(event.deltaY > 0 ? 1 : -1);
});

loadAvatars().catch((error) => {
  setStatus(`Boot failed: ${error.message}`);
});
