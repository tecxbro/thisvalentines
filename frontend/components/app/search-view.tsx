'use client';

import { Search } from 'lucide-react';
import { useState } from 'react';
import type { AvatarItem } from '@/lib/types';

export function SearchView({
  avatars,
  onSelectAvatar,
}: {
  avatars: AvatarItem[];
  onSelectAvatar: (avatarId: string) => void;
}) {
  const [query, setQuery] = useState('');

  const filtered = query.trim()
    ? avatars.filter(
        (a) =>
          a.display_name.toLowerCase().includes(query.toLowerCase()) ||
          a.avatar_id.toLowerCase().includes(query.toLowerCase())
      )
    : avatars;

  return (
    <div className="search-view search-view--web">
      <header className="search-view__header">
        <Search size={20} strokeWidth={2} className="search-view__input-icon" aria-hidden />
        <input
          type="search"
          placeholder="Search agents..."
          className="search-view__input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search"
        />
      </header>
      <ul className="search-view__list">
        {filtered.map((avatar) => (
          <li key={avatar.avatar_id}>
            <button
              type="button"
              className="search-view__row"
              onClick={() => onSelectAvatar(avatar.avatar_id)}
            >
              {avatar.preview_image_url ? (
                <img
                  src={avatar.preview_image_url}
                  alt=""
                  className="search-view__row-avatar"
                />
              ) : (
                <div className="search-view__row-avatar search-view__row-avatar--placeholder" aria-hidden>
                  {avatar.display_name?.charAt(0) ?? ''}
                </div>
              )}
              <span className="search-view__row-name">{avatar.display_name}</span>
            </button>
          </li>
        ))}
      </ul>
      {filtered.length === 0 && (
        <p className="search-view__empty">No agents match your search.</p>
      )}
    </div>
  );
}
