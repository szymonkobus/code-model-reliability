"""The task sets: who is a member, who is kept, and the hashes that pin each list.

Reads ``sets.json``. Per set the file carries the member ids, the kept subset (the members whose audit label is a
keep label), both counts and a sha256 over each sorted list. It also carries the label rule, the reworded copies that
folded into their parent task, the members not kept with the reason, and the identity of wave 1+2 (the kept members
of wave 1 and wave 2 together, the population the published fit stands on).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .content import SET_KEYS, SET_NAMES, list_sha256


@dataclass(frozen=True)
class TaskSet:
    key: str
    members: tuple[str, ...]
    kept: tuple[str, ...]
    sha256_sorted_members: str
    sha256_sorted_kept: str

    @property
    def name(self) -> str:
        return SET_NAMES[self.key]

    @property
    def kept_set(self) -> frozenset[str]:
        return frozenset(self.kept)

    @property
    def member_set(self) -> frozenset[str]:
        return frozenset(self.members)


@dataclass
class Sets:
    by_key: dict[str, TaskSet]
    label_rule: dict
    wave_1_plus_2: dict
    folded_twins: dict
    not_kept: dict[str, list[dict]] = field(default_factory=dict)
    raw: dict = field(default_factory=dict, repr=False)

    def __getitem__(self, key: str) -> TaskSet:
        return self.by_key[key]

    @property
    def keep_labels(self) -> tuple[str, ...]:
        return tuple(self.label_rule.get("keep_labels", ()))

    def set_of(self, task_id: str) -> str | None:
        """The set a task id is a member of, or None (wave 2 and wave 2 parked never overlap)."""
        for key, ts in self.by_key.items():
            if task_id in ts.member_set:
                return key
        return None

    def wave_1_plus_2_kept(self) -> list[str]:
        return sorted(set(self.by_key["wave_1"].kept) | set(self.by_key["wave_2"].kept))


def load_sets(tasks_dir: Path) -> Sets:
    raw = json.loads((tasks_dir / "sets.json").read_text(encoding="utf-8"))
    by_key: dict[str, TaskSet] = {}
    for key in SET_KEYS:
        block = raw["sets"][key]
        by_key[key] = TaskSet(
            key=key,
            members=tuple(block["members"]),
            kept=tuple(block["kept"]),
            sha256_sorted_members=block["sha256_sorted_members"],
            sha256_sorted_kept=block["sha256_sorted_kept"],
        )
    not_kept = {k: raw.get(f"{k}_members_not_kept", []) for k in SET_KEYS}
    return Sets(
        by_key=by_key,
        label_rule=raw.get("label_rule", {}),
        wave_1_plus_2=raw.get("wave_1_plus_2", {}),
        folded_twins=raw.get("folded_twins", {}),
        not_kept=not_kept,
        raw=raw,
    )


def check_sets(sets: Sets) -> list[str]:
    """Every list hash recomputed and compared, kept within members, no overlap between wave 2 and wave 2 parked,
    the counts consistent with the lists, and the wave 1+2 identity. Returns the problems found, empty when none."""
    problems: list[str] = []
    for key, ts in sets.by_key.items():
        if list_sha256(ts.members) != ts.sha256_sorted_members:
            problems.append(f"{key}: the members' hash does not match the list")
        if list_sha256(ts.kept) != ts.sha256_sorted_kept:
            problems.append(f"{key}: the kept list's hash does not match the list")
        if not ts.kept_set <= ts.member_set:
            problems.append(f"{key}: {len(ts.kept_set - ts.member_set)} kept ids are not members")
        if len(set(ts.members)) != len(ts.members):
            problems.append(f"{key}: duplicate member ids")
        block = sets.raw.get("sets", {}).get(key, {})
        if block.get("count") not in (None, len(ts.members)) or block.get("kept_count") not in (None, len(ts.kept)):
            problems.append(f"{key}: the recorded counts differ from the lists")
        not_kept_ids = {row["task_id"] for row in sets.not_kept.get(key, [])}
        if not_kept_ids != ts.member_set - ts.kept_set:
            problems.append(f"{key}: the members-not-kept list does not match members minus kept")
    overlap = sets["wave_2"].member_set & sets["wave_2_parked"].member_set
    if overlap:
        problems.append(f"wave 2 and wave 2 parked share {len(overlap)} ids")
    want = sets.wave_1_plus_2.get("sha256_sorted_kept")
    if want and list_sha256(sets.wave_1_plus_2_kept()) != want:
        problems.append("wave 1+2: the kept hash does not match wave 1 kept plus wave 2 kept")
    want_n = sets.wave_1_plus_2.get("kept_count")
    if want_n is not None and want_n != len(sets.wave_1_plus_2_kept()):
        problems.append("wave 1+2: the kept count does not match the lists")
    return problems
