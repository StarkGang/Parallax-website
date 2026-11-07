import { useEffect, useRef } from 'react';
import { gsap } from '../lib/motion.js';
import { MascotEasterEggBubble, useMascotEasterEgg } from './MascotEasterEgg.jsx';
import './PageScene.css';

/**
 * Page hero built as a stack of depth layers: far artwork, the page title in
 * the middle distance, and the character cut-out in front. The three layers
 * scrub at different speeds against scroll, so the heading belongs to the
 * scene instead of sitting in its own band above it.
 */
export default function PageScene({ bg, mascot, wide = false, children }) {
  const sceneRef = useRef(null);
  const { message, onMascotTap } = useMascotEasterEgg();

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;

    const hero = scene.closest('.page-scene-hero') || scene;

    const ctx = gsap.context(() => {
      const trigger = { trigger: hero, start: 'top top', end: 'bottom top', scrub: true };

      gsap.fromTo(
        '.page-scene-bg',
        { yPercent: -6, scale: 1.08 },
        { yPercent: 6, scale: 1.08, ease: 'none', scrollTrigger: trigger },
      );
      gsap.fromTo(
        '.page-scene-title-layer',
        { yPercent: 0 },
        { yPercent: -10, ease: 'none', scrollTrigger: trigger },
      );
      gsap.fromTo(
        '.page-scene-mascot',
        { yPercent: 7 },
        { yPercent: -22, ease: 'none', scrollTrigger: trigger },
      );
    }, scene);

    return () => ctx.revert();
  }, []);

  return (
    <section className="page-scene-hero">
      <div className="page-scene" ref={sceneRef}>
        <div className="page-scene-bg" aria-hidden="true">
          <img src={bg} alt="" decoding="async" />
        </div>
        <div className="page-scene-veil" aria-hidden="true" />
        <div className="page-scene-title-layer">{children}</div>
        <div
          className={wide ? 'page-scene-mascot is-wide' : 'page-scene-mascot'}
          onClick={onMascotTap}
        >
          <img src={mascot} alt="" decoding="async" />
          <MascotEasterEggBubble message={message} />
        </div>
        <div className="page-scene-fade" aria-hidden="true" />
      </div>
    </section>
  );
}
