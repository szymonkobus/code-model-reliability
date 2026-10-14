# Test fixtures

A three-task set in the judge's shape (`tasks/`), a deterministic stand-in for a model (`model.py`: returns the
canonical solution or a wrong one by a seeded rule, so cells carry failures), and the files each stage is
expected to write for it (`expected/`). The end-to-end smoke test runs every stage on this set in minutes on a
CPU; the unit tests read single files from here.
