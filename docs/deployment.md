# Deployment (M5)

## Docker (local full stack)

```bash
cd travelai
docker compose up -d
```

## Vercel (frontend)

1. Import `travelai/frontend` as project root.
2. Set `NEXT_PUBLIC_API_URL` to Render backend URL.
3. Deploy; ensure SSE proxy timeouts are documented for long plans.

## Render (backend)

1. Web service from `travelai/backend`.
2. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Attach Render Postgres with pgvector; set `DATABASE_URL`, `REDIS_URL`.
4. Environment: `OPENROUTER_API_KEY`, `LANGSMITH_API_KEY`.

## MCP (optional profile)

```bash
docker compose --profile mcp run mcp
```

*M5: wire CI and production env templates.*
