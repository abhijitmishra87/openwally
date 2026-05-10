import os
from pathlib import Path
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv
from loguru import logger

from openwally.tools.artifact_reader import ArtifactReaderTool
from openwally.tools.project_file_writer import ProjectFileWriterTool
from openwally.tools.project_file_reader import ProjectFileReaderTool
from openwally.tools.pytest_runner import PytestRunnerTool
from openwally.tools.npm_build_runner import NpmBuildTool

load_dotenv()

_MODELS: dict[str, str] = {
    "PM_MODEL":             os.getenv("PM_MODEL",             "claude-opus-4-7"),
    "ARCHITECT_MODEL":      os.getenv("ARCHITECT_MODEL",      "claude-opus-4-7"),
    "SECURITY_MODEL":       os.getenv("SECURITY_MODEL",       "claude-opus-4-7"),
    "EM_MODEL":             os.getenv("EM_MODEL",             "claude-sonnet-4-6"),
    "UI_DESIGNER_MODEL":    os.getenv("UI_DESIGNER_MODEL",    "claude-opus-4-7"),
    "UI_DEV_MODEL":         os.getenv("UI_DEV_MODEL",         "claude-opus-4-7"),
    "DEV_MODEL":            os.getenv("DEV_MODEL",            "claude-sonnet-4-6"),
    "CODE_REVIEWER_MODEL":  os.getenv("CODE_REVIEWER_MODEL",  "claude-opus-4-7"),
    "QA_MODEL":             os.getenv("QA_MODEL",             "claude-sonnet-4-6"),
    "UAT_MODEL":            os.getenv("UAT_MODEL",            "claude-haiku-4-5-20251001"),
}

# Valid modes and which tasks pause for human review in each mode.
# "milestone" pauses at the three highest-leverage decision points:
#   - after requirements (before architecture locks in)
#   - after UI design   (before coding starts)
#   - after tests       (before UAT final verdict)
MODES = ("autonomous", "milestone", "interactive")
_MILESTONE_TASKS = {"write_requirements", "design_ui", "write_tests"}

REVIEW_DEPTHS = ("off", "standard", "thorough")

# Injected as {backend_validation_instructions} / {frontend_validation_instructions}
# into implement_code, implement_ui, fix_code, fix_ui when --no-validate is not set.
BACKEND_STANDARDS: str = (
    "Every generated backend MUST follow these non-negotiable engineering standards "
    "regardless of what the spec says:\n\n"
    "  1. **Logging** — import and use a logger (Python `logging` or `loguru`) in every "
    "module. Never use `print()` in production code. Log at INFO for normal operations, "
    "WARNING for recoverable issues, ERROR for failures.\n"
    "  2. **Error handling** — never use a bare `except:`. Always catch specific exception "
    "types. Every API endpoint must return a structured error response "
    "(e.g. `{\"error\": \"message\"}`) — never let exceptions bubble to a 500 with a raw traceback.\n"
    "  3. **Health endpoint** — include a `GET /health` endpoint that returns "
    "`{\"status\": \"ok\"}` with HTTP 200. Required for deployment and monitoring.\n"
    "  4. **Config from env vars** — all configuration (DB URLs, API keys, ports, feature "
    "flags) must come from environment variables via `python-dotenv` or `pydantic-settings`. "
    "No hardcoded values anywhere in the source.\n"
    "  5. **Pydantic validation** — use Pydantic models for all request bodies and "
    "response shapes. Never access `request.json()` directly without validation.\n"
    "  6. **Consistent HTTP status codes** — 201 for resource creation, 400 for bad input, "
    "401 for unauthenticated, 403 for forbidden, 404 for not found, 422 for validation "
    "errors, 500 for unexpected server errors.\n\n"
    "Implement these in every file where applicable before saving the manifest."
)

FRONTEND_STANDARDS: str = (
    "Every generated frontend MUST follow these non-negotiable engineering standards "
    "regardless of what the spec says:\n\n"
    "  1. **Error boundaries** — wrap every major page/route in a React error boundary "
    "component so a single component crash does not take down the whole app.\n"
    "  2. **Env-based API URL** — all backend API calls must use `VITE_API_BASE_URL` from "
    "the environment. No hardcoded URLs or ports anywhere.\n"
    "  3. **Loading / error / empty states** — every component that fetches data must "
    "handle all three states explicitly. Do not render null or a blank screen.\n"
    "  4. **No console.log in production** — remove all `console.log` statements. Use "
    "a conditional logger or remove entirely before saving files.\n"
    "  5. **TypeScript strict mode** — `strict: true` in tsconfig.json. Zero `any` types. "
    "All props and hook return values must be fully typed.\n"
    "  6. **Accessible interactive elements** — every button, input, and link must have "
    "an `aria-label` or visible label. Form fields must be associated with `<label>` elements.\n\n"
    "Implement these in every file where applicable before saving the manifest."
)

REVIEWER_STANDARDS: str = (
    "### Engineering Standards Compliance\n"
    "In addition to architecture and security checks, verify the following standards "
    "are met in the generated code:\n\n"
    "  **Backend:**\n"
    "  - Every module imports and uses a logger — no bare `print()` calls\n"
    "  - No bare `except:` clauses anywhere\n"
    "  - A `GET /health` endpoint exists and returns `{\"status\": \"ok\"}`\n"
    "  - All config values come from env vars — no hardcoded secrets, URLs, or ports\n"
    "  - All API endpoints return structured error responses on failure\n\n"
    "  **Frontend:**\n"
    "  - Error boundaries present on all page-level components\n"
    "  - API base URL sourced from `VITE_API_BASE_URL` — no hardcoded URLs\n"
    "  - No `console.log` statements in any component or hook\n"
    "  - TypeScript strict mode enabled in tsconfig.json\n\n"
    "Flag any violation as a finding in the Code Quality Findings section."
)

BACKEND_VALIDATION_INSTRUCTIONS: str = (
    "After saving the manifest, use the `run_pytest` tool to run the test suite.\n"
    "If tests fail, read the error output carefully, fix the failing source files using\n"
    "`write_project_file`, and run pytest again. Repeat until all tests pass or after\n"
    "3 fix attempts. Append the final pytest result to the bottom of your manifest."
)

FRONTEND_VALIDATION_INSTRUCTIONS: str = (
    "After saving the manifest, use the `run_npm_build` tool to build the frontend.\n"
    "If the build fails, fix the TypeScript errors or missing imports using\n"
    "`write_project_file`, and build again. Repeat until the build succeeds or after\n"
    "3 fix attempts. Append the final build result to the bottom of your manifest."
)

# Injected as {review_instructions} into the review_code task description.
_REVIEW_INSTRUCTIONS: dict[str, str] = {
    "standard": (
        "Read the code using a RISK-PRIORITISED approach — work through these tiers "
        "in order and stop once you have enough evidence to fill every report section:\n\n"
        "  Tier 1 — MUST READ IN FULL (highest risk):\n"
        "    • Any file whose name contains: auth, token, jwt, session, middleware, "
        "permission, role, password, hash, crypto, secret\n"
        "    • All API route/endpoint handler files\n"
        "    • All input validation and sanitisation modules\n\n"
        "  Tier 2 — MUST READ IN FULL (correctness risk):\n"
        "    • Data model definitions (models.py, schemas.py, types/api.ts)\n"
        "    • Frontend hooks that call the backend API (src/hooks/)\n"
        "    • Database access / repository layer\n\n"
        "  Tier 3 — SKIM ONLY (read only if a Tier 1/2 file references something suspicious):\n"
        "    • Utility helpers, config files, constants\n"
        "    • Frontend components and pages (unless a Tier 1 issue traces here)\n\n"
        "  SKIP entirely:\n"
        "    • Test files, lock files (uv.lock, package-lock.json), generated "
        "type declarations (.d.ts)\n\n"
        "For each file you read, note which tier it belongs to in your internal reasoning."
    ),
    "thorough": (
        "Read EVERY source file listed in both manifests — no exceptions, no skimming.\n\n"
        "  • Read every backend file from 6_implementation_manifest.md\n"
        "  • Read every frontend file from 7_ui_manifest.md\n"
        "  • SKIP only: test files, lock files (uv.lock, package-lock.json), "
        "and generated .d.ts declaration files\n\n"
        "Thoroughness is the goal. Flag every discrepancy no matter how minor. "
        "Every claim in the report must be backed by a direct quote or line reference "
        "from the code you read."
    ),
}


def _make_task_callback(on_task_complete=None):
    def callback(output) -> None:
        agent_name = getattr(output, "agent", "unknown agent")
        summary = (output.summary or output.raw or "")[:120].replace("\n", " ")
        logger.info("Agent handover — {} finished | summary: {}…", agent_name, summary)
        if on_task_complete:
            on_task_complete(agent_name)
    return callback


def _llm(model_key: str) -> LLM:
    model = _MODELS[model_key]
    if model.startswith("ollama/"):
        return LLM(
            model=model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    if "/" not in model:
        model = f"anthropic/{model}"
    return LLM(
        model=model,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


# ── Main pipeline crew ────────────────────────────────────────────────────────

@CrewBase
class OpenWallyCrew:
    """Sequential pipeline: PM → Architect → Security → EM → UI Designer →
    Backend Dev → UI Dev → Code Reviewer → QA → UAT"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, project_dir: Path, docs_dir: Path,
                 mode: str = "autonomous", review_depth: str = "standard",
                 validate: bool = True, on_task_complete=None) -> None:
        assert mode in MODES, f"mode must be one of {MODES}"
        assert review_depth in REVIEW_DEPTHS, f"review_depth must be one of {REVIEW_DEPTHS}"
        self._project_dir = project_dir
        self._docs_dir = docs_dir
        self._mode = mode
        self._review_depth = review_depth
        self._validate = validate
        self._on_task_complete = on_task_complete

    # ── Tool factories ────────────────────────────────────────────────────────

    def _doc_reader(self) -> ArtifactReaderTool:
        return ArtifactReaderTool(docs_dir=str(self._docs_dir))

    def _file_writer(self) -> ProjectFileWriterTool:
        return ProjectFileWriterTool(project_dir=str(self._project_dir))

    def _file_reader(self) -> ProjectFileReaderTool:
        return ProjectFileReaderTool(project_dir=str(self._project_dir))

    def _pytest_runner(self) -> PytestRunnerTool:
        return PytestRunnerTool(project_dir=str(self._project_dir))

    def _npm_builder(self) -> NpmBuildTool:
        return NpmBuildTool(project_dir=str(self._project_dir))

    def _human_input(self, task_name: str) -> bool:
        if self._mode == "interactive":
            return True
        if self._mode == "milestone" and task_name in _MILESTONE_TASKS:
            return True
        return False

    # ── Agents ────────────────────────────────────────────────────────────────

    @agent
    def program_manager(self) -> Agent:
        return Agent(config=self.agents_config["program_manager"],
                     llm=_llm("PM_MODEL"), tools=[], verbose=True)

    @agent
    def software_architect(self) -> Agent:
        return Agent(config=self.agents_config["software_architect"],
                     llm=_llm("ARCHITECT_MODEL"), tools=[], verbose=True)

    @agent
    def security_architect(self) -> Agent:
        return Agent(config=self.agents_config["security_architect"],
                     llm=_llm("SECURITY_MODEL"), tools=[], verbose=True)

    @agent
    def engineering_manager(self) -> Agent:
        return Agent(config=self.agents_config["engineering_manager"],
                     llm=_llm("EM_MODEL"), tools=[], verbose=True)

    @agent
    def ui_designer(self) -> Agent:
        return Agent(config=self.agents_config["ui_designer"],
                     llm=_llm("UI_DESIGNER_MODEL"), tools=[], verbose=True)

    @agent
    def developer(self) -> Agent:
        tools = [self._file_writer()]
        if self._validate:
            tools.append(self._pytest_runner())
        return Agent(config=self.agents_config["developer"],
                     llm=_llm("DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def ui_developer(self) -> Agent:
        tools = [self._file_writer()]
        if self._validate:
            tools.append(self._npm_builder())
        return Agent(config=self.agents_config["ui_developer"],
                     llm=_llm("UI_DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def code_reviewer(self) -> Agent:
        return Agent(config=self.agents_config["code_reviewer"],
                     llm=_llm("CODE_REVIEWER_MODEL"),
                     tools=[self._file_reader(), self._doc_reader()],
                     verbose=True)

    @agent
    def quality_engineer(self) -> Agent:
        return Agent(config=self.agents_config["quality_engineer"],
                     llm=_llm("QA_MODEL"),
                     tools=[self._file_writer(), self._file_reader(), self._doc_reader()],
                     verbose=True)

    @agent
    def uat_tester(self) -> Agent:
        return Agent(config=self.agents_config["uat_tester"],
                     llm=_llm("UAT_MODEL"),
                     tools=[self._doc_reader()], verbose=True)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @task
    def write_requirements(self) -> Task:
        return Task(config=self.tasks_config["write_requirements"],
                    human_input=self._human_input("write_requirements"),
                    output_file=str(self._docs_dir / "1_requirements.md"))

    @task
    def design_system(self) -> Task:
        return Task(config=self.tasks_config["design_system"],
                    human_input=self._human_input("design_system"),
                    output_file=str(self._docs_dir / "2_architecture.md"))

    @task
    def threat_model(self) -> Task:
        return Task(config=self.tasks_config["threat_model"],
                    human_input=self._human_input("threat_model"),
                    output_file=str(self._docs_dir / "3_security.md"))

    @task
    def plan_tasks(self) -> Task:
        return Task(config=self.tasks_config["plan_tasks"],
                    human_input=self._human_input("plan_tasks"),
                    output_file=str(self._docs_dir / "4_tasks.md"))

    @task
    def design_ui(self) -> Task:
        return Task(config=self.tasks_config["design_ui"],
                    human_input=self._human_input("design_ui"),
                    output_file=str(self._docs_dir / "5_ui_design.md"))

    @task
    def implement_code(self) -> Task:
        return Task(config=self.tasks_config["implement_code"],
                    human_input=self._human_input("implement_code"),
                    output_file=str(self._docs_dir / "6_implementation_manifest.md"))

    @task
    def implement_ui(self) -> Task:
        return Task(config=self.tasks_config["implement_ui"],
                    human_input=self._human_input("implement_ui"),
                    output_file=str(self._docs_dir / "7_ui_manifest.md"))

    @task
    def review_code(self) -> Task:
        return Task(config=self.tasks_config["review_code"],
                    human_input=self._human_input("review_code"),
                    output_file=str(self._docs_dir / "8_code_review.md"))

    @task
    def write_tests(self) -> Task:
        return Task(config=self.tasks_config["write_tests"],
                    human_input=self._human_input("write_tests"),
                    output_file=str(self._docs_dir / "9_test_plan.md"))

    @task
    def uat_report(self) -> Task:
        return Task(config=self.tasks_config["uat_report"],
                    human_input=self._human_input("uat_report"),
                    output_file=str(self._docs_dir / "10_uat_report.md"))

    # ── Crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        tasks = [
            self.write_requirements(),
            self.design_system(),
            self.threat_model(),
            self.plan_tasks(),
            self.design_ui(),
            self.implement_code(),
            self.implement_ui(),
        ]
        if self._review_depth != "off":
            tasks.append(self.review_code())
        tasks.extend([self.write_tests(), self.uat_report()])
        return Crew(agents=self.agents, tasks=tasks,
                    process=Process.sequential, verbose=True,
                    task_callback=_make_task_callback(self._on_task_complete))


# ── Revision crew (runs only on NO-GO) ───────────────────────────────────────

@CrewBase
class RevisionCrew:
    """Targeted fix cycle: Backend Dev → UI Dev → QA → UAT.
    Runs after the main pipeline returns NO-GO."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, project_dir: Path, docs_dir: Path,
                 revision_num: int, mode: str = "autonomous",
                 validate: bool = True, on_task_complete=None) -> None:
        self._project_dir = project_dir
        self._docs_dir = docs_dir
        self._revision_num = revision_num
        self._mode = mode
        self._validate = validate
        self._on_task_complete = on_task_complete

    def _doc_reader(self) -> ArtifactReaderTool:
        return ArtifactReaderTool(docs_dir=str(self._docs_dir))

    def _file_writer(self) -> ProjectFileWriterTool:
        return ProjectFileWriterTool(project_dir=str(self._project_dir))

    def _file_reader(self) -> ProjectFileReaderTool:
        return ProjectFileReaderTool(project_dir=str(self._project_dir))

    def _pytest_runner(self) -> PytestRunnerTool:
        return PytestRunnerTool(project_dir=str(self._project_dir))

    def _npm_builder(self) -> NpmBuildTool:
        return NpmBuildTool(project_dir=str(self._project_dir))

    def _human_input(self) -> bool:
        return self._mode == "interactive"

    # ── Agents ────────────────────────────────────────────────────────────────

    @agent
    def developer(self) -> Agent:
        tools = [self._file_writer(), self._file_reader(), self._doc_reader()]
        if self._validate:
            tools.append(self._pytest_runner())
        return Agent(config=self.agents_config["developer"],
                     llm=_llm("DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def ui_developer(self) -> Agent:
        tools = [self._file_writer(), self._file_reader(), self._doc_reader()]
        if self._validate:
            tools.append(self._npm_builder())
        return Agent(config=self.agents_config["ui_developer"],
                     llm=_llm("UI_DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def quality_engineer(self) -> Agent:
        return Agent(config=self.agents_config["quality_engineer"],
                     llm=_llm("QA_MODEL"),
                     tools=[self._file_writer(), self._file_reader(), self._doc_reader()],
                     verbose=True)

    @agent
    def uat_tester(self) -> Agent:
        return Agent(config=self.agents_config["uat_tester"],
                     llm=_llm("UAT_MODEL"),
                     tools=[self._doc_reader()], verbose=True)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @task
    def fix_code(self) -> Task:
        return Task(config=self.tasks_config["fix_code"],
                    human_input=self._human_input(),
                    output_file=str(self._docs_dir / f"revision_{self._revision_num}_backend_fixes.md"))

    @task
    def fix_ui(self) -> Task:
        return Task(config=self.tasks_config["fix_ui"],
                    human_input=self._human_input(),
                    output_file=str(self._docs_dir / f"revision_{self._revision_num}_ui_fixes.md"))

    @task
    def re_test(self) -> Task:
        return Task(config=self.tasks_config["re_test"],
                    human_input=self._human_input(),
                    output_file=str(self._docs_dir / f"revision_{self._revision_num}_test_plan.md"))

    @task
    def re_uat(self) -> Task:
        return Task(config=self.tasks_config["re_uat"],
                    human_input=self._human_input(),
                    output_file=str(self._docs_dir / f"revision_{self._revision_num}_uat_report.md"))

    # ── Crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks,
                    process=Process.sequential, verbose=True,
                    task_callback=_make_task_callback(self._on_task_complete))
