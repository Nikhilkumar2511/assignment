import type { Metadata } from "next";

export const metadata: Metadata = { title: "About MindReader" };

export default function About() {
  return (
    <main className="page">
      <p><a href="/">← Back to the game</a></p>
      <h1>About MindReader</h1>
      <p>
        Think of a famous real person or a fictional character. MindReader asks yes/no questions and, after each answer,
        updates how likely every character is. It picks the question that is expected to narrow the field the most, and
        guesses when one character is very likely. One wrong answer lowers the right character&apos;s score but never
        rules it out.
      </p>
      <h2>Where the data comes from</h2>
      <p>
        Characters and facts come from <a href="https://www.wikidata.org" rel="noopener noreferrer">Wikidata</a>, which is
        published under CC0. Popularity uses the number of <a href="https://www.wikipedia.org" rel="noopener noreferrer">Wikipedia</a>{" "}
        articles about each character. Photos come from <a href="https://commons.wikimedia.org" rel="noopener noreferrer">Wikimedia Commons</a>{" "}
        and are only shown when their licence allows reuse; the author and licence are shown under every photo. Fictional
        characters are shown with a generated card, never with copyrighted artwork.
      </p>
      <h2>Learning</h2>
      <p>
        When you confirm a guess, or tell MindReader who you were thinking of, your answers help it guess better next
        time. New characters are reviewed by a moderator before they can be guessed.
      </p>
      <h2>Privacy</h2>
      <p>
        No account, no ads, no tracking cookies. To measure how well the game works, it stores each finished game&apos;s
        answers, the number of questions, the country (from the connection, country level only) and a rough device class.
        Your browser keeps a random id so repeated games from one device can be weighted fairly; the server only stores a
        keyed hash of it. Your IP address is used for rate limiting and is not stored.
      </p>
      <h2>Images and complaints</h2>
      <p>
        If an image or a character entry is wrong or should not be here, use the <a href="/takedown">report form</a>.
      </p>
    </main>
  );
}
