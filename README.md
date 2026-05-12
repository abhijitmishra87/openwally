<p align="center">
  <img src="assets/logo.png" alt="OpenWally" width="220" />
</p>

<h1 align="center">OpenWally</h1>

<p align="center">
  An autonomous AI agent pipeline that generates production-grade software projects from a plain-text idea.<br/>
  Sixteen specialised agents collaborate sequentially — from requirements through API design, security,<br/>
  database, code, deployment, observability, performance, tests, UAT, and a full documentation set —<br/>
  with a self-correcting revision cycle when UAT fails.
</p>

<p align="center">
  Built on <a href="https://github.com/crewaiinc/crewai">CrewAI</a> &nbsp;·&nbsp;
  Evaluated with <a href="https://github.com/UKGovernmentAIS/inspect_ai">Inspect AI</a> &nbsp;·&nbsp;
  Powered by <a href="https://www.anthropic.com">Anthropic Claude</a> or <a href="https://ollama.com">Ollama</a>
</p>

---

## How it works

You provide a project idea. Sixteen specialised agents collaborate sequentially to produce a production-grade, deploy-ready project:

```
Program Manager → Software Architect → API Designer → Security Architect → Database Engineer
    → Engineering Manager → UI/UX Designer → Backend Developer → UI Developer
        → DevOps Engineer → SRE → Performance Engineer
            → Code Reviewer → Quality Engineer → UAT Tester → Technical Writer
                                                                       ↓
                                       NO-GO → Revision cycle (up to N times)
                                           Backend Dev → UI Dev → QA → UAT
                                                                          ↓
                                                                        GO → scaffold & git
```

Each agent receives a **team roster** in its prompt — who else is in the pipeline, what each owns, what they MUST NOT touch — so they stay in their lane and hand off cleanly rather than redoing each other's work.

Every agent appends a **Testing Notes** section to its artifact — domain-specific test cases consumed by the Quality Engineer. Security cases come from the Security Architect, integration cases from the API Designer, query/index cases from the Database Engineer, alert-firing cases from the SRE, and budget-violation cases from the Performance Engineer.

The **Code Reviewer** reads every source file after the developers, DevOps, SRE, and Performance Engineer finish, cross-references the code against the architecture, OpenAPI spec, security requirements, schema, deploy plan, SLOs, and perf budget, and produces a structured report before QA runs.

If UAT returns a NO-GO verdict, a targeted revision crew automatically fixes the defects and re-evaluates — up to a configurable limit. The Technical Writer always runs last to produce the user-facing documentation set.

### Agent roles and models

| # | Agent | Default model | Responsibility |
|---|---|---|---|
| 1 | Program Manager | claude-opus-4-7 | Requirements, FR-xxx, AC-FR-xxx, testing setup notes |
| 2 | Software Architect | claude-opus-4-7 | Component design, API contracts, technology choices |
| 3 | API Designer | claude-sonnet-4-6 | OpenAPI 3.1 spec, error envelope, pagination, versioning, idempotency, rate limits |
| 4 | Security Architect | claude-opus-4-7 | STRIDE threat model, SR-xxx, concrete security test cases |
| 5 | Database Engineer | claude-opus-4-7 | Engine choice, ER model, DDL, indexes, reversible migrations, seed data |
| 6 | Engineering Manager | claude-sonnet-4-6 | T-xxx task list with testable definitions-of-done |
| 7 | UI/UX Designer | claude-opus-4-7 | Wireframes, design tokens, interaction states |
| 8 | Backend Developer | claude-sonnet-4-6 | Python source code, deps.txt, conftest.py, start.sh |
| 9 | UI Developer | claude-opus-4-7 | React + TypeScript + Tailwind + shadcn/ui |
| 10 | DevOps Engineer | claude-sonnet-4-6 | CI/CD workflows, structured JSON logging, Prometheus metrics, optional k8s |
| 11 | Site Reliability Eng | claude-sonnet-4-6 | SLOs, AlertManager rules, runbooks, Grafana dashboard |
| 12 | Performance Engineer | claude-sonnet-4-6 | Perf budget, k6 scripts (smoke/load/spike), hot-path findings, capacity plan |
| 13 | Code Reviewer | claude-opus-4-7 | Verifies code matches every prior artifact — architecture, API, security, schema, SLOs, perf |
| 14 | Quality Engineer | claude-sonnet-4-6 | Full test suite implementing every agent's Testing Notes + review findings |
| 15 | UAT Tester | claude-haiku-4-5 | Pass/fail against all ACs, SRs, contracts; final GO / NO-GO verdict |
| 16 | Technical Writer | claude-sonnet-4-6 | README, docs/api.md, docs/architecture.md, ADRs, CONTRIBUTING.md, CHANGELOG.md |

Every model is independently overridable via environment variable and supports both Claude and Ollama — see [Configuration](#configuration).

> **Cost note:** a full 16-agent run is typically ~$5–10 in Anthropic API spend depending on spec complexity. Use `--review-depth=off` to drop the most expensive agent for a cheaper iteration loop (~$3–6).

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- [Node.js](https://nodejs.org/) 24+ and `npm` — for the generated frontend
- [git](https://git-scm.com/)
- An Anthropic API key **or** [Ollama](https://ollama.com) running locally

Optional:
- [Docker](https://docs.docker.com/get-docker/) 24+ with the `compose` plugin — to deploy generated projects via the auto-scaffolded Dockerfile / compose.yml
- [GitHub CLI (`gh`)](https://cli.github.com/) — to push generated projects to GitHub
- [k6](https://k6.io/) — to run the auto-generated load tests under `perf/k6/`

---

## Installation

```bash
git clone https://github.com/<you>/openwally.git
cd openwally

uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -e .

cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY or configure Ollama models
```

---

## Usage

### Run from an idea file (recommended)

Write your project idea in a `.md` or `.txt` file:

```markdown
# My Project Idea

Build a SaaS expense tracker. Users can submit expenses with a category,
amount, and receipt photo. Managers can approve or reject submissions.
The app should send email notifications on status changes and export
approved expenses as CSV.
```

```bash
openwally run --spec-file idea.md
```

### Run from an inline string

```bash
openwally run --spec "Build a URL shortener with per-link analytics and a React dashboard"
```

### All options

| Flag | Default | Description |
|---|---|---|
| `--spec-file FILE` | — | Path to a `.md` or `.txt` file with the project spec |
| `--spec TEXT` | — | Project idea as an inline string |
| `--name NAME` | derived from spec | Folder name for the generated project |
| `--output-dir DIR` | `./projects` | Parent directory for generated projects |
| `--mode MODE` | `autonomous` | Human-in-the-loop level — see below |
| `--review-depth DEPTH` | `standard` | Code review thoroughness — see below |
| `--max-revisions N` | `2` | Max UAT revision cycles on NO-GO verdict (`0` to disable) |
| `--no-validate` | off | Skip in-pipeline validation — agents won't run pytest or npm build to self-correct |
| `--no-standards` | off | Skip engineering standards injection — bare-bones project, bring your own conventions |

---

## Human-in-the-loop modes

Control how much you want to be involved using `--mode`:

| Mode | Behaviour | When to use |
|---|---|---|
| `autonomous` | Fully hands-off, no pauses (default) | Unattended runs, CI/CD |
| `milestone` | Pauses after **requirements**, **UI design**, and **tests** for your review | First run on a new idea — review before costly steps lock in |
| `interactive` | Pauses after **every agent** for your feedback | Tight control, exploration, debugging |

```bash
# Review requirements and UI design before coding starts
openwally run --spec-file idea.md --mode milestone

# Review every agent's output
openwally run --spec-file idea.md --mode interactive

# Fully autonomous with up to 3 self-correction cycles
openwally run --spec-file idea.md --max-revisions 3
```

When a pause occurs, CrewAI prints the agent's output and prompts you for feedback. Type your notes and press Enter — the agent incorporates your feedback before the next agent runs. Press Enter with no input to accept as-is.

---

## Engineering standards

By default, OpenWally injects a non-negotiable standards checklist into every generated project — regardless of what the spec says. These cover the practices most likely to be missing from a bare AI-generated codebase.

**Backend (enforced on every generated Python project):**

| Standard | What gets generated |
|---|---|
| Structured logging | Every module imports and uses a logger — no `print()` in production code |
| Error handling | No bare `except:` — specific exception types, structured API error responses |
| Health endpoint | `GET /health` returns `{"status": "ok"}` — required for deployment and monitoring |
| Env-var config | All config (DB URLs, keys, ports) from environment variables via `python-dotenv` — no hardcoded values |
| Pydantic validation | All request/response shapes use Pydantic models |
| HTTP status codes | 201 for creation, 400/401/403/404/422 for errors, 500 for unexpected failures |
| Deploy-readiness | `start.sh` binds 0.0.0.0 + `$PORT`, `conftest.py` makes `src/` importable, no hardcoded paths, logs to stdout only |

**Frontend (enforced on every generated React project):**

| Standard | What gets generated |
|---|---|
| Error boundaries | Every page/route wrapped — a component crash won't take down the whole app |
| Env-based API URL | `VITE_API_BASE_URL` used everywhere — no hardcoded URLs |
| Loading / error / empty states | All data-fetching components handle all three explicitly |
| No console.log | All debug statements removed before saving |
| TypeScript strict mode | `strict: true` in tsconfig.json, zero `any` types |
| Accessible elements | All interactive elements have `aria-label` or visible labels |

The **Code Reviewer** also checks for standards compliance as a dedicated section in its report — any violation is flagged as a finding.

> **Live version lookups.** The Architect, Database Engineer, Backend Developer, UI Developer, DevOps Engineer, and Performance Engineer all have access to a `lookup_latest_version` tool that hits `endoflife.date`, PyPI, and the npm registry (no API key required) so they pick currently-supported runtimes and packages at generation time, not what their training data remembers.

Use `--no-standards` for a bare-bones project where you'll apply your own conventions:

```bash
# Default — standards enforced
openwally run --spec-file idea.md

# Bare-bones — no standards injected
openwally run --spec-file idea.md --no-standards

# Combine flags
openwally run --spec-file idea.md --no-standards --no-validate
```

---

## Production-grade output

Every generated project ships deploy-ready and operable on day one. Beyond the source code itself, the pipeline produces:

| Capability | What gets generated | Owned by |
|---|---|---|
| **Containerised deploy** | Multi-stage `Dockerfile` (non-root, healthcheck on `/health`), `frontend/Dockerfile` (node:24 build → nginx:alpine serve), `docker-compose.yml`, `.dockerignore`, `nginx.conf` with `/api/` proxy | Harness scaffolding |
| **Native deploy** | `Makefile` (`install`, `run`, `test`, `docker-up/down/logs`, `clean`), `.env.example`, `start.sh` (binds 0.0.0.0 + `$PORT`) | Harness + Backend Developer |
| **Formal API contract** | `docs/openapi.yaml` (OpenAPI 3.1) with reusable schemas, error envelope, cursor pagination, versioning + deprecation policy, idempotency keys, rate-limit headers | API Designer |
| **Persistence layer** | Engine choice with EOL check, ER diagram, complete DDL, indexes with query-pattern justifications, ordered reversible migrations, seed data | Database Engineer |
| **CI/CD** | `.github/workflows/ci.yml` (pytest + npm build), `.github/workflows/docker.yml` (build + optional push gated on `DOCKER_REGISTRY` secret) | DevOps Engineer |
| **Observability** | `logging_config.py` (structured JSON to stdout with request_id contextvar), `observability.py` (Prometheus counter/histogram/gauge on `/metrics`) | DevOps Engineer |
| **Reliability** | 3–5 SLOs tied to user-visible behaviour, `ops/alerts.yaml` (AlertManager format, every alert links to a runbook), `docs/runbooks/*.md`, `ops/grafana/main-dashboard.json` | SRE |
| **Performance** | Per-endpoint p50/p95/p99 budget, `perf/k6/{smoke,load,spike}.js`, hot-path findings citing file+line, capacity plan grounded in year-1 load | Performance Engineer |
| **Documentation** | `README.md`, `docs/api.md` (full reference grounded in real code), `docs/architecture.md`, `docs/adr/*.md`, `CONTRIBUTING.md`, `CHANGELOG.md` | Technical Writer |

Once generated, the project runs from any directory on any Linux server or macOS:

```bash
cd projects/my-project

# Native
make install && cp .env.example .env && make run

# Docker
cp .env.example .env && make docker-up
curl http://localhost:8000/health
```

The Docker image runs as a non-root user, has a healthcheck wired to `/health`, exposes Prometheus metrics on `/metrics`, and emits structured JSON logs to stdout. The frontend image builds the SPA and serves it via nginx with `/api/` proxied to the backend over the compose network.

---

## In-pipeline validation

By default, the Backend Developer and UI Developer agents validate their own output before finishing:

- **Backend Developer** runs `pytest` after writing source files. If tests fail, it reads the error output, fixes the code, and retries — up to 3 times.
- **UI Developer** runs `npm run build` after writing frontend files. If the build fails, it fixes TypeScript errors or missing imports and retries — up to 3 times.

This catches broken code before it reaches the Code Reviewer and UAT Tester, reducing revision cycles.

Use `--no-validate` to skip this for faster, cheaper runs:

```bash
# Skip validation — fastest iteration
openwally run --spec-file idea.md --no-validate

# Full pipeline with validation (default)
openwally run --spec-file idea.md
```

**No LLM cost:** validation uses subprocess calls (`uv run pytest`, `npm run build`) — no extra API calls.

---

## Code review depth

Control how exhaustively the Code Reviewer reads the generated source with `--review-depth`:

| Depth | Behaviour | Best for |
|---|---|---|
| `off` | Skip code review entirely — agent not added to pipeline | Fast/cheap runs, iteration |
| `standard` | Risk-prioritised: reads auth, API handlers, security code, data models, and API hooks in full; skims utilities (default) | Most runs — catches ~90% of real issues at ~30% of thorough cost |
| `thorough` | Reads every source file in both manifests exhaustively | Pre-release, security-sensitive projects |

```bash
# Default — risk-prioritised
openwally run --spec-file idea.md

# Skip review entirely (fastest)
openwally run --spec-file idea.md --review-depth off

# Read every file
openwally run --spec-file idea.md --review-depth thorough

# Combine with other flags
openwally run --spec-file idea.md --review-depth thorough --mode milestone --max-revisions 3
```

**Standard depth read order** (highest risk first):
1. Auth, token, JWT, session, middleware, permission, password, crypto files
2. API route/endpoint handlers
3. Input validation and sanitisation modules
4. Data model definitions
5. Frontend hooks that call the backend API
6. *(Skipped)* Utilities, config, components, test files, lock files

---

## UAT revision loop

If the UAT Tester returns a **NO-GO** verdict, OpenWally automatically runs a targeted revision cycle:

```
UAT: NO-GO
  → Backend Developer reads the UAT report, fixes backend defects
  → UI Developer reads the UAT report, fixes frontend defects
  → Quality Engineer re-tests the fixed code
  → UAT Tester re-evaluates (focused on prior failures + regression check)
  → GO? Done. Still NO-GO? Repeat up to --max-revisions times.
```

Each revision cycle saves its own artifacts (`revision_1_backend_fixes.md`, `revision_1_uat_report.md`, etc.) so you have a full audit trail. The scaffold step always runs at the end — even on a final NO-GO — so the project is always written to disk for manual fixes.

---

## Output

The generated project is written to `<output-dir>/<project-name>/`:

```
my-project/
├── src/my_project/              # Python backend source
│   ├── logging_config.py        # Structured JSON logging — DevOps
│   └── observability.py         # Prometheus /metrics — DevOps
├── tests/                       # pytest suite (every agent's Testing Notes + review findings)
│   ├── conftest.py
│   └── test_*.py
├── frontend/                    # React + TypeScript + Tailwind frontend
│   ├── src/
│   │   ├── components/ui/       # shadcn/ui primitive wrappers
│   │   ├── components/          # feature components
│   │   ├── pages/               # one file per route
│   │   ├── hooks/               # API hooks
│   │   ├── __tests__/           # Component tests
│   │   └── types/api.ts         # TypeScript types matching backend contracts
│   ├── Dockerfile               # node:24 build → nginx:alpine serve — harness
│   ├── nginx.conf               # SPA fallback + /api/ proxy — harness
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
├── migrations/                  # Reversible SQL migrations — Database Engineer
│   ├── 0001_*.sql
│   └── seed.sql
├── ops/                         # Reliability artifacts — SRE
│   ├── alerts.yaml              # AlertManager rules linked to runbooks
│   └── grafana/main-dashboard.json
├── perf/                        # Performance — Performance Engineer
│   └── k6/{smoke,load,spike}.js
├── docs/                        # User-facing docs — Technical Writer
│   ├── api.md
│   ├── architecture.md
│   ├── openapi.yaml             # OpenAPI 3.1 — API Designer
│   ├── adr/0001-*.md, 0002-*.md, ...
│   └── runbooks/*.md            # Per-alert runbooks — SRE
├── .github/workflows/           # CI/CD — DevOps Engineer
│   ├── ci.yml
│   └── docker.yml
├── Dockerfile                   # python:3.14-slim, multi-stage, non-root — harness
├── docker-compose.yml           # backend + frontend with healthcheck-gated deps — harness
├── Makefile                     # install / run / test / docker-* targets — harness
├── start.sh                     # 0.0.0.0 + $PORT bind — Backend Developer
├── conftest.py                  # makes src/ importable from any cwd — Backend Developer
├── deps.txt                     # Python packages (consumed by uv)
├── pyproject.toml               # Created by uv init
├── uv.lock                      # Pinned dependency tree
├── .dockerignore                # harness
├── .env.example                 # harness (extend with app-specific vars)
├── .gitignore
├── README.md                    # Project overview — Technical Writer
├── CONTRIBUTING.md              # Technical Writer
├── CHANGELOG.md                 # Technical Writer
└── .harness-docs/               # Full pipeline audit trail (16 artifacts + log)
    ├── openwally.log
    ├── 1_requirements.md
    ├── 2_architecture.md
    ├── 2a_api_spec.md
    ├── 3_security.md
    ├── 3a_database_design.md
    ├── 4_tasks.md
    ├── 5_ui_design.md
    ├── 6_implementation_manifest.md
    ├── 7_ui_manifest.md
    ├── 7a_devops_plan.md
    ├── 7b_sre_plan.md
    ├── 7c_performance_plan.md
    ├── 8_code_review.md
    ├── 9_test_plan.md
    ├── 10_uat_report.md
    ├── 11_documentation.md
    └── revision_*/              # Present only if revision cycles ran
```

After the pipeline finishes, OpenWally prints the commands to push your project to GitHub:

```bash
gh repo create my-project --private --source=./projects/my-project --push
```

---

## Running the generated project

Every generated project ships with a Makefile that abstracts both flows:

```bash
cd projects/my-project
cp .env.example .env          # edit with real values if the app needs any

# ── Native (Linux / macOS) ──
make install                  # uv sync + npm install
make run                      # ./start.sh — backend on :8000
make test                     # pytest

# Frontend dev server (second terminal)
make run-frontend             # vite dev on :5173

# ── Docker (recommended for prod) ──
make docker-build
make docker-up                # backend :8000, frontend :3000
make docker-logs
make docker-down
```

Hit `http://localhost:8000/health` to verify, and `http://localhost:8000/metrics` to see the Prometheus metrics the DevOps agent wired.

---

## Configuration

All model assignments can be overridden in `.env`. Every role independently supports either a **Claude model** or a **local Ollama model** — mix and match freely.

### All Claude (default — highest quality)

```dotenv
ANTHROPIC_API_KEY=sk-ant-...

# High-reasoning roles
PM_MODEL=claude-opus-4-7
ARCHITECT_MODEL=claude-opus-4-7
SECURITY_MODEL=claude-opus-4-7
DATABASE_MODEL=claude-opus-4-7
UI_DESIGNER_MODEL=claude-opus-4-7
UI_DEV_MODEL=claude-opus-4-7
CODE_REVIEWER_MODEL=claude-opus-4-7

# Specialist & engineering roles
API_DESIGNER_MODEL=claude-sonnet-4-6
EM_MODEL=claude-sonnet-4-6
DEV_MODEL=claude-sonnet-4-6
DEVOPS_MODEL=claude-sonnet-4-6
SRE_MODEL=claude-sonnet-4-6
PERF_MODEL=claude-sonnet-4-6
QA_MODEL=claude-sonnet-4-6
TECH_WRITER_MODEL=claude-sonnet-4-6

# Pass/fail evaluator
UAT_MODEL=claude-haiku-4-5-20251001
```

### Hybrid — Ollama for lighter roles (cost saving)

Keep Claude for high-reasoning roles and use free local models for pass/fail evaluation:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434

QA_MODEL=ollama/llama3.2
UAT_MODEL=ollama/mistral
TECH_WRITER_MODEL=ollama/llama3.2
```

### Fully local — no API key required

```dotenv
OLLAMA_BASE_URL=http://localhost:11434

PM_MODEL=ollama/llama3.2
ARCHITECT_MODEL=ollama/llama3.2
API_DESIGNER_MODEL=ollama/llama3.2
SECURITY_MODEL=ollama/mistral
DATABASE_MODEL=ollama/llama3.2
EM_MODEL=ollama/llama3.2
UI_DESIGNER_MODEL=ollama/llama3.2
UI_DEV_MODEL=ollama/llama3.2
DEV_MODEL=ollama/mistral
DEVOPS_MODEL=ollama/llama3.2
SRE_MODEL=ollama/llama3.2
PERF_MODEL=ollama/llama3.2
CODE_REVIEWER_MODEL=ollama/mistral
QA_MODEL=ollama/llama3.2
UAT_MODEL=ollama/llama3.2
TECH_WRITER_MODEL=ollama/llama3.2
```

### Ollama setup

```bash
# Install: https://ollama.com
ollama pull llama3.2
ollama pull mistral
ollama list   # confirm models are ready
```

---

## Evaluation harness

[Inspect AI](https://github.com/UKGovernmentAIS/inspect_ai) tasks in `eval/` measure pipeline output quality:

| Task | What it checks |
|---|---|
| `eval_requirements_completeness` | All six sections present, ≥3 numbered FRs and ACs |
| `eval_security_coverage` | STRIDE categories, ≥2 numbered SRs, risk ratings |
| `eval_uat_verdict` | Pipeline produces a clear GO or NO-GO verdict |
| `eval_pytest_pass_rate` | Fraction of generated tests that pass when pytest runs |
| `eval_npm_build` | Generated frontend builds without errors |

```bash
inspect eval eval/pipeline_eval.py --model anthropic/claude-sonnet-4-6
inspect view   # browse results in the web UI
```

---

## Project structure

```
openwally/
├── src/openwally/
│   ├── crew.py                     # OpenWallyCrew + RevisionCrew, TEAM_ROSTER, standards
│   ├── main.py                     # CLI — --mode, --review-depth, --max-revisions, revision loop
│   ├── scaffolding.py              # uv + npm + deploy file generation + git
│   ├── config/
│   │   ├── agents.yaml             # 16 agent roles, goals, backstories
│   │   └── tasks.yaml              # Task descriptions, context chains, {team_roster} injection
│   └── tools/
│       ├── artifact_reader.py      # Reads pipeline docs (reviewer + revision agents)
│       ├── project_file_writer.py  # Writes source files (path-doubling defended)
│       ├── project_file_reader.py  # Reads source files (code reviewer + QA)
│       ├── pytest_runner.py        # uv run --no-project pytest — in-pipeline validation
│       ├── npm_build_runner.py     # npm run build — in-pipeline validation
│       └── latest_version.py       # endoflife.date / PyPI / npm lookups (no API key)
├── eval/
│   ├── pipeline_eval.py            # Inspect AI task definitions
│   └── scorers.py                  # Custom quality scorers
├── .github/workflows/security.yml  # Bandit + pip-audit + Semgrep
└── assets/
    └── logo.png
```

---

## License

MIT
