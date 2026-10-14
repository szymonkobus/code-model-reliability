import re, os, json
TRAIN_READ = re.compile(r"_train(?:pool|probe)\d*_temp_|-voting-read_|_temp_[0-9.]+_a\d+$")
_REG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "runs", "arms.jsonl")
_REG_READOUTS = os.path.join(os.path.dirname(_REG), "arms_readouts.jsonl")
_OFF_ROSTER = None   # configuration ids whose registry row carries census_roster false; loaded once per process
def off_roster_ids():
    """the set of config ids the registry keeps OFF the census roster (census_roster false), read from runs/arms.jsonl and, when present, runs/arms_readouts.jsonl;
    empty when neither can be read (the form rule then stands alone)"""
    global _OFF_ROSTER
    if _OFF_ROSTER is None:
        ids = set()
        for _path in (_REG, _REG_READOUTS):
            try:
                with open(_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try: row = json.loads(line)
                        except Exception: continue
                        if not isinstance(row, dict) or row.get("schema"): continue
                        if row.get("census_roster") is False and isinstance(row.get("config_id"), str): ids.add(row["config_id"])
            except Exception:
                pass
        _OFF_ROSTER = ids
    return _OFF_ROSTER
def at_prefixes(config_id):
    parts = str(config_id).split("@")
    return ["@".join(parts[:i]) for i in range(1, len(parts) + 1)]
def is_training_read(config_id):
    """a key is a training read when ANY of its '@'-prefixes (the whole key included) is a census_roster-false id, or when its form says so"""
    s = str(config_id); off = off_roster_ids()
    return any(q in off for q in at_prefixes(s)) or bool(TRAIN_READ.search(s))
def drop_training_reads(m):
    """a dict keyed by configuration ids without the training-read keys (by the registry flag, then by form); anything that is not a dict is returned as it is"""
    if not isinstance(m, dict): return m
    return {k: v for k, v in m.items() if not is_training_read(k)}
