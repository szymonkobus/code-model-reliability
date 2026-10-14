"""Where the task data lives.

The package reads ``data/tasks/`` of the repository it is installed from. A caller can point it elsewhere with the
``--data`` option of every command or the ``CMR_DATA_DIR`` environment variable (either the repository's ``data``
directory or the ``tasks`` folder inside it).
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "CMR_DATA_DIR"
SETS_FILE = "sets.json"


def _tasks_folder(candidate: Path) -> Path | None:
    for p in (candidate, candidate / "tasks", candidate / "data" / "tasks"):
        if (p / SETS_FILE).is_file():
            return p
    return None


def tasks_dir(explicit: str | os.PathLike | None = None) -> Path:
    """The ``data/tasks`` folder: the explicit path, else the environment variable, else the repository around the
    working directory, else the repository this package was installed from. Raises when none holds ``sets.json``."""
    tried: list[Path] = []
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    if os.environ.get(ENV_VAR):
        candidates.append(Path(os.environ[ENV_VAR]))
    cwd = Path.cwd()
    candidates.extend([cwd, *cwd.parents])
    candidates.append(Path(__file__).resolve().parents[3])
    for c in candidates:
        found = _tasks_folder(c)
        if found is not None:
            return found
        tried.append(c)
    raise FileNotFoundError(
        f"no task data found ({SETS_FILE} missing); tried {', '.join(str(t) for t in tried[:4])}; "
        f"pass --data <repository>/data or set {ENV_VAR}"
    )
