# Security model

The central rule: **the assistant never has more access than the employee using it.** Enfactum OS stays the only authority on who may see what.

## Mandatory constraints and how they are enforced

| # | Constraint | Enforcement |
|---|---|---|
| 1 | AI must not bypass existing authorization | OS tools call existing OS endpoints, so Laravel middleware, policies, gates and scopes run unchanged. The assistant has no service account and no DB connection to Enfactum OS. |
| 2 | AI inherits the authenticated user's permissions | `AuthService` resolves identity from the OS on every request (60 s cache). The user's own token/cookies are forwarded on every OS tool call (`app/tools/os_api.py`). |
| 3 | No unrestricted database access | The assistant only talks to its own SQLite store (documents, chats, audit), always with parameterised queries. Enfactum data is reachable only through declared OS endpoints. |
| 4 | No LLM-generated SQL | No SQL tool exists. Tool arguments are validated against a JSON Schema and sent as URL query/path parameters (URL-encoded) to fixed, admin-declared paths. |
| 5 | Company-data tools are read-only | `OSApiTool` refuses any method other than `GET` at startup, and absolute URLs are rejected. Writes exist only as separate, opt-in **actions** that need a human confirmation (row 9). |
| 6 | Sensitive fields filtered by permission | The OS filters by permission first (API Resources / policies). The assistant then applies a per-tool `response.fields` allow-list and always redacts secret-like keys (password, token, api_key, …). Documents carry role-based `visibility`, applied **before** ranking so restricted text never reaches the model. |
| 7 | Retrieved content is untrusted data | Every tool result is wrapped in `<tool_result>` with an explicit "data, not instructions" notice, and the system prompt forbids following embedded instructions. Only tools already authorised for the user can be called, so injected instructions cannot escalate. |
| 8 | Credentials never exposed to the LLM or frontend | `UserContext.os_token` is excluded from `repr` and `public()` and never placed in prompts. LLM, embedding and search keys live only in server env vars. Error messages returned to the model are generic. |
| 9 | Write operations only via explicit, confirmed tools | `ActionTool` (`app/tools/actions.py`): admin-declared endpoints only, mandatory `required_permission`, JSON-Schema validation, undeclared arguments dropped. The LLM can only *prepare* an action (stored as `pending`). It executes only when the employee clicks **Confirm**; the server then re-checks ownership, permission and expiry, atomically claims it (`pending → running`, so it can never run twice) and calls the OS with the employee's own token, so OS validation and policies decide. Global kill switch: `AI_ACTIONS_ENABLED=false`. |
| 10 | Existing Enfactum OS functionality not broken | The assistant is a separate service. The only OS-side requirements are CORS/embedding settings and, if missing, a `/api/user` endpoint that returns roles and permissions. |

## Additional data paths

- **Read-only DB templates** (`app/tools/db_query.py`):
  - SQL is written by administrators; the model only fills JSON-Schema-validated, driver-bound parameters.
  - Only a single `SELECT`/`WITH` is allowed, with write/DDL keywords rejected at startup.
  - Queries run in a `READ ONLY` transaction with a statement timeout and row cap, over a dedicated read-only database role.
  - `current_user_id`/`current_user_email` come from the verified identity, never from the model.
  - Queries must filter by those values, because the database does not know Enfactum RBAC.
- **Chat attachments** (`app/attachments.py`):
  - Private to the uploader and bound to one conversation; every lookup filters by `user_id`.
  - Content is wrapped as data, not instructions.
  - Files are deleted with the conversation.
- **Personalization** is injected as a lower-priority style section that explicitly cannot override accuracy or security rules.
- **Employee-only access**: every endpoint resolves the OS account type and refuses non-employees (`ALLOWED_USER_TYPES`) with 403, independent of whether the OS menu shows the tab.
- **OCR** (`app/rag/extract.py`): image text is treated exactly like document text (untrusted data). With `OCR_PROVIDER=llm` images are sent to the configured vision model; use `tesseract` to keep them on the server.
- **Generated files** (`app/tools/files.py`): produced by fixed library code from text/table input (no code execution, no templates with macros). They are stored as private attachments of the requesting employee. Spreadsheet cells that look like formulas are neutralised.
- **Serving files**: every uploaded or generated file is served with `Content-Security-Policy: sandbox`, and HTML/SVG are forced to download, so a malicious file can never run script in the assistant's origin. Previews of HTML use a sandboxed iframe.
- **Prompt-injection and actions**: the system prompt forbids preparing actions because a document or tool result asked for it, and in any case nothing changes without the employee's click.

## Defence in depth

- **Tool exposure:** tools whose `required_permission` the user lacks are never sent to the LLM. Calls to unknown or unoffered tools are refused and audited (`tool_denied`).
- **Row-level security:** comes free from the OS. For example, the mock OS returns only the projects a user belongs to, without the assistant knowing that rule.
- **Conversation isolation:** every conversation query filters by `user_id`.
- **Rate limiting:** per user (`RATE_LIMIT_PER_MINUTE`).
- **Uploads:** extension allow-list, size limit, parsed server-side (no macros executed), and only users with `PERM_DOCUMENTS_MANAGE` can upload.
- **Browser:** HTML-escaping Markdown renderer (no raw HTML), a CSP without inline scripts, `nosniff`, `no-referrer`, and restricted `frame-ancestors`.
- **Production guard:** `ENVIRONMENT=production` refuses to start with `AUTH_MODE=demo`, and `/api/docs` is disabled.
- **Audit:** tool calls (name and arguments), uploads and deletions, feedback, edits, and every action prepare / confirm / cancel / result are recorded in `audit_log`.

## Deployment checklist

- [ ] `ENVIRONMENT=production`, `AUTH_MODE=laravel` or `jwt`
- [ ] `MOCK_OS_ENABLED=false`, `SEED_SAMPLE_DOCS=false`, demo documents deleted
- [ ] HTTPS in front of the service; `OS_VERIFY_SSL=true`
- [ ] `CORS_ORIGINS` limited to the Enfactum OS origin(s)
- [ ] `config/os_tools.yaml` reviewed: only real, read-only endpoints, minimal `fields`
- [ ] `actions:` reviewed: low-risk endpoints only, each with a `required_permission`, backed by OS FormRequest validation and policies (or `AI_ACTIONS_ENABLED=false`)
- [ ] `ALLOWED_USER_TYPES=employee` and the identity payload returns `user_type`
- [ ] `OCR_PROVIDER` chosen consciously (`tesseract` if images must not leave your servers)
- [ ] LLM provider data-processing terms approved, or a self-hosted model used
- [ ] `DATA_DIR` on an encrypted, backed-up volume
