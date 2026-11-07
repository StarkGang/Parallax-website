export default function SpeechBubble({ bubble, side, align }) {
  const text = bubble?.text || '';
  const link = bubble?.link;

  return (
    <div
      className={`mascot-bubble is-${side} align-${align}${text ? ' is-visible' : ''}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="mascot-bubble-kicker" aria-hidden="true">
        Parallax guide
      </span>
      <span className="mascot-bubble-text">{text}</span>
      {text && link ? (
        <a className="mascot-bubble-link" href={link.href} target="_blank" rel="noreferrer">
          {link.label}
        </a>
      ) : null}
    </div>
  );
}
