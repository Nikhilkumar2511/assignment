// Builds the one-page version of the game for a Claude artifact:
//   dist-artifact/mindreader.html  (CSS and game code inline; React 18 from cdnjs)
//   dist-artifact/seed.bin         (the character snapshot, gzipped)
import { build } from "esbuild";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, "..");
const out = join(web, "dist-artifact");
mkdirSync(out, { recursive: true });

const result = await build({
  entryPoints: [join(web, "artifact", "main.tsx")],
  bundle: true,
  write: false,
  minify: true,
  format: "iife",
  target: "es2020",
  jsx: "transform",
  jsxFactory: "React.createElement",
  jsxFragment: "React.Fragment",
  inject: [join(web, "artifact", "react-inject.js")],
  alias: {
    react: join(web, "artifact", "react-global.js"),
    "react-dom/client": join(web, "artifact", "react-dom-client.js"),
    "next/dynamic": join(web, "artifact", "next-dynamic.js"),
  },
  tsconfig: join(web, "tsconfig.json"),
  define: {
    "process.env.NODE_ENV": '"production"',
    "process.env.NEXT_PUBLIC_MODE": '"local"',
    "process.env.NEXT_PUBLIC_ARTIFACT": '"1"',
    "process.env.NEXT_PUBLIC_API_BASE": '""',
    "process.env.NEXT_PUBLIC_SHARE_URL": JSON.stringify(process.env.SHARE_URL ?? "https://claude.ai/artifact/JwmqfNoKgNGzDXo3kWazGa"),
  },
  logLevel: "warning",
});
const js = result.outputFiles[0].text.replace(/<\/script/gi, "<\\/script");
const css = readFileSync(join(web, "app", "globals.css"), "utf8") + readFileSync(join(web, "artifact", "overrides.css"), "utf8");
const html = `<title>MindReader</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Think of a famous person or character. MindReader asks questions and guesses who it is.">
<style>${css}</style>
<div id="root"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js"></script>
<script>${js}</script>
`;
writeFileSync(join(out, "mindreader.html"), html);

// SNAPSHOT_DIR=/path/to/snapshot builds the page with another character set (e.g. top 30k from Wikidata).
const seedDir = process.env.SNAPSHOT_DIR ?? join(web, "..", "..", "data", "seed");
// Package: gzip( uint32 header length | header JSON {manifest, display} | arrays.bin ).
// About 3 MB for 30,000 characters instead of about 15 MB as base64 JSON.
const header = Buffer.from(JSON.stringify({
  manifest: JSON.parse(readFileSync(join(seedDir, "manifest.json"), "utf8")),
  display: JSON.parse(readFileSync(join(seedDir, "display.json"), "utf8")),
}));
const arrays = readFileSync(join(seedDir, "arrays.bin"));
const len = Buffer.alloc(4);
len.writeUInt32LE(header.length);
const packed = gzipSync(Buffer.concat([len, header, arrays]), { level: 9 });
writeFileSync(join(out, "seed.bin"), packed);
console.log(`mindreader.html ${(html.length / 1024).toFixed(0)} KB, seed.bin ${(packed.length / 1024).toFixed(0)} KB`);
