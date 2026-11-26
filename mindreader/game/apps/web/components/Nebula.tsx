"use client";

// Animated nebula + star field: one WebGL2 fragment shader, no library (about 4 KB).
// Performance governor:
//  * starts after first paint, so it never delays the Start button
//  * 60 fps normally, 30 fps and half resolution on low-end devices
//  * watches real frame intervals; if frames run slow it lowers resolution, then stops
//  * off entirely (static CSS gradient) for reduced motion, low battery, no WebGL2,
//    or when the player turns animations off; paused while the tab is hidden

import { useEffect, useRef } from "react";
import { deviceClass, lowBattery } from "@/lib/device";

const VERT = `#version 300 es
in vec2 p;
void main() { gl_Position = vec4(p, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision mediump float;
uniform vec2 uRes;
uniform float uTime;
uniform float uMood;
out vec4 o;
float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 5; i++) { v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}
void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  float t = uTime * 0.025;
  vec2 q = vec2(fbm(uv * 1.5 + t), fbm(uv * 1.5 - t + 3.1));
  float n = fbm(uv * 2.0 + q * 1.6 + vec2(t * 0.7, -t));
  vec3 deep = vec3(0.025, 0.02, 0.08);
  vec3 violet = vec3(0.40, 0.20, 0.85);
  vec3 teal = vec3(0.05, 0.50, 0.62);
  vec3 rose = vec3(0.85, 0.25, 0.55);
  vec3 col = mix(deep, violet, smoothstep(0.35, 0.9, n));
  col = mix(col, teal, smoothstep(0.55, 0.95, q.x) * 0.5);
  col = mix(col, rose, smoothstep(0.6, 1.0, q.y) * (0.25 + 0.35 * uMood));
  col *= 0.5 + 0.65 * n;
  vec2 sp = uv * 80.0;
  vec2 id = floor(sp);
  vec2 f = fract(sp) - 0.5;
  float h = hash(id);
  vec2 off = (vec2(hash(id + 1.3), hash(id + 7.1)) - 0.5) * 0.6;
  float star = step(0.982, h) * smoothstep(0.13, 0.0, length(f - off));
  star *= 0.55 + 0.45 * sin(uTime * (0.8 + h * 3.0) + h * 40.0);
  col += star * vec3(0.92, 0.9, 1.0);
  col *= 1.0 - 0.38 * dot(uv, uv);
  o = vec4(col, 1.0);
}`;

function compile(gl: WebGL2RenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader error");
  return s;
}

export default function Nebula({ enabled, mood }: { enabled: boolean; mood: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const moodRef = useRef(mood);
  moodRef.current = mood;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !enabled) return;
    let cancelled = false;
    let raf = 0;
    let cleanup = () => {};

    const startTimer = setTimeout(async () => {
      if (cancelled || (await lowBattery())) return;
      const gl = canvas.getContext("webgl2", { antialias: false, alpha: false, powerPreference: "low-power" });
      if (!gl) return;
      let prog: WebGLProgram;
      try {
        prog = gl.createProgram()!;
        gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
        gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
        gl.linkProgram(prog);
        if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
      } catch {
        return;
      }
      gl.useProgram(prog);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, "p");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      const uRes = gl.getUniformLocation(prog, "uRes");
      const uTime = gl.getUniformLocation(prog, "uTime");
      const uMood = gl.getUniformLocation(prog, "uMood");

      const low = deviceClass() === 0;
      const targetFps = low ? 30 : 60;
      const frameMs = 1000 / targetFps;
      const scales = low ? [0.5, 0.35] : [Math.min(1, 1.5 / (devicePixelRatio || 1)), 0.6, 0.4];
      let level = 0;
      let smoothMood = moodRef.current;

      const resize = () => {
        const s = scales[level] * (devicePixelRatio || 1);
        canvas.width = Math.max(1, Math.round(innerWidth * s));
        canvas.height = Math.max(1, Math.round(innerHeight * s));
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.uniform2f(uRes, canvas.width, canvas.height);
      };
      resize();
      addEventListener("resize", resize);

      const t0 = performance.now();
      let last = 0;
      let samples: number[] = [];
      let prevFrame = 0;
      const loop = (now: number) => {
        raf = requestAnimationFrame(loop);
        if (now - last < frameMs - 2) return;
        if (prevFrame) samples.push(now - prevFrame);
        prevFrame = now;
        last = now;
        smoothMood += (moodRef.current - smoothMood) * 0.05;
        gl.uniform1f(uTime, (now - t0) / 1000);
        gl.uniform1f(uMood, smoothMood);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        if (canvas.style.opacity !== "1") canvas.style.opacity = "1";
        if (samples.length >= 90) {
          const avg = samples.reduce((a, b) => a + b, 0) / samples.length;
          samples = [];
          if (avg > frameMs * 1.6) {
            level++;
            if (level >= scales.length) {
              cancelAnimationFrame(raf);
              canvas.style.opacity = "0"; // fall back to the static gradient
              return;
            }
            resize();
          }
        }
      };
      const onVisibility = () => {
        cancelAnimationFrame(raf);
        prevFrame = 0;
        samples = [];
        if (document.visibilityState === "visible") raf = requestAnimationFrame(loop);
      };
      document.addEventListener("visibilitychange", onVisibility);
      raf = requestAnimationFrame(loop);
      cleanup = () => {
        cancelAnimationFrame(raf);
        removeEventListener("resize", resize);
        document.removeEventListener("visibilitychange", onVisibility);
        gl.getExtension("WEBGL_lose_context")?.loseContext();
      };
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      cleanup();
      canvas.style.opacity = "0";
    };
  }, [enabled]);

  return <canvas ref={canvasRef} className="nebula" aria-hidden="true" />;
}
