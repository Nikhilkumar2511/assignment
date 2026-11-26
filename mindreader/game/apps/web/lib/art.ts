// Colours for generated character cards, chosen from the character's theme (franchise,
// occupation or seed tag). Known franchises get their recognisable colours; anything else
// gets a stable colour pair from a hash of the theme name.

const KNOWN: [RegExp, [string, string]][] = [
  [/marvel|avengers|spider|x-men/i, ["#e23636", "#3b1b6b"]],
  [/\bdc\b|batman|superman|justice league/i, ["#0476f2", "#11131f"]],
  [/star.?wars/i, ["#ffd400", "#0b0b14"]],
  [/harry.?potter|wizarding/i, ["#8a1520", "#d3a625"]],
  [/pok[eé]mon/i, ["#ffcb05", "#2a75bb"]],
  [/nintendo|mario|zelda/i, ["#e60012", "#3b0a4f"]],
  [/disney|pixar/i, ["#113ccf", "#6fd3ff"]],
  [/anime|manga|naruto|dragon ball|one piece/i, ["#ff5fa2", "#5b3df5"]],
  [/lord of the rings|lotr|middle-earth/i, ["#6b4f1d", "#c9a227"]],
  [/bollywood|indian cinema|film actor|actor|actress/i, ["#ff7a00", "#8e1d6b"]],
  [/cricket/i, ["#1e9e4a", "#0b4fd7"]],
  [/football|soccer/i, ["#2e7d32", "#c6ff00"]],
  [/basketball|tennis|athlete|boxer|fighter|racing/i, ["#ef6c00", "#1a237e"]],
  [/music|singer|rapper|band/i, ["#8e24aa", "#ff4081"]],
  [/politic|president|prime minister|royal/i, ["#37474f", "#b0bec5"]],
  [/scien|physic|inventor|engineer/i, ["#00acc1", "#283593"]],
  [/writer|author|poet|book/i, ["#5d4037", "#ffb74d"]],
  [/game/i, ["#00c853", "#311b92"]],
  [/myth|deity|god/i, ["#ffb300", "#4a148c"]],
];

function hashHue(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return Math.abs(h) % 360;
}

export function palette(theme: string | null, name: string): [string, string] {
  const key = theme ?? "";
  for (const [re, colors] of KNOWN) if (re.test(key)) return colors;
  const hue = hashHue(key || name);
  return [`hsl(${hue} 70% 52%)`, `hsl(${(hue + 140) % 360} 60% 22%)`];
}

export function initials(name: string): string {
  const words = name.replace(/\(.*?\)/g, "").split(/[\s\-.]+/).filter((w) => /\p{L}/u.test(w));
  if (words.length === 0) return "?";
  const chars = (words.length === 1 ? [words[0]] : [words[0], words[words.length - 1]]).map((w) => [...w][0]);
  return chars.join("").toUpperCase();
}
