# From knowledge assistant to agentic AI

## Where it is today (phase 1 implemented)

The assistant is an **agent**, not only retrieval. For each request it:

1. decides which sources it needs (LLM, web, documents, attachments, OS tools, DB templates),
2. calls several tools in parallel and iterates (up to `MAX_TOOL_ROUNDS`),
3. **produces outputs**: PDF / Word / PowerPoint / Excel / CSV files, charts and images,
4. **acts in Enfactum OS** through confirmed actions (for example apply for leave or create a task),
5. writes a cited answer, and keeps working in the background if the employee leaves the chat.

| Capability | Status | Where |
|---|---|---|
| Multi-source tool use, parallel, multi-round | Done | `app/agent.py` |
| Read images and scanned PDFs (OCR) | Done | `app/rag/extract.py` |
| Create files, charts, images | Done | `app/tools/files.py`, `app/files/generator.py` |
| Actions with human confirmation | Done | `app/tools/actions.py`, `actions:` in the OS tools YAML |
| Background execution, resume, stop | Done | `app/runs.py` |
| Edit / regenerate / feedback | Done | `POST /api/chat` (`replace_from_message_id`), `/api/messages/{id}/feedback` |
| Task mode with visible plan | Next | |
| Scheduled / recurring jobs | Next | |
| Long-term memory | Next | |
| Approval workflows | Later | |

## The action safety model (in place)

```text
LLM calls an action tool ─► server validates args (JSON Schema, undeclared fields dropped)
                          ─► pending_actions row + confirmation card:  "Apply for leave · annual 12–13 Oct"  [Cancel] [Confirm]
Employee clicks Confirm   ─► server re-checks owner, permission, expiry; claims the row atomically (runs once)
                          ─► calls the existing OS endpoint with the EMPLOYEE's token → Laravel validation/policies/events
                          ─► result on the card and in the conversation; full audit trail
```

- Each action declares a mandatory `required_permission`. `AI_ACTIONS_ENABLED` is a global kill switch.
- Nothing is executed because a document or web page asked for it: actions need the employee's click.
- Start with low-risk, reversible actions (leave, tasks, drafts, comments). Add payments, approvals of others and deletions last, or never.

## Next steps

**1. Task mode.** A "Task" mode with a higher `MAX_TOOL_ROUNDS`, a plan shown up front (the `status` events already render progress), and a single confirmation for a batch of related actions.

**2. Scheduled jobs.** "Every Monday, send me overdue tasks as a PDF." Store task definitions per employee, and run them through a worker (Redis + RQ/Celery, or Laravel queues calling the assistant API with a short-lived token). The `RunManager` already decouples execution from the browser.

**3. Memory.** Short, employee-approved facts ("I manage the Northwind account"), injected like Personalization and listed in Settings, with delete.

**4. Approval workflows.** For actions that need a manager, prepare the request in the OS (where approval already exists) rather than building approvals in the assistant.

Each step is additive. None of them weakens the read path, the confirmation rule, or the "never more access than the employee" guarantee.
