import {
  GENERAL_TIPS,
  MASCOT_TIMING,
  WALK_SPEED_PX_PER_SEC,
  bubbleTtl,
  resolveRouteBehavior,
} from './config/behaviors.js';
import { contextLine, readPageContext } from './PageContext.js';

export const REST_YAW = -0.18;

/** Arrival beats after a stroll, cycled so every clip gets screen time. */
const STROLL_BEATS = ['wave', 'point', 'jump'];

export const MASCOT_STATES = {
  HIDDEN: 'hidden',
  IDLE: 'idle',
  WALKING: 'walking',
  GUIDING: 'guiding',
  RETURNING: 'returning',
};

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

/**
 * Explicit state machine + behaviour scheduler.
 *
 * Guidance is spatial: the mascot moves beside a target and a DOM ring
 * identifies it. When the rigged GLB is present, MascotModel plays
 * Idle/Walk/Point/Wave; this brain never rotates or bends the model to imitate
 * a gesture.
 */
export class MascotBrain {
  constructor({
    registry,
    getLayout,
    reducedMotion = false,
    lowPower = false,
    onPose,
    onBubble,
    onHighlight,
    onState,
    onGesture,
  }) {
    this.registry = registry;
    this.getLayout = getLayout;
    this.reducedMotion = Boolean(reducedMotion);
    this.lowPower = Boolean(lowPower);
    this.onPose = onPose;
    this.onBubble = onBubble;
    this.onHighlight = onHighlight;
    this.onState = onState;
    this.onGesture = onGesture;

    this.state = MASCOT_STATES.HIDDEN;
    this.route = null;
    this.pose = { x: 0, y: 0, facing: REST_YAW, duration: 0, ready: false };
    this.timers = new Set();
    this.history = new Map();
    this.active = false;
    this.paused = false;
    this.destroyed = false;

    this.guidedId = null;
    this.guidingMessage = '';
    this.bubbleOpen = false;
    this.bubbleSeq = 0;
    this.bubbleTimer = null;
    this.holdTimer = null;
    this.moveTimer = null;
    this.ambientTimer = null;
    this.userHighlightTimer = null;

    this.tipIndex = 0;
    this.routeLineShown = false;
    this.ambientShown = false;
    this.lastGuideAt = 0;
    this.lastRepositionAt = 0;

    this.tour = null;
    this.tourActive = false;
    this.tourDone = false;
    this.tourCurrent = null;
    this.tourTimer = null;
    this.tourHintedAt = 0;
    this.hoverId = null;
    this.bubbleSource = null;

    this.strollTimer = null;
    this.strollIndex = 0;
    this.hoverTimer = null;
    this.hoverHoldTimer = null;

    this.actTimer = null;
    this.pointRelease = null;
    this.context = null;
    this.contextAt = 0;
  }

  start(pathname) {
    this.active = true;
    this.setRoute(pathname, true);
    // Open with the greeting clip instead of starting on a static idle.
    this.later(() => {
      if (this.state === MASCOT_STATES.IDLE && !this.bubbleOpen) this.onGesture?.('wave');
    }, 900);
  }

  setRoute(pathname, initial = false) {
    if (this.destroyed) return;
    this.clearTimers();
    this.clearBubble();
    this.onHighlight?.(null);

    this.route = resolveRouteBehavior(pathname);
    this.guidedId = null;
    this.guidingMessage = '';
    this.routeLineShown = false;
    this.ambientShown = false;
    this.tipIndex = 0;
    this.lastGuideAt = 0;
    this.tour = null;
    this.tourActive = false;
    this.tourDone = false;
    this.tourCurrent = null;
    this.tourHintedAt = 0;
    this.hoverId = null;

    if (!this.route) {
      this.setState(MASCOT_STATES.HIDDEN);
      return;
    }

    this.setState(MASCOT_STATES.IDLE);
    const rest = this.restSpot();
    if (rest) this.applyPose(rest, initial ? 0 : 520, REST_YAW);

    this.later(() => this.evaluate(), MASCOT_TIMING.evaluateDelayMs);
    this.scheduleAmbient();
  }

  setLayout() {
    if (this.destroyed || !this.route) return;
    this.clearTimers();
    this.clearBubble();
    this.onHighlight?.(null);
    this.guidedId = null;
    this.tourActive = false;
    this.tourCurrent = null;
    this.hoverId = null;
    this.setState(MASCOT_STATES.IDLE);
    const rest = this.restSpot();
    if (rest) this.applyPose(rest, 0, REST_YAW);
    this.scheduleAmbient();
    this.later(() => this.evaluate(), 900);
  }

  setPaused(paused) {
    if (this.paused === paused) return;
    this.paused = paused;
    if (paused) {
      this.clearTimers();
      this.clearBubble();
      this.onHighlight?.(null);
      this.guidedId = null;
      this.tourActive = false;
      this.tourCurrent = null;
      this.hoverId = null;
      this.snapToRest();
    } else if (this.route) {
      this.evaluate();
    }
  }

  setSettings({ reducedMotion, lowPower } = {}) {
    if (typeof reducedMotion === 'boolean' && reducedMotion !== this.reducedMotion) {
      this.reducedMotion = reducedMotion;
      if (reducedMotion) {
        this.clearTimers();
        this.clearBubble();
        this.onHighlight?.(null);
        this.guidedId = null;
        this.snapToRest();
      } else {
        this.evaluate();
      }
    }
    if (typeof lowPower === 'boolean') this.lowPower = lowPower;
  }

  setState(state) {
    if (this.state === state) return;
    this.state = state;
    this.onState?.(state);
  }

  restSpot() {
    const { size, viewport } = this.getLayout();
    return this.registry.findRestSpot(size, viewport);
  }

  applyPose(spot, duration = 0, facing = this.pose.facing) {
    this.pose = {
      x: spot.x,
      y: spot.y,
      facing,
      duration: this.reducedMotion ? 0 : duration,
      ready: true,
    };
    this.onPose?.(this.pose);
  }

  snapToRest() {
    this.clearLater(this.moveTimer);
    this.moveTimer = null;
    const rest = this.restSpot();
    if (rest) this.applyPose(rest, 0, REST_YAW);
    this.setState(MASCOT_STATES.IDLE);
  }

  walkTo(spot, facing, onArrive, durationOverride) {
    const distance = Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y);
    const duration =
      durationOverride ?? clamp((distance / WALK_SPEED_PX_PER_SEC) * 1000, 360, 2600);

    this.clearLater(this.moveTimer);
    this.applyPose(spot, this.reducedMotion ? 0 : duration, facing);
    this.moveTimer = this.later(
      () => {
        this.moveTimer = null;
        onArrive?.();
      },
      this.reducedMotion ? 20 : duration + 70,
    );
  }

  walkFacing(from, to) {
    const dx = to.x - from.x;
    if (Math.abs(dx) < 12) return REST_YAW;
    return dx < 0 ? -0.92 : 0.92;
  }

  facingFor(spot, rect) {
    if (!rect) return REST_YAW;
    const { size } = this.getLayout();
    const mascotCenterX = (spot?.x ?? this.pose.x) + size.w / 2;
    const targetCenterX = rect.left + rect.width / 2;
    const dx = targetCenterX - mascotCenterX;
    if (Math.abs(dx) < 36) return REST_YAW;
    return dx < 0 ? -0.95 : 0.95;
  }

  later(fn, ms) {
    const id = setTimeout(
      () => {
        this.timers.delete(id);
        if (!this.destroyed) fn();
      },
      Math.max(0, ms),
    );
    this.timers.add(id);
    return id;
  }

  clearLater(id) {
    if (!id) return;
    clearTimeout(id);
    this.timers.delete(id);
  }

  clearTimers() {
    for (const id of this.timers) clearTimeout(id);
    this.timers.clear();
    this.bubbleTimer = null;
    this.holdTimer = null;
    this.moveTimer = null;
    this.ambientTimer = null;
    this.userHighlightTimer = null;
    this.tourTimer = null;
    this.strollTimer = null;
    this.hoverTimer = null;
    this.hoverHoldTimer = null;
    this.actTimer = null;
    this.pointRelease = null;
  }

  say(text, source = 'ambient', ttlOverride) {
    if (!text) return;
    this.bubbleOpen = true;
    this.bubbleSource = source;
    this.clearLater(this.bubbleTimer);
    const ttl = ttlOverride ?? bubbleTtl(text);
    this.onBubble?.({ text, ttl, source, id: ++this.bubbleSeq });
    this.bubbleTimer = this.later(() => {
      this.bubbleTimer = null;
      this.bubbleOpen = false;
      this.onBubble?.(null);
      if (this.state === MASCOT_STATES.IDLE) {
        this.ensureSafeRest();
        if (this.state === MASCOT_STATES.IDLE) this.scheduleAmbient();
      }
    }, ttl);
  }

  clearBubble() {
    this.clearLater(this.bubbleTimer);
    this.bubbleTimer = null;
    this.bubbleOpen = false;
    this.bubbleSource = null;
    this.onBubble?.(null);
  }

  nextTip() {
    const tips = this.route?.tips?.length ? this.route.tips : GENERAL_TIPS;
    const text = tips[this.tipIndex % tips.length];
    this.tipIndex += 1;
    return text;
  }

  canShow(id, cfg = {}) {
    const history = this.history.get(id) || { count: 0, lastAt: 0 };
    const maxShows = cfg.maxShows ?? 1;
    const cooldownMs = cfg.cooldownMs ?? 90000;
    return history.count < maxShows && Date.now() - history.lastAt >= cooldownMs;
  }

  markShown(id) {
    const history = this.history.get(id) || { count: 0, lastAt: 0 };
    history.count += 1;
    history.lastAt = Date.now();
    this.history.set(id, history);
  }

  centerScore(target) {
    const viewport = this.getLayout().viewport;
    const rect = target.rect;
    if (!rect) return Number.MAX_SAFE_INTEGER;
    const x = rect.left + rect.width / 2 - viewport.w / 2;
    const y = rect.top + rect.height / 2 - viewport.h / 2;
    return Math.hypot(x, y);
  }

  pickGuidance({ ignoreCooldown = false } = {}) {
    if (!this.route) return null;
    const { size, viewport } = this.getLayout();

    if (this.route.group) {
      const cfg = this.route.group;
      const entries = this.registry
        .getGroup(cfg.prefix)
        .filter((target) => target.visible)
        .filter(
          (target) =>
            ignoreCooldown ||
            this.canShow(target.id, {
              maxShows: cfg.maxShows,
              cooldownMs: cfg.cooldownMs,
            }),
        )
        .sort(
          (a, b) =>
            Number(b.featured) - Number(a.featured) || this.centerScore(a) - this.centerScore(b),
        );

      let fallback = null;
      for (const entry of entries) {
        const spot = this.registry.findSafeSpot(entry, size, viewport);
        if (spot) return { entry, cfg, spot };
        if (!fallback) fallback = entry;
      }
      return fallback ? { entry: fallback, cfg, spot: null } : null;
    }

    const behaviors = [...(this.route.behaviors || [])];
    behaviors.sort((a, b) => (a.priority ?? 2) - (b.priority ?? 2));
    let fallback = null;
    for (const cfg of behaviors) {
      const entry = this.registry.getTarget(cfg.target);
      if (!entry?.visible) continue;
      if (!ignoreCooldown && !this.canShow(cfg.target, cfg)) continue;
      const spot = this.registry.findSafeSpot(entry, size, viewport);
      if (spot) return { entry, cfg, spot };
      if (!fallback) fallback = { entry, cfg };
    }
    return fallback ? { ...fallback, spot: null } : null;
  }

  evaluate() {
    if (!this.active || !this.route || this.paused || this.destroyed) return;
    if (this.state !== MASCOT_STATES.IDLE) return;
    if (typeof document !== 'undefined' && document.hidden) return;

    // A page tour runs before any ad-hoc pointing: it is the page's own story.
    if (this.maybeStartTour()) return;

    if (this.reducedMotion) {
      if (!this.routeLineShown && this.route.line) {
        this.routeLineShown = true;
        this.say(this.route.line, 'ambient');
      }
      return;
    }

    if (Date.now() - this.lastGuideAt < MASCOT_TIMING.globalCooldownMs) return;

    const candidate = this.pickGuidance();
    if (candidate) {
      this.guideTo(candidate);
      return;
    }

    if (!this.routeLineShown && this.route.line) {
      this.routeLineShown = true;
      this.say(this.route.line, 'ambient');
    }
  }

  guideTo(candidate, userInitiated = false) {
    if (!candidate?.entry) return false;
    const { entry, cfg } = candidate;
    const spot = candidate.spot || null;
    const message = entry.message || cfg.message || this.nextTip();
    const { viewport, size } = this.getLayout();

    this.guidedId = entry.id;
    this.guidingMessage = message;
    this.routeLineShown = true;
    this.ambientShown = true;
    this.lastGuideAt = Date.now();
    this.markShown(entry.id);
    this.clearBubble();

    const rect = entry.el?.getBoundingClientRect?.() || entry.rect;
    const facing = spot ? this.facingFor(spot, rect) : this.pose.facing;
    const isMobile = viewport.w < 760;

    // Mobile, reduced-motion and dense layouts never roam: a ring + bubble
    // from the resting corner is used instead.
    if (this.reducedMotion || isMobile || !spot) {
      this.beginGuide(entry, message, null);
      return true;
    }

    const distance = Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y);
    if (distance < 8) {
      this.applyPose(this.pose, 0, facing);
      this.beginGuide(entry, message, spot);
      return true;
    }

    const duration = clamp((distance / WALK_SPEED_PX_PER_SEC) * 1000, 380, 2600);
    this.setState(MASCOT_STATES.WALKING);
    this.walkTo(spot, facing, () => this.beginGuide(entry, message, spot), duration);
    return true;
  }

  beginGuide(entry, message, spot) {
    const still = this.registry.getTarget(this.guidedId || entry.id);
    if (!still) {
      this.finishGuide();
      return;
    }

    if (spot && !this.reducedMotion) {
      const distance = Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y);
      if (distance > 4) this.applyPose(spot, 0, this.pose.facing);
    }

    this.setState(MASCOT_STATES.GUIDING);
    this.onHighlight?.(still);
    this.say(message, 'guidance');

    const hold = Math.max(MASCOT_TIMING.holdMs, bubbleTtl(message) + 900);
    this.clearLater(this.holdTimer);
    this.holdTimer = this.later(() => {
      this.holdTimer = null;
      this.finishGuide();
    }, hold);
  }

  finishGuide(immediate = false) {
    this.clearLater(this.holdTimer);
    this.holdTimer = null;
    // Sign off the explanation with a wave instead of dropping straight to idle.
    if (!immediate && !this.reducedMotion) this.onGesture?.('wave');
    this.clearLater(this.userHighlightTimer);
    this.userHighlightTimer = null;
    this.onHighlight?.(null);
    this.guidedId = null;
    this.clearBubble();

    if (immediate || this.reducedMotion) {
      this.snapToRest();
      this.scheduleAmbient();
      return;
    }

    const rest = this.restSpot();
    if (!rest) {
      this.setState(MASCOT_STATES.IDLE);
      this.scheduleAmbient();
      return;
    }

    const distance = Math.hypot(rest.x - this.pose.x, rest.y - this.pose.y);
    if (distance < 4) {
      this.applyPose(rest, 0, REST_YAW);
      this.setState(MASCOT_STATES.IDLE);
      this.scheduleAmbient();
      return;
    }

    this.setState(MASCOT_STATES.RETURNING);
    this.walkTo(rest, REST_YAW, () => {
      this.setState(MASCOT_STATES.IDLE);
      this.scheduleAmbient();
    });
  }

  interact() {
    if (!this.active || !this.route || this.destroyed) return;
    this.clickCount = (this.clickCount || 0) + 1;
    const gestureType = STROLL_BEATS[(this.clickCount - 1) % STROLL_BEATS.length];
    this.onGesture?.(gestureType);

    if (this.state === MASCOT_STATES.GUIDING) {
      this.say(this.nextTip(), 'user');
      return;
    }

    if (!this.reducedMotion && this.route.group && this.state === MASCOT_STATES.IDLE) {
      const cfg = this.route.group;
      const entry = this.registry
        .getGroup(cfg.prefix)
        .filter((target) => target.visible)
        .sort(
          (a, b) =>
            Number(b.featured) - Number(a.featured) || this.centerScore(a) - this.centerScore(b),
        )[0];

      if (entry) {
        this.clearLater(this.userHighlightTimer);
        this.guidedId = entry.id;
        this.onHighlight?.(entry);
        this.say(
          entry.label ? `This one — ${entry.label}.` : cfg.message || this.nextTip(),
          'user',
        );
        this.userHighlightTimer = this.later(() => {
          this.userHighlightTimer = null;
          if (this.state !== MASCOT_STATES.GUIDING) {
            this.onHighlight?.(null);
            this.guidedId = null;
          }
        }, 5200);
        return;
      }
    }

    this.say(this.nextTip(), 'user');
  }

  /**
   * If content has loaded underneath a resting mascot, move it off any new
   * interactive element. This also runs when a route bubble just closed, since
   * the bubble used to short-circuit the sync path before the pose check.
   */
  ensureSafeRest() {
    if (!this.active || !this.route || this.paused || this.destroyed) return;
    if (this.state !== MASCOT_STATES.IDLE) return;
    if (Date.now() - this.lastRepositionAt <= MASCOT_TIMING.repositionCooldownMs) return;

    const { size } = this.getLayout();
    if (this.registry.isPoseSafe(this.pose, size)) return;

    this.lastRepositionAt = Date.now();
    const rest = this.restSpot();
    if (rest && Math.hypot(rest.x - this.pose.x, rest.y - this.pose.y) > 2) {
      this.walkTo(rest, REST_YAW, () => {
        this.setState(MASCOT_STATES.IDLE);
        this.sync();
      });
    }
  }

  sync() {
    if (!this.active || !this.route || this.paused || this.destroyed) return;

    if (
      this.guidedId &&
      (this.state === MASCOT_STATES.GUIDING || this.state === MASCOT_STATES.WALKING)
    ) {
      const entry = this.registry.getTarget(this.guidedId);
      if (!entry || !entry.visible) {
        this.finishGuide();
        return;
      }

      this.onHighlight?.(entry);

      if (this.state === MASCOT_STATES.GUIDING && !this.reducedMotion) {
        const { size, viewport } = this.getLayout();
        if (viewport.w < 760) return;
        const spot = this.registry.findSafeSpot(entry, size, viewport);
        if (!spot) return;
        const distance = Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y);
        if (distance > 70) {
          this.setState(MASCOT_STATES.WALKING);
          this.walkTo(spot, this.facingFor(spot, entry.el.getBoundingClientRect()), () =>
            this.beginGuide(entry, this.guidingMessage, spot),
          );
        }
      }
      return;
    }

    if (this.state !== MASCOT_STATES.IDLE) return;

    this.ensureSafeRest();
    if (this.state !== MASCOT_STATES.IDLE) return;
    if (this.maybeStartTour()) return;
    if (this.bubbleOpen) return;

    this.evaluate();
  }

  /* ------------------------------------------------------------------ tour -- */

  resolveTourSteps() {
    const tour = this.route?.tour;
    if (!tour?.steps?.length) return [];
    const steps = [];
    for (const step of tour.steps) {
      if (step.group) {
        const found = this.registry
          .getGroup(step.group)
          .filter((entry) => entry.el?.isConnected)
          .slice(0, step.count ?? 3);
        for (const entry of found) steps.push({ id: entry.id, message: step.message || '' });
      } else if (step.target) {
        steps.push({ id: step.target, message: step.message || '' });
      }
    }
    return steps;
  }

  /**
   * Tours belong to a section, not to page load: the route is walked only once
   * the reader scrolls the first card into view.
   */
  maybeStartTour() {
    if (!this.active || !this.route?.tour || this.paused || this.destroyed) return false;
    if (this.tourActive || this.tourDone) return false;
    if (this.state !== MASCOT_STATES.IDLE || this.bubbleOpen) return false;

    const steps = this.resolveTourSteps();
    if (!steps.length) return false;
    const first = this.registry.getTarget(steps[0].id);
    if (!first?.visible) return false;

    this.beginTour(steps);
    return true;
  }

  beginTour(steps) {
    this.tour = { steps, index: -1 };
    this.tourActive = true;
    this.tourDone = true;
    this.routeLineShown = true;
    this.ambientShown = true;
    this.lastGuideAt = Date.now();
    this.clearLater(this.ambientTimer);

    const intro = this.route?.tour?.intro;
    if (intro) this.say(intro, 'tour');
    this.clearLater(this.tourTimer);
    this.tourTimer = this.later(() => this.tourNext(), intro ? bubbleTtl(intro) + 700 : 240);
  }

  tourNext() {
    this.tourTimer = null;
    if (!this.tourActive || this.paused || this.destroyed || !this.tour) return;

    // A hover takes over the bubble; the tour waits for the reader to let go.
    if (this.hoverId) {
      this.tourTimer = this.later(() => this.tourNext(), 700);
      return;
    }

    const next = this.tour.steps[this.tour.index + 1];
    if (!next) {
      this.endTour();
      return;
    }

    const entry = this.registry.getTarget(next.id);
    if (!entry?.el?.isConnected) {
      this.tour.index += 1;
      this.tourTimer = this.later(() => this.tourNext(), 60);
      return;
    }
    if (!entry.visible) {
      // The next card is below the fold: say so instead of waiting in silence.
      if (Date.now() - this.tourHintedAt > 9000) {
        this.tourHintedAt = Date.now();
        this.say(
          this.route?.tour?.scrollHint ||
            'The next one is further down — keep scrolling and I will carry on.',
          'tour',
        );
      }
      this.tourTimer = this.later(() => this.tourNext(), 900);
      return;
    }

    this.tour.index += 1;
    const message = next.message || entry.message || entry.hover || entry.label || this.nextTip();
    this.tourPoint(entry, message);
  }

  tourPoint(entry, message) {
    if (!this.tourActive) return;
    this.tourCurrent = { entry, message };

    const { size, viewport } = this.getLayout();
    const rect = entry.el.getBoundingClientRect();
    const spot = viewport.w < 760 ? null : this.approachSpot(entry, size, viewport);

    const speak = () => {
      this.tourTimer = null;
      if (!this.tourActive || this.paused) return;
      const still = this.registry.getTarget(entry.id) || entry;
      this.setState(MASCOT_STATES.GUIDING);
      this.onHighlight?.(still);
      this.say(message, 'tour');
      const dwell = Math.max(MASCOT_TIMING.holdMs, bubbleTtl(message) + 1100);
      this.clearLater(this.tourTimer);
      this.tourTimer = this.later(() => this.tourNext(), dwell);
    };

    this.clearLater(this.tourTimer);
    if (!spot || this.reducedMotion) {
      this.applyPose(this.pose, 0, this.facingFor(null, rect));
      speak();
      return;
    }

    // Tours walk slower than ordinary guidance: the reader is following a story.
    const distance = Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y);
    const duration = clamp((distance / (WALK_SPEED_PX_PER_SEC * 0.7)) * 1000, 520, 3200);
    this.setState(MASCOT_STATES.WALKING);
    this.walkTo(spot, this.facingFor(spot, rect), speak, duration);
  }

  endTour() {
    this.tourActive = false;
    this.tourCurrent = null;
    this.clearLater(this.tourTimer);
    this.tourTimer = null;
    this.onHighlight?.(null);

    const outro = this.route?.tour?.outro;
    if (outro) this.say(outro, 'tour');

    const rest = this.reducedMotion ? null : this.restSpot();
    if (!rest) {
      this.setState(MASCOT_STATES.IDLE);
      this.scheduleAmbient();
      return;
    }

    const distance = Math.hypot(rest.x - this.pose.x, rest.y - this.pose.y);
    if (distance < 4) {
      this.applyPose(rest, 0, REST_YAW);
      this.setState(MASCOT_STATES.IDLE);
      this.scheduleAmbient();
      return;
    }

    this.setState(MASCOT_STATES.RETURNING);
    this.walkTo(rest, REST_YAW, () => {
      this.setState(MASCOT_STATES.IDLE);
      this.scheduleAmbient();
    });
  }

  /* ----------------------------------------------------------------- hover -- */

  hoverTarget(id) {
    if (!this.active || !this.route || this.paused || this.destroyed) return;
    const entry = this.registry.getTarget(id);
    if (!entry?.el) return;

    // A new hover replaces the previous one, including its pending walk.
    this.hoverId = id;
    this.clearLater(this.hoverTimer);
    this.hoverTimer = null;
    this.clearLater(this.hoverHoldTimer);
    this.hoverHoldTimer = null;

    // Hold the tour while the reader is reading a card themselves.
    this.clearLater(this.tourTimer);
    this.tourTimer = null;

    const { size, viewport } = this.getLayout();
    const rect = entry.el.getBoundingClientRect();
    const spot =
      this.reducedMotion || viewport.w < 760 ? null : this.approachSpot(entry, size, viewport);

    const speak = () => {
      this.hoverTimer = null;
      // The pointer moved on before arriving: stay quiet.
      if (this.hoverId !== id) return;

      const still = this.registry.getTarget(id) || entry;
      this.onHighlight?.(still);
      this.setState(MASCOT_STATES.GUIDING);

      const text =
        entry.hover ||
        entry.message ||
        (entry.label ? `${entry.label} — worth a closer look.` : '');
      if (text) this.say(text, 'hover', 16000);
    };

    if (!spot) {
      speak();
      return;
    }

    const distance = Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y);
    if (distance < 24) {
      this.applyPose(this.pose, 0, this.facingFor(spot, rect));
      speak();
      return;
    }

    // Walk over to the card, then point at it while the reader reads.
    this.clearLater(this.moveTimer);
    this.setState(MASCOT_STATES.WALKING);
    this.walkTo(spot, this.facingFor(spot, rect), speak);
  }

  unhoverTarget(id) {
    if (this.hoverId !== id) return;
    this.hoverId = null;
    this.clearLater(this.hoverTimer);
    this.hoverTimer = null;
    this.clearLater(this.hoverHoldTimer);
    this.hoverHoldTimer = null;

    if (this.tourActive && this.tourCurrent) {
      const { entry, message } = this.tourCurrent;
      this.clearLater(this.tourTimer);
      this.tourTimer = this.later(() => this.tourPoint(entry, message), 420);
      return;
    }

    if (this.bubbleSource === 'hover') this.clearBubble();

    const guided = this.guidedId ? this.registry.getTarget(this.guidedId) : null;
    this.onHighlight?.(guided || null);

    if (!guided && this.state === MASCOT_STATES.GUIDING) {
      // Release the point pose and hand control back to the stroll cycle.
      this.setState(MASCOT_STATES.IDLE);
      this.scheduleAmbient();
    }
  }

  scheduleAmbient() {
    this.clearLater(this.ambientTimer);
    this.ambientTimer = this.later(() => {
      this.ambientTimer = null;
      this.ambient();
    }, MASCOT_TIMING.ambientDelayMs);
    this.scheduleAct();
  }

  /* ----------------------------------------------------------------- stroll -- */

  scheduleAct(delay) {
    this.clearLater(this.actTimer);
    if (!this.route || this.reducedMotion) return;
    const wait = delay ?? 320 + Math.random() * 640;
    this.actTimer = this.later(() => {
      this.actTimer = null;
      this.act();
    }, wait);
  }

  /**
   * The mascot performs: on every tick it walks somewhere, points at something
   * it can name, waves or hops. Standing still is the rare outcome, used only
   * when the page gives it nothing to do.
   */
  act() {
    if (!this.active || !this.route || this.paused || this.destroyed) return;
    if (this.reducedMotion || this.tourActive) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    if (this.state !== MASCOT_STATES.IDLE || this.bubbleOpen) {
      this.scheduleAct(450);
      return;
    }

    const target = this.nearestVisibleTarget();
    const roll = Math.random();

    if (target && roll < 0.42) {
      this.pointTarget(target);
    } else if (roll < 0.72) {
      if (!this.stroll()) {
        this.onGesture?.('wave');
        this.say(this.narrate(), 'ambient');
      }
    } else if (roll < 0.86) {
      this.onGesture?.('wave');
      this.say(this.narrate(), 'ambient');
    } else if (roll < 0.95) {
      this.onGesture?.('jump');
    } else {
      this.say(this.narrate(), 'ambient');
    }

    this.scheduleAct();
  }

  pageContext() {
    const now = Date.now();
    if (!this.context || now - this.contextAt > 6000) {
      this.context = readPageContext();
      this.contextAt = now;
    }
    return this.context;
  }

  /** Everything it says is grounded in the page it is standing on. */
  narrate() {
    const context = this.pageContext();
    const visible = [...this.registry.targets.values()].filter((entry) => entry.visible);

    if (visible.length && Math.random() < 0.65) {
      const pick = visible[Math.floor(Math.random() * visible.length)];
      const text = pick.hover || pick.message;
      if (text) return text;
      if (pick.label) return `${pick.label} — right there.`;
    }

    return contextLine(context, this.route?.ambient || this.nextTip());
  }

  /** Walk to a target and point at it while describing it. */
  pointTarget(entry) {
    const { size, viewport } = this.getLayout();
    const rect = entry.el?.getBoundingClientRect?.();
    const spot = viewport.w < 760 ? null : this.approachSpot(entry, size, viewport);

    const speak = () => {
      const still = this.registry.getTarget(entry.id) || entry;
      this.onHighlight?.(still);
      this.setState(MASCOT_STATES.GUIDING);
      this.say(
        entry.hover ||
          entry.message ||
          (entry.label ? `${entry.label} — this one.` : this.narrate()),
        'ambient',
      );
      this.clearLater(this.pointRelease);
      this.pointRelease = this.later(() => {
        this.pointRelease = null;
        if (this.state === MASCOT_STATES.GUIDING && !this.hoverId) {
          this.onHighlight?.(null);
          this.setState(MASCOT_STATES.IDLE);
        }
      }, 3200);
    };

    if (!spot) {
      speak();
      return;
    }

    const distance = Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y);
    if (distance < 40) {
      this.applyPose(this.pose, 0, this.facingFor(spot, rect));
      speak();
      return;
    }

    this.setState(MASCOT_STATES.WALKING);
    this.walkTo(spot, this.facingFor(spot, rect), speak);
  }

  /**
   * Crossing the layout is the only way the Walk clip reads as walking, and the
   * arrival beat is what puts Wave, Point and Jump on screen without the reader
   * having to click the mascot.
   */
  stroll() {
    if (!this.active || !this.route || this.paused || this.destroyed) return false;
    if (this.reducedMotion || this.tourActive) return false;
    if (this.state !== MASCOT_STATES.IDLE || this.bubbleOpen) return false;
    if (typeof document !== 'undefined' && document.hidden) return false;

    const { size, viewport } = this.getLayout();
    if (viewport.w < 760) return false;

    const spot = this.pickStrollSpot(size, viewport);
    if (!spot) return false;

    const target = this.nearestVisibleTarget(spot);
    this.strollIndex += 1;

    this.setState(MASCOT_STATES.WALKING);
    this.walkTo(spot, this.walkFacing(this.pose, spot), () => {
      const roll = Math.random();

      // Every arrival ends in an action, weighted so Wave and Jump actually
      // appear instead of the mascot settling into a stand.
      if (target && roll < 0.45) {
        this.onHighlight?.(target);
        this.setState(MASCOT_STATES.GUIDING);
        this.say(
          target.hover || target.message || `${target.label || 'This one'} — right there.`,
          'ambient',
        );
        this.clearLater(this.pointRelease);
        this.pointRelease = this.later(() => {
          this.pointRelease = null;
          if (this.state === MASCOT_STATES.GUIDING && !this.hoverId) {
            this.onHighlight?.(null);
            this.setState(MASCOT_STATES.IDLE);
          }
        }, MASCOT_TIMING.pointHighlightMs || 2600);
      } else if (roll < 0.78) {
        this.setState(MASCOT_STATES.IDLE);
        this.onGesture?.('wave');
        this.say(this.narrate(), 'ambient');
      } else {
        this.setState(MASCOT_STATES.IDLE);
        this.onGesture?.('jump');
      }

      this.scheduleAmbient();
    });
    return true;
  }

  /**
   * Where to stand to point at a card. Dense grids (the catalogue is all cards)
   * have no fully free slot, so fall back to the nearest standable edge instead
   * of refusing to walk at all.
   */
  approachSpot(entry, size, viewport) {
    if (!entry?.el?.isConnected) return null;
    const direct = this.registry.findSafeSpot(entry, size, viewport);
    if (direct) return direct;

    const rect = entry.el.getBoundingClientRect();
    const margin = 16;
    const spots = [
      { x: rect.left - size.w - 10, y: rect.top },
      { x: rect.right + 10, y: rect.top },
      { x: rect.left - size.w - 10, y: rect.top + rect.height - size.h },
      { x: rect.right + 10, y: rect.top + rect.height - size.h },
    ].map((spot) => ({
      x: clamp(spot.x, margin, viewport.w - size.w - margin),
      y: clamp(spot.y, 96, viewport.h - size.h - margin),
    }));

    const strict = spots.filter((spot) => this.registry.isPoseUsable(spot, size, viewport, true));
    const pool = strict.length
      ? strict
      : spots.filter((spot) => this.registry.isPoseUsable(spot, size, viewport, false));
    if (!pool.length) return null;

    const centerX = rect.left + rect.width / 2;
    pool.sort(
      (a, b) => Math.abs(a.x + size.w / 2 - centerX) - Math.abs(b.x + size.w / 2 - centerX),
    );
    return pool[0];
  }

  nearestVisibleTarget(around = this.pose) {
    let best = null;
    let bestScore = Infinity;
    const cx = around.x + this.getLayout().size.w / 2;
    const cy = around.y + this.getLayout().size.h / 2;
    for (const target of this.registry.targets.values()) {
      if (!target.visible || !target.rect) continue;
      const tx = target.rect.left + target.rect.width / 2;
      const ty = target.rect.top + target.rect.height / 2;
      const score = Math.hypot(tx - cx, ty - cy);
      if (score < bestScore) {
        bestScore = score;
        best = target;
      }
    }
    return best;
  } /**
   * Roam the whole viewport, not just the corners: a grid of lanes across the
   * screen gives the Walk clip somewhere to go on every section of every page.
   */
  pickStrollSpot(size, viewport) {
    const margin = 16;
    const top = 96;
    const bottom = viewport.h - size.h - 16;
    const usableWidth = Math.max(1, viewport.w - size.w - margin * 2);
    const columns = viewport.w < 1100 ? 3 : 5;
    const rows = 3;
    const candidates = [];

    for (let column = 0; column < columns; column += 1) {
      for (let row = 0; row < rows; row += 1) {
        candidates.push({
          x: margin + (usableWidth * column) / Math.max(1, columns - 1),
          y: top + ((bottom - top) * row) / Math.max(1, rows - 1),
        });
      }
    }

    const far = candidates.filter(
      (spot) =>
        Math.hypot(spot.x - this.pose.x, spot.y - this.pose.y) >
          MASCOT_TIMING.strollMinDistancePx && this.registry.isPoseUsable(spot, size, viewport),
    );
    if (!far.length) return null;

    // Favour the far half of the screen so each stroll reads as a real walk.
    far.sort(
      (a, b) =>
        Math.hypot(b.x - this.pose.x, b.y - this.pose.y) -
        Math.hypot(a.x - this.pose.x, a.y - this.pose.y),
    );
    const pool = far.slice(0, Math.max(1, Math.ceil(far.length * 0.6)));
    return pool[Math.floor(Math.random() * pool.length)];
  }

  ambient() {
    if (!this.active || !this.route || this.paused || this.reducedMotion) return;
    if (this.state !== MASCOT_STATES.IDLE || this.bubbleOpen) return;
    if (this.ambientShown) return;

    this.ambientShown = true;
    const candidate = this.pickGuidance();
    if (candidate) {
      this.guideTo(candidate);
      return;
    }
    if (this.route.ambient) this.say(this.route.ambient, 'ambient');
  }

  destroy() {
    this.destroyed = true;
    this.active = false;
    this.clearTimers();
  }
}
