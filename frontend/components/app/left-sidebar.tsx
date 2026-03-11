'use client';

import { Home, MessageCircle, Search } from 'lucide-react';
import type { AppView } from './app';

const NAV_ITEMS: { id: AppView; label: string; icon: typeof Home }[] = [
  { id: 'feed', label: 'Feed', icon: Home },
  { id: 'message', label: 'Chat', icon: MessageCircle },
  { id: 'search', label: 'Search', icon: Search },
];

export function LeftSidebar({
  currentView,
  onSelectView,
}: {
  currentView: AppView;
  onSelectView: (view: AppView) => void;
}) {
  return (
    <aside className="app-sidebar" aria-label="Main navigation">
      <div className="app-sidebar__logo" aria-hidden>
        Reels
      </div>
      <nav className="app-sidebar__nav" role="navigation">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`app-sidebar__item ${currentView === id ? 'app-sidebar__item--active' : ''}`}
            onClick={() => onSelectView(id)}
            aria-label={label}
            aria-current={currentView === id ? 'page' : undefined}
          >
            <Icon size={24} strokeWidth={2} aria-hidden />
          </button>
        ))}
      </nav>
    </aside>
  );
}
