def words_share(x):
    for lim, w in ((0.15, "about a tenth"), (0.22, "about a fifth"), (0.28, "about a quarter"), (0.36, "about a third"),
                   (0.46, "about four in ten"), (0.58, "about half"), (0.66, "about six in ten"), (0.71, "about two thirds"),
                   (0.82, "about three quarters"), (10.0, "most")):
        if x < lim:
            return w
    return "most"


def count_words(n):
    return ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"][n] if 0 <= n <= 10 else str(n)
