'use client';

import { Image, User } from 'lucide-react';
import type { AvatarItem } from '@/lib/types';

const PROFILE_GRID_SLOTS = 9;
const PROFILE_GRID_COLUMNS = 3;

const MOCK_STATS: Record<string, { posts: number; followers: number; following: number }> = {
  easy: { posts: 12, followers: 340, following: 28 },
  medium: { posts: 8, followers: 210, following: 15 },
  hard: { posts: 24, followers: 520, following: 42 },
};

const MOCK_BIO: Record<string, string> = {
  easy: 'Here to support and encourage. Ask me anything — I keep it warm and real.',
  medium: 'Analytical and fair. I ask precise questions and keep conversations clear.',
  hard: 'Direct and efficient. No fluff — we get to the point.',
};

export function ProfileView({
  avatarId,
  avatars,
  onBack,
  onMessage,
}: {
  avatarId: string | null;
  avatars: AvatarItem[];
  onBack: () => void;
  onMessage: (avatarId: string) => void;
}) {
  const avatar = avatars.find((a) => a.avatar_id === avatarId) ?? avatars[0];
  if (!avatar) {
    return (
      <div className="profile-view profile-view--web">
        <div className="profile-view__empty-state">
          <User size={48} strokeWidth={1.5} className="profile-view__empty-icon" />
          <p className="profile-view__empty">No profile</p>
        </div>
      </div>
    );
  }

  const stats = MOCK_STATS[avatar.avatar_id] ?? { posts: 0, followers: 0, following: 0 };
  const bio = MOCK_BIO[avatar.avatar_id] ?? `Meet ${avatar.display_name}.`;

  return (
    <div className="profile-view profile-view--web">
      <div className="profile-view__body">
        <div className="profile-view__top">
          {avatar.preview_image_url ? (
            <img
              src={avatar.preview_image_url}
              alt=""
              className="profile-view__avatar"
            />
          ) : (
            <div className="profile-view__avatar profile-view__avatar--placeholder" aria-hidden>
              {avatar.display_name?.charAt(0) ?? ''}
            </div>
          )}
          <div className="profile-view__meta">
            <h1 className="profile-view__handle">{avatar.display_name}</h1>
            <div className="profile-view__stats">
              <div className="profile-view__stat">
                <strong>{stats.posts}</strong>
                <span>posts</span>
              </div>
              <div className="profile-view__stat">
                <strong>{stats.followers}</strong>
                <span>followers</span>
              </div>
              <div className="profile-view__stat">
                <strong>{stats.following}</strong>
                <span>following</span>
              </div>
            </div>
            <p className="profile-view__bio">{bio}</p>
            <div className="profile-view__actions">
              <button type="button" className="profile-view__btn profile-view__btn--follow">
                Follow
              </button>
              <button
                type="button"
                className="profile-view__btn profile-view__btn--message"
                onClick={() => onMessage(avatar.avatar_id)}
              >
                Message
              </button>
            </div>
          </div>
        </div>

        <div className="profile-view__grid" style={{ display: 'grid', gridTemplateColumns: `repeat(${PROFILE_GRID_COLUMNS}, 1fr)`, gap: 4 }}>
          {Array.from({ length: PROFILE_GRID_SLOTS }, (_, i) => {
            const url = (avatar.profile_image_urls ?? [])[i];
            return (
              <div key={i} className="profile-view__grid-slot" style={{ aspectRatio: '1', background: 'var(--surface)', borderRadius: 8, overflow: 'hidden' }}>
                {url ? (
                  <img src={url} alt="" className="profile-view__grid-img" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <div className="profile-view__grid-placeholder" style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed var(--border)', color: 'var(--muted)' }}>
                    <Image size={28} strokeWidth={1.5} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
