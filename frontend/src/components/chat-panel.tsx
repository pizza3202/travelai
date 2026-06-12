"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ChatPanel() {
  const [message, setMessage] = useState(
    "Plan a 5-day Japan trip under $2500. I like food, nature, and culture."
  );
  const [events, setEvents] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  async function sendMessage() {
    setLoading(true);
    setEvents([]);
    const conversationId = crypto.randomUUID();
    const sessionId = crypto.randomUUID();

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          conversation_id: conversationId,
          session_id: sessionId,
          message,
          departure_city: "San Francisco",
        }),
      });

      if (!res.ok || !res.body) {
        setEvents([`Error: ${res.status} ${res.statusText}`]);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data:")) {
            setEvents((prev) => [...prev, line.slice(5).trim()]);
          }
        }
      }
    } catch (e) {
      setEvents([`Error: ${e}`]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-2xl mx-auto">
      <textarea
        className="w-full min-h-[100px] rounded-md border border-border bg-background p-3 text-sm"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Describe your trip..."
      />
      <Button onClick={sendMessage} disabled={loading}>
        {loading ? "Planning..." : "Plan Trip"}
      </Button>
      <p className="text-xs text-muted-foreground">
        SSE events: trace · delta · card · final · error (M3: rich cards UI)
      </p>
      <pre className="text-xs bg-muted p-4 rounded-lg overflow-auto max-h-96">
        {events.length ? events.join("\n\n") : "No events yet."}
      </pre>
    </div>
  );
}
