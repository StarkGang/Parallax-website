import { useEffect, useRef } from 'react';
import Lenis from 'lenis';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

let globalLenis = null;

export function getLenis() {
  return globalLenis;
}

/**
 * Initializes Lenis smooth scrolling and synchronizes it with GSAP's ScrollTrigger.
 */
export function initSmoothScroll() {
  if (typeof window === 'undefined') return () => {};
  
  if (globalLenis) {
    globalLenis.destroy();
  }

  const lenis = new Lenis({
    duration: 1.15,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    smoothWheel: true,
    touchMultiplier: 1.5,
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

    let bounds = null;

    const onMouseEnter = () => {
      bounds = el.getBoundingClientRect();
    };

    const onMouseMove = (e) => {
      if (!bounds) bounds = el.getBoundingClientRect();
      const x = (e.clientX - bounds.left) / bounds.width - 0.5;
      const y = (e.clientY - bounds.top) / bounds.height - 0.5;

      gsap.to(el, {
        rotateX: -y * maxTilt,
        rotateY: x * maxTilt,
        scale,
        transformPerspective: perspective,
        transformStyle: 'preserve-3d',
        ease: 'power1.out',
        duration: 0.25,
      });

      // Update CSS variables for radial glare spotlight
      el.style.setProperty('--mouse-x', `${(x + 0.5) * 100}%`);
      el.style.setProperty('--mouse-y', `${(y + 0.5) * 100}%`);
    };

    const onMouseLeave = () => {
      bounds = null;
      gsap.to(el, {
        rotateX: 0,
        rotateY: 0,
        scale: 1,
        ease: 'power2.out',
        duration: 0.5,
      });
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

