#!/usr/bin/env python3
import json, re, sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from kwrite import write_json
P = os.path.join(ROOT, "knowledge", "disclosures.json")
FACE_KEYS = ("N_definition", "unit", "sentence", "sentence_template", "arms_note", "status_line", "companion_line", "flag_text", "status", "hover", "label", "title", "note", "class", "basis", "render", "meaning", "summary", "rule_text", "text")
# ordered: longest / most specific first
TABLE = [
 # exact special cases first (two plain strings whose 'wave 2' already meant the focused half)
 (r"Generation is focused on wave 2 \(869 tasks\), the easier new tasks; wave 2 parked \(893 tasks\) is stopped, its finished results kept and served, and it receives background runs only on free machines\.", "Generation is focused on the easier 869 wave 2 tasks; the 893 parked wave 2 tasks are stopped, their finished results kept and served, with background runs only on free machines."),
 (r"Generation is focused on wave 2, the easier new tasks; wave 2 parked is stopped with its results kept and gets background runs on free machines only\.", "Generation is focused on the easier wave 2 tasks; the parked wave 2 tasks are stopped with their results kept and get background runs on free machines only."),
 # LeetCode as the name of a wave 2 family on faces: described by its mechanism (the tasks whose prompt opens with typing imports)
 (r"On the 297 LeetCode tasks, six strong models fail", "On the 297 wave 2 tasks whose prompt opens with typing imports, six strong models fail"),
 (r"LeetCode and the wave 1 results are being re-judged", "those tasks and the wave 1 results are being re-judged"),
 (r"LeetCode and the original HumanEval results are being re-judged", "those tasks and the wave 1 results are being re-judged"),
 (r"the six models' LeetCode reliability is a pending basis change", "the six models' reliability on those tasks is a pending basis change"),
 (r"six strong models' LeetCode reliability will move", "six strong models' reliability on the typing-import tasks will move"),
 (r"LeetCode re-judge pending", "typing-import re-judge pending"),
 (r"the 297 LeetCode tasks", "the 297 typing-import tasks of wave 2"),
 (r"297 LeetCode tasks", "297 typing-import tasks of wave 2"),
 (r"LeetCode tasks", "typing-import tasks of wave 2"),
 (r"LeetCode reliability", "reliability on the typing-import tasks"),
 (r"\bLeetCode\b", "the typing-import tasks"),
 # source benchmark names as set names
 (r"the board's own HumanEval\+/MBPP\+ ", "wave 1's own "),
 (r"the board's HumanEval\+/MBPP\+ ", "wave 1's "),
 (r"the original tasks' own HumanEval\+/MBPP\+ ", "wave 1's own "),
 (r"the original tasks' HumanEval\+/MBPP\+ ", "wave 1's "),
 (r"HumanEval\+/MBPP\+ ", ""),
 (r"HumanEval\+ and MBPP\+", "wave 1"),
 (r"HumanEval\+ / MBPP\+", "wave 1"),
 (r"the original HumanEval results", "the wave 1 results"),
 (r"HumanEval\+", "wave 1"),
 (r"MBPP\+", "wave 1"),
 (r"Mbpp\+", "wave 1"),
 (r"\bHumanEval\b(?![/+])", "wave 1"),
 (r"\bMBPP\b(?![/+])", "wave 1"),
 # the board as the wave 1 set (the /progress/ page sense does not occur in these strings — read in the dry-run)
 (r"pool vs original tasks", "wave 2 and wave 2 parked vs wave 1"),
 (r"pool vs board", "wave 2 and wave 2 parked vs wave 1"),
 (r"the board card", "the wave 1 card"),
 (r"their board card", "their wave 1 card"),
 (r"the board budget", "the wave 1 budget"),
 (r"\bboard and pool\b", "wave 1, wave 2 and wave 2 parked"),
 (r"\bboard versions\b", "wave 1 versions"),
 (r"\bboard identity\b", "wave 1 identity"),
 (r"\bboard legs\b", "wave 1 legs"),
 (r"its board card", "its wave 1 card"),
 (r"\bboard results\b", "wave 1 results"),
 (r"an EvalPlus-generated", "a wave 1 grader-generated"),
 (r"\bEvalPlus's\b", "the wave 1 grader's"),
 (r"\bEvalPlus\b", "the wave 1 grader"),
 (r"\bevalplus's\b", "the wave 1 grader's"),
 (r"\bevalplus\b", "the wave 1 grader"),
 (r"the board's", "wave 1's"),
 (r"the board\b", "wave 1"),
 # original / new as set names
 (r"the original tasks' ", "wave 1's "),
 (r"the original tasks'", "wave 1's"),
 (r"original-task card", "wave 1 card"),
 (r"original-task", "wave 1"),
 (r"original tasks rows", "wave 1 rows"),
 (r"original tasks", "wave 1 tasks"),
 (r"original task\b", "wave 1 task"),
 (r"the new task pool", "wave 2 and wave 2 parked"),
 (r"new task pool", "wave 2 and wave 2 parked"),
 (r"new-task pool", "wave 2 and wave 2 parked"),
 (r"(?<!focused )(?<!parked )(?<!easier )(?<!harder )new tasks", "wave 2 and wave 2 parked tasks"),
 (r"new-task", "wave 2 and wave 2 parked"),
 (r"\bthe pool's\b", "wave 2 and wave 2 parked's"),
 (r" of record\b", ""),
 (r"\bThe pool\b", "Wave 2"),
 (r"\bthe pool\b", "wave 2 and wave 2 parked"),
 (r"\b[Pp]ool (tasks|configurations|results|route|surfaces|versions|arms|cells|rows|side|@768-marker versions)\b", r"wave 2 and wave 2 parked \1"),
 (r"\bfocused wave 2 tasks\b", "wave 2 tasks"),
 (r"\bparked wave 2 tasks\b", "wave 2 parked tasks"),
 (r"\bfocused new tasks\b", "wave 2 tasks"),
 (r"\bparked new tasks\b", "wave 2 parked tasks"),
 (r"\bthe focused wave 2\b", "wave 2"),
 (r"\bthe parked wave 2\b", "wave 2 parked"),
 # grammar after the swaps
 (r"wave 1 tasks (identity|budget|results|versions|re-run|scorer's|legs)", r"wave 1 \1"),
 (r"the wave 1 tasks carries", "wave 1 carries"),
 (r"the original wave 1", "the wave 1"),
 (r"wave 1 tasks and pool\b", "wave 1 and wave 2"),
 (r"wave 1 tasks and wave 2", "wave 1 and wave 2"),
 (r"wave 1 tasks tasks", "wave 1 tasks"),
 (r"the wave 1 grader whole-task", "the wave 1 grader's whole-task"),
 (r"cut at wave 1 card", "cut at the wave 1 card"),
]
RX = [(re.compile(a), b) for a, b in TABLE]
def rewrite(s):
    out = s
    for rx, rep in RX: out = rx.sub(rep, out)
    return out
def walk(o, path, changes):
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and k in FACE_KEYS:
                n = rewrite(v)
                if n != v: changes.append((path + "/" + k, v, n)); o[k] = n
            else: walk(v, path + "/" + k, changes)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            if isinstance(v, str):
                n = rewrite(v)
                if n != v and re.search(r"/(" + "|".join(FACE_KEYS) + r")$", path): changes.append((path + f"[{i}]", v, n)); o[i] = n
            else: walk(v, path + f"[{i}]", changes)
def main():
    dry = "--dry-run" in sys.argv
    d = json.load(open(P)); changes = []
    walk(d, "", changes)
    for p, a, b in changes: print(f"{p}\n   - {a}\n   + {b}")
    print(f"wave_vocabulary_pass: {len(changes)} face strings {'would change' if dry else 'changed'}")
    if not dry and changes: write_json(P, d)
if __name__ == "__main__": main()
