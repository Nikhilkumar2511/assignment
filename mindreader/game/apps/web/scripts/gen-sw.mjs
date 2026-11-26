// Writes out/sw.js with a precache list of the built app shell and a version hash, so a
// new deploy replaces the old cache.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "..", "out");
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else files.push(relative(out, p).split("\\").join("/"));
  }
})(out);
const shell = files.filter((f) =>
  /^(_next\/static\/.+\.(js|css|woff2)|index\.html|about\.html|takedown\.html|404\.html|manifest\.webmanifest|icons\/.+|offline\/.+)$/.test(f),
);
const hash = createHash("sha256");
for (const f of shell) hash.update(f).update(readFileSync(join(out, f)));
const version = hash.digest("hex").slice(0, 12);
const urls = shell.map((f) => "/" + f.replace(/index\.html$/, "").replace(/\.html$/, ""));
const template = readFileSync(join(here, "sw.template.js"), "utf8");
writeFileSync(join(out, "sw.js"), template.replace("__VERSION__", version).replace("__PRECACHE__", JSON.stringify(urls)));
console.log(`sw.js: ${urls.length} files precached, version ${version}`);
