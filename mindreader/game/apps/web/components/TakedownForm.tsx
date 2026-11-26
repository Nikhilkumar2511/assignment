"use client";

import { FormEvent, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "";

export default function TakedownForm() {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const entity = String(form.get("entity") ?? "").replace(/^Q/i, "").trim();
    setState("sending");
    try {
      const res = await fetch(`${API}/v1/takedown`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          kind: form.get("kind"),
          entityId: /^\d+$/.test(entity) ? Number(entity) : undefined,
          url: form.get("url") || undefined,
          name: form.get("name"),
          email: form.get("email"),
          details: form.get("details"),
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.message ?? "The request could not be sent.");
      }
      setState("sent");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request could not be sent.");
      setState("error");
    }
  }

  if (state === "sent") return <p className="note" role="status">Thank you. Your request was received and will be reviewed.</p>;
  return (
    <form className="form" onSubmit={submit}>
      <label>
        What is the problem?
        <select name="kind" required defaultValue="image">
          <option value="image">A photo should not be shown</option>
          <option value="likeness">My likeness is used without permission</option>
          <option value="data">The information is wrong</option>
          <option value="other">Something else</option>
        </select>
      </label>
      <label>
        Character name or Wikidata id (optional)
        <input name="entity" maxLength={80} />
      </label>
      <label>
        Link to the image or page (optional)
        <input name="url" type="url" maxLength={500} />
      </label>
      <label>
        Your name
        <input name="name" required minLength={2} maxLength={120} autoComplete="name" />
      </label>
      <label>
        Your email (only used to reply to you)
        <input name="email" type="email" required maxLength={254} autoComplete="email" />
      </label>
      <label>
        Details
        <textarea name="details" required minLength={10} maxLength={4000} rows={6} />
      </label>
      {state === "error" && <p className="note note--error" role="alert">{error}</p>}
      <button className="btn btn--primary" type="submit" disabled={state === "sending"}>Send request</button>
    </form>
  );
}
