# Repository Guidelines

## Project Structure & Module Organization

The repository is currently in a planning stage. [`README.md`](README.md) defines the product direction, and `chromantis.png` is a reference asset. As implementation begins, keep runtime code under `src/`, tests under `tests/`, and any static assets under `assets/` or `docs/`. Mirror the domain described in the README: scanner, metadata extraction, indexing, and bot integration should remain separate modules.

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

## Commit & Pull Request Guidelines

The repository has no commit history yet, so adopt short imperative commit messages such as `Add FTP path parser` or `Document indexing workflow`. Keep commits focused. Pull requests should include a concise summary, linked issue when relevant, test evidence, and screenshots or chat transcripts for user-facing bot behavior.

## Security & Configuration Tips

Never commit FTP credentials, bot tokens, or private photo paths. Store secrets in an untracked `.env` file and provide a sanitized `.env.example` when configuration is introduced.
