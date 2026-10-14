"""The extractor versions the published verdicts rest on, one module per stamp.

A module is named ``v2_<sha16>`` after the stamp of the file as it ran (``v2@`` and the first sixteen hex digits
of the file's sha256). Each module's logic is the stamped file's; its documentation was rewritten for a reader,
so the shipped bytes differ while the syntax tree without comments and docstrings is the same, which
``generate.extract.logic_sha256`` checks against the hash recorded for each stamp. ``generate.extract`` lists the
stamps, what each version added, and which published attempts carry it.
"""
