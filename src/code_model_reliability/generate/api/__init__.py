"""Generation through the providers' batch interfaces: one request per attempt, one cycle for every provider.

The cycle (``batch``): build the requests from the task set and the arm's card; submit them in batches; ask their
status; fetch the results into a ledger keyed by request id; resubmit what is missing or errored; finalize into
the stage's output files with the current extractor. Each provider module holds the cards the published attempts
were drawn with (the model string and the request parameters) and the few lines that speak its wire
format. Keys come from the environment only: ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ``GEMINI_API_KEY``.

The prompt is one user message: the instruction sentence and the task in a ```python fence (``prompts.api_user_message``);
no system prompt and no pre-filled assistant turn, so every API arm shares one shape and differs from the open-weight
arms in the opening of the model's turn (a recorded difference, not a hidden one).
"""
