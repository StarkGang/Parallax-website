import { createContext, useEffect, useMemo, useState } from 'react';

export const THEME_ACCENTS = [
  { id: 'cyan', name: 'Cyber Cyan', hex: '#38bdf8', secondary: '#818cf8', desc: 'Default Parallax' },
  { id: 'violet', name: 'Neon Violet', hex: '#c084fc', secondary: '#a855f7', desc: 'Synthwave' },
  { id: 'amber', name: 'Solar Amber', hex: '#fbbf24', secondary: '#f59e0b', desc: 'High-voltage Gold' },
  { id: 'lime', name: 'Toxic Lime', hex: '#a3e635', secondary: '#4ade80', desc: 'Matrix Terminal' },
  { id: 'rose', name: 'Hyper Rose', hex: '#fb7185', secondary: '#f43f5e', desc: 'Laser Cyberpunk' },
  { id: 'ice', name: 'Arctic Frost', hex: '#7dd3fc', secondary: '#06b6d4', desc: 'Glacial Chill' },
];

const ThemeContext = createContext(null);

export function ThemeProvider({ children }) {
  const [accent, setAccentState] = useState(() => {
    try {
      return localStorage.getItem('px_theme_accent') || 'cyan';
    } catch {
      return 'cyan';
    }
  });

  const setAccent = (newAccent) => {
    setAccentState(newAccent);
    try {
      localStorage.setItem('px_theme_accent', newAccent);
    } catch {}
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-accent', accent);
  }, [accent]);

  const currentTheme = useMemo(() => {
    return THEME_ACCENTS.find((t) => t.id === accent) || THEME_ACCENTS[0];
  }, [accent]);

  const value = useMemo(
    () => ({
      accent,
      setAccent,
      currentTheme,
      accents: THEME_ACCENTS,
    }),
    [accent, currentTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

