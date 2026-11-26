// Confetti burst and the share card. Hand-written canvas code, no libraries.

import type { CharacterCard } from "./client";
import { initials, palette } from "./art";

export function confetti(count: number): void {
  if (typeof document === "undefined") return;
  const canvas = document.createElement("canvas");
  canvas.className = "confetti";
  canvas.setAttribute("aria-hidden", "true");
  const dpr = Math.min(2, devicePixelRatio || 1);
  canvas.width = innerWidth * dpr;
  canvas.height = innerHeight * dpr;
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d")!;
  ctx.scale(dpr, dpr);
  const colors = ["#ffd166", "#ef476f", "#06d6a0", "#7df9ff", "#b8a2ff", "#ffffff"];
  const parts = Array.from({ length: count }, () => ({
    x: innerWidth / 2 + (Math.random() - 0.5) * 120,
    y: innerHeight * 0.38,
    vx: (Math.random() - 0.5) * 13,
    vy: -Math.random() * 13 - 5,
    r: Math.random() * Math.PI,
    vr: (Math.random() - 0.5) * 0.35,
    w: 6 + Math.random() * 6,
    h: 3 + Math.random() * 4,
    c: colors[(Math.random() * colors.length) | 0],
  }));
  const start = performance.now();
  const step = (now: number) => {
    const t = now - start;
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (const p of parts) {
      p.vy += 0.38;
      p.vx *= 0.99;
      p.x += p.vx;
      p.y += p.vy;
      p.r += p.vr;
      ctx.save();
      ctx.globalAlpha = Math.max(0, 1 - t / 1800);
      ctx.translate(p.x, p.y);
      ctx.rotate(p.r);
      ctx.fillStyle = p.c;
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      ctx.restore();
    }
    if (t < 1800) requestAnimationFrame(step);
    else canvas.remove();
  };
  requestAnimationFrame(step);
}

function wrap(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number) {
  const words = text.split(" ");
  let line = "";
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, y);
      line = w;
      y += lineHeight;
    } else line = test;
  }
  ctx.fillText(line, x, y);
  return y;
}

/** 1080 x 1350 PNG: "MindReader guessed <name> in <n> questions". */
export async function shareCardBlob(card: CharacterCard, headline: string, url: string): Promise<Blob> {
  const W = 1080;
  const H = 1350;
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const ctx = c.getContext("2d")!;
  const bg = ctx.createLinearGradient(0, 0, W, H);
  bg.addColorStop(0, "#140a3a");
  bg.addColorStop(0.55, "#3b1f8f");
  bg.addColorStop(1, "#0b4a5c");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < 140; i++) {
    ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.7})`;
    ctx.beginPath();
    ctx.arc(Math.random() * W, Math.random() * H, Math.random() * 2.2, 0, Math.PI * 2);
    ctx.fill();
  }
  const [a, b] = palette(card.theme, card.name);
  const cx = W / 2;
  const cy = 520;
  const r = 270;
  const g = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
  g.addColorStop(0, a);
  g.addColorStop(1, b);
  ctx.shadowColor = "rgba(157,123,255,0.9)";
  ctx.shadowBlur = 80;
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = "#fff";
  ctx.textAlign = "center";
  ctx.font = "800 190px system-ui, sans-serif";
  ctx.fillText(initials(card.name), cx, cy + 66);
  ctx.font = "700 46px system-ui, sans-serif";
  ctx.fillStyle = "#cbbcff";
  ctx.fillText("MindReader", cx, 140);
  ctx.fillStyle = "#fff";
  ctx.font = "800 84px system-ui, sans-serif";
  const y = wrap(ctx, card.name, cx, 920, W - 140, 92);
  ctx.font = "500 48px system-ui, sans-serif";
  ctx.fillStyle = "#e7e0ff";
  wrap(ctx, headline, cx, y + 90, W - 160, 62);
  ctx.font = "500 36px system-ui, sans-serif";
  ctx.fillStyle = "#9fe9f2";
  ctx.fillText(url.replace(/^https?:\/\//, ""), cx, H - 80);
  return new Promise((resolve) => c.toBlob((blob) => resolve(blob!), "image/png"));
}

/** Web Share with the image when supported; otherwise copy the text and download the image. */
export async function shareResult(card: CharacterCard, text: string, headline: string): Promise<"shared" | "copied"> {
  if (process.env.NEXT_PUBLIC_ARTIFACT === "1") {
    // Embedded build: no Web Share or downloads, so copy the text (inside the click handler).
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* clipboard refused */
    }
    return "copied";
  }
  const url = location.origin;
  const blob = await shareCardBlob(card, headline, url);
  const file = new File([blob], "mindreader.png", { type: "image/png" });
  const data: ShareData = { text, url, files: [file] };
  if (navigator.canShare?.(data)) {
    try {
      await navigator.share(data);
      return "shared";
    } catch {
      /* cancelled: fall through to copy */
    }
  } else if (navigator.share) {
    try {
      await navigator.share({ text, url });
      return "shared";
    } catch {
      /* cancelled */
    }
  }
  try {
    await navigator.clipboard.writeText(`${text} ${url}`);
  } catch {
    /* clipboard blocked: the download still works */
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "mindreader.png";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  return "copied";
}
