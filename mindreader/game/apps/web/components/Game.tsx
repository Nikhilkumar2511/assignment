"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Mascot, { MascotState } from "./Mascot";
import CharacterArt from "./CharacterArt";
import Teach from "./Teach";
import { connect, type CharacterCard, type GameClient, type GameView } from "@/lib/client";
import { deviceClass, deviceId, getPref, prefersReducedMotion, setPref } from "@/lib/device";
import { confetti, shareResult } from "@/lib/effects";
import { detectLang, Lang, LANGS, RTL, STRINGS } from "@/lib/i18n";

const Nebula = dynamic(() => import("./Nebula"), { ssr: false });

type Screen = "landing" | "question" | "reveal" | "won" | "lost" | "done";

interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
}

const ANSWER_KEYS: Record<string, number> = { "1": 0, "2": 4, "3": 2, "4": 1, "5": 3, y: 0, n: 4, d: 2 };

export default function Game() {
  const [lang, setLang] = useState<Lang>("en");
  const [contrast, setContrast] = useState(false);
  const [motion, setMotion] = useState(true);
  const [client, setClient] = useState<GameClient | null>(null);
  const [screen, setScreen] = useState<Screen>("landing");
  const [view, setView] = useState<GameView | null>(null);
  const [mascot, setMascot] = useState<MascotState>("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [shake, setShake] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [won, setWon] = useState<{ card: CharacterCard; questions: number } | null>(null);
  const [install, setInstall] = useState<InstallPrompt | null>(null);
  const [shareNote, setShareNote] = useState<string | null>(null);
  const [pendingStart, setPendingStart] = useState(false);
  const questionRef = useRef<HTMLHeadingElement>(null);
  const viewRef = useRef<GameView | null>(null);
  viewRef.current = view;
  const clientRef = useRef<GameClient | null>(null);
  clientRef.current = client;
  const t = STRINGS[lang];
  const animate = motion && !prefersReducedMotionSafe();

  // ---------------------------------------------------------------- setup
  useEffect(() => {
    setLang((getPref("lang", "") as Lang) || detectLang());
    setContrast(getPref("contrast", "0") === "1");
    setMotion(getPref("motion", "1") === "1");
    connect(deviceId(), deviceClass()).then(setClient, () => setError(STRINGS.en.error));
    const onInstall = (e: Event) => {
      e.preventDefault();
      setInstall(e as InstallPrompt);
    };
    addEventListener("beforeinstallprompt", onInstall);
    const onHide = () => {
      const v = viewRef.current;
      if (v && (v.status === "asking" || v.status === "guessing")) clientRef.current?.abandon(v);
    };
    addEventListener("pagehide", onHide);
    return () => {
      removeEventListener("beforeinstallprompt", onInstall);
      removeEventListener("pagehide", onHide);
    };
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = RTL.includes(lang) ? "rtl" : "ltr";
    setPref("lang", lang);
  }, [lang]);
  useEffect(() => {
    document.documentElement.dataset.contrast = contrast ? "high" : "normal";
    setPref("contrast", contrast ? "1" : "0");
  }, [contrast]);
  useEffect(() => {
    document.documentElement.dataset.motion = motion ? "on" : "off";
    setPref("motion", motion ? "1" : "0");
  }, [motion]);

  // ---------------------------------------------------------------- moves
  const apply = useCallback((v: GameView) => {
    setView(v);
    if (v.status === "asking") {
      setScreen("question");
      setMascot(v.confidence > 0.6 ? "confident" : "idle");
    } else if (v.status === "guessing") {
      setScreen("reveal");
      setFlipped(false);
      setMascot("confident");
      setTimeout(() => {
        setFlipped(true);
        if (animate) confetti(deviceClass() === 0 ? 30 : 60);
      }, 120);
    } else if (v.status === "lost") {
      setScreen("lost");
      setMascot("sad");
    }
  }, [animate]);

  const run = useCallback(async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch {
      setError(t.error);
    } finally {
      setBusy(false);
    }
  }, [busy, t]);

  const start = () => run(async () => {
    if (!client) {
      setPendingStart(true);
      setMascot("thinking");
      return;
    }
    setMessage(null);
    setWon(null);
    setShareNote(null);
    setMascot("thinking");
    apply(await client.start(lang));
  });

  const answer = (code: number) => run(async () => {
    if (!client || !view || view.status !== "asking") return;
    setMascot("thinking");
    apply(await client.answer(view, code));
  });

  const undo = () => run(async () => {
    if (!client || !view?.canUndo) return;
    apply(await client.undo(view));
  });

  const respond = (correct: boolean) => run(async () => {
    if (!client || !view || view.status !== "guessing") return;
    if (correct) {
      const card = view.guess!;
      const next = await client.guess(view, true);
      setView(next);
      setWon({ card, questions: next.questionsAsked });
      setScreen("won");
      setMascot("happy");
      if (animate) confetti(deviceClass() === 0 ? 70 : 150);
      client.finish(next, {}).catch(() => undefined);
      return;
    }
    setMascot("surprised");
    if (animate) {
      setShake(true);
      await new Promise((r) => setTimeout(r, 650));
      setShake(false);
    }
    apply(await client.guess(view, false));
  });

  const finishLost = (opts: { entityId?: number; newCharacter?: { name: string; description: string } }, card?: CharacterCard) =>
    run(async () => {
      if (!client || !view) return;
      await client.finish(view, opts);
      setMessage(card ? t.thanksKnown(card.name) : opts.newCharacter ? t.thanksNew : t.thanksPlain);
      setScreen("done");
      setMascot("happy");
    });

  useEffect(() => {
    if (client && pendingStart) {
      setPendingStart(false);
      start();
    }
  }, [client, pendingStart]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------- keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const k = e.key.toLowerCase();
      if (screen === "question" && k in ANSWER_KEYS) {
        e.preventDefault();
        answer(ANSWER_KEYS[k]);
      } else if (screen === "question" && k === "u") {
        undo();
      } else if (screen === "reveal" && flipped && (k === "y" || k === "n")) {
        respond(k === "y");
      }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    if (screen === "question") questionRef.current?.focus({ preventScroll: true });
  }, [screen, view?.question?.id]);

  // ---------------------------------------------------------------- render
  const pct = Math.round((view?.confidence ?? 0) * 100);
  return (
    <>
      <Nebula enabled={animate} mood={screen === "reveal" || screen === "won" ? 1 : view?.confidence ?? 0} />
      <div className="shell">
        <header className="top">
          <a className="brand" href="/" aria-label="MindReader">MindReader</a>
          <div className="top__controls">
            <label className="sr-only" htmlFor="lang">{t.language}</label>
            <select id="lang" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
            <button className={`chip ${contrast ? "is-on" : ""}`} aria-pressed={contrast} aria-label={t.contrast}
              title={t.contrast} onClick={() => setContrast(!contrast)}>
              <span aria-hidden="true" className="chip__icon">◐</span><span className="chip__text">{t.contrast}</span>
            </button>
            <button className={`chip ${motion ? "is-on" : ""}`} aria-pressed={motion} aria-label={t.motion}
              title={t.motion} onClick={() => setMotion(!motion)}>
              <span aria-hidden="true" className="chip__icon">✦</span><span className="chip__text">{t.motion}</span>
            </button>
          </div>
        </header>

        <main className={`stage stage--${screen}`} aria-busy={busy}>
          <div className="stage__mascot">
            <Mascot state={busy && screen === "question" ? "thinking" : mascot} />
          </div>

          <section className="panel" aria-live="polite">
            {client?.mode === "offline" && process.env.NEXT_PUBLIC_ARTIFACT !== "1" && <p className="note">{t.offline}</p>}
            {error && <p className="note note--error" role="alert">{error}</p>}

            {screen === "landing" && (
              <div className="landing">
                <h1 className="landing__title">MindReader</h1>
                <p className="landing__tagline">{t.tagline}</p>
                <button className="btn btn--primary btn--xl" onClick={start} disabled={busy || pendingStart}>{t.start}</button>
                {client && <p className="landing__count">{t.characters(client.characters.toLocaleString(lang))}</p>}
                {install && (
                  <button className="btn btn--ghost" onClick={() => install.prompt().then(() => setInstall(null))}>{t.install}</button>
                )}
              </div>
            )}

            {screen === "question" && view?.question && (
              <div className="question" key={view.question.id}>
                <p className="question__step">{t.question(view.step)} <span aria-hidden="true">/ {view.maxQuestions}</span></p>
                <h2 className="question__text" ref={questionRef} tabIndex={-1} dir="auto">{view.question.text}</h2>
                <div className="answers" role="group" aria-label={view.question.text}>
                  <button className="btn btn--answer btn--yes" onClick={() => answer(0)} disabled={busy}><kbd>1</kbd>{t.yes}</button>
                  <button className="btn btn--answer btn--no" onClick={() => answer(4)} disabled={busy}><kbd>2</kbd>{t.no}</button>
                  <button className="btn btn--answer" onClick={() => answer(1)} disabled={busy}><kbd>4</kbd>{t.probably}</button>
                  <button className="btn btn--answer" onClick={() => answer(3)} disabled={busy}><kbd>5</kbd>{t.probablyNot}</button>
                  <button className="btn btn--answer btn--wide" onClick={() => answer(2)} disabled={busy}><kbd>3</kbd>{t.dontKnow}</button>
                </div>
                <div className="meter">
                  <div className="meter__label"><span>{t.sure}</span><span>{pct}%</span></div>
                  <div className="meter__track" role="progressbar" aria-label={t.sure} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                    <div className="meter__fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <div className="row">
                  <button className="btn btn--ghost" onClick={undo} disabled={!view.canUndo || busy}>↶ {t.undo}</button>
                  <button className="btn btn--ghost" onClick={() => { setScreen("landing"); setView(null); setMascot("idle"); }}>{t.restart}</button>
                </div>
                <p className="hint">{t.keyboard}</p>
              </div>
            )}

            {screen === "reveal" && view?.guess && (
              <div className="reveal">
                <p className="question__step">{t.guessOf(view.wrongGuesses + 1, view.maxGuesses)}</p>
                <p className="reveal__lead">{t.iThink}</p>
                <div className={`flip ${flipped ? "is-flipped" : ""} ${shake ? "is-shaking" : ""}`}>
                  <div className="flip__inner">
                    <div className="flip__face flip__front" aria-hidden="true"><span>?</span></div>
                    <div className="flip__face flip__back">
                      <div className="glow-burst" aria-hidden="true" />
                      <CharacterArt card={view.guess} photoLabel={t.photo} />
                    </div>
                  </div>
                </div>
                <h2 className="reveal__name" dir="auto">{view.guess.name}</h2>
                <p className="reveal__desc" dir="auto">{view.guess.description}</p>
                <p className="reveal__ask">{t.isItRight}</p>
                <div className="row row--center">
                  <button className="btn btn--primary" onClick={() => respond(true)} disabled={busy || !flipped}>{t.right}</button>
                  <button className="btn btn--secondary" onClick={() => respond(false)} disabled={busy || !flipped}>{t.wrong}</button>
                </div>
              </div>
            )}

            {screen === "won" && won && (
              <div className="won">
                <h2 className="won__title">{t.gotIt}</h2>
                <div className="won__card"><CharacterArt card={won.card} photoLabel={t.photo} /></div>
                <h3 className="reveal__name" dir="auto">{won.card.name}</h3>
                <p className="reveal__desc" dir="auto">{won.card.description}</p>
                <p className="won__line">{t.guessedIn(won.card.name, won.questions)}</p>
                <div className="row row--center">
                  <button className="btn btn--secondary" onClick={async () => {
                    const r = await shareResult(won.card, t.shareText(won.card.name, won.questions), t.guessedIn(won.card.name, won.questions));
                    setShareNote(r === "copied" ? t.shared : null);
                  }}>{t.share}</button>
                  <button className="btn btn--primary" onClick={start}>{t.playAgain}</button>
                </div>
                {shareNote && <p className="note" role="status">{shareNote}</p>}
              </div>
            )}

            {screen === "lost" && client && (
              <div className="lost">
                <h2 className="won__title">{t.youWin}</h2>
                <Teach client={client} lang={lang} t={t} busy={busy}
                  onPick={(c) => finishLost({ entityId: c.id }, c)}
                  onNew={(name, description) => finishLost({ newCharacter: { name, description } })}
                  onSkip={() => finishLost({})} />
              </div>
            )}

            {screen === "done" && (
              <div className="done">
                <p className="won__line">{message}</p>
                <button className="btn btn--primary btn--xl" onClick={start}>{t.playAgain}</button>
              </div>
            )}
          </section>
        </main>

        <footer className="foot">
          {process.env.NEXT_PUBLIC_ARTIFACT !== "1" && (
            <>
              <a href="/about">{t.about}</a>
              <a href="/takedown">{t.takedown}</a>
            </>
          )}
          <span>Data: <a href="https://www.wikidata.org" rel="noopener noreferrer">Wikidata</a> (CC0), Wikipedia, Wikimedia Commons</span>
        </footer>
      </div>
    </>
  );
}

function prefersReducedMotionSafe() {
  return typeof window !== "undefined" && prefersReducedMotion();
}
