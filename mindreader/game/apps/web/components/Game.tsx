"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Mascot, { MascotState, Reaction } from "./Mascot";
import CharacterArt from "./CharacterArt";
import ShareRow from "./ShareRow";
import Teach from "./Teach";
import { connect, type CharacterCard, type GameClient, type GameView } from "@/lib/client";
import { deviceClass, deviceId, getPref, prefersReducedMotion, setPref } from "@/lib/device";
import { confetti } from "@/lib/effects";
import { STRINGS } from "@/lib/i18n";
import { moodFor, quip } from "@/lib/quips";

const Nebula = dynamic(() => import("./Nebula"), { ssr: false });

type Screen = "landing" | "question" | "reveal" | "won" | "lost" | "done";

interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
}

const ANSWER_KEYS: Record<string, number> = { "1": 0, "2": 4, "3": 2, "4": 1, "5": 3, y: 0, n: 4, d: 2 };
const REACTION_FOR: Reaction[] = ["nod", "nod", "tilt", "shake", "shake"]; // by answer code
const lang = "en" as const;
const t = STRINGS.en;

interface Score {
  mind: number;
  you: number;
}

function loadScore(): Score {
  try {
    const s = JSON.parse(getPref("score", "{}"));
    return { mind: Number(s.mind) || 0, you: Number(s.you) || 0 };
  } catch {
    return { mind: 0, you: 0 };
  }
}

export default function Game() {
  const [contrast, setContrast] = useState(false);
  const [motion, setMotion] = useState(true);
  const [client, setClient] = useState<GameClient | null>(null);
  const [screen, setScreen] = useState<Screen>("landing");
  const [view, setView] = useState<GameView | null>(null);
  const [mascot, setMascot] = useState<MascotState>("idle");
  const [reaction, setReaction] = useState<{ type: Reaction; key: number }>({ type: null, key: 0 });
  const [bubble, setBubble] = useState<{ text: string; key: number }>({ text: "", key: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [shake, setShake] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [won, setWon] = useState<{ card: CharacterCard; questions: number } | null>(null);
  const [install, setInstall] = useState<InstallPrompt | null>(null);
  const [pendingStart, setPendingStart] = useState(false);
  const [score, setScore] = useState<Score>({ mind: 0, you: 0 });
  const questionRef = useRef<HTMLHeadingElement>(null);
  const viewRef = useRef<GameView | null>(null);
  viewRef.current = view;
  const clientRef = useRef<GameClient | null>(null);
  clientRef.current = client;
  const animate = motion && !(typeof window !== "undefined" && prefersReducedMotion());

  const say = useCallback((text: string) => setBubble((b) => ({ text, key: b.key + 1 })), []);
  const react = useCallback((type: Reaction) => setReaction((r) => ({ type, key: r.key + 1 })), []);
  const bump = useCallback((who: keyof Score) => {
    setScore((s) => {
      const next = { ...s, [who]: s[who] + 1 };
      setPref("score", JSON.stringify(next));
      return next;
    });
  }, []);

  // ---------------------------------------------------------------- setup
  useEffect(() => {
    setContrast(getPref("contrast", "0") === "1");
    setMotion(getPref("motion", "1") === "1");
    setScore(loadScore());
    say("Hi, I'm Mira. Think of anyone famous, and I'll guess who it is.");
    connect(deviceId(), deviceClass()).then(setClient, () => setError(t.error));
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
  }, [say]);

  useEffect(() => {
    document.documentElement.lang = "en";
    document.documentElement.dir = "ltr";
  }, []);
  useEffect(() => {
    document.documentElement.dataset.contrast = contrast ? "high" : "normal";
    setPref("contrast", contrast ? "1" : "0");
  }, [contrast]);
  useEffect(() => {
    document.documentElement.dataset.motion = motion ? "on" : "off";
    setPref("motion", motion ? "1" : "0");
  }, [motion]);

  // ---------------------------------------------------------------- moves
  const apply = useCallback(async (v: GameView, lastAnswer?: number) => {
    if (v.status === "guessing") {
      // A short drumroll before the reveal.
      setMascot("thinking");
      say(quip("reveal"));
      if (animate) await new Promise((r) => setTimeout(r, 900));
      setView(v);
      setScreen("reveal");
      setFlipped(false);
      setMascot("confident");
      setTimeout(() => {
        setFlipped(true);
        if (animate) confetti(deviceClass() === 0 ? 30 : 60);
      }, 120);
      return;
    }
    setView(v);
    if (v.status === "asking") {
      setScreen("question");
      setMascot(v.confidence > 0.45 ? "confident" : "idle");
      if (lastAnswer === 2) say(quip("dontKnow"));
      else if (v.questionsAsked === 0) say(quip("start"));
      else if (v.questionsAsked % 2 === 0 || v.confidence > 0.45) say(quip(moodFor(v.confidence)));
    } else if (v.status === "lost") {
      setScreen("lost");
      setMascot("sad");
      say(quip("lost"));
      bump("you");
    }
  }, [animate, say, bump]);

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
  }, [busy]);

  const start = () => run(async () => {
    if (!client) {
      setPendingStart(true);
      setMascot("thinking");
      return;
    }
    setMessage(null);
    setWon(null);
    setMascot("thinking");
    await apply(await client.start(lang));
  });

  useEffect(() => {
    if (client && pendingStart) {
      setPendingStart(false);
      start();
    }
  }, [client, pendingStart]); // eslint-disable-line react-hooks/exhaustive-deps

  const answer = (code: number) => run(async () => {
    if (!client || !view || view.status !== "asking") return;
    react(REACTION_FOR[code]);
    setMascot("thinking");
    await apply(await client.answer(view, code), code);
  });

  const undo = () => run(async () => {
    if (!client || !view?.canUndo) return;
    say("Let's go back one.");
    await apply(await client.undo(view));
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
      say(quip("won"));
      bump("mind");
      if (animate) confetti(deviceClass() === 0 ? 70 : 150);
      client.finish(next, {}).catch(() => undefined);
      return;
    }
    setMascot("surprised");
    react("shake");
    say(quip("wrong"));
    if (animate) {
      setShake(true);
      await new Promise((r) => setTimeout(r, 650));
      setShake(false);
    }
    await apply(await client.guess(view, false));
  });

  const finishLost = (opts: { entityId?: number; newCharacter?: { name: string; description: string } }, card?: CharacterCard) =>
    run(async () => {
      if (!client || !view) return;
      await client.finish(view, opts);
      setMessage(card ? t.thanksKnown(card.name) : opts.newCharacter ? t.thanksNew : t.thanksPlain);
      setScreen("done");
      setMascot("happy");
      say(card ? `${card.name}! I'll remember that.` : "Thanks for playing!");
    });

  const poke = () => {
    react("giggle");
    say(quip("poke"));
  };

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
  const scoreLine = `MindReader ${score.mind} : ${score.you} You`;
  return (
    <>
      <Nebula enabled={animate} mood={screen === "reveal" || screen === "won" ? 1 : view?.confidence ?? 0} />
      <div className="shell">
        <header className="top">
          <a className="brand" href="./" aria-label="MindReader">MindReader</a>
          <div className="top__controls">
            {(score.mind > 0 || score.you > 0) && <span className="score" aria-label={`Score: ${scoreLine}`}>{scoreLine}</span>}
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
            {bubble.text && (
              <p key={bubble.key} className="bubble" aria-hidden="true">{bubble.text}</p>
            )}
            <Mascot state={busy && screen === "question" ? "thinking" : mascot} reaction={reaction.type}
              reactionKey={reaction.key} onPoke={poke} />
          </div>

          <section className="panel" aria-live="polite">
            {client?.mode === "offline" && process.env.NEXT_PUBLIC_ARTIFACT !== "1" && <p className="note">{t.offline}</p>}
            {error && <p className="note note--error" role="alert">{error}</p>}

            {screen === "landing" && (
              <div className="landing">
                <h1 className="landing__title">MindReader</h1>
                <p className="landing__tagline">{t.tagline}</p>
                <button className="btn btn--primary btn--xl" onClick={start} disabled={busy || pendingStart}>{t.start}</button>
                {client && <p className="landing__count">{t.characters(client.characters.toLocaleString("en"))}</p>}
                {install && (
                  <button className="btn btn--ghost" onClick={() => install.prompt().then(() => setInstall(null))}>{t.install}</button>
                )}
              </div>
            )}

            {screen === "question" && view?.question && (
              <div className="question" key={view.question.id}>
                <p className="question__step">{t.question(view.step)}</p>
                <h2 className="question__text" ref={questionRef} tabIndex={-1}>{view.question.text}</h2>
                <div className="answers" role="group" aria-label={view.question.text}>
                  <button className="btn btn--answer btn--yes" onClick={() => answer(0)} disabled={busy}><kbd>1</kbd>{t.yes}</button>
                  <button className="btn btn--answer btn--no" onClick={() => answer(4)} disabled={busy}><kbd>2</kbd>{t.no}</button>
                  <button className="btn btn--answer" onClick={() => answer(1)} disabled={busy}><kbd>4</kbd>{t.probably}</button>
                  <button className="btn btn--answer" onClick={() => answer(3)} disabled={busy}><kbd>5</kbd>{t.probablyNot}</button>
                  <button className="btn btn--answer btn--wide" onClick={() => answer(2)} disabled={busy}><kbd>3</kbd>{t.dontKnow}</button>
                </div>
                <div className="meter">
                  <div className="meter__label"><span>Reading your mind</span><span>{pct}%</span></div>
                  <div className="meter__track" role="progressbar" aria-label={t.sure} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                    <div className="meter__fill" style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <div className="row">
                  <button className="btn btn--ghost" onClick={undo} disabled={!view.canUndo || busy}>↶ {t.undo}</button>
                  <button className="btn btn--ghost" onClick={() => { setScreen("landing"); setView(null); setMascot("idle"); say("Ready when you are."); }}>{t.restart}</button>
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
                <p className="won__score">{scoreLine}</p>
                <button className="btn btn--primary btn--xl" onClick={start}>{t.playAgain}</button>
                <p className="share__label">Challenge your friends</p>
                <ShareRow text={t.shareText(won.card.name, won.questions)} />
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
                <p className="won__score">{scoreLine}</p>
                <button className="btn btn--primary btn--xl" onClick={start}>{t.playAgain}</button>
                <p className="share__label">I beat MindReader. Can you?</p>
                <ShareRow text="I beat MindReader, the mind-reading game. Can you?" />
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
          <span>Data: <a href="https://www.wikidata.org" target="_blank" rel="noopener noreferrer">Wikidata</a> (CC0), Wikipedia, Wikimedia Commons</span>
        </footer>
      </div>
    </>
  );
}
