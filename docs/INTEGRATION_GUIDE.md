# Enfactum AI Assistant: Complete Integration Guide

This guide takes the assistant from a local test to a production integration with **Enfactum OS** (Laravel / Filament / React / PostgreSQL). It covers the OS itself, live company data (APIs and databases), and company knowledge (documents).

> The assistant was built without access to the Enfactum OS source. Wherever this guide shows Laravel code, adapt route names, models and permission names to the real codebase (`php artisan route:list`, `app/Models`, `app/Policies`).

## Contents

1. [How the pieces fit](#1-how-the-pieces-fit)
2. [Run it locally](#2-run-it-locally)
3. [Choose and configure the AI model](#3-choose-and-configure-the-ai-model)
4. [Connect employee sign-in (authentication)](#4-connect-employee-sign-in-authentication)
5. [Map roles and permissions (RBAC)](#5-map-roles-and-permissions-rbac)
6. [Connect live company data](#6-connect-live-company-data)
7. [Load company knowledge (documents)](#7-load-company-knowledge-documents)
8. [Embed the assistant in Enfactum OS](#8-embed-the-assistant-in-enfactum-os)
9. [Deploy to production](#9-deploy-to-production)
10. [Test the integration](#10-test-the-integration)
11. [Troubleshooting](#11-troubleshooting)
12. [Reference](#12-reference)

---

## 1. How the pieces fit

```text
Employee (browser, already signed in to Enfactum OS)
   │  token or session cookie
   ▼
Enfactum AI Assistant (this service, FastAPI)
   ├─ Who is this?   → asks Enfactum OS  GET /api/...me  → id, roles, permissions
   ├─ General knowledge  → LLM directly
   ├─ Public / current   → web search
   ├─ Company knowledge  → knowledge base (uploaded documents, filtered by role)
   ├─ Chat attachments   → files/images the employee attached to this chat (text in images/scans read by OCR)
   ├─ Live company data
   │     ├─ A. Enfactum OS API tools  (recommended: call existing APIs with the EMPLOYEE's token)
   │     └─ B. Read-only DB templates (only when no API exists; admin-written SQL)
   ├─ Actions (agentic)  → prepared by the AI, confirmed by the employee, executed by the OS with their token
   └─ Outputs            → PDF / Word / PowerPoint / Excel / CSV files, charts, images (download cards)
```

Inside Enfactum OS the assistant is an **application tab for employees only** (section 8). Client accounts are refused by the assistant itself, not only hidden in the OS menu.

**Golden rule:** the assistant never has more access than the employee using it. Enfactum OS remains the authority for identity, roles, permissions and row-level rules.

---

## 2. Run it locally

```bash
cd enfactum-ai-agent
cp .env.example .env            # the server reads ONLY .env
# edit .env → LLM_API_KEY=...
./run.sh                        # Windows: run.bat    Docker: docker compose up -d --build
```

Open <http://localhost:8080>. Demo mode signs you in as a single test employee against a bundled mock OS, with three sample policies (one HR-only, hidden from this employee). Use it to confirm the model, search and UI work before connecting the real OS.

Then open **Settings → About → Test connection**. It should report "Connected".

---

## 3. Choose and configure the AI model

Only `LLM_API_KEY` is required. The provider is detected from the key prefix:

| Key prefix | Provider | Default model | Embeddings |
|---|---|---|---|
| `sk-` / `sk-proj-` | OpenAI | gpt-4o-mini | yes |
| `AIza` | Google Gemini | gemini-2.0-flash | yes |
| `gsk_` | Groq | llama-3.3-70b-versatile | keyword search |
| `sk-or-` | OpenRouter | openai/gpt-4o-mini | keyword search |
| `sk-ant-` | Anthropic | claude-3-5-haiku-latest | keyword search |

Override with `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`. For a model that stays inside your network:

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:14b          # must support tool calling
EMBEDDING_PROVIDER=local       # pip install -r requirements-optional.txt
LLM_SUPPORTS_VISION=false      # unless the model reads images
```

Requirements:

- The model must support **tool/function calling**.
- Set `LLM_CONTEXT_WINDOW` if the model differs from the provider default. It drives the UI context meter and history trimming.
- Providers without an embeddings API fall back to keyword search automatically. Set `EMBEDDING_PROVIDER=local` for semantic search with no API.

For accuracy, use `gpt-4o`/`gpt-4.1` class models. For speed and cost, use `gpt-4o-mini`/`gemini-2.0-flash`.

### Speed: answers in under 5 seconds

Every answer logs where the time went, and the UI shows it when you hover the time next to the ✓ under each answer:

```text
answer user=103 conv=1a2b3c4d total=2840ms first_token=910ms llm=2100ms tools=640ms rounds=2 tools=['search_company_documents']
```

| If this is slow | Do this |
|---|---|
| `first_token` high with no tools | The model is slow or "thinking". Use a fast non-reasoning model (`gpt-4o-mini`, `gpt-4.1-mini`, `gemini-2.0-flash`, Groq `llama-3.3-70b-versatile`), or set `LLM_REASONING_EFFORT=low` (`minimal`/`none` where supported). `gemini-2.5-*`, `o3`/`o4`, `gpt-5*` think by default and commonly take 10–60 s. |
| `tools` high, web questions | Set `TAVILY_API_KEY` (≈1 s, no page fetching), or `WEB_FETCH_PAGES=0` for DuckDuckGo. |
| `tools` high, company questions | Embeddings slow/unreachable: they now time out after 4 s and fall back to keyword search; for consistent speed use `EMBEDDING_PROVIDER=local`. Slow OS endpoints: add indexes / pagination in the OS, lower `timeout_seconds` in the tools YAML. |
| `rounds` ≥ 3 | Tool descriptions overlap, so the model searches repeatedly. Make descriptions specific; keep `MAX_TOOL_ROUNDS=4`. |
| Everything slow | The provider region is far away or rate-limited (`429` in logs). |

Defaults are tuned for speed: `LLM_TIMEOUT_SECONDS=30`, `LLM_MAX_RETRIES=1`, `TOOL_TIMEOUT_SECONDS=12`, `WEB_TIMEOUT_SECONDS=6`, `WEB_FETCH_PAGES=1`. If your `.env` was copied from an older `.env.example`, update those values.

---

## 4. Connect employee sign-in (authentication)

Pick **one** option. All three make the assistant see the same employee the OS sees.

### Option A: Sanctum token (recommended)

**4A.1 Add an identity endpoint to Enfactum OS** (read-only; changes nothing existing). With `spatie/laravel-permission`:

```php
// routes/api.php
use Illuminate\Http\Request;

Route::middleware('auth:sanctum')->get('/ai/me', function (Request $request) {
    $u = $request->user();
    return [
        'id'          => $u->id,
        'name'        => $u->name,
        'email'       => $u->email,
        'user_type'   => $u->user_type ?? 'employee',              // "employee" | "client" (see section 5)
        'roles'       => $u->getRoleNames(),                       // ["employee", "hr_manager"]
        'permissions' => $u->getAllPermissions()->pluck('name'),   // ["employees.view", ...]
    ];
});
```

Without spatie, return whatever the OS uses (e.g. `$u->role->name`, `$u->permissions()->pluck('slug')`). Any shape works: map it with dot-paths in step 4A.3.

**4A.2 Give the frontend a token for the assistant.** Filament/React sessions usually use cookies, so issue a short-lived Sanctum token from the logged-in session:

```php
// routes/web.php  (session-authenticated)
Route::middleware(['web', 'auth'])->post('/ai/token', function (Request $request) {
    $user = $request->user();
    $user->tokens()->where('name', 'ai-assistant')->delete();          // one active token per user
    return ['token' => $user->createToken('ai-assistant', ['*'], now()->addHours(8))->plainTextToken];
});
```

(`createToken` with an expiry needs Sanctum 3.3+/4.x. On older versions, set `'expiration' => 480` in `config/sanctum.php`.)

**4A.3 Configure the assistant:**

```env
AUTH_MODE=laravel
OS_BASE_URL=https://os.enfactum.example
OS_USER_ENDPOINT=/api/ai/me
OS_USER_ID_FIELD=id
OS_USER_ROLES_FIELD=roles              # e.g. data.roles if wrapped
OS_USER_PERMISSIONS_FIELD=permissions
```

Identity is cached for `AUTH_CACHE_SECONDS` (default 60). A role change in the OS applies within a minute.

### Option B: shared session cookies (same parent domain)

Serve the assistant at e.g. `ai.enfactum.example` next to `os.enfactum.example`:

```env
# assistant .env
AUTH_MODE=laravel
OS_FORWARD_COOKIES=true
OS_USER_ENDPOINT=/api/ai/me
```

```env
# Enfactum OS .env
SESSION_DOMAIN=.enfactum.example
SANCTUM_STATEFUL_DOMAINS=os.enfactum.example,ai.enfactum.example
```

No token handling at all: employees who are signed in to the OS are signed in to the assistant.

### Option C: signed JWT

The OS signs a short-lived JWT (`sub`, `name`, `email`, `roles`, `permissions`) with a shared secret or RSA key (e.g. `firebase/php-jwt`):

```env
AUTH_MODE=jwt
JWT_SECRET=<32+ random bytes>        # or JWT_PUBLIC_KEY_FILE + JWT_ALGORITHMS=RS256
JWT_ISSUER=enfactum-os
```

This is the fastest option (no identity round-trip). OS API tools forward the JWT, so the OS API must also accept it (e.g. a custom guard). Otherwise combine it with DB tools only.

---

## 5. Map roles and permissions (RBAC)

**Employees vs. clients.** Enfactum OS has two account types, and the assistant is for employees only. The assistant reads the account type from `OS_USER_TYPE_FIELD` (default `user_type`) in the identity payload; if that field is missing, an account whose roles are all in `CLIENT_ROLES` (default `client`) is treated as a client. Every API call from a type not in `ALLOWED_USER_TYPES` (default `employee`) gets `403 employees_only`, and the UI shows an "employees only" screen. This holds even if a client finds the URL, so the OS menu hiding the tab is a convenience, not the control.

```env
OS_USER_TYPE_FIELD=user_type      # or e.g. data.type / account_type
ALLOWED_USER_TYPES=employee
CLIENT_ROLES=client,client_admin
```

| Assistant setting | Suggested OS permission | Effect |
|---|---|---|
| `PERM_CHAT` | `ai.use` | Who may use the assistant (empty = every employee) |
| `PERM_WEB_SEARCH` | `ai.web_search` | Who may trigger web searches |
| `PERM_DOCUMENTS_MANAGE` | `ai.documents.manage` | Who may add/remove knowledge-base documents |
| `ADMIN_ROLES` | `super_admin,admin` | Roles that see all documents and pass assistant checks |
| `required_permission` (per tool) | the permission guarding that OS route | Hides tools the employee can't use |

Create the permissions once in the OS, for example with a seeder:

```php
foreach (['ai.use', 'ai.web_search', 'ai.documents.manage'] as $p) {
    \Spatie\Permission\Models\Permission::findOrCreate($p, 'web');
}
Role::findByName('employee')->givePermissionTo(['ai.use', 'ai.web_search']);
Role::findByName('hr_manager')->givePermissionTo('ai.documents.manage');
```

How access is enforced, from outermost to innermost:

1. **Assistant feature gate** (`PERM_*`).
2. **Tool exposure:** a tool whose `required_permission` the employee lacks is never shown to the model.
3. **Enfactum OS itself:** middleware, policies, gates and scopes run on every API call made with the employee's token. This is the real security boundary.
4. **Field allow-list and secret redaction** on every tool response.
5. **Document visibility:** role lists on each knowledge-base document, applied before search ranking.

---

## 6. Connect live company data

### 6A. Enfactum OS API tools (recommended)

Each tool is one **existing, read-only GET endpoint**, declared in `config/os_tools.yaml` and called with the employee's own credentials.

**Step 1: find candidate endpoints**

```bash
php artisan route:list --path=api --method=GET
```

Good candidates sit behind `auth:sanctum`, authorise with a policy or `can:` middleware, and return an **API Resource**.

**Step 2: if a module has no API yet, add a thin read-only one** that reuses existing authorisation:

```php
// routes/api.php
Route::middleware('auth:sanctum')->prefix('ai')->group(function () {
    Route::get('/projects', [\App\Http\Controllers\Api\AiProjectController::class, 'index']);
});

// app/Http/Controllers/Api/AiProjectController.php
class AiProjectController extends Controller
{
    public function index(Request $request)
    {
        $this->authorize('viewAny', Project::class);                  // existing policy

        $projects = Project::query()
            ->visibleTo($request->user())                              // existing scope / row-level rule
            ->when($request->search, fn ($q, $s) => $q->where('name', 'ilike', "%{$s}%"))
            ->when($request->status, fn ($q, $s) => $q->where('status', $s))
            ->with(['client:id,name', 'manager:id,name'])
            ->latest()->limit(25)->get();

        return ProjectResource::collection($projects);                 // hides sensitive attributes
    }
}
```

If there is no `visibleTo` scope, apply the same filter the Filament resource uses (for example `getEloquentQuery()` in the Filament Resource), so the API and the UI agree.

**Step 3: declare the tool**

```yaml
# config/os_tools.yaml
base_url: ${OS_BASE_URL}
timeout_seconds: 10
tools:
  - name: search_projects
    label: Projects
    description: >
      Search Enfactum projects by name or client and filter by status. Returns name, client,
      status, manager and dates. Only projects the employee may see are returned.
    method: GET
    path: /api/ai/projects
    required_permission: projects.view
    parameters:
      type: object
      properties:
        search: {type: string, description: "Project or client name"}
        status: {type: string, enum: [planning, active, on_hold, completed]}
    response:
      root: data
      fields: [id, name, client.name, status, manager.name, start_date, end_date]
      max_items: 25
```

**Step 4: activate:**

```env
OS_TOOLS_FILE=config/os_tools.yaml
MOCK_OS_ENABLED=false
```

The startup log shows `Loaded N Enfactum OS tools`. Invalid files stop startup with a clear message. Only `GET` is accepted.

Tips for accurate tool use:

- Write `description` as *when to use it* and *what it returns*. The model routes on it.
- Keep parameters few and typed. Use `enum` for statuses.
- Keep `fields` minimal. Fewer tokens give faster and more precise answers.
- Typical modules: employee directory, projects, clients/CRM, contracts, vendors, invoices/finance, leave, assets, tickets.

### 6B. Read-only database templates (only when there is no API)

For data without an API (reporting tables, a data warehouse), the assistant can run **SQL written by an administrator**. The model only chooses a query and fills validated parameters. It never writes SQL.

> DB templates bypass Laravel policies. Each query must enforce access itself (for example `WHERE user_id = %(current_user_id)s`) and should be gated with `required_permission`. Prefer 6A whenever possible.

**Step 1: create a read-only PostgreSQL role** (run as a DB admin):

```sql
CREATE ROLE ai_readonly LOGIN PASSWORD '<strong-password>';
ALTER ROLE ai_readonly SET default_transaction_read_only = on;
ALTER ROLE ai_readonly SET statement_timeout = '5s';
GRANT CONNECT ON DATABASE enfactum TO ai_readonly;

-- Expose curated views, not raw tables with sensitive columns
CREATE SCHEMA IF NOT EXISTS ai;
CREATE VIEW ai.leave_balances AS
  SELECT user_id, leave_type, year, entitled_days, used_days FROM leave_balances;
GRANT USAGE ON SCHEMA ai TO ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA ai TO ai_readonly;
```

Point it at a **read replica** if one exists.

**Step 2: install the driver and configure:**

```bash
pip install "psycopg[binary]"
```

```env
COMPANY_DB_DSN=postgresql://ai_readonly:<password>@db-replica:5432/enfactum
DB_TOOLS_FILE=config/db_tools.yaml
```

**Step 3: write templates** in `config/db_tools.yaml` (examples are in the file):

```yaml
tools:
  - name: my_leave_balance
    label: My leave balance
    description: The current employee's remaining leave days by type for this year.
    sql: |
      SELECT leave_type, entitled_days, used_days, entitled_days - used_days AS remaining
      FROM ai.leave_balances
      WHERE user_id = %(current_user_id)s AND year = EXTRACT(YEAR FROM CURRENT_DATE)
    max_rows: 20
```

Safeguards enforced by the assistant:

- Only a single `SELECT`/`WITH` statement, and no write/DDL keywords.
- Every placeholder must be declared.
- `current_user_id` and `current_user_email` are injected from the verified identity and cannot come from the model.
- Parameters are driver-bound.
- Execution runs in a `READ ONLY` transaction with a timeout and a row cap, with secret-like columns redacted.

### 6C. Other systems (HRMS, CRM, ERP, ticketing)

Two options:

- **Through Enfactum OS:** if the OS already integrates with the system, expose a read-only OS endpoint (6A). The employee's OS permissions then apply.
- **Directly:** add a small tool class next to `app/tools/os_api.py`. Use the employee's own OAuth token for that system, never a shared admin key, and keep it read-only.

### 6D. Actions: let the assistant do things (agentic, confirmed)

Add write operations under `actions:` in the same YAML file as the read tools. The assistant can only **prepare** an action:

```text
"Apply for annual leave next Mon–Tue"
  → AI resolves dates, calls create_leave_request(...)         → nothing is sent to the OS yet
  → UI shows a card: Apply for leave · annual leave from 2026-10-12 to 2026-10-13   [Cancel] [Confirm]
  → employee clicks Confirm → server re-checks permission + expiry, claims the action once,
    POST /api/leave-requests with the EMPLOYEE's token → Laravel validation/policies/events run as usual
  → card shows "Completed" (or the OS validation error)
```

```yaml
actions:
  - name: create_leave_request
    label: Apply for leave
    description: Submit a leave request for the current employee.
    method: POST                       # POST | PUT | PATCH | DELETE
    path: /api/leave-requests          # existing OS route; path params like /api/tasks/{task_id} allowed
    required_permission: leave.create  # mandatory for actions
    summary: "{leave_type} leave from {start_date} to {end_date}"
    field_labels: {leave_type: Leave type, start_date: From, end_date: To}
    success_message: Leave request submitted for approval.
    parameters:                        # JSON Schema; only declared properties are sent as the JSON body
      type: object
      properties:
        leave_type: {type: string, enum: [annual, sick, casual]}
        start_date: {type: string, description: "YYYY-MM-DD"}
        end_date: {type: string, description: "YYYY-MM-DD"}
      required: [leave_type, start_date, end_date]
```

Guidance:

- Start with low-risk, reversible actions (leave requests, tasks, drafts, comments). Keep payments, approvals of others and deletions out, or add them last.
- The OS route must use the same validation and policies as the OS UI (FormRequest + `authorize`). The assistant relies on them.
- Return `422` with Laravel's `{"errors": {...}}` for bad input; the card shows the messages.
- `AI_ACTIONS_ENABLED=false` removes every action instantly. Confirmations expire after `ACTION_EXPIRY_MINUTES`.
- Every prepare / confirm / cancel / result is written to `audit_log`.
- Sanctum tokens issued for the assistant need the abilities these routes check (or `['*']`).

The demo config (`config/os_tools.demo.yaml`) ships two working examples against the mock OS: apply for leave and create task.

---

## 7. Load company knowledge (documents)

**What belongs here:** policies, handbooks, SOPs, process docs, product manuals, templates, FAQs. That is static knowledge. Live records (employees, projects, invoices) belong in tools (section 6), not in documents.

### Ways to add documents

| Method | Who | How |
|---|---|---|
| Composer **+ → Add to knowledge base** | Users with `PERM_DOCUMENTS_MANAGE` | Pick a file, set the audience, upload |
| **Settings → Knowledge base** | Same | Drag and drop, set title and audience |
| Bulk script | Admin / cron | `python scripts/ingest_folder.py ./policies --url https://ai.enfactum.example --token $TOKEN` |
| Restricted folder | Admin | `python scripts/ingest_folder.py ./hr --roles hr_manager,super_admin --token $TOKEN` |

Supported formats: PDF (including scanned PDFs), DOCX, PPTX, XLSX, CSV, TXT, MD, HTML, JSON, and images (PNG, JPG, WEBP, GIF, BMP, TIFF).

**Text in images and scanned PDFs (OCR).** Pages without a text layer and uploaded images are read automatically:

| `OCR_PROVIDER` | Engine | Notes |
|---|---|---|
| `auto` (default) | Vision LLM if `LLM_SUPPORTS_VISION=true`, else Tesseract if installed | Best accuracy on tables, handwriting, screenshots |
| `llm` | Vision model; `OCR_MODEL` / `OCR_BASE_URL` / `OCR_API_KEY` can point to a cheaper one | e.g. `gpt-4o-mini`, `gemini-2.0-flash` |
| `tesseract` | Local and offline | `brew install tesseract` / `apt-get install tesseract-ocr` + `pip install pytesseract`; included in the Docker image |
| `none` | Disabled | |

`OCR_MAX_PAGES` (default 30) caps OCR per PDF. The original file is stored, so employees can **preview and download** every knowledge-base document from Settings → Knowledge base (permission-checked like search).

### Audience (who can retrieve a document)

- **All employees**: `scope: all`.
- **Restricted**: a list of OS role names. Only employees whose roles (from `/api/ai/me`) match, or admins, can retrieve any part of it. Filtering happens before ranking, so restricted text never reaches the model for other users.

### Keeping it in sync with SharePoint / Google Drive / Confluence

1. Export or sync the source to a folder (OneDrive/Drive desktop sync, Confluence space export, `rclone sync`).
2. Run `scripts/ingest_folder.py <folder> --skip-existing --roles ...` from cron or CI.
3. To update a document, delete the old version in Settings → Knowledge base and re-upload.

### Chat attachments vs. knowledge base

| | Chat attachment (+ → Files or images) | Knowledge base |
|---|---|---|
| Visible to | Only the employee, only in that chat | Everyone in the chosen audience |
| Permission needed | None | `PERM_DOCUMENTS_MANAGE` |
| Images | Yes: seen by vision models, text read by OCR | Yes: text read by OCR and indexed |
| Typical use | "Summarise this contract", "What's in this screenshot?" | Company policies and manuals |

### Files the assistant creates

Employees can ask for outputs, for example "make this a PDF report", "export the projects to Excel", "turn this into a 5-slide deck" or "chart revenue by quarter". The assistant writes the content and calls:

| Tool | Output | Library |
|---|---|---|
| `create_file` | PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, HTML, JSON | fpdf2, python-docx, python-pptx, openpyxl |
| `create_chart` | PNG chart (bar, line, area, pie, donut, scatter, stacked) | matplotlib |
| `generate_image` | PNG image from a prompt | OpenAI-compatible images API (`IMAGE_GENERATION`, `IMAGE_MODEL`) |

Files are private to the employee, are shown as cards with **Preview** and **Download**, and are deleted with the chat. Any answer can also be downloaded as PDF, Word, Markdown or text from the ⤓ button under it. Spreadsheet cells that start with `=`, `+`, `-` or `@` are neutralised against formula injection.

### Writing documents that answer well

- Use clear headings. Each chunk keeps its section heading.
- One topic per document, with the title stating the topic and version or date.
- Prefer text over images of text. Use tables for numbers.

---

## 8. Embed the assistant in Enfactum OS

Serve the assistant on its own (sub)domain, e.g. `https://ai.enfactum.example`, and add the OS origin to `CORS_ORIGINS` in the assistant's `.env`.

There are three embed modes, chosen by URL:

| URL | Use |
|---|---|
| `/?embed=app` | **Full application inside an OS tab** (recommended): sidebar with chats, settings, knowledge base. Brand header hidden, since the OS has its own. |
| `/?embed=widget` (or `?embed=1`) | Compact panel: chat only, no sidebar (slide-over / floating button). |
| `/` | Standalone at its own domain. |

Chat URLs are `/c/<conversation-id>`, so a refresh or browser back/forward keeps the employee in the same chat. Answers are generated server-side: switching chats, closing the tab, minimising or refreshing does **not** stop them. The sidebar shows a spinner while a chat is working and a blue ✓ when a new answer is ready.

**App descriptor.** `GET /api/app-manifest` returns the name, description, icon, entry URL and audience (`["employee"]`), so an OS app launcher can register the tab from config.

**Messages to the host page** (`window.postMessage`, only to origins in `CORS_ORIGINS`):

| Direction | Message | Meaning |
|---|---|---|
| OS → assistant | `{type: "enfactum-ai-token", token}` | Sign in with this Sanctum token |
| OS → assistant | `{type: "enfactum-ai-theme", theme: "light"\|"dark"\|"system"}` | Follow the OS theme |
| assistant → OS | `{type: "enfactum-ai-ready", version}` | Signed in and ready |
| assistant → OS | `{type: "enfactum-ai-auth-required"}` | Token missing/expired; send a fresh one |

### 8A. React (Vite): an "AI Assistant" application tab for employees

Add it next to the other employee applications, guarded by the same user-type check the OS menu uses:

```tsx
// src/apps/registry.ts (wherever the OS defines its employee applications)
{ id: "ai-assistant", name: "AI Assistant", icon: AiIcon, path: "/apps/ai",
  audience: "employee", permission: "ai.use", element: <AiAssistantApp /> }
```

```tsx
// src/apps/AiAssistantApp.tsx
import { useCallback, useEffect, useRef } from "react";

const AI_URL = import.meta.env.VITE_AI_ASSISTANT_URL;   // https://ai.enfactum.example

export function AiAssistantApp() {
  const frame = useRef<HTMLIFrameElement>(null);

  const sendToken = useCallback(async () => {
    const { token } = await fetch("/ai/token", { method: "POST", credentials: "include",
      headers: { "X-XSRF-TOKEN": getXsrfCookie() } }).then((r) => r.json());
    frame.current?.contentWindow?.postMessage({ type: "enfactum-ai-token", token }, AI_URL);
  }, []);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== AI_URL) return;
      if (e.data?.type === "enfactum-ai-auth-required") sendToken();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [sendToken]);

  return <iframe ref={frame} src={`${AI_URL}/?embed=app`} onLoad={sendToken} title="AI Assistant"
                 className="h-full w-full border-0" allow="clipboard-write" />;
}
```

Hide the tab for clients in the OS menu as usual. The assistant also refuses client accounts itself (section 5).

### 8A-bis. React: slide-over widget (optional)

```tsx
// src/components/AiAssistant.tsx
import { useEffect, useRef } from "react";

const AI_URL = import.meta.env.VITE_AI_ASSISTANT_URL;   // https://ai.enfactum.example

export function AiAssistant() {
  const frame = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const send = async () => {
      const { token } = await fetch("/ai/token", { method: "POST", credentials: "include",
        headers: { "X-XSRF-TOKEN": getXsrfCookie() } }).then((r) => r.json());
      frame.current?.contentWindow?.postMessage({ type: "enfactum-ai-token", token }, AI_URL);
    };
    frame.current?.addEventListener("load", send);
    return () => frame.current?.removeEventListener("load", send);
  }, []);

  return <iframe ref={frame} src={`${AI_URL}/?embed=widget`} title="Enfactum AI"
                 className="h-full w-full border-0" allow="clipboard-write" />;
}
```

`?embed=widget` hides the assistant's own sidebar. Mount it as a slide-over panel from the main layout. With Option 4B (cookies), skip the token step entirely.

### 8B. React: native component

Call the API from your own components and design system:

```ts
const res = await fetch(`${AI_URL}/api/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ message, conversation_id, mode: "auto", attachment_ids: [] }),
});
// Server-Sent Events: run · conversation · user_message · status · token · artifact · usage · sources · done · error · run_end
```

See `static/app.js` (`send()`, `handleEvent()`) for a complete stream parser. Upload attachments first with `POST /api/attachments` (multipart `file`) and pass the returned ids. If the connection drops, re-attach with `GET /api/runs/{run_id}/events?from=<last seq + 1>`; the answer keeps generating meanwhile.

### 8C. Filament admin panel

Register a render hook that adds a floating button with the iframe to every panel page:

```php
// app/Providers/Filament/AdminPanelProvider.php
use Filament\View\PanelsRenderHook;
use Illuminate\Support\Facades\Blade;

public function panel(Panel $panel): Panel
{
    return $panel
        // ...
        ->renderHook(PanelsRenderHook::BODY_END, fn (): string => Blade::render('@include("ai.widget")'));
}
```

```blade
{{-- resources/views/ai/widget.blade.php --}}
<div x-data="{ open: false }" class="fixed bottom-6 right-6 z-50">
  <button x-on:click="open = !open" class="rounded-full bg-primary-600 px-4 py-3 text-white shadow-lg">Ask AI</button>
  <div x-show="open" x-cloak class="mt-3 h-[640px] w-[420px] overflow-hidden rounded-2xl bg-white shadow-2xl">
    <iframe src="{{ config('services.ai.url') }}/?embed=widget" class="h-full w-full border-0"
            x-on:load="$el.contentWindow.postMessage({type:'enfactum-ai-token',
              token:'{{ auth()->user()->createToken('ai-assistant', ['*'], now()->addHours(8))->plainTextToken }}'},
              '{{ config('services.ai.url') }}')"></iframe>
  </div>
</div>
```

To avoid creating a token on every page load, cache it in the session (e.g. `session()->remember('ai_token', ...)`) or use the cookie option (4B).

For a full-page **application** in Filament (instead of a floating widget), add a custom page visible to employees only:

```php
// app/Filament/Pages/AiAssistant.php
class AiAssistant extends \Filament\Pages\Page
{
    protected static ?string $navigationIcon = 'heroicon-o-sparkles';
    protected static ?string $navigationLabel = 'AI Assistant';
    protected static string $view = 'filament.pages.ai-assistant';

    public static function canAccess(): bool
    {
        $u = auth()->user();
        return $u && ($u->user_type ?? 'employee') === 'employee' && $u->can('ai.use');
    }
}
```

```blade
{{-- resources/views/filament/pages/ai-assistant.blade.php --}}
<x-filament-panels::page>
  <iframe src="{{ config('services.ai.url') }}/?embed=app" class="w-full rounded-xl border-0" style="height: calc(100vh - 10rem)"
          x-data x-on:load="$el.contentWindow.postMessage({type:'enfactum-ai-token', token:'{{ session('ai_token') }}'}, '{{ config('services.ai.url') }}')"></iframe>
</x-filament-panels::page>
```

---

## 9. Deploy to production

**`.env` essentials**

```env
ENVIRONMENT=production              # refuses AUTH_MODE=demo, disables /api/docs
AUTH_MODE=laravel
MOCK_OS_ENABLED=false
SEED_SAMPLE_DOCS=false
OS_TOOLS_FILE=config/os_tools.yaml
CORS_ORIGINS=https://os.enfactum.example
```

**Docker**

```bash
docker compose up -d --build
```

Data (knowledge base, chats, attachments, audit log) lives in the `assistant-data` volume (`/app/data`). Back it up.

**Reverse proxy.** Streaming requires buffering to be off:

```nginx
server {
  server_name ai.enfactum.example;
  listen 443 ssl http2;
  client_max_body_size 30m;
  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;              # required for token streaming
    proxy_read_timeout 300s;
  }
}
```

Run **one worker per container** (the default). Background answer runs live in that process, so several uvicorn workers behind one URL would break re-attaching to a running answer. Use more containers with sticky sessions instead.

**Scaling.** One container handles hundreds of concurrent employees. Beyond that, move the index to PostgreSQL + pgvector and the rate limiter to Redis, then add replicas (see `docs/ARCHITECTURE.md`).

---

## 10. Test the integration

Run these with at least three real accounts: a regular employee, a manager, and an HR/finance user.

| Test | Expected |
|---|---|
| Settings → About → Test connection | "Connected" |
| "What is the capital of Japan?" | Direct answer, no sources |
| "Latest news about <topic> this week" | Web sources with dates |
| A question answered by an HR-only document, asked as a regular employee | "Not found / no access", with no content leak |
| Same question as HR | Answer citing the document |
| "Show all projects with budgets" as a regular employee | Only their projects, no budgets (whatever the OS allows) |
| Salary of a colleague as a regular employee | Access denied or no salary field |
| Attach a PDF and ask for a summary | Summary citing the attachment |
| Attach a screenshot and ask about it | Description (vision models) |
| Paste a document containing "ignore previous instructions…" | Instruction ignored |
| Revoke a permission in the OS, wait 60 s, ask again | Access removed |
| Sign in as a **client** account and open the assistant | "Employees only" screen; every API call returns 403 |
| Attach a photo of a printed page / a scanned PDF | Text is read and quoted correctly |
| "Create a PDF report of my projects" / "Export to Excel" / "Make a 5-slide deck" | Download card; Preview shows the content |
| "Chart project budgets" | Chart image in the answer |
| "Apply for sick leave tomorrow" | Confirmation card; nothing happens in the OS until Confirm; then "Completed" |
| Confirm the same action twice (two tabs) | Executed once |
| Ask a long question, switch to another chat, come back | Sidebar spinner, then a blue ✓; the full answer is there |
| Refresh the page during an answer | Same chat reopens and the answer keeps streaming |
| Edit an earlier question | Later messages are replaced by the new answer |

Automated tests: `pip install -r requirements-optional.txt && pytest`.

---

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "The AI model is not configured" | `LLM_API_KEY` empty. Put it in `.env` (not `.env.example`) and restart. |
| "The AI provider rejected the API key" | Key invalid, revoked, or for a different provider. Check the detected provider in Settings → About. Set `LLM_PROVIDER` / `LLM_BASE_URL` if needed. |
| "API key has no access to this model" | Change `LLM_MODEL` to a model your account can use. |
| "Rate-limiting or no credit" | Add billing or credit at the provider, or lower usage. |
| "Model … not found" | Wrong `LLM_MODEL` for that provider. |
| "Make sure the model supports tool calling" | Choose a tool-calling model (most current GPT, Gemini, Claude, Llama 3.1+, Qwen 2.5+). |
| Answers stream all at once | Proxy buffering is on. Set `proxy_buffering off`. |
| 401 in the UI | The OS rejected the token, or `OS_USER_ENDPOINT` is wrong. Test with `curl -H "Authorization: Bearer <token>" $OS_BASE_URL/api/ai/me`. |
| Roles/permissions empty | Field mapping. Set `OS_USER_ROLES_FIELD` / `OS_USER_PERMISSIONS_FIELD` to the right dot-path. |
| OS tool always "ACCESS DENIED" | The OS policy denies it for that user (correct), or the token lacks abilities / the guard differs. |
| Documents never found | Check the document audience matches the user's role names exactly. |
| Web search unavailable | Outbound internet blocked. Set `TAVILY_API_KEY`, or `WEB_SEARCH_PROVIDER=none`. |
| iframe blank | Add the OS origin to `CORS_ORIGINS` (also controls `frame-ancestors`). |
| Answers take 10 s or more | See "Speed" in section 3: check the `answer … total= first_token= tools=` log line. Usually a thinking model or slow web/embedding calls. |
| "Reading text from images needs OCR" | Set `LLM_SUPPORTS_VISION=true` with a vision model, or install Tesseract and set `OCR_PROVIDER=tesseract`. |
| "missing a library for pdf/pptx files" | `pip install -r requirements.txt` again (fpdf2, python-pptx, matplotlib, pymupdf were added). |
| Image generation not offered | Needs an OpenAI key (`LLM_API_KEY` sk-… or `IMAGE_API_KEY`), or `IMAGE_BASE_URL` for a compatible service. |
| Action card says "denied" | The OS policy refused it for that employee (correct), or the Sanctum token lacks the ability. |
| "Employees only" for a real employee | The identity payload's `user_type` isn't `employee`, or all their roles are listed in `CLIENT_ROLES`. |

Logs: `docker compose logs -f assistant` (or the terminal running `run.sh`). The first lines show the detected provider, model, loaded tools and indexed chunks.

---

## 12. Reference

**Files you will edit**

| File | Purpose |
|---|---|
| `.env` | All configuration |
| `config/os_tools.yaml` | Enfactum OS API tools (`tools:` read, `actions:` confirmed writes) |
| `config/db_tools.yaml` | Read-only SQL templates |
| `scripts/ingest_folder.py` | Bulk knowledge-base upload |

**HTTP API**

| Endpoint | Purpose |
|---|---|
| `POST /api/chat` | Ask a question; starts a background run and streams it (SSE). `replace_from_message_id` = edit/regenerate |
| `GET /api/runs`, `GET /api/runs/{id}/events?from=N`, `POST /api/runs/{id}/cancel` | Running/unseen answers, re-attach with replay, stop |
| `POST /api/attachments`, `DELETE /api/attachments/{id}` | Chat attachments |
| `GET /api/files/{id}[?download=1]`, `GET /api/files/{id}/text` | Attachments and generated files: view, download, text preview |
| `GET/POST/DELETE /api/documents`, `GET /api/documents/{id}/file`, `GET /api/documents/{id}/text` | Knowledge base, preview and download |
| `GET/PATCH/DELETE /api/conversations[/{id}]`, `POST /api/conversations/{id}/seen`, `GET /api/export` | History, pin/rename, read markers, export |
| `POST /api/messages/{id}/feedback`, `POST /api/messages/{id}/export` | 👍/👎 and download an answer (pdf, docx, md, txt, html) |
| `POST /api/actions/{id}/confirm`, `POST /api/actions/{id}/cancel` | Confirm or cancel a prepared action |
| `GET/PUT /api/settings` | Per-employee preferences |
| `GET /api/me`, `GET /api/app-manifest`, `GET /api/health`, `GET /api/health/llm` | Identity, OS app descriptor, health, model check |

Security model: see `docs/SECURITY.md`. Agentic roadmap: see `docs/AGENTIC_ROADMAP.md`.
