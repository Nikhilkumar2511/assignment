// Loads a knowledge snapshot (see pipeline/mrpipe/snapshot.py for the format) into typed arrays.

export type Lang = "en" | "hi" | "es" | "pt" | "ja" | "fr" | "ar";
export type Scope = "all" | "real" | "fictional";

export interface ManifestQuestion {
  id: number;
  key: string;
  kind: "group" | "cells";
  group: number | null;
  values: number[] | null;
  scope: Scope;
  dup: number | null;
  text: Partial<Record<Lang, string>>;
}

export interface Manifest {
  format: number;
  version: number;
  source: string;
  createdAt: string;
  langs: Lang[];
  entityCount: number;
  groups: { id: number; key: string; pMatch: number; pOther: number }[];
  questions: ManifestQuestion[];
  arrays: Record<string, { type: "f32" | "i32" | "u8"; offset: number; length: number }>;
}

export interface DisplayImage {
  p: string; // storage prefix, e.g. "img/42" -> img/42-256.avif
  a?: string; // author
  l?: string; // licence short name
  lu?: string; // licence url
  c?: string; // credit page
}

export interface DisplayItem {
  id: number;
  k: "real" | "fictional";
  n: Partial<Record<Lang, string>>;
  d: Partial<Record<Lang, string>>;
  t?: string; // theme: franchise, occupation or seed tag
  img?: DisplayImage;
}

export interface Group {
  id: number;
  pMatch: number; // quantized 0..255
  pOther: number;
  ptr: Int32Array;
  val: Int32Array;
}

export interface Question extends ManifestQuestion {
  index: number;
  valueSet: Set<number> | null;
}

export interface KB {
  version: number;
  source: string;
  n: number;
  ids: Int32Array;
  prior: Float32Array;
  kind: Uint8Array;
  questions: Question[];
  questionIndex: Map<number, number>;
  groups: Map<number, Group>;
  cellPtr: Int32Array;
  cellEnt: Int32Array;
  cellP: Uint8Array;
  entityIndex: Map<number, number>;
  // (group id << 0) + value id -> indices of eq questions on that value
  valueQuestions: Map<string, number[]>;
  // questions that are always considered (cells, multi-value "in" questions)
  alwaysCandidates: number[];
  display: DisplayItem[] | null;
}

export const Q_HALF = 128; // quantized 0.5

export function quantize(p: number): number {
  return Math.max(0, Math.min(255, Math.round(p * 255)));
}

function view(buf: ArrayBuffer, spec: { type: string; offset: number; length: number }) {
  switch (spec.type) {
    case "f32":
      return new Float32Array(buf, spec.offset, spec.length);
    case "i32":
      return new Int32Array(buf, spec.offset, spec.length);
    case "u8":
      return new Uint8Array(buf, spec.offset, spec.length);
    default:
      throw new Error(`unknown array type ${spec.type}`);
  }
}

export function loadKB(manifest: Manifest, buffer: ArrayBuffer, display: DisplayItem[] | null = null): KB {
  if (manifest.format !== 1) throw new Error(`unsupported snapshot format ${manifest.format}`);
  const arr = (name: string) => {
    const spec = manifest.arrays[name];
    if (!spec) throw new Error(`snapshot is missing array ${name}`);
    return view(buffer, spec);
  };
  const n = manifest.entityCount;
  const ids = arr("ids") as Int32Array;
  const groups = new Map<number, Group>();
  for (const g of manifest.groups) {
    if (!manifest.arrays[`g${g.id}.ptr`]) continue;
    groups.set(g.id, {
      id: g.id,
      pMatch: quantize(g.pMatch),
      pOther: quantize(g.pOther),
      ptr: arr(`g${g.id}.ptr`) as Int32Array,
      val: arr(`g${g.id}.val`) as Int32Array,
    });
  }
  const questions: Question[] = [];
  const questionIndex = new Map<number, number>();
  const valueQuestions = new Map<string, number[]>();
  const alwaysCandidates: number[] = [];
  manifest.questions.forEach((q, index) => {
    const usable = q.kind === "cells" || (q.group !== null && groups.has(q.group));
    const question: Question = {
      ...q,
      index,
      valueSet: q.kind === "group" && q.values ? new Set(q.values) : null,
    };
    questions.push(question);
    questionIndex.set(q.id, index);
    if (!usable) return;
    if (q.kind === "group" && q.values && q.values.length === 1) {
      const key = `${q.group}:${q.values[0]}`;
      const list = valueQuestions.get(key) ?? [];
      list.push(index);
      valueQuestions.set(key, list);
    } else {
      alwaysCandidates.push(index);
    }
  });
  const entityIndex = new Map<number, number>();
  for (let i = 0; i < n; i++) entityIndex.set(ids[i], i);
  return {
    version: manifest.version,
    source: manifest.source,
    n,
    ids,
    prior: arr("prior") as Float32Array,
    kind: arr("kind") as Uint8Array,
    questions,
    questionIndex,
    groups,
    cellPtr: arr("cells.ptr") as Int32Array,
    cellEnt: arr("cells.ent") as Int32Array,
    cellP: arr("cells.p") as Uint8Array,
    entityIndex,
    valueQuestions,
    alwaysCandidates,
    display,
  };
}

/** Quantized P(yes) of every character for one question, written into `out` (length n). */
export function fillColumn(kb: KB, qi: number, out: Uint8Array): void {
  const q = kb.questions[qi];
  const g = q.kind === "group" && q.group !== null ? kb.groups.get(q.group) : undefined;
  if (g && q.valueSet && q.valueSet.size === 1) {
    // Fast path for the common "is your character from X" question: compare to one value.
    const { ptr, val, pMatch, pOther } = g;
    const v = q.values![0];
    for (let e = 0; e < kb.n; e++) {
      const start = ptr[e];
      const end = ptr[e + 1];
      if (start === end) {
        out[e] = Q_HALF;
        continue;
      }
      let hit = false;
      for (let k = start; k < end; k++) {
        if (val[k] === v) {
          hit = true;
          break;
        }
      }
      out[e] = hit ? pMatch : pOther;
    }
  } else if (g && q.valueSet) {
    const { ptr, val, pMatch, pOther } = g;
    const set = q.valueSet;
    for (let e = 0; e < kb.n; e++) {
      const start = ptr[e];
      const end = ptr[e + 1];
      if (start === end) {
        out[e] = Q_HALF;
        continue;
      }
      let hit = false;
      for (let k = start; k < end; k++) {
        if (set.has(val[k])) {
          hit = true;
          break;
        }
      }
      out[e] = hit ? pMatch : pOther;
    }
  } else {
    out.fill(Q_HALF);
  }
  const end = kb.cellPtr[qi + 1];
  for (let k = kb.cellPtr[qi]; k < end; k++) out[kb.cellEnt[k]] = kb.cellP[k];
}

/** Quantized P(yes) for one character and question. */
export function cell(kb: KB, qi: number, e: number): number {
  // explicit cell first (binary search: entities are ascending within a question)
  let lo = kb.cellPtr[qi];
  let hi = kb.cellPtr[qi + 1] - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const v = kb.cellEnt[mid];
    if (v === e) return kb.cellP[mid];
    if (v < e) lo = mid + 1;
    else hi = mid - 1;
  }
  const q = kb.questions[qi];
  if (q.kind !== "group" || q.group === null || !q.valueSet) return Q_HALF;
  const g = kb.groups.get(q.group);
  if (!g) return Q_HALF;
  const start = g.ptr[e];
  const end = g.ptr[e + 1];
  if (start === end) return Q_HALF;
  for (let k = start; k < end; k++) if (q.valueSet.has(g.val[k])) return g.pMatch;
  return g.pOther;
}
