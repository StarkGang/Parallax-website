import { useEffect, useRef, useState } from 'react';
import { createMascotStage } from './MascotModel.js';

export default function MascotCanvas({
  facing,
  state,
  gesture,
  paused,
  reducedMotion,
  lowPower,
  dprCap,
  onFail,
  onReady,
}) {
  const hostRef = useRef(null);
  const stageRef = useRef(null);
  const [ready, setReady] = useState(false);
  const callbacks = useRef({ onFail, onReady });
  // Render must stay pure, so the latest callbacks are published after commit.
  useEffect(() => {
    callbacks.current = { onFail, onReady };
  }, [onFail, onReady]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const stage = createMascotStage({
      host,
      dprCap: dprCap ?? (lowPower ? 1 : 1.5),
      antialias: !lowPower,
      reducedMotion,
      onFail: () => callbacks.current.onFail?.(),
      onReady: () => {
        setReady(true);
        callbacks.current.onReady?.();
      },
    });

    if (!stage) return undefined;
    stageRef.current = stage;

    const observer = new ResizeObserver(() => stage.resize());
    observer.observe(host);

    return () => {
      observer.disconnect();
      stage.dispose();
      stageRef.current = null;
    };
    // The stage is intentionally created once. Quality settings are applied to
    // the existing instance through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    stageRef.current?.setFacing(facing);
  }, [facing]);

  useEffect(() => {
    stageRef.current?.setState(state);
  }, [state]);

  useEffect(() => {
    stageRef.current?.setPaused(paused);
  }, [paused]);

  useEffect(() => {
    stageRef.current?.setReducedMotion(reducedMotion);
  }, [reducedMotion]);

  const gestureRef = useRef(gesture);
  useEffect(() => {
    if (gesture === gestureRef.current) return;
    gestureRef.current = gesture;
    if (typeof gesture === 'string') {
      const type = gesture.split('-')[0];
      if (type === 'jump') stageRef.current?.jump?.();
      else if (type === 'wave') stageRef.current?.wave?.();
      else stageRef.current?.playGesture?.(type);
    } else {
      stageRef.current?.wave?.();
    }
  }, [gesture]);

  return (
    <div
      ref={hostRef}
      className={`mascot-canvas${ready ? ' is-ready' : ''}`}
      aria-hidden="true"
    />
  );
}
