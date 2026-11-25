"""The Wikidata class graph (P279) as compact arrays, with closure and ancestor queries."""
from __future__ import annotations

import re

import duckdb
import numpy as np


class ClassGraph:
    def __init__(self, child: np.ndarray, parent: np.ndarray, labels: dict[int, str]):
        self.labels = labels
        # parent -> children (for subclass closure) and child -> parents (for ancestors)
        self._down = self._csr(parent, child)
        self._up = self._csr(child, parent)

    @staticmethod
    def _csr(src: np.ndarray, dst: np.ndarray):
        order = np.argsort(src, kind="stable")
        s, d = src[order], dst[order]
        keys, starts = np.unique(s, return_index=True)
        ends = np.append(starts[1:], len(s))
        return keys, starts, ends, d

    @staticmethod
    def _neighbours(csr, node: int) -> np.ndarray:
        keys, starts, ends, d = csr
        i = np.searchsorted(keys, node)
        if i < len(keys) and keys[i] == node:
            return d[starts[i]:ends[i]]
        return d[:0]

    @classmethod
    def load(cls, pass1_dir: str) -> "ClassGraph":
        con = duckdb.connect()
        edges = con.execute(f"SELECT child, parent FROM read_parquet('{pass1_dir}/class_edges/*.parquet')").fetchnumpy()
        labs = con.execute(f"SELECT qid, en FROM read_parquet('{pass1_dir}/class_labels/*.parquet') WHERE en IS NOT NULL").fetchall()
        return cls(edges["child"].astype(np.int64), edges["parent"].astype(np.int64), dict(labs))

    def descendants(self, roots: list[int]) -> set[int]:
        """All classes below the roots, roots included."""
        seen = set(int(r) for r in roots)
        stack = list(seen)
        while stack:
            node = stack.pop()
            for child in self._neighbours(self._down, node):
                c = int(child)
                if c not in seen:
                    seen.add(c)
                    stack.append(c)
        return seen

    def ancestors(self, node: int, depth: int, stop: set[int] | frozenset = frozenset()) -> list[tuple[int, int]]:
        """(ancestor, distance) pairs up to `depth` levels above `node`, nearest first.
        Classes in `stop` are neither returned nor climbed through."""
        out, frontier, seen = [], [int(node)], {int(node)}
        for dist in range(1, depth + 1):
            nxt = []
            for n in frontier:
                for parent in self._neighbours(self._up, n):
                    p = int(parent)
                    if p not in seen and p not in stop:
                        seen.add(p)
                        out.append((p, dist))
                        nxt.append(p)
            frontier = nxt
            if not frontier:
                break
        return out

    def label(self, qid: int) -> str | None:
        return self.labels.get(int(qid))

    def find_by_label(self, patterns: list[str]) -> dict[int, str]:
        regs = [re.compile(p, re.I) for p in patterns]
        return {q: lab for q, lab in self.labels.items() if any(r.search(lab) for r in regs)}

    def match_patterns(self, classes: list[int], patterns: list[tuple[str, str]], depth: int,
                       stop: set[int] | None = None) -> set[str]:
        """Values whose regex matches the label of any class or ancestor (up to depth)."""
        compiled = [(re.compile(p, re.I), v) for p, v in patterns]
        found: set[str] = set()
        candidates = []
        for c in classes:
            candidates.append(int(c))
            candidates.extend(a for a, _ in self.ancestors(c, depth) if not stop or a not in stop)
        for c in candidates:
            lab = self.label(c)
            if not lab:
                continue
            for reg, value in compiled:
                if reg.search(lab):
                    found.add(value)
        return found
