"use client";

// The character's picture: a licensed Commons photo (AVIF/WebP, 256 and 512 px) with
// attribution, or a generated card (silhouette, initials, franchise colours) when there is
// no free image, which is the case for most fictional characters.

import { useState } from "react";
import type { CharacterCard } from "@/lib/client";
import { initials, palette } from "@/lib/art";

export function GeneratedArt({ card, size = 512 }: { card: CharacterCard; size?: number }) {
  const [a, b] = palette(card.theme, card.name);
  const id = `g${card.id}`;
  const fictional = card.kind === "fictional";
  return (
    <svg viewBox="0 0 200 200" width={size} height={size} role="img" aria-label={card.name} className="art-generated">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={a} />
          <stop offset="100%" stopColor={b} />
        </linearGradient>
        <radialGradient id={`${id}l`} cx="50%" cy="35%" r="60%">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="200" height="200" fill={`url(#${id})`} />
      <rect width="200" height="200" fill={`url(#${id}l)`} />
      <g fill="#fff" opacity="0.13">
        {[...Array(14)].map((_, i) => (
          <circle key={i} cx={(i * 47) % 200} cy={(i * 83) % 200} r={(i % 3) + 1.2} />
        ))}
      </g>
      <g fill="#000" opacity="0.32">
        <circle cx="100" cy="78" r="34" />
        <path d="M40 200 C 44 140, 72 118, 100 118 C 128 118, 156 140, 160 200 Z" />
        {fictional && <path d="M100 26 l6 14 l15 2 l-11 10 l3 15 l-13 -8 l-13 8 l3 -15 l-11 -10 l15 -2z" opacity="0.9" />}
      </g>
      <text x="100" y="178" textAnchor="middle" fontSize="40" fontWeight="800" fill="#fff"
        fontFamily="system-ui, sans-serif" style={{ letterSpacing: 2 }}>
        {initials(card.name)}
      </text>
    </svg>
  );
}

export default function CharacterArt({ card, photoLabel }: { card: CharacterCard; photoLabel: string }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const img = card.image;
  return (
    <figure className="art">
      <div className="art__frame">
        {(!img || failed) && <GeneratedArt card={card} />}
        {img && !failed && (
          <picture>
            <source type="image/avif" srcSet={`${img.avif[256]} 256w, ${img.avif[512]} 512w`} sizes="(max-width: 600px) 70vw, 320px" />
            <source type="image/webp" srcSet={`${img.webp[256]} 256w, ${img.webp[512]} 512w`} sizes="(max-width: 600px) 70vw, 320px" />
            <img src={img.webp[512]} alt={card.name} className={`art__photo ${loaded ? "is-loaded" : ""}`}
              onLoad={() => setLoaded(true)} onError={() => setFailed(true)} decoding="async" />
          </picture>
        )}
      </div>
      {img && !failed && (
        <figcaption className="art__credit">
          {photoLabel}: {img.creditUrl ? <a href={img.creditUrl} target="_blank" rel="noopener noreferrer">{img.author ?? "Wikimedia Commons"}</a> : img.author}
          {img.license && (
            <>
              {", "}
              {img.licenseUrl ? <a href={img.licenseUrl} target="_blank" rel="noopener noreferrer license">{img.license}</a> : img.license}
            </>
          )}
        </figcaption>
      )}
    </figure>
  );
}
