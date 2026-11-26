import type { Metadata } from "next";
import TakedownForm from "@/components/TakedownForm";

export const metadata: Metadata = { title: "Report an image or entry - MindReader" };

export default function Takedown() {
  return (
    <main className="page">
      <p><a href="/">← Back to the game</a></p>
      <h1>Report an image or entry</h1>
      <p>
        Use this form if a photo or a character entry uses your image or likeness without permission, contains wrong
        information, or should be removed for another reason. We review every request.
      </p>
      <TakedownForm />
    </main>
  );
}
