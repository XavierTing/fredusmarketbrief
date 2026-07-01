# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python pipeline that creates and sends a daily US market infographic. Core code lives in `src/`: `main.py` orchestrates the run, `market_data.py` fetches or loads market data, `narrative.py` generates copy, `infographic.py` renders HTML to PNG, and `telegram_sender.py` delivers the image. Shared typed data objects are in `src/models.py`, while configuration and symbol lists are in `src/config.py`.

Tests are in `tests/` and mirror source modules with names like `test_market_data.py`. The Jinja template is `templates/infographic.html.j2`, sample offline input is `samples/sample_market_data.json`, helper scripts are in `tools/`, and generated images go to `out/` which is ignored by Git.

## Build, Test, and Development Commands

- `pip install -r requirements.txt` installs runtime and test dependencies.
- `python -m playwright install chromium` installs the headless browser needed for PNG rendering.
- `python -m src.main --mock --dry-run --out out/demo.png` renders from bundled sample data without network calls, Claude, or Telegram sending.
- `python -m src.main --dry-run` uses live market data and narrative generation but skips Telegram delivery.
- `python -m src.main` runs the full scheduled workflow locally.
- `pytest` runs the test suite.

## Coding Style & Naming Conventions

Use Python 3.12-compatible code, 4-space indentation, type hints for public functions, and `dataclass` models for pipeline data. Keep modules focused on one pipeline stage. Prefer descriptive snake_case for functions and variables, PascalCase for dataclasses, and uppercase names for constants such as environment-backed settings. Keep comments short and useful, especially around graceful degradation or external API quirks.

## Testing Guidelines

Use `pytest`. Name files `tests/test_<module>.py` and tests `test_<behavior>()`. Favor offline tests with `load_mock()`, monkeypatching, and temporary paths. Rendering tests may skip when Playwright or Chromium is unavailable; do not require network access or real credentials for normal test runs.

## Commit & Pull Request Guidelines

No Git history is available in this workspace, so use concise imperative commit subjects such as `Add yield normalization test` or `Update infographic layout`. Pull requests should include a short summary, test results (`pytest`), and a rendered sample image when changing `templates/` or `src/infographic.py`.

## Security & Configuration Tips

Copy `.env.example` to `.env` for local secrets and never commit `.env`. Required live-run values are `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID`; `AGENT_NAME` is optional branding. Use `--mock --dry-run` for safe local validation.
