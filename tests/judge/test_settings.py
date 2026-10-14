"""The judging-settings records: every field pinned, ids derived from the values, the record written whole."""

import dataclasses

from code_model_reliability.judge import settings


def test_the_two_records_differ_and_their_ids_are_stable():
    assert settings.CURRENT.id != settings.STOCK_EVALUATOR.id
    assert settings.CURRENT.id == settings.CURRENT.id and len(settings.CURRENT.id) == 12
    changed = dataclasses.replace(settings.CURRENT, time_limit_floor_s=1.0)
    assert changed.id != settings.CURRENT.id, "a moved setting is a different id"
    renamed = dataclasses.replace(settings.CURRENT, name="other")
    assert renamed.id == settings.CURRENT.id, "the name is not a setting"
    loaded = dataclasses.replace(settings.CURRENT, workers=16)
    assert loaded.id == settings.CURRENT.id, "the workers are a load field, not a setting"


def test_describe_names_every_setting_and_the_harness():
    record = settings.describe(settings.CURRENT, n_tasks=3)
    fields = {f.name for f in dataclasses.fields(settings.JudgingSettings)}
    assert fields <= set(record["settings"])
    assert record["settings_id"] == settings.CURRENT.id
    assert record["harness"]["commit"] == settings.HARNESS_COMMIT
    assert record["n_tasks"] == 3


def test_values_of_record():
    c = settings.CURRENT
    assert (c.time_limit_floor_s, c.time_limit_factor, c.set_cap_s, c.memory_gib) == (15.0, 4.0, None, 8.0)
    assert c.leading_imports == "leading-imports-v4.1-self-shadowing-refined"
    assert settings.CAPPED.set_cap_s == 300.0 and settings.CAPPED.values() != c.values()
    assert dataclasses.replace(settings.CAPPED, set_cap_s=None).id == c.id, "the cap is the only difference"
    s = settings.STOCK_EVALUATOR
    assert (s.time_limit_floor_s, s.set_cap_s, s.memory_gib, s.workers) == (4.0, 60.0, 12.0, 8)
    assert len(settings.RECORDS) == 3


def test_memory_limit_adds_the_interpreters_own_size():
    limit = settings.memory_limit_bytes(settings.CURRENT)
    assert limit >= 8 * 2**30
