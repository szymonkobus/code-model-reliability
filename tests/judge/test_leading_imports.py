"""The leading-imports rule on text: the block, the bindings, the builtins restore, the echo clause, the prelude."""

from code_model_reliability.judge import leading_imports

DEMO = "from typing import List\n\n# helper import\nimport math\ndef f(x):\n    import os\n    return x\n"
STAR = "from math import *\nfrom operator import *\ndef h(a, b, m):\n    pass\n"
HEAPQ = "from heapq import *\nfrom typing import *\ndef f(a):\n    pass\n"


def run(program: str) -> dict:
    ns: dict = {}
    exec(program, ns)
    return ns


def test_leading_block_skips_blank_lines_and_comments_and_stops_at_the_first_other_line():
    assert leading_imports.leading_imports(DEMO) == ["from typing import List", "import math"]
    assert leading_imports.leading_imports("def g():\n    pass\n") == []


def test_apply_is_byte_exact_on_the_plain_case_and_a_no_op_without_imports():
    assert leading_imports.apply(DEMO, "def f(x):\n    return x\n") == (
        "from typing import List\nimport math\nfrom builtins import *\n\ndef f(x):\n    return x\n"
    )
    assert leading_imports.apply("def g():\n    pass\n", "X") == "X"


def test_a_shadowed_builtin_is_restored():
    program = leading_imports.apply(STAR, "def h(a, b, m):\n    return pow(a, b, m)\n")
    assert run(program)["h"](3, 4, 5) == 1
    bare = "".join(l + "\n" for l in leading_imports.leading_imports(STAR)) + "\ndef h(a, b, m):\n    return pow(a, b, m)\n"
    try:
        run(bare)["h"](3, 4, 5)
    except TypeError:
        pass
    else:
        raise AssertionError("without the restore, the star import's pow shadows the builtin")


def test_an_echoed_star_import_does_not_undo_the_restore():
    echo = "from math import *\nfrom operator import *\ndef h(a, b, m):\n    return pow(a, b, m)\n"
    assert run(leading_imports.apply(STAR, echo))["h"](3, 4, 5) == 1
    late = '"""doc"""\nimport sys\nfrom math import *\ndef h(a, b, m):\n    return pow(a, b, m)\n'
    assert run(leading_imports.apply(STAR, late))["h"](3, 4, 5) == 1


def test_star_imported_modules_are_bound_so_qualified_use_resolves():
    qualified = "def f(a):\n    heapq.heappush(a, 1)\n    return a\n"
    program = leading_imports.apply(HEAPQ, qualified)
    assert program.startswith("from heapq import *\nfrom typing import *\nimport heapq\nimport typing\n" + leading_imports.BUILTINS_LINE)
    assert run(program)["f"]([]) == [1]
    assert leading_imports.module_bindings(HEAPQ, qualified) == ["heapq", "typing"] == leading_imports.star_modules(HEAPQ)


def test_a_self_shadowing_module_keeps_its_callable_unless_only_used_qualified():
    header = "from bisect import *\nfrom typing import *\ndef f(a, x):\n    pass\n"
    bare_call = "def f(a, x):\n    return bisect(a, x)\n"
    assert leading_imports.module_bindings(header, bare_call) == ["typing"]
    assert run(leading_imports.apply(header, bare_call))["f"]([1, 2, 3], 2) == 2
    qualified = "def f(a, x):\n    return bisect.bisect_right(a, x)\n"
    assert leading_imports.module_bindings(header, qualified) == ["bisect", "typing"]
    assert run(leading_imports.apply(header, qualified))["f"]([1, 2, 3], 2) == 2
    both = "def f(a, x):\n    return bisect(a, x) + bisect.bisect_left(a, x)\n"
    assert leading_imports.module_bindings(header, both) == ["typing"]


def test_a_future_line_is_lifted_to_the_top():
    program = leading_imports.apply(DEMO, "from __future__ import annotations\ndef f(x: List[int]) -> int:\n    return len(x)\n")
    assert program.startswith("from __future__ import annotations\nfrom typing import List\nimport math\n")
    assert run(program)["f"]([1, 2]) == 2


def test_the_programs_own_assignment_overrides_a_binding():
    assert run(leading_imports.apply(HEAPQ, "heapq = None\ndef f(a):\n    return heapq\n"))["f"]([]) is None


def test_typing_prelude_comes_first_after_a_future_line():
    program = leading_imports.apply_typing("def g():\n    pass\n", "from __future__ import annotations\ndef g(x: Optional[int]):\n    return x\n")
    assert program.startswith("from __future__ import annotations\n" + leading_imports.TYPING_PRELUDE)
    assert run(program)["g"](3) == 3
    with_imports = leading_imports.apply_typing(DEMO, "def f(x: Dict[str, int]):\n    return x\n")
    assert with_imports.startswith(leading_imports.TYPING_PRELUDE + "from typing import List\nimport math\n")
