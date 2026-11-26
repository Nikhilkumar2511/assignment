// The spec's "1,000-character sample": a synthetic knowledge base shaped like the Wikidata
// build (attribute groups with p_match / p_other, unknown values, trait cells, a long-tail
// popularity prior), played by simulated players who sometimes answer wrongly.

import { describe, expect, it } from "vitest";
import { playGame } from "./helpers";
import { synthetic } from "./synthetic";

describe("1,000-character synthetic sample", () => {
  const kb = synthetic(1000);

  it("guesses popular characters (top 20%) within 20 questions at least 80% of the time, with 5% noise", () => {
    let ok = 0;
    let total = 0;
    for (let e = 0; e < 200; e += 2) {
      const r = playGame(kb, e, 0.05, e + 7);
      if (r.won && r.questions <= 20) ok++;
      total++;
    }
    expect(ok / total).toBeGreaterThanOrEqual(0.8);
  });

  it("wins at least 80% overall within the 40-question limit, with 5% noise", () => {
    let wins = 0;
    let total = 0;
    const qs: number[] = [];
    for (let e = 0; e < 1000; e += 5) {
      const r = playGame(kb, e, 0.05, e + 3);
      wins += r.won ? 1 : 0;
      qs.push(r.questions);
      total++;
    }
    expect(wins / total).toBeGreaterThanOrEqual(0.8);
    expect(Math.max(...qs)).toBeLessThanOrEqual(40);
  });
});
