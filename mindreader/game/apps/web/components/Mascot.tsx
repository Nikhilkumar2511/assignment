"use client";

// "Mira", the mind-reading orb. Original SVG mascot.
// * Moods: idle, thinking, confident (smirk), surprised (gasp), happy, sad
// * Alive: blinks at random, eyes follow the pointer (or glance around when idle),
//   drifts slowly around its spot, small sparkles orbit it
// * Reactions to answers: nod (yes), shake (no), tilt (don't know), giggle (tapped)
// Everything animates transform/opacity only, so it stays smooth on mid-range phones.

import { useEffect, useRef, useState } from "react";

export type MascotState = "idle" | "thinking" | "confident" | "surprised" | "happy" | "sad";
export type Reaction = "nod" | "shake" | "tilt" | "giggle" | null;

const MOUTHS: Record<MascotState, string> = {
  idle: "M42 69 Q50 74 58 69",
  thinking: "M45 70 L56 68",
  confident: "M41 69 Q52 73 59 64",
  surprised: "",
  happy: "M39 66 Q50 80 61 66",
  sad: "M42 72 Q50 66 58 72",
};

export default function Mascot({
  state, reaction = null, reactionKey = 0, onPoke, size = 180,
}: {
  state: MascotState;
  reaction?: Reaction;
  reactionKey?: number;
  onPoke?: () => void;
  size?: number;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const lookRef = useRef<SVGGElement>(null);
  const [blink, setBlink] = useState(false);
  const closed = state === "happy";

  // Random blinking, sometimes a double blink.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const once = (delay: number) => {
      timers.push(setTimeout(() => setBlink(true), delay));
      timers.push(setTimeout(() => setBlink(false), delay + 130));
    };
    const loop = () => {
      timer = setTimeout(() => {
        once(0);
        if (Math.random() < 0.25) once(260);
        loop();
      }, 2200 + Math.random() * 3600);
    };
    loop();
    return () => {
      clearTimeout(timer);
      timers.forEach(clearTimeout);
    };
  }, []);

  // Eyes follow the pointer; with no pointer movement they glance around on their own.
  useEffect(() => {
    let raf = 0;
    let tx = 0, ty = 0, x = 0, y = 0;
    let lastMove = 0;
    const onMove = (e: PointerEvent) => {
      const el = rootRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      const d = Math.hypot(dx, dy) || 1;
      const k = Math.min(1, d / 260);
      tx = (dx / d) * 2.6 * k;
      ty = (dy / d) * 2.2 * k;
      lastMove = performance.now();
    };
    const glance = setInterval(() => {
      if (performance.now() - lastMove > 3000) {
        const looks = [[0, 0], [-2.4, -1], [2.4, -1], [0, 1.8], [-1.5, 1.2], [1.8, 0.5]];
        [tx, ty] = looks[Math.floor(Math.random() * looks.length)];
      }
    }, 1900);
    const tick = () => {
      x += (tx - x) * 0.14;
      y += (ty - y) * 0.14;
      lookRef.current?.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
      raf = requestAnimationFrame(tick);
    };
    addEventListener("pointermove", onMove, { passive: true });
    raf = requestAnimationFrame(tick);
    return () => {
      removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
      clearInterval(glance);
    };
  }, []);

  return (
    <div ref={rootRef} className={`mascot mascot--${state} ${blink ? "is-blinking" : ""}`} style={{ width: size, height: size }}>
      <button type="button" className="mascot__hit" onClick={onPoke} aria-label="Poke Mira" tabIndex={-1} />
      <div className="mascot__wander" aria-hidden="true">
        <div key={reactionKey} className={`mascot__react ${reaction ? `react--${reaction}` : ""}`}>
          <svg viewBox="0 0 100 100" width="100%" height="100%">
            <defs>
              <radialGradient id="orb" cx="38%" cy="32%" r="70%">
                <stop offset="0%" stopColor="#f3edff" />
                <stop offset="35%" stopColor="#b8a2ff" />
                <stop offset="75%" stopColor="#6b45e8" />
                <stop offset="100%" stopColor="#2a1677" />
              </radialGradient>
              <radialGradient id="glow" cx="50%" cy="50%" r="50%">
                <stop offset="60%" stopColor="#9d7bff" stopOpacity="0.55" />
                <stop offset="100%" stopColor="#9d7bff" stopOpacity="0" />
              </radialGradient>
              <linearGradient id="swirl" x1="0" x2="1">
                <stop offset="0%" stopColor="#7df9ff" stopOpacity="0" />
                <stop offset="50%" stopColor="#7df9ff" stopOpacity="0.75" />
                <stop offset="100%" stopColor="#ff8ad8" stopOpacity="0" />
              </linearGradient>
            </defs>
            <circle className="mascot__glow" cx="50" cy="52" r="48" fill="url(#glow)" />
            <g className="mascot__orbit">
              <circle cx="50" cy="8" r="1.6" fill="#7df9ff" />
              <circle cx="92" cy="60" r="1.2" fill="#ff8ad8" />
              <circle cx="14" cy="74" r="1.4" fill="#fff" />
            </g>
            <g className="mascot__body">
              <ellipse cx="50" cy="94" rx="20" ry="3.5" fill="#000" opacity="0.25" className="mascot__shadow" />
              <circle cx="50" cy="52" r="34" fill="url(#orb)" />
              <g className="mascot__swirl">
                <path d="M24 56 C 36 34, 64 34, 76 50" stroke="url(#swirl)" strokeWidth="3" fill="none" strokeLinecap="round" />
                <path d="M28 64 C 42 48, 62 52, 74 60" stroke="url(#swirl)" strokeWidth="2" fill="none" strokeLinecap="round" opacity="0.7" />
              </g>
              <ellipse cx="39" cy="35" rx="9" ry="5" fill="#fff" opacity="0.55" transform="rotate(-25 39 35)" />
              <g className="mascot__brows">
                <path d="M33 41 Q38 38 43 40" stroke="#1d0f52" strokeWidth="2.2" fill="none" strokeLinecap="round" className="brow-l" />
                <path d="M57 40 Q62 38 67 41" stroke="#1d0f52" strokeWidth="2.2" fill="none" strokeLinecap="round" className="brow-r" />
              </g>
              {closed ? (
                <g stroke="#1d0f52" strokeWidth="2.6" fill="none" strokeLinecap="round">
                  <path d="M33 52 Q38 47 43 52" />
                  <path d="M57 52 Q62 47 67 52" />
                </g>
              ) : (
                <g className="mascot__eyes">
                  <ellipse cx="38" cy="52" rx="6" ry="7" fill="#fff" />
                  <ellipse cx="62" cy="52" rx="6" ry="7" fill="#fff" />
                  <g ref={lookRef}>
                    <g className="mascot__pupils">
                      <circle cx="38" cy="53" r="3.3" fill="#1d0f52" />
                      <circle cx="62" cy="53" r="3.3" fill="#1d0f52" />
                      <circle cx="39.3" cy="51.6" r="1.1" fill="#fff" />
                      <circle cx="63.3" cy="51.6" r="1.1" fill="#fff" />
                    </g>
                  </g>
                </g>
              )}
              {state === "surprised" ? (
                <ellipse cx="50" cy="70" rx="4.5" ry="6" fill="#1d0f52" />
              ) : (
                <path d={MOUTHS[state]} stroke="#1d0f52" strokeWidth="2.6" fill="none" strokeLinecap="round" />
              )}
              <circle cx="30" cy="62" r="3.5" fill="#ff8ad8" opacity="0.45" className="mascot__cheek" />
              <circle cx="70" cy="62" r="3.5" fill="#ff8ad8" opacity="0.45" className="mascot__cheek" />
            </g>
            <g className="mascot__sparkles" fill="#fff">
              <path d="M14 22 l2 5 l5 2 l-5 2 l-2 5 l-2 -5 l-5 -2 l5 -2z" />
              <path d="M84 16 l1.5 3.5 l3.5 1.5 l-3.5 1.5 l-1.5 3.5 l-1.5 -3.5 l-3.5 -1.5 l3.5 -1.5z" />
              <path d="M88 70 l1.2 3 l3 1.2 l-3 1.2 l-1.2 3 l-1.2 -3 l-3 -1.2 l3 -1.2z" />
            </g>
          </svg>
        </div>
      </div>
    </div>
  );
}
