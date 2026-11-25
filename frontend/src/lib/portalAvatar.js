import { useEffect, useState } from 'react';

export const PORTAL_AVATARS = [
  { id: 'butterfly', label: 'Butterfly', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-butterfly.png`, kind: 'glyph' },
  { id: 'frog', label: 'Frog (Φ)', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-frog.png`, kind: 'glyph' },
  { id: 'flower', label: 'Flower', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-flower.png`, kind: 'glyph' },
  { id: 'leaf', label: 'Leaf', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-leaf.png`, kind: 'glyph' },
  { id: 'root', label: 'Root', src: `${import.meta.env.BASE_URL}images/avatars/root.png`, kind: 'portrait' },
  { id: 'lisbon', label: 'Lisbon', src: `${import.meta.env.BASE_URL}images/avatars/lisbon.png`, kind: 'portrait' },
  { id: 'reese', label: 'Reese', src: `${import.meta.env.BASE_URL}images/avatars/reese.png`, kind: 'portrait' },
  { id: 'jane', label: 'Jane', src: `${import.meta.env.BASE_URL}images/avatars/jane.png`, kind: 'portrait' },
  { id: 'finch', label: 'Finch', src: `${import.meta.env.BASE_URL}images/avatars/finch.png`, kind: 'portrait' },
  { id: 'olivia', label: 'Olivia', src: `${import.meta.env.BASE_URL}images/avatars/olivia.png`, kind: 'portrait' },
  { id: 'lelouch', label: 'Lelouch', src: `${import.meta.env.BASE_URL}images/avatars/lelouch.png`, kind: 'portrait' },
];

export function getStoredAvatarId(userId, fallbackId = 'root') {
  try {
    const saved = localStorage.getItem(`px_portal_glyph_${userId || 'guest'}`);
    if (saved && PORTAL_AVATARS.some((item) => item.id === saved)) return saved;
  } catch {}
  return fallbackId;
}

export function usePortalAvatar(userId, fallbackId = 'root') {
  const [avatarId, setAvatarId] = useState(() => getStoredAvatarId(userId, fallbackId));

  useEffect(() => {
    const sync = () => setAvatarId(getStoredAvatarId(userId, fallbackId));
    sync();
    window.addEventListener('px-glyph-change', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('px-glyph-change', sync);
      window.removeEventListener('storage', sync);
    };
  }, [userId, fallbackId]);

  const selectAvatar = (nextId) => {
    try {
      localStorage.setItem(`px_portal_glyph_${userId || 'guest'}`, nextId);
    } catch {}
    setAvatarId(nextId);
    window.dispatchEvent(new Event('px-glyph-change'));
  };

  const avatar = PORTAL_AVATARS.find((item) => item.id === avatarId) || PORTAL_AVATARS[4];
  return [avatar, selectAvatar];
}

