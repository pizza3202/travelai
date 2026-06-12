import { ChatPanel } from "@/components/chat-panel";

export default function Home() {
  return (
    <main className="min-h-screen p-8">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold tracking-tight">TravelAI</h1>
        <p className="text-muted-foreground mt-2">
          Multi-agent travel planner — capstone
        </p>
      </div>
      <ChatPanel />
    </main>
  );
}
