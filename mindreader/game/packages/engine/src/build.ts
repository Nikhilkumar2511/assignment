// Builds an in-memory snapshot from plain arrays. Used by tests, benchmarks and tools; the
// production snapshot comes from pipeline/mrpipe/snapshot.py in the same binary layout.

import { DisplayItem, loadKB, KB, Manifest, ManifestQuestion, quantize } from "./kb";

export interface BuildInput {
  ids: number[];
  prior: number[];
  kind: ("real" | "fictional")[];
  groups: { id: number; key: string; pMatch: number; pOther: number; values: number[][] }[]; // values[e] = value ids
  questions: (Omit<ManifestQuestion, "text"> & { text?: ManifestQuestion["text"]; cells?: [number, number][] })[]; // cells: [entityIndex, p]
  display?: DisplayItem[];
}

export function buildKB(input: BuildInput): KB {
  const n = input.ids.length;
  const parts: { name: string; type: "f32" | "i32" | "u8"; data: ArrayLike<number> }[] = [];
  parts.push({ name: "ids", type: "i32", data: input.ids });
  parts.push({ name: "prior", type: "f32", data: input.prior });
  parts.push({ name: "kind", type: "u8", data: input.kind.map((k) => (k === "real" ? 1 : 2)) });
  for (const g of input.groups) {
    const ptr = new Int32Array(n + 1);
    const val: number[] = [];
    for (let e = 0; e < n; e++) {
      for (const v of g.values[e] ?? []) val.push(v);
      ptr[e + 1] = val.length;
    }
    parts.push({ name: `g${g.id}.ptr`, type: "i32", data: ptr });
    parts.push({ name: `g${g.id}.val`, type: "i32", data: val });
  }
  const qptr = [0];
  const ent: number[] = [];
  const pq: number[] = [];
  for (const q of input.questions) {
    const cells = [...(q.cells ?? [])].sort((a, b) => a[0] - b[0]);
    for (const [e, p] of cells) {
      ent.push(e);
      pq.push(quantize(p));
    }
    qptr.push(ent.length);
  }
  parts.push({ name: "cells.ptr", type: "i32", data: qptr });
  parts.push({ name: "cells.ent", type: "i32", data: ent });
  parts.push({ name: "cells.p", type: "u8", data: pq });

  const size = (p: (typeof parts)[number]) => p.data.length * (p.type === "u8" ? 1 : 4);
  let total = 0;
  for (const p of parts) total += Math.ceil(size(p) / 8) * 8;
  const buffer = new ArrayBuffer(total);
  const arrays: Manifest["arrays"] = {};
  let offset = 0;
  for (const p of parts) {
    const target =
      p.type === "f32" ? new Float32Array(buffer, offset, p.data.length)
      : p.type === "i32" ? new Int32Array(buffer, offset, p.data.length)
      : new Uint8Array(buffer, offset, p.data.length);
    target.set(Array.from(p.data));
    arrays[p.name] = { type: p.type, offset, length: p.data.length };
    offset += Math.ceil(size(p) / 8) * 8;
  }
  const manifest: Manifest = {
    format: 1,
    version: 1,
    source: "built",
    createdAt: new Date(0).toISOString(),
    langs: ["en"],
    entityCount: n,
    groups: input.groups.map(({ id, key, pMatch, pOther }) => ({ id, key, pMatch, pOther })),
    questions: input.questions.map(({ cells: _cells, text, ...q }) => ({ ...q, text: text ?? { en: q.key } })),
    arrays,
  };
  return loadKB(manifest, buffer, input.display ?? null);
}
