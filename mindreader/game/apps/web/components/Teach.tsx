"use client";

// After a loss: "Who were you thinking of?" with typeahead, or submit a new character.

import { useEffect, useId, useRef, useState } from "react";
import type { CharacterCard, GameClient } from "@/lib/client";
import type { Lang, Strings } from "@/lib/i18n";

export default function Teach({
  client, lang, t, onPick, onNew, onSkip, busy,
}: {
  client: GameClient;
  lang: Lang;
  t: Strings;
  onPick: (c: CharacterCard) => void;
  onNew: (name: string, description: string) => void;
  onSkip: () => void;
  busy: boolean;
}) {
  const [q, setQ] = useState("");
  const [desc, setDesc] = useState("");
  const [results, setResults] = useState<CharacterCard[]>([]);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => inputRef.current?.focus(), []);
  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) {
      setResults([]);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      client.search(query, lang).then((r) => live && (setResults(r), setActive(-1)), () => live && setResults([]));
    }, 180);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [q, client, lang]);

  const exact = results.some((r) => r.name.toLowerCase() === q.trim().toLowerCase());
  const canAdd = q.trim().length >= 2 && !exact && client.mode === "online";

  return (
    <div className="teach">
      <label htmlFor="teach-input" className="teach__label">{t.whoWasIt}</label>
      <div className="combo">
        <input
          id="teach-input" ref={inputRef} type="text" value={q} maxLength={60} autoComplete="off"
          placeholder={t.searchPlaceholder} role="combobox" aria-expanded={results.length > 0} aria-controls={listId}
          aria-autocomplete="list" aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(results.length - 1, a + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(-1, a - 1));
            } else if (e.key === "Enter" && active >= 0) {
              e.preventDefault();
              onPick(results[active]);
            }
          }}
        />
        {results.length > 0 && (
          <ul id={listId} role="listbox" className="combo__list">
            {results.map((r, i) => (
              <li key={r.id} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                className={i === active ? "is-active" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => onPick(r)}>
                <strong dir="auto">{r.name}</strong>
                <span dir="auto">{r.description}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {canAdd && (
        <div className="teach__new">
          <input type="text" value={desc} maxLength={140} placeholder={t.description} aria-label={t.description}
            onChange={(e) => setDesc(e.target.value)} />
          <button className="btn btn--primary" disabled={busy} onClick={() => onNew(q.trim(), desc.trim())}>
            {t.notInList(q.trim())}
          </button>
        </div>
      )}
      <button className="btn btn--ghost" onClick={onSkip} disabled={busy}>{t.skip}</button>
    </div>
  );
}
