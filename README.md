<p align="center">
  <img src="assets/logo.png" alt="OpenWally" width="220" />
</p>

<h1 align="center">OpenWally</h1>

<p align="center">
  An autonomous AI agent pipeline that generates complete software projects from a plain-text idea.<br/>
  Nine specialized agents — each backed by a different Claude model — collaborate to produce<br/>
  requirements, architecture, security analysis, backend code, a modern React frontend, tests, and a UAT report.
</p>

<p align="center">
  Built on <a href="https://github.com/crewaiinc/crewai">CrewAI</a> &nbsp;·&nbsp;
  Evaluated with <a href="https://github.com/UKGovernmentAIS/inspect_ai">Inspect AI</a> &nbsp;·&nbsp;
  Powered by <a href="https://www.anthropic.com">Anthropic Claude</a>
</p>

---

## How it works

You provide a project idea. The pipeline does the rest:

```
Program Manager → Software Architect → Security Architect → Engineering Manager
    → UI/UX Designer → Backend Developer → UI Developer → Quality Engineer → UAT Tester
```

Each agent reads the prior agent's output as context and writes its own artifact to `.harness-docs/`. The backend developer and UI developer write actual source files directly into the generated project. After the pipeline completes, the scaffolding step initialises a `uv`-managed Python environment, installs the React frontend with `npm`, and makes the first `git` commit — ready to push to GitHub.

### Agent roles and models

| Agent | Model | Responsibility |
|---|---|---|
| Program Manager | claude-opus-4-7 | Requirements doc with numbered FRs and acceptance criteria |
| Software Architect | claude-opus-4-7 | System design, API contracts, data models |
| Security Architect | claude-opus-4-7 | STRIDE threat model, numbered security requirements |
| Engineering Manager | claude-sonnet-4-6 | Ordered dev task list with definitions of done |
| UI/UX Designer | claude-opus-4-7 | Wireframes, design tokens, shadcn/ui component mapping |
| Backend Developer | claude-sonnet-4-6 | Python source code + `deps.txt` |
| UI Developer | claude-opus-4-7 | React + TypeScript + Tailwind + shadcn/ui frontend |
| Quality Engineer | claude-sonnet-4-6 | pytest suite for backend and frontend |
| UAT Tester | claude-haiku-4-5 | Pass/fail against every acceptance criterion, GO/NO-GO verdict |

Every model assignment is overridable via environment variable — see [Configuration](#configuration).

---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- [Node.js](https://nodejs.org/) 18+ and `npm` — for the generated frontend
- [git](https://git-scm.com/)
- An Anthropic API key

Optional, for pushing to GitHub:
- [GitHub CLI (`gh`)](https://cli.github.com/)

---

## Installation

```bash
git clone https://github.com/<you>/openwally.git
cd openwally

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -e .

# Configure your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
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

Then run:

```bash
openwally run --spec-file idea.md
```

### Run from an inline string

```bash
openwally run --spec "Build a URL shortener with per-link analytics and a React dashboard"
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--spec-file FILE` | — | Path to a `.md` or `.txt` file with the project spec |
| `--spec TEXT` | — | Project idea as an inline string (mutually exclusive with `--spec-file`) |
| `--name NAME` | derived from spec | Folder name for the generated project |
| `--output-dir DIR` | `./projects` | Parent directory for generated projects |

---

## Output

The generated project is written to `<output-dir>/<project-name>/`:

```
my-project/
├── src/my_project/          # Python backend source
│   └── ...
├── tests/                   # pytest test suite
│   ├── conftest.py
│   └── test_*.py
├── frontend/                # React + TypeScript + Tailwind frontend
│   ├── src/
│   │   ├── components/ui/   # shadcn/ui primitive wrappers
│   │   ├── components/      # feature components
│   │   ├── pages/           # one file per route
│   │   ├── hooks/           # API hooks (typed, no direct fetch in components)
│   │   └── types/api.ts     # TypeScript types matching backend contracts
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
├── deps.txt                 # Python package list (consumed by scaffolding)
├── pyproject.toml           # Created by uv init
├── uv.lock
├── .venv/                   # Python virtual environment
├── .gitignore
└── .harness-docs/           # Pipeline documents
    ├── 1_requirements.md
    ├── 2_architecture.md
    ├── 3_security.md
    ├── 4_tasks.md
    ├── 5_ui_design.md
    ├── 6_implementation_manifest.md
    ├── 7_ui_manifest.md
    ├── 8_test_plan.md
    └── 9_uat_report.md
```

After the pipeline finishes, OpenWally prints the exact commands to push your new project to GitHub:

```bash
# One-step create + push with GitHub CLI
gh repo create my-project --private --source=./projects/my-project --push

# Or manually
git -C ./projects/my-project remote add origin git@github.com:<you>/my-project.git
git -C ./projects/my-project push -u origin main
```

---

## Running the generated project

```bash
cd projects/my-project

# Backend (FastAPI example)
uv run uvicorn src.my_project.main:app --reload

# Frontend (in a second terminal)
cd frontend
npm run dev
```

---

## Configuration

All model assignments can be overridden in `.env`:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...

# Per-role model overrides — defaults shown
PM_MODEL=claude-opus-4-7
ARCHITECT_MODEL=claude-opus-4-7
SECURITY_MODEL=claude-opus-4-7
EM_MODEL=claude-sonnet-4-6
UI_DESIGNER_MODEL=claude-opus-4-7
UI_DEV_MODEL=claude-opus-4-7
DEV_MODEL=claude-sonnet-4-6
QA_MODEL=claude-sonnet-4-6
UAT_MODEL=claude-haiku-4-5-20251001

# Output directory for generated projects
OUTPUT_DIR=./projects
```

Assigning different models to different roles is intentional — it reduces single-model bias and lets high-complexity roles (architect, UI) use a more capable model while keeping cost down for simpler tasks.

---

## Evaluation harness

[Inspect AI](https://github.com/UKGovernmentAIS/inspect_ai) tasks in `eval/` measure pipeline output quality across three dimensions:

| Task | What it checks |
|---|---|
| `eval_requirements_completeness` | All six required sections present, ≥3 numbered FRs, ≥3 numbered ACs |
| `eval_security_coverage` | STRIDE categories mentioned, ≥2 numbered SRs, risk ratings present |
| `eval_uat_verdict` | Pipeline produces a clear GO or NO-GO verdict |

Run the full eval suite:

```bash
inspect eval eval/pipeline_eval.py --model anthropic/claude-sonnet-4-6
```

Results are logged by Inspect AI and viewable in its web UI (`inspect view`).

---

## Project structure

```
openwally/
├── src/openwally/
│   ├── crew.py              # CrewAI @CrewBase — agents, tasks, pipeline order
│   ├── main.py              # CLI entry point
│   ├── scaffolding.py       # uv + npm + git post-pipeline setup
│   ├── config/
│   │   ├── agents.yaml      # Agent roles, goals, backstories, model assignments
│   │   └── tasks.yaml       # Task descriptions, expected outputs, context chain
│   └── tools/
│       ├── artifact_writer.py      # Writes pipeline docs to .harness-docs/
│       └── project_file_writer.py  # Writes source files into the generated project
├── eval/
│   ├── pipeline_eval.py     # Inspect AI task definitions
│   └── scorers.py           # Custom quality scorers
└── assets/
    └── logo.png
```

---

## Publishing to GitHub

See [UPLOAD.md](UPLOAD.md) for a complete step-by-step guide to safely uploading this project to your private GitHub repository.

---

## License

MIT
