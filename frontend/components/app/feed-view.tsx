'use client';

import {
  ChevronDown,
  ChevronUp,
  Heart,
  MessageCircle,
  Phone,
  Send,
} from 'lucide-react';
import type { RefObject } from 'react';
import type { AvatarItem } from '@/lib/types';

type PermissionState = 'pending' | 'granted' | 'denied';

function getCaption(avatar: AvatarItem): string {
  return avatar.caption ?? `${avatar.display_name} — tap Call to connect.`;
}

const ICON_SIZE = 24;
const STROKE = 2;

export function FeedView({
  avatars,
  activeAvatarIndex,
  activeAvatar,
  videoContainerRef,
  hasRemoteVideo,
  idleHint,
  permissionState,
  error,
  requestMicPermission,
  switchAvatar,
  connectToAvatarId,
  onOpenProfile,
}: {
  avatars: AvatarItem[];
  activeAvatarIndex: number;
  activeAvatar: AvatarItem | null;
  videoContainerRef: RefObject<HTMLDivElement | null>;
  hasRemoteVideo: boolean;
  idleHint: string | null;
  permissionState: PermissionState;
  error: string | null;
  requestMicPermission: () => void;
  switchAvatar: (delta: number) => void;
  connectToAvatarId: (avatarId: string) => void;
  onOpenProfile: (avatarId: string) => void;
}) {
  return (
    <section className="feed-view feed-view--web">
      <div className="feed-view__center">
        <div className="feed-view__stage" ref={videoContainerRef}>
          {!hasRemoteVideo && activeAvatar && (activeAvatar?.preview_image_url ? (
            <img
              src={activeAvatar.preview_image_url}
              alt={activeAvatar.display_name}
              className="feed-view__preview preview-image"
            />
          ) : null)}
          {idleHint && <div className="idle-hint">{idleHint}</div>}

          <div className="feed-view__overlay feed-view__overlay--left">
            <button
              type="button"
              className="feed-view__profile-row"
              onClick={() => activeAvatar && onOpenProfile(activeAvatar.avatar_id)}
            >
              {activeAvatar?.preview_image_url ? (
                <img
                  src={activeAvatar.preview_image_url}
                  alt=""
                  className="feed-view__avatar-thumb"
                />
              ) : (
                <div className="feed-view__avatar-thumb feed-view__avatar-thumb--placeholder" aria-hidden>
                  {activeAvatar?.display_name?.charAt(0) ?? ''}
                </div>
              )}
              <span className="feed-view__username">{activeAvatar?.display_name ?? ''}</span>
              <span className="feed-view__follow-btn">Follow</span>
            </button>
            <p className="feed-view__caption">
              {activeAvatar ? getCaption(activeAvatar) : ''}
            </p>
          </div>
        </div>
      </div>

      <div className="feed-view__rail">
        <button type="button" className="feed-view__rail-nav" onClick={() => switchAvatar(-1)} aria-label="Previous reel">
          <ChevronUp size={ICON_SIZE} strokeWidth={STROKE} />
        </button>
        <button type="button" className="feed-view__action">
          <Heart size={ICON_SIZE} strokeWidth={STROKE} />
          <span className="feed-view__action-count">0</span>
        </button>
        <button type="button" className="feed-view__action">
          <MessageCircle size={ICON_SIZE} strokeWidth={STROKE} />
          <span className="feed-view__action-count">0</span>
        </button>
        <button type="button" className="feed-view__action">
          <Send size={ICON_SIZE} strokeWidth={STROKE} />
        </button>
        <button
          type="button"
          className="feed-view__action feed-view__action--call"
          onClick={() => activeAvatar && connectToAvatarId(activeAvatar.avatar_id)}
          disabled={permissionState !== 'granted'}
          title="Call"
        >
          <Phone size={ICON_SIZE} strokeWidth={STROKE} />
          <span className="feed-view__action-label">Call</span>
        </button>
        <button type="button" className="feed-view__rail-nav" onClick={() => switchAvatar(1)} aria-label="Next reel">
          <ChevronDown size={ICON_SIZE} strokeWidth={STROKE} />
        </button>
      </div>

      {permissionState === 'denied' && (
        <div className="feed-view__mic">
          <button type="button" className="feed-view__mic-btn" onClick={() => requestMicPermission()}>
            Allow microphone to call
          </button>
        </div>
      )}
      {error && <div className="error feed-view__error">{error}</div>}
    </section>
  );
}
