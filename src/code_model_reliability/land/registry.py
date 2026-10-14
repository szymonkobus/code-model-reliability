"""The registry: every arm named once, with what identifies it.

An arm is a model under one generation protocol. Its row carries the arm id, the model id and the name of
record, the family, the form (plain, thinking or completion), the protocol's name and its version token, the
temperature, the attempts
per task, the sets it ran, the judging settings id its verdicts carry, and the extractor its samples carry (its
stamp, which names the version, and its file's sha256). The rows are built from what the generate and judge stages wrote beside each arm's samples
(``generation.json`` and ``judging.json``), joined to the curated model map (``arm_map.tsv``: model stem to arm
id, name and family) and to the names of record of the trained models (``names.json``). A header row carries
the schema name and the row count, so a reader can tell a complete file from a cut one.

Reads the arm directories, ``arm_map.tsv`` and ``names.json``; writes ``registry/arms.jsonl``.
"""

from __future__ import annotations

import csv
import json
import pathlib
from typing import Any, Iterable

SCHEMA = "arms-registry-v2"
FIELDS = ("arm", "model_id", "model_name", "family", "form", "protocol", "protocol_version", "temperature",
          "attempts_per_task", "sets", "judging", "extractor", "extractor_sha256")
FORMS = ("plain", "thinking", "completion")


def load_arm_map(path: str | pathlib.Path) -> dict[str, dict[str, str]]:
    """``arm_map.tsv``: columns ``stem``, ``arm``, ``model_id``, ``model_name``, ``family``; keyed by stem."""
    with open(path, encoding="utf-8", newline="") as fh:
        return {row["stem"]: row for row in csv.DictReader(fh, delimiter="\t")}


def load_names(path: str | pathlib.Path | None) -> dict[str, Any]:
    if not path or not pathlib.Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def row_from_arm_dir(arm_dir: str | pathlib.Path, arm_map: dict[str, dict[str, str]], names: dict[str, Any] | None = None) -> dict[str, Any]:
    """One registry row from an arm directory's ``generation.json`` and ``judging.json``."""
    arm_dir = pathlib.Path(arm_dir)
    with open(arm_dir / "generation.json", encoding="utf-8") as fh:
        gen = json.load(fh)
    judging_id = None
    if (arm_dir / "judging.json").exists():
        with open(arm_dir / "judging.json", encoding="utf-8") as fh:
            judging_id = json.load(fh).get("settings_id")
    # the generation record (generate.records.GenerationRecord): the protocol by its name as given to --protocol,
    # its version token beside it, the form, the sampling as one block, the task set it ran
    stem = gen.get("model_stem") or gen.get("arm", arm_dir.name)
    mapped = arm_map.get(stem, {})
    arm = gen.get("arm") or mapped.get("arm") or arm_dir.name
    model_id = gen.get("model_id") or mapped.get("model_id")
    model_name = mapped.get("model_name") or (names or {}).get(arm, {}).get("name_of_record") or model_id
    form = gen.get("form", "plain")
    if form not in FORMS:
        raise ValueError(f"{arm}: form must be one of {FORMS}, not {form!r}")
    sets = gen.get("sets") or ([gen["task_set"]] if gen.get("task_set") else [])
    sampling = gen.get("sampling") or {}
    return {
        "arm": arm,
        "model_id": model_id,
        "model_name": model_name,
        "family": mapped.get("family") or gen.get("family"),
        "form": form,
        "protocol": gen.get("protocol"),
        "protocol_version": gen.get("protocol_version"),
        "temperature": sampling.get("temperature"),
        "attempts_per_task": gen.get("attempts_per_task"),
        "sets": sets,
        "judging": judging_id,
        # the extractor's stamp names its version (two shipped: the wave 1 re-extraction's and the wave 2 landings');
        # the sha256 is the extractor file's, held to the stamp by the generate stage
        "extractor": (gen.get("extractor") or {}).get("stamp") or (gen.get("extractor") or {}).get("name"),
        "extractor_sha256": (gen.get("extractor") or {}).get("sha256"),
    }


def build(arm_dirs: Iterable[str | pathlib.Path], arm_map: dict[str, dict[str, str]], names: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = [row_from_arm_dir(d, arm_map, names) for d in arm_dirs]
    seen: dict[str, int] = {}
    for r in rows:
        seen[r["arm"]] = seen.get(r["arm"], 0) + 1
    duplicates = sorted(a for a, n in seen.items() if n > 1)
    if duplicates:
        raise ValueError(f"an arm is named more than once: {duplicates}")
    return sorted(rows, key=lambda r: r["arm"])


def write(rows: list[dict[str, Any]], path: str | pathlib.Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"schema": SCHEMA, "n_rows": len(rows), "fields": list(FIELDS)}) + "\n")
        for r in rows:
            fh.write(json.dumps({k: r.get(k) for k in FIELDS}, sort_keys=True) + "\n")


def read(path: str | pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The header and the rows; raises when the header's count and the rows disagree."""
    with open(path, encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh if line.strip()]
    if not lines or lines[0].get("schema") != SCHEMA:
        raise ValueError(f"not a registry file: {path}")
    header, rows = lines[0], lines[1:]
    if header.get("n_rows") != len(rows):
        raise ValueError(f"registry {path} carries {len(rows)} rows, its header says {header.get('n_rows')}")
    return header, rows
