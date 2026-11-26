import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { DisplayItem, KB, loadKB, Manifest } from "@mindreader/engine";

export async function loadSnapshot(dir: string): Promise<KB> {
  const [manifestText, bin, displayText] = await Promise.all([
    readFile(join(dir, "manifest.json"), "utf8"),
    readFile(join(dir, "arrays.bin")),
    readFile(join(dir, "display.json"), "utf8"),
  ]);
  const manifest = JSON.parse(manifestText) as Manifest;
  // Copy into a standalone ArrayBuffer so typed-array offsets line up with the file.
  const buffer = bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength) as ArrayBuffer;
  const display = JSON.parse(displayText) as DisplayItem[];
  if (display.length !== manifest.entityCount) {
    throw new Error(`display.json has ${display.length} rows, manifest says ${manifest.entityCount}`);
  }
  return loadKB(manifest, buffer, display);
}

/** Holds the live snapshot; reload() swaps it atomically (SIGHUP or POST /v1/admin/reload). */
export class SnapshotHolder {
  kb!: KB;
  constructor(private dir: string) {}

  async reload(): Promise<KB> {
    this.kb = await loadSnapshot(this.dir);
    return this.kb;
  }
}
