# Tool & Coding Conventions (TOOLS.md)

<!-- このファイルにプロジェクト固有のコマンド・ツール規約・注意点を記述します。
     エージェントはこのファイルをシステムプロンプトに自動注入します。 -->

## Common Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run tests (fail fast)
uv run pytest -x

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## Build & Test Notes

<!-- プロジェクト固有のビルド手順や注意点を記述してください -->
- Always run `uv run ruff check .` before committing
- Tests are located in `tests/`

## Tool Notes

<!-- bash ツールで使うコマンドの癖・制限など -->
- Use `grep -r` for recursive search
- Use `find . -name "*.py"` for file discovery
