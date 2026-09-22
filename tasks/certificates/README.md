# Certificates

`certificates.jsonl` has one line for every new task ever certified: the tasks of wave 2 and wave 2 parked, and the
pilot tasks that belong to neither set. A certificate records the task's identity (`task_id`, `content_sha256` over the
eight judged fields, `superseded_prev_sha256` when the task changed), the set it was certified into (`set`: `frame` for
the two sets of record, `pilot` for the pilot tasks), its status, whether it is eligible for the fits by status and audit
(`fit_keep_set`), the day it was certified (`certified_on`), its audit label (`audit_label`), the difficulty band it was
aimed at (`band_aim`), and its provenance (channel, upstream dataset and row, title, URL, licence, contest rating and
tags where the upstream has them). Set membership is not in the certificates; it is the frozen list in `tasks/sets.json`.

Provenance fields: `channel` names how the task entered (an imported dataset, a paraphrase twin of a wave-1 task, a targeted
task written for a difficulty band, the easy tail, or the easy-task pilot); `source_dataset`, `problem_key`, `source_row`,
`title`, `url`, `license`, `rating`, `tags` and `dates` describe the upstream row of an imported task (`dates` has two
fields: `fetched`, the day the upstream row was read, and `source_date`, the upstream's own date: the contest day of a
Codeforces-derived task, the release month of a benchmark set); `source_task_id` names the wave-1 parent of a twin and
`source_benchmark` its benchmark; `channel` is present on written and twin tasks and absent on imported rows, whose
`source_dataset` says where they came from; `family_id` and `archetype` name the template a written task was generated
from (the easy-tail templates are `E1` to `E5`; a suffixed code is a variant of that template);
`way` is the numbered recipe of the pilot's generator; `band_aim` is the difficulty band a written task was aimed at
(`easy`, `mid`, `hard`); `difficulty` and `time_limit_s` are the upstream's own difficulty label and time limit.

Status values: `complete-for-admission` (certified with a complete test set), `retracted-to-reserve` (certified, then set
aside from the frame), `withdrawn` (removed after certification), `excluded-provisional-tier1` (held out of the frame
pending a check), `awaiting-components` (certification incomplete) and `held-empty-tests` (no usable tests). Only tasks
with `fit_keep_set` true enter the fits.

`task_versions.json` records every version boundary (a semantic content change with judged attempts on both sides) as the
pair of content hashes; `version_pins.json` records the eight tasks re-imported with changed tests: `current_content_sha256`,
`superseded_short_hashes` (the 16-character short hashes of the superseded versions), `reimport_delta` (the fields that changed) and
`pinned_on`; `suite_v1_manifest.jsonl` is the first fixed task list, kept for the version chain.

How certification worked: a certificate was written for a task once its eight judged fields were fixed and its reference
solution reproduced every expected output; the content hash over those fields is the identity every judged cell carries,
so a task whose content changed after judging gets a new hash and its old cells stay tied to the old content. The
certification tools are not part of this import; `tasks/rebuild_restricted.py`
checks any task file against the certified hashes.
