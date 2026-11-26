import { buildKB, BuildInput, KB, rng } from "../src";

export function synthetic(n: number, seed = 1, scale = 1): KB {
  const r = rng(seed);
  const pick = (k: number, skew = 2) => Math.floor(Math.pow(r(), skew) * k);
  const groupSpecs = [
    { id: 1, key: "kind", card: 2, known: 1, pMatch: 0.97, pOther: 0.03 },
    { id: 2, key: "gender", card: 3, known: 0.98, pMatch: 0.95, pOther: 0.04 },
    { id: 4, key: "decade", card: 20, known: 0.8, pMatch: 0.95, pOther: 0.05 },
    { id: 5, key: "region", card: 10, known: 0.9, pMatch: 0.93, pOther: 0.08 },
    { id: 6, key: "country", card: 60 * scale, known: 0.85, pMatch: 0.93, pOther: 0.08 },
    { id: 7, key: "occupation", card: 80 * scale, known: 0.8, pMatch: 0.92, pOther: 0.12 },
    { id: 19, key: "franchise", card: 120 * scale, known: 0.4, pMatch: 0.95, pOther: 0.06 },
    { id: 22, key: "creator", card: 90 * scale, known: 0.3, pMatch: 0.9, pOther: 0.08 },
  ];
  const groups: BuildInput["groups"] = groupSpecs.map((g) => ({ ...g, values: [] as number[][] }));
  const kind: ("real" | "fictional")[] = [];
  for (let e = 0; e < n; e++) {
    kind.push(r() < 0.7 ? "real" : "fictional");
    groupSpecs.forEach((g, gi) => {
      const vals: number[] = [];
      if (g.key === "kind") vals.push(kind[e] === "real" ? 1 : 2);
      else if (r() < g.known) {
        vals.push(g.id * 1000 + pick(g.card));
        if (g.key === "occupation" && r() < 0.3) vals.push(g.id * 1000 + pick(g.card));
      }
      groups[gi].values.push(vals);
    });
  }
  const questions: BuildInput["questions"] = [];
  let qid = 1;
  for (const g of groupSpecs) {
    for (let v = 0; v < g.card; v++) {
      questions.push({ id: qid++, key: `eq:${g.key}:${v}`, kind: "group", group: g.id, values: [g.id * 1000 + v],
        scope: "all", dup: null });
    }
  }
  // 40 trait questions filled for the 50% most popular characters, as the LLM step does.
  for (let t = 0; t < 40; t++) {
    const cells: [number, number][] = [];
    for (let e = 0; e < n / 2; e++) cells.push([e, r() < 0.2 ? 0.92 : 0.08]);
    questions.push({ id: qid++, key: `trait:${t}`, kind: "cells", group: null, values: null, scope: "all", dup: null, cells });
  }
  const prior = Array.from({ length: n }, (_, e) => Math.log(1 + 50 / (1 + e / 20)));
  return buildKB({ ids: Array.from({ length: n }, (_, e) => 100000 + e), prior, kind, groups, questions });
}

