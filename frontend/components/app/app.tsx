'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track } from 'livekit-client';
import { FeedView } from '@/components/app/feed-view';
import { LeftSidebar } from '@/components/app/left-sidebar';
import { MessageView } from '@/components/app/message-view';
import { ProfileView } from '@/components/app/profile-view';
import { SearchView } from '@/components/app/search-view';
import type {
  AvatarItem,
  AvatarsResponse,
  ConnectionDetails,
  LiveKitConnectionDetails,
} from '@/lib/types';

type PermissionState = 'pending' | 'granted' | 'denied';
export type AppView = 'feed' | 'profile' | 'message' | 'search';

const MICROPHONE_CAPTURE_OPTIONS = {
  noiseSuppression: true,
  echoCancellation: true,
  autoGainControl: true,
  voiceIsolation: true,
  channelCount: 1,
} as const;

export function App() {
  return <AppContent />;
}

function AppContent() {
  const [currentView, setCurrentView] = useState<AppView>('feed');
  const [avatars, setAvatars] = useState<AvatarItem[]>([]);
  const [activeAvatarIndex, setActiveAvatarIndex] = useState(0);
  const [selectedAvatarId, setSelectedAvatarId] = useState<string | null>(null);
  const [permissionState, setPermissionState] = useState<PermissionState>('pending');
  const [error, setError] = useState<string | null>(null);
  const [hasRemoteVideo, setHasRemoteVideo] = useState(false);

  const videoContainerRef = useRef<HTMLDivElement>(null);
  const audioContainerRef = useRef<HTMLDivElement>(null);
  const initialConnectTriggeredRef = useRef(false);
  const wheelAtRef = useRef(0);
  const connectRequestSeqRef = useRef(0);

  const livekitRoomRef = useRef<Room | null>(null);
  const livekitCleanupRef = useRef<(() => void) | null>(null);

  const activeAvatar = avatars[activeAvatarIndex] ?? null;

  const clearVideoContainer = useCallback(() => {
    const container = videoContainerRef.current;
    if (!container) return;
    container.querySelectorAll('video').forEach((node) => node.remove());
    setHasRemoteVideo(false);
  }, []);

  const clearAudioContainer = useCallback(() => {
    const container = audioContainerRef.current;
    if (!container) return;
    container.querySelectorAll('audio').forEach((node) => node.remove());
  }, []);

  const attachLiveKitTrack = useCallback((track: Track) => {
    if (!videoContainerRef.current || track.kind !== Track.Kind.Video) return;

    const element = track.attach();
    element.setAttribute('playsinline', 'true');
    element.setAttribute('autoplay', 'true');
    element.className = 'remote-video';

    clearVideoContainer();
    videoContainerRef.current.appendChild(element);
    setHasRemoteVideo(true);
  }, [clearVideoContainer]);

  const attachLiveKitAudioTrack = useCallback((track: Track) => {
    if (!audioContainerRef.current || track.kind !== Track.Kind.Audio) return;

    const element = track.attach() as HTMLMediaElement;
    element.setAttribute('autoplay', 'true');
    element.muted = false;
    element.volume = 1;
    element.style.display = 'none';

    audioContainerRef.current.appendChild(element);
    void element.play().catch(() => {
      // browsers can block autoplay until user gesture
    });
  }, []);

  const disconnectActiveConnection = useCallback(async () => {
    if (livekitCleanupRef.current) {
      livekitCleanupRef.current();
      livekitCleanupRef.current = null;
    }

    const livekitRoom = livekitRoomRef.current;
    if (livekitRoom) {
      livekitRoomRef.current = null;
      try {
        await livekitRoom.disconnect();
      } catch {
        // keep disconnect best-effort
      }
    }

    clearVideoContainer();
    clearAudioContainer();
  }, [clearAudioContainer, clearVideoContainer]);

  useEffect(() => {
    return () => {
      void disconnectActiveConnection();
    };
  }, [disconnectActiveConnection]);

  const requestMicPermission = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: MICROPHONE_CAPTURE_OPTIONS,
      });
      stream.getTracks().forEach((track) => track.stop());
      setPermissionState('granted');
      console.log('[reels] microphone permission granted');
    } catch (err) {
      setPermissionState('denied');
      setError('Microphone permission is required to talk to avatars.');
      console.error('[reels] microphone permission denied', err);
    }
  }, []);

  const fetchConnectionDetails = useCallback(async (avatarId: string): Promise<ConnectionDetails> => {
    const res = await fetch('/api/connection-details', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ avatar_id: avatarId }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Connection endpoint failed (${res.status}): ${text}`);
    }

    const data = (await res.json()) as ConnectionDetails;
    if (typeof data.serverUrl !== 'string' || typeof data.participantToken !== 'string') {
      throw new Error('Invalid connection payload from backend');
    }

    return data;
  }, []);

  const connectLiveKit = useCallback(async (
    details: LiveKitConnectionDetails,
    avatarId: string,
    displayName: string,
    requestSeq: number
  ) => {
    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
    });

    const onConnected = () => {
      if (livekitRoomRef.current !== room) return;
      console.log('[reels] livekit connected', { room: room.name, avatarId });
    };

    const onDisconnected = () => {
      if (livekitRoomRef.current !== room) return;
      clearVideoContainer();
      clearAudioContainer();
      console.log('[reels] livekit disconnected');
    };

    const onTrackSubscribed = (
      track: Track,
      _publication: unknown,
      participant: { identity: string }
    ) => {
      if (livekitRoomRef.current !== room) return;
      console.log('[reels] livekit track subscribed', {
        kind: track.kind,
        participant: participant.identity,
      });
      if (track.kind === Track.Kind.Video) {
        attachLiveKitTrack(track);
      } else if (track.kind === Track.Kind.Audio) {
        attachLiveKitAudioTrack(track);
      }
    };

    const onTrackUnsubscribed = (track: Track) => {
      if (track.kind === Track.Kind.Video) {
        track.detach().forEach((el) => el.remove());
        clearVideoContainer();
      } else if (track.kind === Track.Kind.Audio) {
        track.detach().forEach((el) => el.remove());
      }
    };

    room.on(RoomEvent.Connected, onConnected);
    room.on(RoomEvent.Disconnected, onDisconnected);
    room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
    room.on(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);

    livekitCleanupRef.current = () => {
      room.off(RoomEvent.Connected, onConnected);
      room.off(RoomEvent.Disconnected, onDisconnected);
      room.off(RoomEvent.TrackSubscribed, onTrackSubscribed);
      room.off(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);
    };

    livekitRoomRef.current = room;
    await room.connect(details.serverUrl, details.participantToken);

    if (connectRequestSeqRef.current !== requestSeq) {
      await disconnectActiveConnection();
      return;
    }

    await room.localParticipant.setMicrophoneEnabled(true, MICROPHONE_CAPTURE_OPTIONS);

    setError(null);
    setSelectedAvatarId(avatarId);
  }, [
    attachLiveKitAudioTrack,
    attachLiveKitTrack,
    clearAudioContainer,
    clearVideoContainer,
    disconnectActiveConnection,
  ]);

  const connectToAvatarId = useCallback(async (avatarId: string) => {
    if (permissionState !== 'granted') return;

    const targetAvatar = avatars.find((item) => item.avatar_id === avatarId);
    if (!targetAvatar) {
      setError(`Unknown avatar: ${avatarId}`);
      return;
    }

    const requestSeq = connectRequestSeqRef.current + 1;
    connectRequestSeqRef.current = requestSeq;

    setError(null);
    setHasRemoteVideo(false);

    try {
      const details = await fetchConnectionDetails(avatarId);
      if (connectRequestSeqRef.current !== requestSeq) return;

      await disconnectActiveConnection();
      if (connectRequestSeqRef.current !== requestSeq) return;

      await connectLiveKit(details, avatarId, targetAvatar.display_name, requestSeq);
    } catch (err) {
      if (connectRequestSeqRef.current !== requestSeq) return;
      setError(err instanceof Error ? err.message : String(err));
      console.error('[reels] connect failed', err);
    }
  }, [
    avatars,
    permissionState,
    fetchConnectionDetails,
    disconnectActiveConnection,
    connectLiveKit,
  ]);

  const connectCurrentAvatar = useCallback(async () => {
    if (!activeAvatar) return;
    await connectToAvatarId(activeAvatar.avatar_id);
  }, [activeAvatar, connectToAvatarId]);

  const switchAvatar = useCallback(
    async (delta: number) => {
      if (!avatars.length) return;
      const nextIndex = (activeAvatarIndex + delta + avatars.length) % avatars.length;
      const nextAvatarId = avatars[nextIndex].avatar_id;
      setActiveAvatarIndex(nextIndex);
      setSelectedAvatarId(nextAvatarId);

      if (permissionState === 'granted') {
        await connectToAvatarId(nextAvatarId);
      }
    },
    [activeAvatarIndex, avatars, permissionState, connectToAvatarId]
  );

  useEffect(() => {
    async function loadAvatars() {
      try {
        const response = await fetch('/api/avatars', { cache: 'no-store' });
        if (!response.ok) {
          throw new Error(`Avatar fetch failed (${response.status})`);
        }

        const payload = (await response.json()) as AvatarsResponse;
        const active = (payload.avatars ?? []).filter((item) => item.is_active);
        if (!active.length) {
          throw new Error('No active avatars returned from backend');
        }

        setAvatars(active);
        setSelectedAvatarId(active[0].avatar_id);
        console.log('[reels] avatars loaded', active.map((item) => item.avatar_id));
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        console.error('[reels] failed loading avatars', err);
      }
    }

    void loadAvatars();
  }, []);

  useEffect(() => {
    void requestMicPermission();
  }, [requestMicPermission]);

  useEffect(() => {
    if (!activeAvatar || permissionState !== 'granted') return;
    if (initialConnectTriggeredRef.current) return;

    initialConnectTriggeredRef.current = true;
    void connectCurrentAvatar();
  }, [activeAvatar, permissionState, connectCurrentAvatar]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (currentView !== 'feed') return;
      if (event.key === 'ArrowDown') {
        void switchAvatar(1);
      } else if (event.key === 'ArrowUp') {
        void switchAvatar(-1);
      }
    };

    const onWheel = (event: WheelEvent) => {
      if (currentView !== 'feed') return;
      const now = Date.now();
      if (now - wheelAtRef.current < 500) return;
      if (Math.abs(event.deltaY) < 40) return;

      wheelAtRef.current = now;
      void switchAvatar(event.deltaY > 0 ? 1 : -1);
    };

    window.addEventListener('keydown', onKey);
    window.addEventListener('wheel', onWheel, { passive: true });

    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('wheel', onWheel);
    };
  }, [switchAvatar, currentView]);

  return (
    <div className="app-shell">
      <div ref={audioContainerRef} aria-hidden style={{ display: 'none' }} />
      <LeftSidebar currentView={currentView} onSelectView={setCurrentView} />
      <main className="app-main">
        {currentView === 'feed' && (
          <FeedView
            avatars={avatars}
            activeAvatarIndex={activeAvatarIndex}
            activeAvatar={activeAvatar}
            videoContainerRef={videoContainerRef}
            hasRemoteVideo={hasRemoteVideo}
            idleHint={null}
            permissionState={permissionState}
            error={error}
            requestMicPermission={requestMicPermission}
            switchAvatar={(delta: number) => {
              void switchAvatar(delta);
            }}
            connectToAvatarId={(avatarId: string) => {
              void connectToAvatarId(avatarId);
            }}
            onOpenProfile={(avatarId: string) => {
              setSelectedAvatarId(avatarId);
              setCurrentView('profile');
            }}
          />
        )}
        {currentView === 'profile' && (
          <ProfileView
            avatarId={selectedAvatarId}
            avatars={avatars}
            onBack={() => setCurrentView('feed')}
            onMessage={(avatarId: string) => {
              setSelectedAvatarId(avatarId);
              setCurrentView('message');
            }}
          />
        )}
        {currentView === 'message' && (
          <MessageView
            avatars={avatars}
            selectedAvatarId={selectedAvatarId}
            permissionState={permissionState}
            onCall={(avatarId: string) => {
              const idx = avatars.findIndex((a) => a.avatar_id === avatarId);
              if (idx >= 0) setActiveAvatarIndex(idx);
              setSelectedAvatarId(avatarId);
              setCurrentView('feed');
              setTimeout(() => {
                void connectToAvatarId(avatarId);
              }, 0);
            }}
            onOpenProfile={(avatarId: string) => {
              setSelectedAvatarId(avatarId);
              setCurrentView('profile');
            }}
          />
        )}
        {currentView === 'search' && (
          <SearchView
            avatars={avatars}
            onSelectAvatar={(id: string) => {
              setSelectedAvatarId(id);
              setCurrentView('profile');
            }}
          />
        )}
      </main>
    </div>
  );
}
