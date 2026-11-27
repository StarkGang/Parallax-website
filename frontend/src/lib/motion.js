import { useEffect, useRef } from 'react';
import Lenis from 'lenis';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

let globalLenis = null;

/**
 * Initializes Lenis smooth scrolling and synchronizes it with GSAP's ScrollTrigger.
 */
export function initSmoothScroll() {
  if (typeof window === 'undefined') return () => {};

  if (globalLenis) {
    globalLenis.destroy();
  }

  // Touch devices (Android especially) keep native momentum scrolling: Lenis
  // wheel smoothing is for fine pointers only, so touch scrolling never fights
  // the OS or the collapsing address bar.
  const finePointer =
    typeof window.matchMedia === 'function' ? window.matchMedia('(pointer: fine)').matches : true;

  const lenis = new Lenis({
    duration: 1.15,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smoothWheel: finePointer,
    syncTouch: false,
    touchMultiplier: finePointer ? 1.5 : 1,
  });

  globalLenis = lenis;
  window.__lenis = lenis;

  // Sync with GSAP ScrollTrigger
  lenis.on('scroll', ScrollTrigger.update);

  const tickerCallback = (time) => {
    lenis.raf(time * 1000);
  };

  gsap.ticker.add(tickerCallback);
  gsap.ticker.lagSmoothing(0);

  return () => {
    gsap.ticker.remove(tickerCallback);
    lenis.destroy();
    globalLenis = null;
    window.__lenis = null;
  };
}

/**
 * React hook to enable Tathva-style 3D mouse tilt and dynamic glare effect on a container.
 */
export function useCardTilt({ maxTilt = 12, perspective = 1000, scale = 1.02 } = {}) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;

    const coarse =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(pointer: coarse)').matches
        : false;

    const apply = (x, y) => {
      // x, y are normalised to roughly [-0.5, 0.5] around the card centre.
      gsap.to(el, {
        rotateX: -y * maxTilt * 2,
        rotateY: x * maxTilt * 2,
        scale,
        transformPerspective: perspective,
        transformStyle: 'preserve-3d',
        ease: 'power1.out',
        duration: 0.25,
      });
      el.style.setProperty('--mouse-x', `${(x + 0.5) * 100}%`);
      el.style.setProperty('--mouse-y', `${(y + 0.5) * 100}%`);
    };

    const reset = () => {
      gsap.to(el, {
        rotateX: 0,
        rotateY: 0,
        scale: 1,
        ease: 'power2.out',
        duration: 0.5,
      });
    };

    if (coarse) {
      // Touch devices have no hover: drive the tilt from device orientation so
      // cards still feel alive. Android Chrome exposes this without a prompt.
      let baseGamma = null;
      let baseBeta = null;
      const onOrient = (e) => {
        if (e.gamma == null || e.beta == null) return;
        if (baseGamma === null) {
          baseGamma = e.gamma;
          baseBeta = e.beta;
        }
        const x = Math.max(-0.5, Math.min(0.5, (e.gamma - baseGamma) / 60));
        const y = Math.max(-0.5, Math.min(0.5, (e.beta - baseBeta) / 60));
        apply(x, y);
      };
      window.addEventListener('deviceorientation', onOrient, { passive: true });
      return () => window.removeEventListener('deviceorientation', onOrient);
    }

    let bounds = null;

    const onMouseEnter = () => {
      bounds = el.getBoundingClientRect();
    };

    const onMouseMove = (e) => {
      if (!bounds) bounds = el.getBoundingClientRect();
      const x = (e.clientX - bounds.left) / bounds.width - 0.5;
      const y = (e.clientY - bounds.top) / bounds.height - 0.5;
      apply(x, y);
    };

    const onMouseLeave = () => {
      bounds = null;
      reset();
    };

    el.addEventListener('mouseenter', onMouseEnter);
    el.addEventListener('mousemove', onMouseMove);
    el.addEventListener('mouseleave', onMouseLeave);

    return () => {
      el.removeEventListener('mouseenter', onMouseEnter);
      el.removeEventListener('mousemove', onMouseMove);
      el.removeEventListener('mouseleave', onMouseLeave);
    };
  }, [maxTilt, perspective, scale]);

  return ref;
}

export { gsap, ScrollTrigger, Lenis };
