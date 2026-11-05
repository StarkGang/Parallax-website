const TARGET_SELECTOR = '[data-mascot-target]';
const INTERACTIVE_SELECTOR =
  'a[href], button, input, select, textarea, [role="button"], [contenteditable="true"], [data-mascot-protect]';
const TEXT_SELECTOR =
  'h1, h2, h3, h4, h5, h6, p, li, label, legend, blockquote, figcaption, td, th';
const SAFE_TOP = 96;
const EDGE = 14;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function overlaps(a, b, pad = 0) {
  return (
    a.left < b.right + pad &&
    a.right > b.left - pad &&
    a.top < b.bottom + pad &&
    a.bottom > b.top - pad
  );
}

function inViewport(rect, viewport) {
  return rect.bottom > 0 && rect.top < viewport.h && rect.right > 0 && rect.left < viewport.w;
}

/**
 * Tracks every [data-mascot-target] on the page. Positions are measured, never
 * hardcoded, so layout changes cannot break the mascot.
 */
export class TargetRegistry {
  constructor({ onChange, onHover } = {}) {
    this.onChange = onChange;
    this.onHover = onHover;
    this.targets = new Map();
    this.byElement = new Map();
    this.io = null;
    this.ro = null;
    this.mo = null;
    this.scrollRaf = 0;
    this.notifyTimer = null;
    this.scanTimer = null;
    this.started = false;
    this._handlers = {};
    this._obstacleCache = null;
    this._obstacleKey = '';
    this._obstacleAt = 0;
  }

  start() {
    if (this.started || typeof window === 'undefined') return;
    this.started = true;

    this.io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const target = this.byElement.get(entry.target);
          if (target) target.intersecting = entry.isIntersecting;
        }
        this.scheduleMeasure();
      },
      { rootMargin: '-84px 0px -36px 0px', threshold: [0, 0.1, 0.5] },
    );

    this.ro = new ResizeObserver(() => this.scheduleMeasure());
    this.mo = new MutationObserver(() => this.scheduleScan());
    this.mo.observe(document.body, { childList: true, subtree: true });

    this._handlers.onScroll = () => this.scheduleMeasure();
    this._handlers.onResize = () => this.scheduleScan();

    window.addEventListener('scroll', this._handlers.onScroll, { passive: true, capture: true });
    window.addEventListener('resize', this._handlers.onResize);
    window.visualViewport?.addEventListener('resize', this._handlers.onResize);

    this.scan();
  }

  scan() {
    if (!this.started) return;
    document.querySelectorAll(TARGET_SELECTOR).forEach((element) => {
      if (!element.closest('.mascot-layer')) this.track(element);
    });

    for (const [element, target] of this.byElement) {
      if (!element.isConnected) this.untrack(target);
    }

    this._obstacleCache = null;
    this.measure(true);
  }

  track(element) {
    if (this.byElement.has(element)) return;
    const id = element.getAttribute('data-mascot-target');
    if (!id) return;

    const target = {
      id,
      el: element,
      intersecting: true,
      rect: null,
      visible: false,
      message: element.getAttribute('data-mascot-message') || '',
      action: element.getAttribute('data-mascot-action') || 'point',
      label: element.getAttribute('data-mascot-label') || '',
      hover: element.getAttribute('data-mascot-hover') || '',
      featured: element.getAttribute('data-mascot-featured') === 'true',
      priority: Number(element.getAttribute('data-mascot-priority') || 2),
    };

    // Hovering a target is a direct question; the brain answers it in the bubble
    // and pauses any running tour until the pointer leaves.
    target._onEnter = () => this.onHover?.('enter', target);
    target._onLeave = () => this.onHover?.('leave', target);
    element.addEventListener('pointerenter', target._onEnter);
    element.addEventListener('pointerleave', target._onLeave);

    this.byElement.set(element, target);
    this.targets.set(id, target);
    this.io?.observe(element);
    this.ro?.observe(element);
  }

  untrack(target) {
    this.targets.delete(target.id);
    this.byElement.delete(target.el);
    this.io?.unobserve(target.el);
    this.ro?.unobserve(target.el);
    if (target._onEnter) target.el.removeEventListener('pointerenter', target._onEnter);
    if (target._onLeave) target.el.removeEventListener('pointerleave', target._onLeave);
  }

  scheduleScan() {
    clearTimeout(this.scanTimer);
    this.scanTimer = setTimeout(() => {
      this.scanTimer = null;
      this.scan();
    }, 220);
  }

  scheduleMeasure() {
    if (this.scrollRaf) return;
    this.scrollRaf = requestAnimationFrame(() => {
      this.scrollRaf = 0;
      this.measure(true);
    });
  }

  measure(notify = false) {
    if (typeof window === 'undefined') return;
    const viewport = { w: window.innerWidth, h: window.innerHeight };

    for (const target of this.targets.values()) {
      if (!target.el.isConnected) continue;
      const rect = target.el.getBoundingClientRect();
      target.rect = {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      };
      target.visible =
        target.intersecting &&
        rect.width > 1 &&
        rect.height > 1 &&
        rect.bottom > SAFE_TOP &&
        rect.top < viewport.h - 12 &&
        rect.right > 8 &&
        rect.left < viewport.w - 8;
    }

    if (notify) this.scheduleNotify();
  }

  scheduleNotify() {
    if (this.notifyTimer) return;
    this.notifyTimer = setTimeout(() => {
      this.notifyTimer = null;
      this.onChange?.();
    }, 140);
  }

  refresh() {
    this.scan();
  }

  getTarget(id) {
    const target = this.targets.get(id);
    if (!target || !target.el.isConnected) return null;
    return target;
  }

  getGroup(prefix) {
    return [...this.targets.values()].filter(
      (target) => target.el.isConnected && target.id.startsWith(prefix),
    );
  }

  getObstacles(viewport) {
    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const key = `${viewport.w}x${viewport.h}:${Math.round(window.scrollX)}:${Math.round(window.scrollY)}`;
    if (this._obstacleCache && this._obstacleKey === key && now - this._obstacleAt < 200) {
      return this._obstacleCache;
    }

    const rects = [];
    document.querySelectorAll(`${INTERACTIVE_SELECTOR}, ${TEXT_SELECTOR}`).forEach((element) => {
      if (element.closest('.mascot-layer') || element.closest('[aria-hidden="true"]')) return;
      if (element.classList.contains('skip')) return;

      // Text inside a target belongs to the target's own card; the target rect
      // is already rejected as a whole. All other page copy is protected.
      if (element.matches(TEXT_SELECTOR) && element.closest(TARGET_SELECTOR)) return;

      const rect = element.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;
      if (!inViewport(rect, viewport)) return;
      rects.push(rect);
    });

    this._obstacleCache = rects;
    this._obstacleKey = key;
    this._obstacleAt = now;
    return rects;
  }

  findSafeSpot(target, size, viewport) {
    if (!target?.el?.isConnected) return null;
    const rect = target.el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return null;

    const obstacles = this.getObstacles(viewport);
    const gap = 18;
    const centeredY = rect.top + rect.height * 0.5 - size.h * 0.42;
    const candidates = [
      { side: 'right', x: rect.right + gap, y: centeredY },
      { side: 'left', x: rect.left - size.w - gap, y: centeredY },
      { side: 'right', x: rect.right + gap, y: rect.top },
      { side: 'left', x: rect.left - size.w - gap, y: rect.top },
      { side: 'right', x: rect.right + gap, y: rect.bottom - size.h },
      { side: 'left', x: rect.left - size.w - gap, y: rect.bottom - size.h },
      { side: 'above', x: rect.left + rect.width / 2 - size.w / 2, y: rect.top - size.h - gap },
      { side: 'below', x: rect.left + rect.width / 2 - size.w / 2, y: rect.bottom + gap },
      { side: 'margin-left', x: EDGE, y: centeredY },
      { side: 'margin-right', x: viewport.w - size.w - EDGE, y: centeredY },
      { side: 'margin-left', x: EDGE, y: rect.top },
      { side: 'margin-right', x: viewport.w - size.w - EDGE, y: rect.top },
    ];

    let best = null;
    for (const candidate of candidates) {
      const x = clamp(candidate.x, EDGE, viewport.w - size.w - EDGE);
      const y = clamp(candidate.y, SAFE_TOP, viewport.h - size.h - EDGE);
      const box = { left: x, top: y, right: x + size.w, bottom: y + size.h };

      if (box.left < EDGE - 1 || box.top < SAFE_TOP - 1) continue;
      if (box.right > viewport.w - EDGE + 1 || box.bottom > viewport.h - EDGE + 1) continue;
      if (overlaps(box, rect, 18)) continue;
      if (obstacles.some((obstacle) => overlaps(box, obstacle, 4))) continue;

      const centerX = box.left + size.w / 2;
      const centerY = box.top + size.h / 2;
      const targetX = rect.left + rect.width / 2;
      const targetY = rect.top + rect.height / 2;
      let score = Math.hypot(centerX - targetX, centerY - targetY);
      if (candidate.side === 'above' || candidate.side === 'below') score += 28;
      if (candidate.side === 'left' || candidate.side === 'right') score -= 8;
      if (candidate.side.startsWith('margin')) score += 220;

      if (!best || score < best.score) best = { x, y, side: candidate.side, score };
    }

    return best;
  }

  findRestSpot(size, viewport) {
    const obstacles = this.getObstacles(viewport);
    const candidates = [
      { x: EDGE, y: viewport.h - size.h - 16 },
      { x: viewport.w - size.w - EDGE, y: viewport.h - size.h - 16 },
      { x: 20, y: viewport.h - size.h - 16 },
      { x: viewport.w - size.w - 20, y: viewport.h - size.h - 16 },
      { x: 20, y: Math.max(SAFE_TOP, viewport.h - size.h - 108) },
      { x: viewport.w - size.w - 20, y: Math.max(SAFE_TOP, viewport.h - size.h - 108) },
      { x: 20, y: Math.max(SAFE_TOP, viewport.h * 0.52 - size.h / 2) },
    ];

    for (const candidate of candidates) {
      const x = clamp(candidate.x, EDGE, viewport.w - size.w - EDGE);
      const y = clamp(candidate.y, SAFE_TOP, viewport.h - size.h - EDGE);
      const box = { left: x, top: y, right: x + size.w, bottom: y + size.h };
      if (obstacles.some((obstacle) => overlaps(box, obstacle, 6))) continue;
      return { x, y };
    }

    return {
      x: clamp(candidates[0].x, EDGE, viewport.w - size.w - EDGE),
      y: clamp(candidates[0].y, SAFE_TOP, viewport.h - size.h - EDGE),
    };
  }

  /**
   * Interactive controls only. A roaming mascot may float over decorative
   * copy, but it must never sit on a link, button or field.
   */
  getInteractiveObstacles(viewport) {
    const rects = [];
    document.querySelectorAll(INTERACTIVE_SELECTOR).forEach((element) => {
      if (element.closest('.mascot-layer') || element.closest('[aria-hidden="true"]')) return;
      const rect = element.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;
      if (!inViewport(rect, viewport)) return;
      rects.push(rect);
    });
    return rects;
  }

  isPoseUsable(
    pose,
    size,
    viewport = { w: window.innerWidth, h: window.innerHeight },
    strict = true,
  ) {
    const box = { left: pose.x, top: pose.y, right: pose.x + size.w, bottom: pose.y + size.h };
    if (
      box.left < EDGE ||
      box.top < SAFE_TOP ||
      box.right > viewport.w - EDGE ||
      box.bottom > viewport.h - EDGE
    ) {
      return false;
    }
    if (!strict) return true;
    return !this.getInteractiveObstacles(viewport).some((rect) => overlaps(box, rect, 6));
  }

  isPoseSafe(pose, size) {
    if (typeof window === 'undefined') return true;
    const viewport = { w: window.innerWidth, h: window.innerHeight };
    const box = { left: pose.x, top: pose.y, right: pose.x + size.w, bottom: pose.y + size.h };
    if (
      box.left < EDGE ||
      box.top < SAFE_TOP ||
      box.right > viewport.w - EDGE ||
      box.bottom > viewport.h - EDGE
    ) {
      return false;
    }
    return !this.getObstacles(viewport).some((obstacle) => overlaps(box, obstacle, 6));
  }

  destroy() {
    this.started = false;
    this.io?.disconnect();
    this.ro?.disconnect();
    this.mo?.disconnect();
    if (this._handlers.onScroll) {
      window.removeEventListener('scroll', this._handlers.onScroll, { capture: true });
    }
    if (this._handlers.onResize) {
      window.removeEventListener('resize', this._handlers.onResize);
      window.visualViewport?.removeEventListener('resize', this._handlers.onResize);
    }
    cancelAnimationFrame(this.scrollRaf);
    clearTimeout(this.notifyTimer);
    clearTimeout(this.scanTimer);
    this._obstacleCache = null;
    this.targets.clear();
    this.byElement.clear();
  }
}
