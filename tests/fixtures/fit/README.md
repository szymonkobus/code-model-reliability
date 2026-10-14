# Fit stage fixtures

The fit stage's tests build their inputs in code (`tests/fit/conftest.py`): a synthetic engine result with
crossing draws from known distributions, and small cells tables with hand-computable positions. Nothing here is
read at test time; the end-to-end smoke writes its fit under a temporary directory.
