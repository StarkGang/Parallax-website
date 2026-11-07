import { useEffect, useRef, useState } from 'react';

const LOGO = `${import.meta.env.BASE_URL}images/Parallax Brochure Design Assets/Parallax Design Utilities/logos/logo.webp`;

const PARALLAX_LOGS = [
  '[eth0] LINK_ESTABLISHED',
  'node_1 [NSSCE_PALAKKAD]',
  'node_2 [CONVENTION_CORE]',
  'subsys [PASS_ALLOCATOR]',
  'subsys [BIOMETRIC_AUTH]',
  'feed_1 [LIVE_TELEMETRY]',
  'cache  [RAM_L1_EDGE_READY]',
  'subsys [ALL_SYSTEMS_GO]',
];

const PARALLAX_RESOURCES = [
  'parallax.core.kernel',
  'parallax.network.nssce_node',
  'parallax.identity.pass_matrix',
  'parallax.events.hackathon_24h',
  'parallax.events.coding_sprint',
  'parallax.events.paper_presentation',
  'parallax.events.circuit_debugging',
  'samaritan.parallax.online',
];

export function SamaritanBootLoader({ onComplete, isReady = true }) {
  // Never start paneWidth at 50% to prevent full-screen black occlusion on slow/laggy browsers
  const [phase, setPhase] = useState('loading');
  const [progress, setProgress] = useState(12);
  const [currentResource, setCurrentResource] = useState(PARALLAX_RESOURCES[0]);
  const [logs, setLogs] = useState(['[eth0] LINK_ESTABLISHED']);
  const [blinkCursor, setBlinkCursor] = useState(true);
  const [paneWidth, setPaneWidth] = useState('20%');
  const finishedRef = useRef(false);

  // Blinking cursor effect for LOADING _
  useEffect(() => {
    const curInterval = setInterval(() => {
      setBlinkCursor((b) => !b);
    }, 320);
    return () => clearInterval(curInterval);
  }, []);

  // Streaming log lines based on progress
  useEffect(() => {
    const logIdx = Math.min(
      PARALLAX_LOGS.length - 1,
      Math.floor((progress / 100) * PARALLAX_LOGS.length)
    );
    const newLogs = PARALLAX_LOGS.slice(0, logIdx + 1);
    setLogs(newLogs);

    const resIdx = Math.min(
      PARALLAX_RESOURCES.length - 1,
      Math.floor((progress / 100) * PARALLAX_RESOURCES.length)
    );
    setCurrentResource(PARALLAX_RESOURCES[resIdx]);
  }, [progress]);

  // Smooth realistic progress leading towards readiness
  useEffect(() => {
    if (finishedRef.current) return;

    let timer = null;
    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }

        // If backend / data is ready, accelerate swiftly to 100
        if (isReady) {
          const next = prev + 24;
          return next >= 100 ? 100 : next;
        }

        // If still waiting on real network response, advance smoothly up to 86%
        if (prev < 86) {
          return prev + Math.floor(Math.random() * 6 + 3);
        }

        return prev;
      });
    }, 60);

    // Fallback safety: never keep the user waiting more than 2s, whatever the network does.
    const safety = setTimeout(() => {
      setProgress(100);
    }, 2000);

    return () => {
      clearInterval(interval);
      clearTimeout(safety);
      if (timer) clearTimeout(timer);
    };
  }, [isReady]);

  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  // Completion choreography. The timers live inside the effect so a re-render
  // (including React's development double-mount) can never strand the overlay
  // on "connection established" with the site unreachable behind it.
  useEffect(() => {
    if (progress < 100) return undefined;

    setPhase('connected');
    const timers = [
      setTimeout(() => setPhase('command'), 220),
      setTimeout(() => {
        setPhase('unveiling');
        setPaneWidth('0%');
      }, 620),
      setTimeout(() => {
        setPhase('done');
        onCompleteRef.current?.();
      }, 840),
    ];

    return () => timers.forEach((timer) => clearTimeout(timer));
  }, [progress]);

  // Emergency skip handler (user clicks or hits escape to enter immediately)
  const handleQuickSkip = () => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    setPhase('unveiling');
    setPaneWidth('0%');
    setTimeout(() => {
      setPhase('done');
      onCompleteRef.current?.();
    }, 160);
  };

  if (phase === 'done') return null;

  return (
    <div
      className={`samaritan-boot-screen ${phase === 'unveiling' ? 'fade-out' : ''}`}
      onClick={handleQuickSkip}
      role="region"
      aria-label="System Initializing"
    >
      {/* Left Pane (Aperture shutter) */}
      <div
        className="samaritan-pane samaritan-pane-left"
        style={{ width: paneWidth }}
      >
        <div className="samaritan-overlay-cap left-cap" />
        <div className="samaritan-boot-log">
          {logs.map((line, idx) => (
            <div key={idx} className="samaritan-log-line">
              <span className="samaritan-bracket">[</span>
              <span className="samaritan-log-num">{idx < 10 ? ` 0${idx}` : idx}</span>
              <span className="samaritan-bracket">]</span>
              <span className="samaritan-log-text">{line}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Center Main Display Pane */}
      <div className="samaritan-pane-center">
        {/* Phase: Loading */}
        {phase === 'loading' && (
          <div className="samaritan-loader-box">
            {/* Parallax Convention Logo */}
            <div className="samaritan-brand-lockup">
              <img src={LOGO} alt="PARALLAX" className="samaritan-brand-logo" />
              <div className="samaritan-brand-sub">
                ISTE STUDENT CHAPTER · NSS COLLEGE OF ENGINEERING, PALAKKAD
              </div>
            </div>

            {/* Inverted Loading Badge */}
            <div className="samaritan-badge-row">
              <span className="samaritan-invert-badge">
                INITIALIZING SYSTEM <span className="samaritan-cursor">{blinkCursor ? '_' : ' '}</span>
              </span>
            </div>

            {/* Cycling Resource Stream */}
            <div className="samaritan-resource-name">{currentResource}</div>

            {/* Clean Progress Bar Container */}
            <div className="samaritan-bar-wrap">
              <div
                className="samaritan-bar-fill"
                style={{ width: `${progress}%` }}
              />
            </div>

            <div className="samaritan-pct-label">{progress}%</div>
          </div>
        )}

        {/* Phase: Connected */}
        {phase === 'connected' && (
          <div className="samaritan-connected-box">
            <span className="samaritan-invert-badge large">
              CONNECTION ESTABLISHED
            </span>
          </div>
        )}

        {(phase === 'command' || phase === 'unveiling') && (
          <div className="samaritan-command-box">
            <div className="samaritan-message-container">
              <img src={LOGO} alt="PARALLAX" className="samaritan-command-logo" />
              <hr className="samaritan-command-hr" />
            </div>

            <div className="samaritan-marker">
              <span className="samaritan-triangle">&#9650;</span>
            </div>

            <div className="samaritan-command-sub">
              DEVELOPED BY FRINGE LABS 
            </div>

            <div className="samaritan-command-kicker">
              ALL SYSTEMS ONLINE // SESSION INTEGRITY VERIFIED
            </div>
          </div>
        )}
      </div>

      {/* Right Pane (Aperture shutter) */}
      <div
        className="samaritan-pane samaritan-pane-right"
        style={{ width: paneWidth }}
      >
        <div className="samaritan-overlay-cap right-cap" />
        <div className="samaritan-right-decor">
          <div className="samaritan-sys-tag">ISTE NSSCE NODE</div>
          <div className="samaritan-sys-sub">PARALLAX v4.8</div>
        </div>
      </div>
    </div>
  );
}
