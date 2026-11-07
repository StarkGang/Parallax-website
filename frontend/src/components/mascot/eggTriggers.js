/**
 * Playful triggers for the guide.
 *
 * Three ways to make it say something it was not asked to say:
 *   - type "midhun" anywhere outside a field
 *   - press ← ← → →
 *   - swipe left, left, right, right on touch
 *
 * Detection is passive: nothing is prevented, no keys are captured.
 */
const WORD = 'midhun';
const ARROW_SEQUENCE = ['ArrowLeft', 'ArrowLeft', 'ArrowRight', 'ArrowRight'];
const SWIPE_SEQUENCE = ['left', 'left', 'right', 'right'];
const SWIPE_MIN_DX = 70;
const SWIPE_MIN_RATIO = 1.4;

function isTypingField(target) {
  if (!target || !(target instanceof Element)) return false;
  if (target.isContentEditable) return true;
  return /^(input|textarea|select)$/i.test(target.tagName);
}

const matches = (sequence, expected) => sequence.join('|') === expected.join('|');

export function attachEggTriggers(onTrigger, { cooldownMs = 2500 } = {}) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => {};

  let wordBuffer = '';
  let keySequence = [];
  let swipeSequence = [];
  let touchStart = null;
  let lastFiredAt = 0;

  const fire = (reason) => {
    const now = Date.now();
    if (now - lastFiredAt < cooldownMs) return;
    lastFiredAt = now;
    onTrigger?.(reason);
  };

  const onKeyDown = (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (isTypingField(event.target)) return;

    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      keySequence = [...keySequence, event.key].slice(-ARROW_SEQUENCE.length);
      if (matches(keySequence, ARROW_SEQUENCE)) {
        keySequence = [];
        fire('keys');
      }
      return;
    }

    const char = event.key.length === 1 ? event.key.toLowerCase() : '';
    if (!char) return;

    wordBuffer = `${wordBuffer}${char}`.slice(-WORD.length);
    if (wordBuffer === WORD) {
      wordBuffer = '';
      fire('typed');
    }
  };

  const onTouchStart = (event) => {
    const touch = event.touches?.[0];
    if (!touch) return;
    touchStart = { x: touch.clientX, y: touch.clientY };
  };

  const onTouchEnd = (event) => {
    if (!touchStart) return;
    const touch = event.changedTouches?.[0];
    const start = touchStart;
    touchStart = null;
    if (!touch) return;

    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) < SWIPE_MIN_DX) return;
    if (Math.abs(dx) < Math.abs(dy) * SWIPE_MIN_RATIO) return;

    const direction = dx < 0 ? 'left' : 'right';
    swipeSequence = [...swipeSequence, direction].slice(-SWIPE_SEQUENCE.length);
    if (matches(swipeSequence, SWIPE_SEQUENCE)) {
      swipeSequence = [];
      fire('swipe');
    }
  };

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('touchstart', onTouchStart, { passive: true });
  window.addEventListener('touchend', onTouchEnd, { passive: true });

  return () => {
    window.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('touchstart', onTouchStart);
    window.removeEventListener('touchend', onTouchEnd);
  };
}
