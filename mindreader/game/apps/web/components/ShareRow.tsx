"use client";

// Share buttons. WhatsApp, X and Facebook are plain links (they work everywhere, including
// embedded pages); "Share" uses the phone's share sheet where the browser allows it.

import { useState } from "react";

const SHARE_URL = process.env.NEXT_PUBLIC_SHARE_URL ?? "";

export default function ShareRow({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const url = SHARE_URL || (typeof location !== "undefined" ? location.origin : "");
  const full = `${text} ${url}`.trim();
  const canNative = typeof navigator !== "undefined" && !!navigator.share && process.env.NEXT_PUBLIC_ARTIFACT !== "1";
  const enc = encodeURIComponent;

  return (
    <div className="share" role="group" aria-label="Share">
      {canNative && (
        <button className="share__btn" onClick={() => navigator.share({ text, url }).catch(() => undefined)}>
          Share
        </button>
      )}
      <a className="share__btn share__btn--wa" href={`https://wa.me/?text=${enc(full)}`} target="_blank" rel="noopener noreferrer">
        WhatsApp
      </a>
      <a className="share__btn share__btn--x" href={`https://twitter.com/intent/tweet?text=${enc(text)}&url=${enc(url)}`}
        target="_blank" rel="noopener noreferrer">
        X
      </a>
      <a className="share__btn share__btn--fb" href={`https://www.facebook.com/sharer/sharer.php?u=${enc(url)}&quote=${enc(text)}`}
        target="_blank" rel="noopener noreferrer">
        Facebook
      </a>
      <button className="share__btn" onClick={() => {
        navigator.clipboard?.writeText(full).then(() => setCopied(true), () => setCopied(false));
      }}>
        {copied ? "Copied!" : "Copy"}
      </button>
    </div>
  );
}
