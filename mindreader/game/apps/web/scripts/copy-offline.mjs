// Copies the seed snapshot into public/offline so the PWA can play without a network.
import { cpSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "..", "data", "seed");
const dst = join(here, "..", "public", "offline");
mkdirSync(dst, { recursive: true });
for (const f of ["manifest.json", "arrays.bin", "display.json"]) cpSync(join(src, f), join(dst, f));
console.log("offline seed copied to public/offline");
