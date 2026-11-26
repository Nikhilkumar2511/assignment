// Typeahead over character names in every language. In memory: one normalised string per
// name, scanned in popularity order (snapshot order), so the first hits are the best known.

import { KB, Lang } from "@mindreader/engine";
import { CharacterCard, cardFromDisplay } from "./view";

export function normalize(s: string): string {
  return s
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "") // Latin accents only; Devanagari and other marks stay
    .toLowerCase()
    .replace(/[\s!-/:-@[-`{-~¡-¿ -⁯　-〿・！-／]+/g, " ")
    .trim();
}

export class NameIndex {
  private names: string[] = [];
  private owner: Int32Array = new Int32Array(0);
  private rankOf: Int32Array = new Int32Array(0); // popularity rank of each entity (0 = most popular)

  constructor(private kb: KB) {
    const names: string[] = [];
    const owner: number[] = [];
    kb.display?.forEach((d, i) => {
      const seen = new Set<string>();
      for (const n of Object.values(d.n)) {
        const norm = normalize(n ?? "");
        if (norm && !seen.has(norm)) {
          seen.add(norm);
          names.push(norm);
          owner.push(i);
        }
      }
    });
    this.names = names;
    this.owner = Int32Array.from(owner);
    const idx = Array.from({ length: kb.n }, (_, i) => i).sort((a, b) => kb.prior[b] - kb.prior[a]);
    this.rankOf = new Int32Array(kb.n);
    idx.forEach((e, r) => (this.rankOf[e] = r));
  }

  search(query: string, lang: Lang, limit: number, imageBase: string): CharacterCard[] {
    const q = normalize(query);
    if (q.length < 2 || !this.kb.display) return [];
    const rank = new Map<number, number>(); // entity -> score (lower is better)
    for (let k = 0; k < this.names.length; k++) {
      const name = this.names[k];
      const pos = name.indexOf(q);
      if (pos < 0) continue;
      const score = pos === 0 ? 0 : name[pos - 1] === " " ? 1 : 2;
      const e = this.owner[k];
      const cur = rank.get(e);
      if (cur === undefined || score < cur) rank.set(e, score);
    }
    return [...rank.entries()]
      .sort((a, b) => a[1] - b[1] || this.rankOf[a[0]] - this.rankOf[b[0]])
      .slice(0, limit)
      .map(([e]) => cardFromDisplay(this.kb.display![e], lang, imageBase, this.kb.source));
  }
}
