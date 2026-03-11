'use client';

import {
  ImagePlus,
  Info,
  MessageCircle,
  Mic,
  Search,
  Send,
  Smile,
  Video,
} from 'lucide-react';
import { useCallback, useState } from 'react';
import type { AvatarItem } from '@/lib/types';

type PermissionState = 'pending' | 'granted' | 'denied';

type ThreadMessage = { role: 'user' | 'agent'; text: string };

const MOCK_LAST: Record<string, { text: string; time: string; unread?: boolean }> = {
  easy: { text: 'Thanks for connecting!', time: '2h', unread: true },
  medium: { text: 'Sent a message', time: '1d' },
  hard: { text: 'Got it.', time: '3d', unread: true },
};

const TABS = ['Primary', 'General', 'Requests'] as const;

export function MessageView({
  avatars,
  selectedAvatarId,
  permissionState,
  onCall,
  onOpenProfile,
}: {
  avatars: AvatarItem[];
  selectedAvatarId: string | null;
  permissionState: PermissionState;
  onCall: (avatarId: string) => void;
  onOpenProfile?: (avatarId: string) => void;
}) {
  const [threadAvatarId, setThreadAvatarId] = useState<string | null>(selectedAvatarId);
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('Primary');
  const [searchQuery, setSearchQuery] = useState('');
  const [threadMessages, setThreadMessages] = useState<Record<string, ThreadMessage[]>>({});
  const [inputValue, setInputValue] = useState('');
  const [sending, setSending] = useState(false);

  const threadAvatar = avatars.find((a) => a.avatar_id === threadAvatarId);
  const currentThread = threadAvatarId ? (threadMessages[threadAvatarId] ?? []) : [];

  const sendMessage = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || !threadAvatar) return;
    setInputValue('');
    setThreadMessages((prev) => ({
      ...prev,
      [threadAvatar.avatar_id]: [...(prev[threadAvatar.avatar_id] ?? []), { role: 'user', text }],
    }));
    setSending(true);
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          avatar_id: threadAvatar.avatar_id,
          message: text,
          thread_id: threadAvatar.avatar_id,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setThreadMessages((prev) => ({
          ...prev,
          [threadAvatar.avatar_id]: [
            ...(prev[threadAvatar.avatar_id] ?? []),
            { role: 'agent', text: `Error: ${(data as { detail?: string }).detail ?? res.statusText}` },
          ],
        }));
        return;
      }
      const data = (await res.json()) as { reply: string };
      setThreadMessages((prev) => ({
        ...prev,
        [threadAvatar.avatar_id]: [
          ...(prev[threadAvatar.avatar_id] ?? []),
          { role: 'agent', text: data.reply },
        ],
      }));
    } catch (err) {
      setThreadMessages((prev) => ({
        ...prev,
        [threadAvatar.avatar_id]: [
          ...(prev[threadAvatar.avatar_id] ?? []),
          { role: 'agent', text: `Failed to send: ${err instanceof Error ? err.message : 'Unknown error'}` },
        ],
      }));
    } finally {
      setSending(false);
    }
  }, [inputValue, threadAvatar]);
  const filteredAvatars = searchQuery.trim()
    ? avatars.filter(
        (a) =>
          a.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          a.avatar_id.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : avatars;

  return (
    <div className="message-view message-view--web">
      <div className="message-view__list-panel">
        <div className="message-view__tabs">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`message-view__tab ${activeTab === tab ? 'message-view__tab--active' : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="message-view__search-wrap">
          <Search size={18} strokeWidth={2} className="message-view__search-icon" aria-hidden />
          <input
            type="search"
            placeholder="Search"
            className="message-view__search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search conversations"
          />
        </div>
        <ul className="message-view__list">
          {filteredAvatars.map((avatar) => {
            const last = MOCK_LAST[avatar.avatar_id] ?? { text: 'No messages yet', time: '', unread: false };
            const isSelected = threadAvatarId === avatar.avatar_id;
            return (
              <li key={avatar.avatar_id}>
                <button
                  type="button"
                  className={`message-view__row ${isSelected ? 'message-view__row--selected' : ''}`}
                  onClick={() => setThreadAvatarId(avatar.avatar_id)}
                >
                  {avatar.preview_image_url ? (
                    <img src={avatar.preview_image_url} alt="" className="message-view__row-avatar" />
                  ) : (
                    <div className="message-view__row-avatar message-view__row-avatar--placeholder" aria-hidden>
                      {avatar.display_name?.charAt(0) ?? ''}
                    </div>
                  )}
                  <div className="message-view__row-main">
                    <span className="message-view__row-name">{avatar.display_name}</span>
                    <span className="message-view__row-preview">{last.text}</span>
                  </div>
                  {last.time && <span className="message-view__row-time">{last.time}</span>}
                  {last.unread && <span className="message-view__row-dot" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="message-view__thread-panel">
        {threadAvatar ? (
          <>
            <header className="message-view__thread-header">
              {threadAvatar.preview_image_url ? (
                <img
                  src={threadAvatar.preview_image_url}
                  alt=""
                  className="message-view__thread-header-avatar"
                />
              ) : (
                <div className="message-view__thread-header-avatar message-view__thread-header-avatar--placeholder" aria-hidden>
                  {threadAvatar.display_name?.charAt(0) ?? ''}
                </div>
              )}
              <div className="message-view__thread-header-info">
                <span className="message-view__thread-header-name">{threadAvatar.display_name}</span>
              </div>
              <button
                type="button"
                className="message-view__thread-header-btn"
                onClick={() => onOpenProfile?.(threadAvatar.avatar_id)}
              >
                View profile
              </button>
              <button type="button" className="message-view__thread-header-icon" title="Video call" onClick={() => onCall(threadAvatar.avatar_id)} disabled={permissionState !== 'granted'}>
                <Video size={20} strokeWidth={2} />
              </button>
              <button type="button" className="message-view__thread-header-icon" title="Info">
                <Info size={20} strokeWidth={2} />
              </button>
            </header>
            <div className="message-view__thread-messages">
              {currentThread.map((msg, i) => (
                <div
                  key={i}
                  className={`message-view__bubble message-view__bubble--${msg.role}`}
                >
                  {msg.text}
                </div>
              ))}
              {sending && (
                <div className="message-view__bubble message-view__bubble--agent">
                  …
                </div>
              )}
            </div>
            <div className="message-view__input-bar">
              <button type="button" className="message-view__input-icon" aria-label="Emoji">
                <Smile size={22} strokeWidth={2} />
              </button>
              <input
                type="text"
                placeholder="Message..."
                className="message-view__input"
                aria-label="Message"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage();
                  }
                }}
                disabled={sending}
              />
              <button type="button" className="message-view__input-icon" aria-label="Attach">
                <ImagePlus size={22} strokeWidth={2} />
              </button>
              <button type="button" className="message-view__input-icon" aria-label="Voice">
                <Mic size={22} strokeWidth={2} />
              </button>
              <button
                type="button"
                className="message-view__input-icon message-view__input-send"
                aria-label="Send"
                onClick={() => void sendMessage()}
                disabled={sending || !inputValue.trim()}
              >
                <Send size={20} strokeWidth={2} />
              </button>
            </div>
          </>
        ) : (
          <div className="message-view__empty-state">
            <MessageCircle size={48} strokeWidth={1.5} className="message-view__empty-icon" />
            <p className="message-view__empty-text">Select a conversation</p>
          </div>
        )}
      </div>
    </div>
  );
}
