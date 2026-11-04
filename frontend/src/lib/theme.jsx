import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Palette, Check, Sparkles, X } from 'lucide-react';

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

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}

export function ThemeCustomizer() {
  const { accent, setAccent, accents, currentTheme } = useTheme();
  const [open, setOpen] = useState(false);

  return (
    <aside className="theme-customizer-root" aria-label="Theme Customizer">
      {open ? (
        <div className="theme-customizer-popover rise" role="dialog" aria-label="Customize theme accent">
          <div className="theme-popover-head">
            <div className="theme-popover-title">
              <Sparkles size={14} className="accent-icon" />
              <span>Theme Customizer</span>
            </div>
            <button
              type="button"
              className="theme-popover-close"
              onClick={() => setOpen(false)}
              aria-label="Close customizer"
            >
              <X size={15} />
            </button>
          </div>

          <p className="theme-popover-sub">
            Customize the convention palette and QR code styling across all surfaces.
          </p>

          <div className="theme-palette-grid">
            {accents.map((item) => {
              const active = item.id === accent;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`theme-chip-btn ${active ? 'is-active' : ''}`}
                  onClick={() => setAccent(item.id)}
                  title={`${item.name} (${item.desc})`}
                >
                  <span
                    className="theme-color-swatch"
                    style={{ background: `linear-gradient(135deg, ${item.hex}, ${item.secondary})` }}
                  >
                    {active ? <Check size={12} color="#000" strokeWidth={3} /> : null}
                  </span>
                  <div className="theme-chip-text">
                    <b>{item.name}</b>
                    <small>{item.desc}</small>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="theme-popover-footer">
            <span className="theme-badge-preview" style={{ color: currentTheme.hex }}>
              Active: {currentTheme.name}
            </span>
            <button
              type="button"
              className="theme-reset-btn"
              onClick={() => setAccent('cyan')}
              disabled={accent === 'cyan'}
            >
              Reset to Cyan
            </button>
          </div>
        </div>
      ) : null}

      {/* Floating launcher trigger */}
      <button
        type="button"
        className={`theme-launcher-trigger ${open ? 'is-open' : ''}`}
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Open theme customizer"
        title="Customize convention theme & QR"
        style={{
          borderColor: currentTheme.hex,
          boxShadow: `0 16px 36px -10px rgba(0, 0, 0, 0.8), 0 0 18px -4px ${currentTheme.hex}55`,
        }}
      >
        <Palette size={16} style={{ color: currentTheme.hex }} />
        <span className="theme-trigger-label" style={{ color: '#f8fafc' }}>Theme</span>
      </button>
    </aside>
  );
}

