# Repository Guidelines

## Project Structure & Module Organization

Runtime code lives under `src/`, tests under `tests/`, and entry scripts under `scripts/`. Keep the current domain split intact: `source/` for archive access, `parsing/` for deterministic metadata extraction, `db/` for SQLite persistence and migrations, `app/` for shared product logic, `api/` for the local HTTP layer, and `bot/` for Telegram-specific delivery.

## Build, Test, and Development Commands

There is no committed build system yet, so contributors should add tooling together with the first production code. When introducing a stack, document the canonical commands in `README.md` and keep them stable. Expected examples:

- `make dev` or `npm run dev`: start the local development entry point.
- `make test` or `npm test`: run the full automated test suite.
- `make lint` or `npm run lint`: enforce formatting and static checks.

Do not merge code that adds a new workflow without also adding its command to the README.

## Coding Style & Naming Conventions

Use 4 spaces for Python and 2 spaces for JavaScript or JSON. Prefer descriptive, lowercase names for directories and files, for example `src/indexer/path_parser.py` or `src/bot/telegram-client.ts`. Use `snake_case` for Python modules and functions, `camelCase` for JavaScript or TypeScript variables, and `PascalCase` only for classes or React-style components. Add a formatter and linter with the first language runtime you introduce and run them before opening a PR.

## Testing Guidelines

Place tests in `tests/` and name them after the behavior they cover, such as `test_path_parser.py` or `telegram-bot.search.spec.ts`. Prefer deterministic unit tests around path parsing, metadata normalization, and indexing because the project goal is traceable retrieval. Include regression coverage for any bug fix.

When changing SQLite schema or startup behavior, add a regression test for existing-database compatibility. `Repository.init_schema()` must work both on a fresh database and on older local databases created by previous versions.

## Commit & Pull Request Guidelines

The repository has no commit history yet, so adopt short imperative commit messages such as `Add FTP path parser` or `Document indexing workflow`. Keep commits focused. Pull requests should include a concise summary, linked issue when relevant, test evidence, and screenshots or chat transcripts for user-facing bot behavior.

## Security & Configuration Tips

Never commit FTP credentials, bot tokens, or private photo paths. Store secrets in an untracked `.env` file and provide a sanitized `.env.example` when configuration is introduced.
