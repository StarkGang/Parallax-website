import { useEffect, useRef } from "react";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import "./HeroOdyssey.css";

const VERTEX_SRC = `
  attribute vec2 aPosition;
  void main() {
    gl_Position = vec4(aPosition, 0.0, 1.0);
  }
`;

const FRAGMENT_SRC = `
  precision mediump float;
  uniform vec2 iResolution;
  uniform float iTime;
  uniform float uHue;
  uniform float uXOffset;
  uniform float uSpeed;
  uniform float uIntensity;
  uniform float uSize;

  #define OCTAVE_COUNT 8

  vec3 hsv2rgb(vec3 c) {
    vec3 rgb = clamp(abs(mod(c.x * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return c.z * mix(vec3(1.0), rgb, c.y);
  }

  float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * .1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
  }

  mat2 rotate2d(float theta) {
    float c = cos(theta);
    float s = sin(theta);
    return mat2(c, -s, s, c);
  }

  float noise(vec2 p) {
    vec2 ip = floor(p);
    vec2 fp = fract(p);
    vec2 t = smoothstep(0.0, 1.0, fp);
    float a = hash12(ip);
    float b = hash12(ip + vec2(1.0, 0.0));
    float c = hash12(ip + vec2(0.0, 1.0));
    float d = hash12(ip + vec2(1.0, 1.0));
    return mix(mix(a, b, t.x), mix(c, d, t.x), t.y);
  }

  float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    for (int i = 0; i < OCTAVE_COUNT; ++i) {
      value += amplitude * noise(p);
      p = rotate2d(0.45) * p * 2.0;
      amplitude *= 0.5;
    }
    return value;
  }

  void main() {
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    uv = 2.0 * uv - 1.0;
    uv.x *= iResolution.x / iResolution.y;
    uv.x += uXOffset;
    uv += 2.0 * fbm(uv * uSize + 0.8 * iTime * uSpeed) - 1.0;

    float dist = max(abs(uv.x), 0.001);
    vec3 baseColor = hsv2rgb(vec3(uHue / 360.0, 0.7, 0.8));
    vec3 color = baseColor * (0.07 / dist) * uIntensity;
    gl_FragColor = vec4(color, 1.0);
  }
`;

function Lightning({
  hue = 220,
  speed = 0.5,
  intensity = 0.6,
  size = 2,
  xOffset = 0,
}) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const gl = canvas?.getContext("webgl", { antialias: false, alpha: false });
    if (!canvas || !gl) return undefined;

    const compile = (source, type) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error("Hero shader compile error:", gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    };

    const vertexShader = compile(VERTEX_SRC, gl.VERTEX_SHADER);
    const fragmentShader = compile(FRAGMENT_SRC, gl.FRAGMENT_SHADER);
    if (!vertexShader || !fragmentShader) return undefined;

    const program = gl.createProgram();
    if (!program) return undefined;
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("Hero shader link error:", gl.getProgramInfoLog(program));
      return undefined;
    }
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const position = gl.getAttribLocation(program, "aPosition");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    const uniform = (name) => gl.getUniformLocation(program, name);
    const resolution = uniform("iResolution");
    const time = uniform("iTime");
    const hueUniform = uniform("uHue");
    const xOffsetUniform = uniform("uXOffset");
    const speedUniform = uniform("uSpeed");
    const intensityUniform = uniform("uIntensity");
    const sizeUniform = uniform("uSize");
    const start = performance.now();
    let frame = 0;
    let visible = true;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const width = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width === width && canvas.height === height) return;
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    };

    const render = (now) => {
      if (!visible) return;
      resize();
      gl.uniform2f(resolution, canvas.width, canvas.height);
      gl.uniform1f(time, (now - start) / 1000);
      gl.uniform1f(hueUniform, hue);
      gl.uniform1f(xOffsetUniform, xOffset);
      gl.uniform1f(speedUniform, speed);
      gl.uniform1f(intensityUniform, intensity);
      gl.uniform1f(sizeUniform, size);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      frame = requestAnimationFrame(render);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    const visibilityHandler = () => {
      visible = !document.hidden;
      if (visible && !frame) frame = requestAnimationFrame(render);
    };
    document.addEventListener("visibilitychange", visibilityHandler);
    frame = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", visibilityHandler);
      gl.deleteProgram(program);
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
      gl.deleteBuffer(buffer);
    };
  }, [hue, speed, intensity, size, xOffset]);

  return <canvas ref={canvasRef} className="ho-canvas" aria-hidden="true" />;
}

export default function HeroOdyssey({
  title = "Hero Odyssey",
  subtitle = "Lighting Up The Future",
  description = "Explore a convention built for bold ideas, practical engineering, and new perspectives.",
  beamSize = 1.7,
  beamOffset = 0.6,
}) {
  return (
    <section className="ho-root" aria-labelledby="home-hero-title">
      <div className="ho-container">

        <div className="ho-content">
          {/* <div className="ho-pill ho-item" style={{ "--ho-i": 0 }}>
            <span>Join us for the next perspective</span>
            <ArrowRight size={16} aria-hidden="true" />
          </div> */}
          <h1 id="home-hero-title" className="ho-title ho-item" style={{ "--ho-i": 1 }}>
            {title}
          </h1>
          <h2 className="ho-subtitle ho-item" style={{ "--ho-i": 2 }}>
            {subtitle}
          </h2>
          <p className="ho-desc ho-item" style={{ "--ho-i": 3 }}>
            {description}
          </p>
                    {/* Event facts */}
          <div
            className="ho-facts ho-item"
            style={{
              "--ho-i": 5,
              background: "transparent",
              border: "none",
              boxShadow: "none",
              fontSize: "0.72rem",
              letterSpacing: "0.5ch",
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-start",
              whiteSpace: "nowrap"
            }}
            aria-label="Event facts"
          >
            <span className="tf-parallax-fg" style={{ background: "transparent", border: "none", boxShadow: "none", opacity: 0.5, display: "block", whiteSpace: "nowrap" }}>
              Individual &amp; team events
            </span>
            <span className="ho-facts-separator" aria-hidden="true" style={{ display: "none" }}>  •  </span>
            <span className="tf-parallax-fg" style={{ background: "transparent", border: "none", boxShadow: "none", opacity: 0.5, display: "block", whiteSpace: "nowrap" }}>
              2 days together
            </span>
            <span className="ho-facts-separator" aria-hidden="true" style={{ display: "none" }}>  •  </span>
            <span className="tf-parallax-fg" style={{ background: "transparent", border: "none", boxShadow: "none", opacity: 0.5, display: "block", whiteSpace: "nowrap" }}>
              20th & 21st March
            </span>
            <span className="ho-facts-separator" aria-hidden="true" style={{ display: "none" }}>  •  </span>
            <span className="tf-parallax-fg" style={{ background: "transparent", border: "none", boxShadow: "none", opacity: 0.5, display: "block", whiteSpace: "nowrap" }}>
              NSS College Of Engineering, Palakkad
            </span>
          </div>
          <Link to="/events" className="ho-cta ho-item" style={{ "--ho-i": 4 }}>
            Discover the programme
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>

      </div>

      <div className="ho-bg" aria-hidden="true">
        <div className="ho-overlay" />
        <div className="ho-glow" />
        <div className="ho-beam">
          <Lightning size={beamSize} xOffset={beamOffset} />
        </div>
      </div>



    </section>
  );
}
