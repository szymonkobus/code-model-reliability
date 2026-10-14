def words_share(x):
    for lim, w in ((0.05, "a few percent"), (0.15, "about a tenth"), (0.22, "about a fifth"), (0.28, "about a quarter"), (0.36, "about a third"),
                   (0.46, "about four in ten"), (0.58, "about half"), (0.66, "about six in ten"), (0.71, "about two thirds"),
                   (0.82, "about three quarters"), (10.0, "most")):
        if x < lim:
            return w
    return "most"


_SET_WORDS = [
    ("Combined (HumanEval+ & MBPP+)", "wave 1 (both parts)"), ("HumanEval+ & MBPP+", "wave 1's two parts"),
    ("HumanEval+", "wave 1, one part"), ("MBPP+", "wave 1, the other part"),
    ("HE-only (sol)", "one part of wave 1 only (solution text)"), ("MBPP-only (sol)", "the other part only (solution text)"),
    ("HE-only", "one part of wave 1 only"), ("MBPP-only", "the other part only"),
]


def set_words(s):
    for o, n in _SET_WORDS:
        s = s.replace(o, n)
    return s


def count_words(n):
    return ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"][n] if 0 <= n <= 10 else str(n)
