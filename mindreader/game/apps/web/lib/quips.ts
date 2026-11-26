// What Mira says in her speech bubble. Picked at random, never the same line twice in a row.

export type QuipMood = "start" | "low" | "mid" | "high" | "dontKnow" | "reveal" | "wrong" | "won" | "lost" | "poke";

const QUIPS: Record<QuipMood, string[]> = {
  start: [
    "Think of someone famous. Got it? Let's begin.",
    "Clear your mind. I'm listening.",
    "I already have a feeling about this one...",
    "Picture them clearly. I'll do the rest.",
  ],
  low: ["Hmm, tell me more.", "Interesting...", "Noted.", "Okay, okay...", "Let me think about that.", "Go on..."],
  mid: [
    "I'm starting to see something...",
    "Getting warmer...",
    "The fog is clearing.",
    "Ooh, this is getting interesting.",
    "A few names are floating up...",
  ],
  high: [
    "I think I know who it is!",
    "Almost there...",
    "One or two more and I've got it.",
    "I can feel it!",
    "Don't make that face, I'm close.",
  ],
  dontKnow: ["No worries.", "That's fine, I'll find another way.", "Fair enough!", "Skipping that one."],
  reveal: ["I've got it...", "Drumroll, please...", "Let me read your mind..."],
  wrong: ["What?! I was so sure!", "Hmm, tricky one. Let me keep going.", "You're good at this.", "Okay, new plan."],
  won: ["Too easy!", "I read you like a book.", "Mind: read.", "Another one for Mira!"],
  lost: ["You beat me! Who was it?", "I'm stumped...", "Well played. Teach me?"],
  poke: ["Hey, that tickles!", "Focus on your character!", "I'm thinking, I'm thinking!", "Boop!", "Hee hee!"],
};

let last = "";

export function quip(mood: QuipMood): string {
  const list = QUIPS[mood].filter((q) => q !== last);
  last = list[Math.floor(Math.random() * list.length)];
  return last;
}

export function moodFor(confidence: number): QuipMood {
  return confidence > 0.45 ? "high" : confidence > 0.15 ? "mid" : "low";
}
