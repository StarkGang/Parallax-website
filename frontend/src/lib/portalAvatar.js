import { useEffect, useState } from 'react';

// Selectable portal avatars: the 4 Fringe glyphs plus the copied character portraits.
export const PORTAL_AVATARS = [
  { id: 'butterfly', label: 'Butterfly', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-butterfly.png`, kind: 'glyph' },
  { id: 'frog', label: 'Frog (Φ)', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-frog.png`, kind: 'glyph' },
  { id: 'flower', label: 'Flower', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-flower.png`, kind: 'glyph' },
  { id: 'leaf', label: 'Leaf', src: `${import.meta.env.BASE_URL}images/glyphs/fringe-leaf.png`, kind: 'glyph' },
  { id: 'root', label: 'Root', src: `${import.meta.env.BASE_URL}images/root.jpg`, kind: 'portrait' },
  { id: 'lisbon', label: 'Lisbon', src: `${import.meta.env.BASE_URL}images/lisbon.jpg`, kind: 'portrait' },
  { id: 'parallax', label: 'Parallax', src: `${import.meta.env.BASE_URL}images/parallax.jpg`, kind: 'portrait' },
  { id: 'parallax-2', label: 'Parallax (Ω)', src: `${import.meta.env.BASE_URL}images/parallax-2.jpg`, kind: 'portrait' },
];

const DEFAULT_ROLE_AVATARS = {
  root: PORTAL_AVATARS[4],
  lisbon: PORTAL_AVATARS[5],
  parallax: PORTAL_AVATARS[6],
  'parallax-2': PORTAL_AVATARS[7],
};

export function getStoredAvatarId(userId, fallbackId = 'parallax') {
  try {
    const saved = localStorage.getItem(`px_portal_glyph_${userId || 'guest'}`);
    if (saved && PORTAL_AVATARS.some((item) => item.id === saved)) return saved;
  } catch {}
  return fallbackId;
}

export function usePortalAvatar(userId, fallbackId = 'parallax') {
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

  const avatar =
    PORTAL_AVATARS.find((item) => item.id === avatarId) ||
    DEFAULT_ROLE_AVATARS[avatarId] ||
    DEFAULT_ROLE_AVATARS.root;
  return [avatar, selectAvatar];
}
