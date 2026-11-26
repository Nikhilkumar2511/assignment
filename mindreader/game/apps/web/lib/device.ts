// Device capability and preference detection. Nothing here leaves the device except
// the coarse device class (0 low, 1 mid, 2 high) sent with a finished game.

export type DeviceClass = 0 | 1 | 2;

interface NavigatorExtras {
  deviceMemory?: number;
  connection?: { saveData?: boolean; effectiveType?: string };
  getBattery?: () => Promise<{ level: number; charging: boolean }>;
}

export function deviceClass(): DeviceClass {
  if (typeof navigator === "undefined") return 1;
  const nav = navigator as Navigator & NavigatorExtras;
  const mem = nav.deviceMemory ?? 4;
  const cores = nav.hardwareConcurrency ?? 4;
  if (nav.connection?.saveData || mem <= 3 || cores <= 4) return 0;
  if (mem >= 8 && cores >= 8) return 2;
  return 1;
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** True when the battery is low and not charging (Chromium only; elsewhere false). */
export async function lowBattery(): Promise<boolean> {
  const nav = navigator as Navigator & NavigatorExtras;
  if (!nav.getBattery) return false;
  try {
    const b = await nav.getBattery();
    return !b.charging && b.level < 0.2;
  } catch {
    return false;
  }
}

export function deviceId(): string {
  try {
    let id = localStorage.getItem("mr.device");
    if (!id) {
      const bytes = crypto.getRandomValues(new Uint8Array(18));
      id = btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
      localStorage.setItem("mr.device", id);
    }
    return id;
  } catch {
    return "";
  }
}

export function getPref(key: string, fallback: string): string {
  try {
    return localStorage.getItem(`mr.${key}`) ?? fallback;
  } catch {
    return fallback;
  }
}

export function setPref(key: string, value: string): void {
  try {
    localStorage.setItem(`mr.${key}`, value);
  } catch {
    /* private mode: preference lasts for this page only */
  }
}
