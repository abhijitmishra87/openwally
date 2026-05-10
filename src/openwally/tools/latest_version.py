"""
Look up current stable versions of runtimes and packages from public registries.
No API keys required.
"""
import json
import urllib.error
import urllib.request
from crewai.tools import BaseTool
from loguru import logger


_RUNTIME_ALIASES = {
    "python": "python",
    "py": "python",
    "node": "nodejs",
    "nodejs": "nodejs",
    "node.js": "nodejs",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "java": "java",
    "ruby": "ruby",
    "php": "php",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "redis": "redis",
    "nginx": "nginx",
}


def _http_get_json(url: str, timeout: float = 5.0) -> dict | list:
    req = urllib.request.Request(url, headers={"User-Agent": "openwally/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LatestVersionTool(BaseTool):
    name: str = "lookup_latest_version"
    description: str = (
        "Look up the current stable version of a programming language runtime, "
        "Python (pip) package, or Node (npm) package. Use before pinning versions "
        "or making technology choices so the project ships on supported software.\n\n"
        "Arguments:\n"
        "  ecosystem (str) — one of: 'runtime', 'pypi', 'npm'\n"
        "  name (str)      — runtime name (e.g. 'python', 'nodejs', 'postgresql') "
        "or package name (e.g. 'fastapi', 'react')\n\n"
        "Returns the latest stable version plus, for runtimes, the EOL date of that "
        "release line so you can pick something supported."
    )

    def _run(self, ecosystem: str, name: str) -> str:
        ecosystem = (ecosystem or "").strip().lower()
        name = (name or "").strip().lower()
        if not ecosystem or not name:
            return "Error: both 'ecosystem' and 'name' are required."

        try:
            if ecosystem == "runtime":
                return self._lookup_runtime(name)
            if ecosystem == "pypi":
                return self._lookup_pypi(name)
            if ecosystem == "npm":
                return self._lookup_npm(name)
            return f"Error: unknown ecosystem '{ecosystem}'. Use 'runtime', 'pypi', or 'npm'."
        except urllib.error.HTTPError as e:
            logger.warning("version lookup HTTP error for {}/{}: {}", ecosystem, name, e)
            return f"Lookup failed for {ecosystem}/{name}: HTTP {e.code}"
        except urllib.error.URLError as e:
            logger.warning("version lookup network error for {}/{}: {}", ecosystem, name, e)
            return f"Lookup failed for {ecosystem}/{name}: network error ({e.reason})"
        except (TimeoutError, json.JSONDecodeError) as e:
            logger.warning("version lookup parse/timeout for {}/{}: {}", ecosystem, name, e)
            return f"Lookup failed for {ecosystem}/{name}: {e}"

    def _lookup_runtime(self, name: str) -> str:
        product = _RUNTIME_ALIASES.get(name, name)
        data = _http_get_json(f"https://endoflife.date/api/{product}.json")
        if not isinstance(data, list) or not data:
            return f"No data for runtime '{name}'."
        # endoflife.date sorts newest-first; pick the most recent non-EOL entry
        today = __import__("datetime").date.today().isoformat()
        for entry in data:
            eol = entry.get("eol")
            if eol is True:
                continue
            if isinstance(eol, str) and eol < today:
                continue
            cycle = entry.get("cycle", "?")
            latest = entry.get("latest", "?")
            release_date = entry.get("releaseDate", "?")
            eol_str = eol if isinstance(eol, str) else "supported"
            logger.debug("runtime {} → cycle {} latest {} eol {}", product, cycle, latest, eol_str)
            return (
                f"{product}: latest stable is {latest} (release line {cycle}, "
                f"first released {release_date}, supported until {eol_str}). "
                f"Use this for Dockerfile base images, CI matrices, and runtime requirements."
            )
        return f"No supported release line found for '{name}' — all are past EOL."

    def _lookup_pypi(self, name: str) -> str:
        data = _http_get_json(f"https://pypi.org/pypi/{name}/json")
        info = data.get("info", {}) if isinstance(data, dict) else {}
        version = info.get("version", "?")
        requires_python = info.get("requires_python") or "any"
        logger.debug("pypi {} → {} (requires {})", name, version, requires_python)
        return (
            f"PyPI package '{name}': latest stable is {version} "
            f"(requires-python: {requires_python})."
        )

    def _lookup_npm(self, name: str) -> str:
        data = _http_get_json(f"https://registry.npmjs.org/{name}/latest")
        version = data.get("version", "?") if isinstance(data, dict) else "?"
        logger.debug("npm {} → {}", name, version)
        return f"npm package '{name}': latest stable is {version}."
