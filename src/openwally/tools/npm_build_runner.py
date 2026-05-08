from pathlib import Path
import subprocess
from crewai.tools import BaseTool


class NpmBuildTool(BaseTool):
    name: str = "run_npm_build"
    description: str = (
        "Run npm install and npm run build in the generated project's frontend/ directory. "
        "Returns build success or the compiler/bundler errors. "
        "Call this after writing frontend files to validate your implementation."
    )
    project_dir: str = ""

    def _run(self, args: str = "") -> str:
        frontend_path = Path(self.project_dir) / "frontend"

        if not frontend_path.exists():
            return "No frontend/ directory found — write frontend files first."

        if not (frontend_path / "package.json").exists():
            return "No package.json found in frontend/ — write it before running the build."

        install = subprocess.run(
            ["npm", "install", "--silent", "--no-audit", "--no-fund"],
            cwd=str(frontend_path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install.returncode != 0:
            output = (install.stdout + install.stderr).strip()
            return f"npm install failed:\n{output[:4000]}"

        build = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_path),
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = (build.stdout + build.stderr).strip()
        if len(output) > 8000:
            output = output[:8000] + "\n... (output truncated)"

        if build.returncode == 0:
            return f"Build succeeded.\n{output}"
        return f"Build failed (exit {build.returncode}):\n{output}"
