export type AvatarItem = {
  avatar_id: string;
  display_name: string;
  preview_image_url?: string | null;
  profile_image_urls?: string[];
  caption?: string | null;
  is_active: boolean;
};

export type AvatarsResponse = {
  avatars: AvatarItem[];
};

export type LiveKitConnectionDetails = {
  provider?: 'livekit';
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
  participantIdentity?: string;
  expiresAt?: string;
};

export type ConnectionDetails = LiveKitConnectionDetails;
