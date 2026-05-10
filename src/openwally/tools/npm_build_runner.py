from pathlib import Path
import subprocess
from crewai.tools import BaseTool
from loguru import logger


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
            logger.warning("npm_build: no frontend/ directory in {}", self.project_dir)
            return "No frontend/ directory found — write frontend files first."

        if not (frontend_path / "package.json").exists():
            logger.warning("npm_build: no package.json in {}", str(frontend_path))
            return "No package.json found in frontend/ — write it before running the build."

        logger.info("Running npm build validation in {}", str(frontend_path))
        install = subprocess.run(
            ["npm", "install", "--silent", "--no-audit", "--no-fund"],
            cwd=str(frontend_path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install.returncode != 0:
            output = (install.stdout + install.stderr).strip()
            logger.error("npm install failed: {}", output[:500])
            return f"npm install failed:\n{output[:4000]}"

        logger.debug("npm install succeeded")

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
            logger.info("npm run build succeeded")
            return f"Build succeeded.\n{output}"

        logger.warning("npm run build failed (exit {}) — agent will attempt fixes", build.returncode)
        logger.debug("npm build output:\n{}", output[:2000])
        return f"Build failed (exit {build.returncode}):\n{output}"
