"""
Post-crew scaffolding: sets up the uv-managed Python backend, installs the
React frontend with npm, writes .gitignore, and makes the first git commit.
"""
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()

_GITIGNORE = """\
# Python
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/

# Node / frontend
frontend/node_modules/
frontend/dist/
frontend/.vite/

# Env & OS
.env
.DS_Store
"""

_DOCKERIGNORE = """\
.git
.gitignore
.venv
__pycache__
*.pyc
*.pyo
.pytest_cache
.ruff_cache
.harness-docs
.env
.env.*
!.env.example
node_modules
dist
build
.vite
*.log
.DS_Store
README.md
"""

_BACKEND_DOCKERFILE = """\
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

FROM python:3.12-slim AS runtime
RUN groupadd -r app && useradd -r -g app -u 1000 app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app . .
RUN chmod +x start.sh
ENV PATH="/app/.venv/bin:$PATH" \\
    PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \\
    CMD python -c "import urllib.request,sys; \\
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)" \\
    || exit 1
CMD ["./start.sh"]
"""

_FRONTEND_DOCKERFILE = """\
# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \\
    CMD wget -q -O - http://localhost/ > /dev/null 2>&1 || exit 1
"""

_FRONTEND_NGINX_CONF = """\
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # SPA fallback — let the client router handle unknown paths
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to the backend service (compose-network DNS)
    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""

_DOCKER_COMPOSE = """\
services:
  backend:
    build: .
    image: {project}-backend
    restart: unless-stopped
    env_file:
      - .env
    environment:
      PORT: "8000"
    ports:
      - "${{BACKEND_PORT:-8000}}:8000"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
{frontend_service}"""

_FRONTEND_COMPOSE_BLOCK = """\

  frontend:
    build: ./frontend
    image: {project}-frontend
    restart: unless-stopped
    ports:
      - "${{FRONTEND_PORT:-3000}}:80"
    depends_on:
      backend:
        condition: service_healthy
"""

_ENV_EXAMPLE = """\
# Application
PORT=8000

# Add other env vars your app needs:
# DATABASE_URL=
# SECRET_KEY=
# LOG_LEVEL=INFO
"""

_MAKEFILE = """\
.PHONY: help install run run-frontend test docker-build docker-up docker-down docker-logs clean

help:
\t@echo "Targets:"
\t@echo "  install        Install backend (uv sync) and frontend (npm install) deps"
\t@echo "  run            Run backend natively (./start.sh)"
\t@echo "  run-frontend   Run frontend dev server"
\t@echo "  test           Run pytest"
\t@echo "  docker-build   Build all Docker images"
\t@echo "  docker-up      Start the stack in the background"
\t@echo "  docker-down    Stop the stack"
\t@echo "  docker-logs    Tail container logs"
\t@echo "  clean          Remove caches and build artifacts"

install:
\tuv sync
\t@if [ -d frontend ]; then cd frontend && npm install; fi

run:
\t./start.sh

run-frontend:
\tcd frontend && npm run dev

test:
\tuv run pytest

docker-build:
\tdocker compose build

docker-up:
\tdocker compose up -d

docker-down:
\tdocker compose down

docker-logs:
\tdocker compose logs -f

clean:
\trm -rf .venv .pytest_cache .ruff_cache __pycache__ frontend/node_modules frontend/dist
"""

_README_DEPLOY_APPENDIX = """\

---

## Deployment

This project is deploy-ready for any Linux server or macOS, both natively and via Docker.

### Native (Linux / macOS)

Requires [`uv`](https://docs.astral.sh/uv/) and (if there is a frontend) Node.js 20+.

```sh
make install        # installs backend + frontend deps
cp .env.example .env # then edit .env with real values
make run            # starts the backend on http://localhost:8000
make test           # runs the test suite
```

### Docker (recommended for production)

Requires Docker 24+ with the `compose` plugin.

```sh
cp .env.example .env # edit .env first
make docker-build
make docker-up      # backend on :8000, frontend on :3000
make docker-logs
make docker-down
```

The backend image is multi-stage, runs as a non-root user, and exposes a `/health` endpoint used by the container's HEALTHCHECK. The frontend image builds the SPA and serves it via nginx with `/api/` proxied to the backend over the compose network.
"""


def _run(cmd: list[str], cwd: Path, label: str, required: bool = True) -> bool:
    console.print(f"  [dim]$ {' '.join(cmd)}[/dim]")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        level = "[red]Error" if required else "[yellow]Warning"
        console.print(f"  {level} ({label}):[/] {result.stderr.strip() or result.stdout.strip()}")
        return False
    console.print(f"  [green]✓[/green] {label}")
    return True


def _read_txt(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


# ── Python backend (uv) ───────────────────────────────────────────────────────

def _scaffold_backend(project_dir: Path, project_name: str) -> None:
    console.print("\n[bold cyan]Backend — uv[/bold cyan]")

    _run(["uv", "init", "--name", project_name, "--no-readme"], cwd=project_dir, label="uv init")

    # Remove the stub uv creates if the Developer already wrote main files
    for stub in ["hello.py", "main.py"]:
        candidate = project_dir / stub
        if candidate.exists() and candidate.stat().st_size < 100:
            candidate.unlink()

    deps = _read_txt(project_dir / "deps.txt")
    if deps:
        _run(["uv", "add"] + deps, cwd=project_dir, label=f"uv add ({len(deps)} packages)")
    else:
        console.print("  [yellow]deps.txt not found — skipping uv add[/yellow]")

    _run(["uv", "add", "--dev", "pytest", "pytest-asyncio"], cwd=project_dir, label="uv add --dev pytest")
    _run(["uv", "sync"], cwd=project_dir, label="uv sync")


# ── React frontend (npm) ──────────────────────────────────────────────────────

def _scaffold_frontend(project_dir: Path) -> None:
    frontend_dir = project_dir / "frontend"
    if not frontend_dir.exists() or not (frontend_dir / "package.json").exists():
        console.print("\n  [dim]No frontend/package.json found — skipping npm install[/dim]")
        return

    console.print("\n[bold cyan]Frontend — npm[/bold cyan]")

    # Prefer npm; fall back gracefully if not available
    ok = _run(["npm", "install"], cwd=frontend_dir, label="npm install", required=False)
    if not ok:
        console.print(
            "  [yellow]npm install failed or npm not found.[/yellow]\n"
            f"  Run manually:  cd {frontend_dir} && npm install"
        )
        return

    # Type-check the generated frontend
    _run(["npm", "run", "build", "--", "--noEmit"], cwd=frontend_dir,
         label="tsc type-check", required=False)


# ── Deploy scaffolding (Docker + Make) ────────────────────────────────────────

def _scaffold_deploy(project_dir: Path, project_name: str) -> None:
    console.print("\n[bold cyan]Deploy scaffolding[/bold cyan]")

    has_frontend = (project_dir / "frontend" / "package.json").exists()

    (project_dir / "Dockerfile").write_text(_BACKEND_DOCKERFILE, encoding="utf-8")
    console.print("  [green]✓[/green] Dockerfile (backend)")

    (project_dir / ".dockerignore").write_text(_DOCKERIGNORE, encoding="utf-8")
    console.print("  [green]✓[/green] .dockerignore")

    if not (project_dir / ".env.example").exists():
        (project_dir / ".env.example").write_text(_ENV_EXAMPLE, encoding="utf-8")
        console.print("  [green]✓[/green] .env.example")

    (project_dir / "Makefile").write_text(_MAKEFILE, encoding="utf-8")
    console.print("  [green]✓[/green] Makefile")

    if has_frontend:
        frontend_dir = project_dir / "frontend"
        (frontend_dir / "Dockerfile").write_text(_FRONTEND_DOCKERFILE, encoding="utf-8")
        (frontend_dir / "nginx.conf").write_text(_FRONTEND_NGINX_CONF, encoding="utf-8")
        (frontend_dir / ".dockerignore").write_text(_DOCKERIGNORE, encoding="utf-8")
        console.print("  [green]✓[/green] frontend/Dockerfile + nginx.conf")
        frontend_block = _FRONTEND_COMPOSE_BLOCK.format(project=project_name)
    else:
        frontend_block = ""

    compose = _DOCKER_COMPOSE.format(project=project_name, frontend_service=frontend_block)
    (project_dir / "docker-compose.yml").write_text(compose, encoding="utf-8")
    console.print("  [green]✓[/green] docker-compose.yml")

    # Ensure start.sh is executable if the agent wrote one
    start_sh = project_dir / "start.sh"
    if start_sh.exists():
        start_sh.chmod(0o755)
        console.print("  [green]✓[/green] start.sh marked executable")
    else:
        console.print("  [yellow]Warning:[/yellow] start.sh not found — Docker entrypoint will fail")

    # Append a deployment section to README so users see the Docker / native flows
    readme = project_dir / "README.md"
    appendix = _README_DEPLOY_APPENDIX
    if readme.exists():
        existing = readme.read_text(encoding="utf-8")
        if "## Deployment" not in existing:
            readme.write_text(existing.rstrip() + "\n" + appendix, encoding="utf-8")
            console.print("  [green]✓[/green] README.md — appended Deployment section")
    else:
        readme.write_text(f"# {project_name}\n" + appendix, encoding="utf-8")
        console.print("  [green]✓[/green] README.md — created with Deployment section")


# ── Git ───────────────────────────────────────────────────────────────────────

def _init_git(project_dir: Path, project_name: str) -> None:
    console.print("\n[bold cyan]Git[/bold cyan]")

    (project_dir / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    console.print("  [green]✓[/green] .gitignore written")

    _run(["git", "init"], cwd=project_dir, label="git init")
    _run(["git", "add", "-A"], cwd=project_dir, label="git add -A")
    _run(
        ["git", "commit", "-m", "Initial commit — generated by openwally"],
        cwd=project_dir,
        label="git commit",
    )

    console.print(f"\n[bold green]Project ready:[/bold green] {project_dir}")
    console.print(
        f"\n  Push to GitHub (choose one):\n\n"
        f"    [cyan]gh repo create {project_name} --private --source={project_dir} --push[/cyan]\n\n"
        f"  or:\n\n"
        f"    git -C {project_dir} remote add origin git@github.com:<you>/{project_name}.git\n"
        f"    git -C {project_dir} push -u origin main\n"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def scaffold(project_dir: Path, project_name: str) -> None:
    console.print(f"\n[bold]Scaffolding:[/bold] {project_dir}")
    _scaffold_backend(project_dir, project_name)
    _scaffold_frontend(project_dir)
    _scaffold_deploy(project_dir, project_name)
    _init_git(project_dir, project_name)
