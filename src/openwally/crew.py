import os
from pathlib import Path
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

from openwally.tools.artifact_writer import ArtifactWriterTool
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
                 validate: bool = True) -> None:
        assert mode in MODES, f"mode must be one of {MODES}"
        assert review_depth in REVIEW_DEPTHS, f"review_depth must be one of {REVIEW_DEPTHS}"
        self._project_dir = project_dir
        self._docs_dir = docs_dir
        self._mode = mode
        self._review_depth = review_depth
        self._validate = validate
        super().__init__()

    # ── Tool factories ────────────────────────────────────────────────────────

    def _doc_writer(self) -> ArtifactWriterTool:
        return ArtifactWriterTool(output_dir=str(self._docs_dir))

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
                     llm=_llm("PM_MODEL"), tools=[self._doc_writer()], verbose=True)

    @agent
    def software_architect(self) -> Agent:
        return Agent(config=self.agents_config["software_architect"],
                     llm=_llm("ARCHITECT_MODEL"), tools=[self._doc_writer()], verbose=True)

    @agent
    def security_architect(self) -> Agent:
        return Agent(config=self.agents_config["security_architect"],
                     llm=_llm("SECURITY_MODEL"), tools=[self._doc_writer()], verbose=True)

    @agent
    def engineering_manager(self) -> Agent:
        return Agent(config=self.agents_config["engineering_manager"],
                     llm=_llm("EM_MODEL"), tools=[self._doc_writer()], verbose=True)

    @agent
    def ui_designer(self) -> Agent:
        return Agent(config=self.agents_config["ui_designer"],
                     llm=_llm("UI_DESIGNER_MODEL"), tools=[self._doc_writer()], verbose=True)

    @agent
    def developer(self) -> Agent:
        tools = [self._file_writer(), self._doc_writer()]
        if self._validate:
            tools.append(self._pytest_runner())
        return Agent(config=self.agents_config["developer"],
                     llm=_llm("DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def ui_developer(self) -> Agent:
        tools = [self._file_writer(), self._doc_writer()]
        if self._validate:
            tools.append(self._npm_builder())
        return Agent(config=self.agents_config["ui_developer"],
                     llm=_llm("UI_DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def code_reviewer(self) -> Agent:
        return Agent(config=self.agents_config["code_reviewer"],
                     llm=_llm("CODE_REVIEWER_MODEL"),
                     tools=[self._file_reader(), self._doc_reader(), self._doc_writer()],
                     verbose=True)

    @agent
    def quality_engineer(self) -> Agent:
        return Agent(config=self.agents_config["quality_engineer"],
                     llm=_llm("QA_MODEL"),
                     tools=[self._file_writer(), self._file_reader(),
                            self._doc_writer(), self._doc_reader()],
                     verbose=True)

    @agent
    def uat_tester(self) -> Agent:
        return Agent(config=self.agents_config["uat_tester"],
                     llm=_llm("UAT_MODEL"),
                     tools=[self._doc_writer(), self._doc_reader()], verbose=True)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @task
    def write_requirements(self) -> Task:
        return Task(config=self.tasks_config["write_requirements"],
                    human_input=self._human_input("write_requirements"))

    @task
    def design_system(self) -> Task:
        return Task(config=self.tasks_config["design_system"],
                    human_input=self._human_input("design_system"))

    @task
    def threat_model(self) -> Task:
        return Task(config=self.tasks_config["threat_model"],
                    human_input=self._human_input("threat_model"))

    @task
    def plan_tasks(self) -> Task:
        return Task(config=self.tasks_config["plan_tasks"],
                    human_input=self._human_input("plan_tasks"))

    @task
    def design_ui(self) -> Task:
        return Task(config=self.tasks_config["design_ui"],
                    human_input=self._human_input("design_ui"))

    @task
    def implement_code(self) -> Task:
        return Task(config=self.tasks_config["implement_code"],
                    human_input=self._human_input("implement_code"))

    @task
    def implement_ui(self) -> Task:
        return Task(config=self.tasks_config["implement_ui"],
                    human_input=self._human_input("implement_ui"))

    @task
    def review_code(self) -> Task:
        return Task(config=self.tasks_config["review_code"],
                    human_input=self._human_input("review_code"))

    @task
    def write_tests(self) -> Task:
        return Task(config=self.tasks_config["write_tests"],
                    human_input=self._human_input("write_tests"))

    @task
    def uat_report(self) -> Task:
        return Task(config=self.tasks_config["uat_report"],
                    human_input=self._human_input("uat_report"))

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
                    process=Process.sequential, verbose=True)


# ── Revision crew (runs only on NO-GO) ───────────────────────────────────────

@CrewBase
class RevisionCrew:
    """Targeted fix cycle: Backend Dev → UI Dev → QA → UAT.
    Runs after the main pipeline returns NO-GO."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, project_dir: Path, docs_dir: Path,
                 revision_num: int, mode: str = "autonomous",
                 validate: bool = True) -> None:
        self._project_dir = project_dir
        self._docs_dir = docs_dir
        self._revision_num = revision_num
        self._mode = mode
        self._validate = validate
        super().__init__()

    def _doc_writer(self) -> ArtifactWriterTool:
        return ArtifactWriterTool(output_dir=str(self._docs_dir))

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
        tools = [self._file_writer(), self._file_reader(),
                 self._doc_writer(), self._doc_reader()]
        if self._validate:
            tools.append(self._pytest_runner())
        return Agent(config=self.agents_config["developer"],
                     llm=_llm("DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def ui_developer(self) -> Agent:
        tools = [self._file_writer(), self._file_reader(),
                 self._doc_writer(), self._doc_reader()]
        if self._validate:
            tools.append(self._npm_builder())
        return Agent(config=self.agents_config["ui_developer"],
                     llm=_llm("UI_DEV_MODEL"), tools=tools, verbose=True)

    @agent
    def quality_engineer(self) -> Agent:
        return Agent(config=self.agents_config["quality_engineer"],
                     llm=_llm("QA_MODEL"),
                     tools=[self._file_writer(), self._file_reader(),
                            self._doc_writer(), self._doc_reader()],
                     verbose=True)

    @agent
    def uat_tester(self) -> Agent:
        return Agent(config=self.agents_config["uat_tester"],
                     llm=_llm("UAT_MODEL"),
                     tools=[self._doc_writer(), self._doc_reader()],
                     verbose=True)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @task
    def fix_code(self) -> Task:
        return Task(config=self.tasks_config["fix_code"],
                    human_input=self._human_input())

    @task
    def fix_ui(self) -> Task:
        return Task(config=self.tasks_config["fix_ui"],
                    human_input=self._human_input())

    @task
    def re_test(self) -> Task:
        return Task(config=self.tasks_config["re_test"],
                    human_input=self._human_input())

    @task
    def re_uat(self) -> Task:
        return Task(config=self.tasks_config["re_uat"],
                    human_input=self._human_input())

    # ── Crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks,
                    process=Process.sequential, verbose=True)
