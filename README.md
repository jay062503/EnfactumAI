# Enfactum AI Assistant

A self-hosted, permission-aware **AI agent for Enfactum employees**, built to plug into **Enfactum OS** (Laravel / Filament / React / PostgreSQL) as an employee-only application tab. It answers from every kind of knowledge, reads files and images, creates documents, and performs confirmed actions in the OS. Each question is routed to the right source:

| Question type | Source | How |
|---|---|---|
| General knowledge | The LLM itself | Answered directly, lowest latency |
| Public / current information | Web search | Tavily (if key set) or DuckDuckGo, with inline citations |
| Company knowledge | Knowledge base | Role-filtered hybrid search over uploaded policies and manuals |
| Your own files | Chat attachments | Files and images attached with **+**; text in images and scans read by OCR |
| Live company data | Enfactum OS APIs / read-only DB templates | Called with the **employee's own credentials**, so OS RBAC applies |

**Agent capabilities:**
- **Creates files:** PDF, Word, PowerPoint, Excel, CSV, TXT, Markdown, HTML, JSON. Also charts, and images where an image model is available. Each has Preview and Download.
- **Acts in Enfactum OS:** for example apply for leave or create a task. The assistant prepares the action, the employee clicks **Confirm**, and the OS executes it with the employee's token.
- **Reads images and scanned PDFs:** via a vision model or Tesseract OCR.
- **Keeps working in the background:** switch chats, minimise or refresh and the answer continues. The sidebar shows a spinner, then a blue ✓.
- **Fast:** fail-fast timeouts and per-answer timing telemetry. With a fast model, answers complete in under 5 s.

**UI:**
- Streaming answers with clickable citations, plus a status line (spinner → ✓ Completed · time).
- Message actions: copy, edit, regenerate, 👍/👎, read aloud, download as PDF/Word/Markdown.
- Chat URLs (`/c/<id>`), so refresh and back/forward keep the conversation.
- Sidebar with chat search, pinned and recent chats; rename, pin or delete from the ⋯ menu.
- Answer-source modes: Auto / General / Web / Company.
- Attach files or images, by button, drag-and-drop or paste.
- Context-window meter.
- Knowledge base with preview, download and role-based audience.
- Full **Settings**: General, Personalization, Chats & history, Knowledge base, Account, About.
- Employee-only: client accounts are refused.

---

## Quick start

**Requirements:** Python 3.10+ (or Docker) and an API key for a tool-calling LLM.

```bash
cd enfactum-ai-agent
cp .env.example .env          # set LLM_API_KEY=...  (the server reads only .env)
./run.sh                      # Windows: run.bat    Docker: docker compose up -d --build
```

Open <http://localhost:8080>, then go to **Settings → About → Test connection**.

The provider is detected from the key:

| Key prefix | Provider |
|---|---|
| `sk-` | OpenAI |
| `AIza` | Gemini |
| `gsk_` | Groq |
| `sk-or-` | OpenRouter |
| `sk-ant-` | Anthropic |

Ollama and vLLM also work. See `.env.example`.

Local mode signs you in as **one test employee** against a bundled mock Enfactum OS with sample policies. In production, identity, roles and permissions come from Enfactum OS.

Things to try:
- "What is our leave policy?"
- "Show my projects as a chart"
- "Create a PDF status report of my projects"
- "Export the employee directory to Excel"
- "Apply for casual leave next Friday", then Confirm on the card
- attach a photo of a document and ask "what does this say?"

**Speed:** use a fast model (`gpt-4o-mini`, `gpt-4.1-mini`, `gemini-2.0-flash`, Groq Llama) or set `LLM_REASONING_EFFORT=low`. "Thinking" models such as `gemini-2.5-*`, `o3`/`o4` or `gpt-5*` can take 10–60 s. Each answer's timing breakdown is in the logs and appears on hover over the time under the answer. See [Speed](docs/INTEGRATION_GUIDE.md#speed-answers-in-under-5-seconds).

**Upgrading from an earlier version?** Run `pip install -r requirements.txt` again (new libraries were added for PDF, PowerPoint, charts and OCR) and compare your `.env` with `.env.example`, especially `LLM_TIMEOUT_SECONDS`, `WEB_FETCH_PAGES` and `MAX_TOOL_ROUNDS`. Existing data migrates automatically.

## Connecting to Enfactum OS

Everything is in **[docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md)**:

- sign-in: Sanctum token, shared cookie or JWT
- RBAC mapping, including employee vs. client accounts
- live data through OS API tools or read-only SQL templates
- confirmed write actions (agentic)
- loading company documents (with OCR), including bulk sync
- adding the assistant as an **employee-only application tab** in React or Filament (`?embed=app`, `/api/app-manifest`)
- speed tuning, deployment, testing and troubleshooting

No code changes are needed in this repository; it is all configuration.

## Documentation

| Doc | Contents |
|---|---|
| [docs/INTEGRATION_GUIDE.md](docs/INTEGRATION_GUIDE.md) | Step-by-step integration with Enfactum OS, databases and company knowledge |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, request flow, accuracy and performance design |
| [docs/SECURITY.md](docs/SECURITY.md) | Mandatory security constraints and how each is enforced |
| [docs/AGENTIC_ROADMAP.md](docs/AGENTIC_ROADMAP.md) | What the agent can do today (files, actions, background runs) and what comes next |

## Project layout

```text
app/
  main.py            FastAPI app and HTTP API
  agent.py           Tool-calling loop: parallel tools, citations, attachments, artifacts, timing, stop
  runs.py            Background answer runs: survive tab switches/refresh, replay, stop
  prompts.py         Source routing, grounding, security rules, actions, files, personalization
  auth.py            Identity: demo / Laravel Sanctum / JWT → UserContext (employee-only gate)
  llm.py             OpenAI-compatible client, provider detection, vision reader, clear error messages
  attachments.py     Per-chat files and images, generated files
  files/generator.py PDF / DOCX / PPTX / XLSX / CSV / TXT / MD / HTML / JSON builders, charts
  rag/               Parsers, OCR extraction, chunker, embeddings, hybrid BM25+vector index with role filtering
  tools/             web_search, company documents, OS API tools, actions, DB templates, file/chart/image tools
  mock_os.py         Local stand-in for Enfactum OS incl. leave & task endpoints (disabled in production)
static/              UI (no build step)
config/              os_tools.yaml, db_tools.yaml, demo_users.yaml, os_tools.demo.yaml
scripts/             ingest_folder.py (bulk knowledge-base upload)
tests/               pytest suite
```
