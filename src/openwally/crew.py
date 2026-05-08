import os
from pathlib import Path
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

from openwally.tools.artifact_writer import ArtifactWriterTool
from openwally.tools.project_file_writer import ProjectFileWriterTool

load_dotenv()

_MODELS: dict[str, str] = {
    "PM_MODEL":         os.getenv("PM_MODEL",         "claude-opus-4-7"),
    "ARCHITECT_MODEL":  os.getenv("ARCHITECT_MODEL",  "claude-opus-4-7"),
    "SECURITY_MODEL":   os.getenv("SECURITY_MODEL",   "claude-opus-4-7"),
    "EM_MODEL":         os.getenv("EM_MODEL",         "claude-sonnet-4-6"),
    "UI_DESIGNER_MODEL":os.getenv("UI_DESIGNER_MODEL","claude-opus-4-7"),
    "UI_DEV_MODEL":     os.getenv("UI_DEV_MODEL",     "claude-opus-4-7"),
    "DEV_MODEL":        os.getenv("DEV_MODEL",        "claude-sonnet-4-6"),
    "QA_MODEL":         os.getenv("QA_MODEL",         "claude-sonnet-4-6"),
    "UAT_MODEL":        os.getenv("UAT_MODEL",        "claude-haiku-4-5-20251001"),
}


def _llm(model_key: str) -> LLM:
    model = _MODELS[model_key]
    if model.startswith("ollama/"):
        return LLM(
            model=model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    # accept explicit provider prefix (e.g. "anthropic/claude-...") or bare model name
    if "/" not in model:
        model = f"anthropic/{model}"
    return LLM(
        model=model,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )


@CrewBase
class OpenWallyCrew:
    """Sequential pipeline: PM → Architect → Security → EM → Dev → QA → UAT"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(self, project_dir: Path, docs_dir: Path) -> None:
        self._project_dir = project_dir
        self._docs_dir = docs_dir
        super().__init__()

    def _doc_writer(self) -> ArtifactWriterTool:
        return ArtifactWriterTool(output_dir=str(self._docs_dir))

    def _file_writer(self) -> ProjectFileWriterTool:
        return ProjectFileWriterTool(project_dir=str(self._project_dir))

    # ── Agents ────────────────────────────────────────────────────────────────

    @agent
    def program_manager(self) -> Agent:
        return Agent(
            config=self.agents_config["program_manager"],
            llm=_llm("PM_MODEL"),
            tools=[self._doc_writer()],
            verbose=True,
        )

    @agent
    def software_architect(self) -> Agent:
        return Agent(
            config=self.agents_config["software_architect"],
            llm=_llm("ARCHITECT_MODEL"),
            tools=[self._doc_writer()],
            verbose=True,
        )

    @agent
    def security_architect(self) -> Agent:
        return Agent(
            config=self.agents_config["security_architect"],
            llm=_llm("SECURITY_MODEL"),
            tools=[self._doc_writer()],
            verbose=True,
        )

    @agent
    def engineering_manager(self) -> Agent:
        return Agent(
            config=self.agents_config["engineering_manager"],
            llm=_llm("EM_MODEL"),
            tools=[self._doc_writer()],
            verbose=True,
        )

    @agent
    def ui_designer(self) -> Agent:
        return Agent(
            config=self.agents_config["ui_designer"],
            llm=_llm("UI_DESIGNER_MODEL"),
            tools=[self._doc_writer()],
            verbose=True,
        )

    @agent
    def ui_developer(self) -> Agent:
        return Agent(
            config=self.agents_config["ui_developer"],
            llm=_llm("UI_DEV_MODEL"),
            tools=[self._file_writer(), self._doc_writer()],
            verbose=True,
        )

    @agent
    def developer(self) -> Agent:
        return Agent(
            config=self.agents_config["developer"],
            llm=_llm("DEV_MODEL"),
            tools=[self._file_writer(), self._doc_writer()],
            verbose=True,
        )

    @agent
    def quality_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["quality_engineer"],
            llm=_llm("QA_MODEL"),
            tools=[self._file_writer(), self._doc_writer()],
            verbose=True,
        )

    @agent
    def uat_tester(self) -> Agent:
        return Agent(
            config=self.agents_config["uat_tester"],
            llm=_llm("UAT_MODEL"),
            tools=[self._doc_writer()],
            verbose=True,
        )

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @task
    def write_requirements(self) -> Task:
        return Task(config=self.tasks_config["write_requirements"])

    @task
    def design_system(self) -> Task:
        return Task(config=self.tasks_config["design_system"])

    @task
    def threat_model(self) -> Task:
        return Task(config=self.tasks_config["threat_model"])

    @task
    def plan_tasks(self) -> Task:
        return Task(config=self.tasks_config["plan_tasks"])

    @task
    def design_ui(self) -> Task:
        return Task(config=self.tasks_config["design_ui"])

    @task
    def implement_code(self) -> Task:
        return Task(config=self.tasks_config["implement_code"])

    @task
    def implement_ui(self) -> Task:
        return Task(config=self.tasks_config["implement_ui"])

    @task
    def write_tests(self) -> Task:
        return Task(config=self.tasks_config["write_tests"])

    @task
    def uat_report(self) -> Task:
        return Task(config=self.tasks_config["uat_report"])

    # ── Crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
