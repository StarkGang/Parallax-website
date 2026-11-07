import { useCallback, useEffect, useRef, useState } from 'react';
import './MascotEasterEgg.css';

/**
 * Small, purely-for-fun replies. Tapping the mascot (or the guide character)
 * four times surfaces one at random; nothing here is tied to convention data.
 */
export const EASTER_EGGS = [
  {
    text: 'Made by Midhun K M. I just stand here and look deep.',
  },
  {
    text: 'Midhun K M built me. Say hi:',
    link: { href: 'https://midhunkm.pages.dev/', label: 'midhunkm.pages.dev' },
  },
  {
    text: 'Say hi to Starkgang on GitHub, he still owes me a commit.',
    link: { href: 'https://github.com/starkgang', label: 'github.com/starkgang' },
  },
  {
    text: 'Warner Stark? Been a while, tell hi from me, if you see him!',
  },
  {
    text: 'The Fringe series was great. Man, what a run that was.',
  },
  {
    text: 'I have walked this page more than you have. No complaints though.',
  },
  {
    text: 'If you find a bug, call it a feature with commitment issues.',
  },
  {
    text: 'I am a mascot, not a cashier, the pass price lives on the pass page.',
  },
];

export function pickEasterEgg() {
  return EASTER_EGGS[Math.floor(Math.random() * EASTER_EGGS.length)];
}

/** Fired by the global keyboard/swipe triggers; any egg surface listens for it. */
export const MASCOT_EGG_EVENT = 'parallax:mascot-egg';

/** Bubbles are plain text, so a link is spelled out for the guide to read. */
export function formatEggText(egg) {
  if (!egg) return '';
  return egg.link ? `${egg.text} ${egg.link.label}` : egg.text;
}

export function useMascotEasterEgg(tapsNeeded = 4) {
  const [message, setMessage] = useState(null);
  const taps = useRef(0);
  const timer = useRef(null);

  const onMascotTap = useCallback(() => {
    taps.current += 1;
    if (taps.current < tapsNeeded) return;
    taps.current = 0;

    setMessage(pickEasterEgg());
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setMessage(null), 8000);
  }, [tapsNeeded]);

  useEffect(() => {
    const onEgg = () => {
      setMessage(pickEasterEgg());
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setMessage(null), 8000);
    };

    window.addEventListener(MASCOT_EGG_EVENT, onEgg);
    return () => {
      window.removeEventListener(MASCOT_EGG_EVENT, onEgg);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  return { message, onMascotTap };
}

export function MascotEasterEggBubble({ message }) {
  if (!message) return null;

  return (
    <div className="mascot-egg" role="status" aria-live="polite">
      <span className="mascot-egg-kicker" aria-hidden="true">
        Easter egg
      </span>
      <span className="mascot-egg-text">
        {message.text}
        {message.link ? (
          <>
            {' '}
            <a
              className="mascot-egg-link"
              href={message.link.href}
              target="_blank"
              rel="noreferrer"
            >
              {message.link.label}
            </a>
          </>
        ) : null}
      </span>
    </div>
  );
}
