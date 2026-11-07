import { useEffect, useRef } from "react";
import "./HudFrame.css";

/**
 * Scalable 12-slice HUD shell (from .reference/scifi-card.html).
 *
 * The artwork is fixed-size slices: corners and crests keep their shape while
 * the thin runs between them stretch. `--s` is derived from the element width
 * so the chrome stays proportional at any size — 1:1 art is 1173 x 1316.
 */
export default function HudFrame({
  as: Tag = "div",
  className = "",
  bodyClassName = "",
  children,
  ...rest
}) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const fit = () => {
      const width = el.clientWidth;
      if (!width) return;
      const s = Math.min(0.5, Math.max(0.14, width / 1173));
      el.style.setProperty("--s", s.toFixed(4));
    };

    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`hud ${className}`.trim()}
      {...rest}
    >
      <div className="hud-art" aria-hidden="true">
        <div className="hud-row hud-top">
          <span className="p-tl" />
          <span className="p-ts1" />
          <span className="p-tc" />
          <span className="p-ts2" />
          <span className="p-tr" />
        </div>
        <div className="hud-row hud-mid">
          <span className="p-ml" />
          <span />
          <span className="p-mr" />
        </div>
        <div className="hud-row hud-bot">
          <span className="p-bl" />
          <span className="p-bs1" />
          <span className="p-bc" />
          <span className="p-bs2" />
          <span className="p-br" />
        </div>
      </div>

      <div className={`hud-body ${bodyClassName}`.trim()}>{children}</div>
    </Tag>
  );
}
