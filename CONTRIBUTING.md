# Contributing

Use Python 3.11+ and `uv sync --locked`. Run `uv run ruff check .` and `uv run pytest` before opening a pull request. Keep documentation, prompts, errors, and comments in English.

Never use real Meshy API calls in tests. Mock HTTP requests, cover workflow transitions and interruption recovery, and use synthetic assets. Tests should verify observable behavior, especially that resumed workflows cannot repeat a paid submission. Do not commit API keys, signed asset URLs, user reference images, generated models, or workflow state.

When changing an API payload, verify the current official Meshy documentation and update the skill and tool documentation where behavior changes. Keep ambiguous POST outcomes recoverable rather than adding automatic retries.

Image preparation uses Codex ImageGen capabilities; avoid implying that the Python package itself generates concept images or guarantees geometric consistency. Review the skill with realistic subjects and mixed-variant references.
