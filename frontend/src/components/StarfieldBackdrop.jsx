import { useEffect, useRef } from 'react';


export default function StarfieldBackdrop() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return undefined;

    const reducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let width = window.innerWidth;
    let height = window.innerHeight;
    let dpr = Math.min(window.devicePixelRatio || 1, 1.5);

    const makeRng = (initialSeed) => {
      let seed = initialSeed;
      return () => {
        seed = (seed * 1664525 + 1013904223) % 4294967296;
        return seed / 4294967296;
      };
    };

    const pickStarColor = (r) => {
      if (r < 0.16) return '255, 206, 152'; // warm amber-gold
      if (r < 0.34) return '255, 238, 214'; // warm cream
      if (r > 0.68) return '186, 214, 255'; // cool O/B-type blue-white
      return '244, 248, 255'; // crisp white
    };

    // Offscreen canvas for the static Milky Way dust band + dense pinpoint micro-stars
    const backdropCanvas = document.createElement('canvas');
    const backdropCtx = backdropCanvas.getContext('2d', { alpha: true });

    const renderBackdrop = () => {
      if (!backdropCtx) return;
      backdropCanvas.width = Math.max(1, Math.floor(width * dpr));
      backdropCanvas.height = Math.max(1, Math.floor(height * dpr));
      backdropCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      backdropCtx.clearRect(0, 0, width, height);

      const bRand = makeRng(91027);

      // Subtle diagonal Milky Way galactic band (center-right to upper-left/lower-right sweep)
      const bandAngle = -0.22; // gentle cosmic tilt
      const cx = width * 0.52;
      const cy = height * 0.48;

      backdropCtx.save();
      backdropCtx.translate(cx, cy);
      backdropCtx.rotate(bandAngle);

      const bandLength = Math.hypot(width, height) * 1.15;
      const bandHeight = Math.max(220, height * 0.44);

      // Layered soft galactic glow clouds
      for (let i = 0; i < 38; i += 1) {
        const lx = (bRand() - 0.5) * bandLength;
        const ly = (bRand() - 0.5) * bandHeight * 0.55;
        const rad = 90 + bRand() * 210;
        const warm = bRand() < 0.28;
        const alpha = 0.012 + bRand() * 0.022;
        const grad = backdropCtx.createRadialGradient(lx, ly, 0, lx, ly, rad);
        if (warm) {
          grad.addColorStop(0, `rgba(215, 198, 172, ${alpha.toFixed(4)})`);
          grad.addColorStop(0.55, `rgba(140, 162, 198, ${(alpha * 0.45).toFixed(4)})`);
        } else {
          grad.addColorStop(0, `rgba(165, 192, 232, ${alpha.toFixed(4)})`);
          grad.addColorStop(0.5, `rgba(110, 138, 185, ${(alpha * 0.4).toFixed(4)})`);
        }
        grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
        backdropCtx.fillStyle = grad;
        backdropCtx.beginPath();
        backdropCtx.arc(lx, ly, rad, 0, Math.PI * 2);
        backdropCtx.fill();
      }

      // Subtle dark cosmic dust rifts inside the band for mottled realism
      backdropCtx.globalCompositeOperation = 'destination-out';
      for (let i = 0; i < 18; i += 1) {
        const dx = (bRand() - 0.5) * bandLength * 0.9;
        const dy = (bRand() - 0.5) * bandHeight * 0.28;
        const dr = 45 + bRand() * 115;
        const dGrad = backdropCtx.createRadialGradient(dx, dy, 0, dx, dy, dr);
        dGrad.addColorStop(0, 'rgba(0, 0, 0, 0.38)');
        dGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
        backdropCtx.fillStyle = dGrad;
        backdropCtx.beginPath();
        backdropCtx.arc(dx, dy, dr, 0, Math.PI * 2);
        backdropCtx.fill();
      }
      backdropCtx.restore();
      backdropCtx.globalCompositeOperation = 'source-over';

      // Dense pinpoint micro-star field (~1,100–1,450 tiny background stars)
      const microCount = Math.min(1450, Math.max(750, Math.round((width * height) / 1450)));
      const cosA = Math.cos(bandAngle);
      const sinA = Math.sin(bandAngle);

      for (let i = 0; i < microCount; i += 1) {
        let sx;
        let sy;
        const inBand = bRand() < 0.44;
        if (inBand) {
          // Gaussian-like spread along the galactic band
          const u1 = (bRand() + bRand() + bRand()) / 3 - 0.5;
          const bx = (bRand() - 0.5) * bandLength;
          const by = u1 * bandHeight * 0.9;
          sx = cx + bx * cosA - by * sinA;
          sy = cy + bx * sinA + by * cosA;
        } else {
          sx = bRand() * width;
          sy = bRand() * height;
        }

        if (sx < 0 || sx > width || sy < 0 || sy > height) continue;

        const r = 0.35 + Math.pow(bRand(), 2.6) * 0.72;
        const alpha = (inBand ? 0.22 : 0.16) + Math.pow(bRand(), 2.0) * 0.52;
        const col = pickStarColor(bRand());

        backdropCtx.fillStyle = `rgba(${col}, ${alpha.toFixed(3)})`;
        backdropCtx.beginPath();
        backdropCtx.arc(sx, sy, r, 0, Math.PI * 2);
        backdropCtx.fill();
      }
    };

    // Animated twinkling star field
    const rand = makeRng(42027);
    const starCount = Math.min(260, Math.max(150, Math.round((width * height) / 7800)));
    const stars = Array.from({ length: starCount }, (_, i) => {
      const layer = i % 3;
      const color = pickStarColor(rand());
      const u = Math.max(rand(), 0.015);
      const bright = Math.pow(1 - u, 2.35);
      const isHero = i < 16;

      return {
        x: rand(),
        y: rand(),
        layer,
        isHero,
        depth: layer === 0 ? 0.03 : layer === 1 ? 0.07 : 0.13,
        pointerDepth: layer === 0 ? 3 : layer === 1 ? 7 : 13,
        radius: isHero ? 1.15 + bright * 0.95 : 0.48 + bright * (layer === 2 ? 1.15 : 0.75),
        baseAlpha: isHero ? 0.78 + bright * 0.22 : 0.32 + bright * 0.65,
        speed: 0.9 + rand() * 2.6,
        speed2: 1.7 + rand() * 3.4,
        phase: rand() * Math.PI * 2,
        phase2: rand() * Math.PI * 2,
        color,
      };
    });

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      renderBackdrop();
    };

    resize();

    let targetPx = 0;
    let targetPy = 0;
    let smoothPx = 0;
    let smoothPy = 0;
    let smoothScroll = window.scrollY || 0;

    const onPointerMove = (e) => {
      if (reducedMotion) return;
      targetPx = (e.clientX / Math.max(1, width) - 0.5) * 2;
      targetPy = (e.clientY / Math.max(1, height) - 0.5) * 2;
    };

    window.addEventListener('resize', resize, { passive: true });
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    let rafId = 0;
    const start = performance.now();

    const draw = (now) => {
      rafId = requestAnimationFrame(draw);
      if (document.hidden) return;

      const t = (now - start) * 0.001;
      const scrollY = window.scrollY || window.pageYOffset || 0;

      if (!reducedMotion) {
        smoothScroll += (scrollY - smoothScroll) * 0.14;
        smoothPx += (targetPx - smoothPx) * 0.06;
        smoothPy += (targetPy - smoothPy) * 0.06;
      }

      ctx.clearRect(0, 0, width, height);

      // Draw pre-rendered Milky Way & pinpoint micro-stars
      if (backdropCanvas.width > 0 && backdropCanvas.height > 0) {
        ctx.drawImage(backdropCanvas, 0, 0, width, height);
      }

      // Draw live twinkling stars
      for (let i = 0; i < stars.length; i += 1) {
        const s = stars[i];
        const py = reducedMotion ? 0 : smoothScroll * s.depth + smoothPy * s.pointerDepth;
        const px = reducedMotion ? 0 : smoothPx * s.pointerDepth;

        const sx = (((s.x * width - px) % width) + width) % width;
        const sy = (((s.y * height - py) % height) + height) % height;

        // Multi-harmonic twinkle for organic sparkle
        const wave =
          0.5 +
          0.5 *
            Math.sin(t * s.speed + s.phase) *
            (0.65 + 0.35 * Math.cos(t * s.speed2 + s.phase2));
        const twinkle = reducedMotion ? 1 : 0.32 + 0.68 * Math.pow(wave, 1.3);
        const alpha = Math.min(1, s.baseAlpha * twinkle);

        if (s.isHero) {
          const haloR = s.radius * 3.8;
          const halo = ctx.createRadialGradient(sx, sy, 0, sx, sy, haloR);
          halo.addColorStop(0, `rgba(${s.color}, ${(alpha * 0.42).toFixed(3)})`);
          halo.addColorStop(0.45, `rgba(${s.color}, ${(alpha * 0.12).toFixed(3)})`);
          halo.addColorStop(1, 'rgba(0, 0, 0, 0)');
          ctx.fillStyle = halo;
          ctx.beginPath();
          ctx.arc(sx, sy, haloR, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(sx, sy, s.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${s.color}, ${alpha.toFixed(3)})`;
        ctx.fill();
      }
    };

    if (reducedMotion) {
      draw(performance.now());
      cancelAnimationFrame(rafId);
    } else {
      rafId = requestAnimationFrame(draw);
    }

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointerMove);
    };
  }, []);

  return <canvas ref={canvasRef} className="px-starfield-canvas" aria-hidden="true" />;
}
