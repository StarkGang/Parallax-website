export default function SpeechBubble({ bubble, side, align }) {
  const text = bubble?.text || '';

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
    </div>
  );
}
