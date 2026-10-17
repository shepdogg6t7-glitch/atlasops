# AtlasOps

Document-indexing and "ask" app. Upload a document, index it, ask questions, get answers with source citations.

## Stack
- FastAPI API (`apps/api`), Redpanda consumer, database, storage
- Next.js frontend in `apps/web`
- LLM: Gemini, model pinned to `gemini-3.5-flash-lite`

## Environment
- Develop in Ubuntu-22.04 on WSL2 at `~/projects/atlasops`, not on the Windows side
- Node 24 via nvm
- Other worktrees exist (copilot-worktrees on Windows). Check the folder and branch with `pwd` and `git branch --show-current` before editing.

## Gotchas
- Do not use the old default model `gemini-2.5-flash-lite`. It returns a 404.
- Run frontend builds with `NODE_ENV=production`. A non-standard value breaks the build.
- `LLM_API_KEY` lives in `.env` on the FastAPI host only. Never put it in the frontend, in logs, or in anything committed.
- Stage files by name, not `git add .`. There is a stray empty file called `main` in the repo root.

## Formatting
- Run Prettier (width 100, config in `.prettierrc.json`) on any frontend file you change in `apps/web` before finishing.
- Python is not formatted by Prettier. Markdown is not format-on-save.

## Verify your work
- Frontend, from `apps/web`: `npm ci`, `npm run lint`, then `NODE_ENV=production npm run build`
- Backend unit tests mock Gemini, so passing tests do not prove the live key works.
- For changes touching indexing or `/ask`, test live: index a PDF, search, ask, and confirm the answer cites a source passage.

## Rules
- Ask before you commit, push, delete, or spend money. Never run anything that bills an API.
- Use Plan Mode for auth, rate limiting, hosting, or anything that touches more than a few files.
- Do not invent config values, versions, or endpoints. If something is not in the repo, say "Not found."
- Keep changes small and explain what you changed in plain English.

## Open work
- Auth is built in a separate worktree and is not yet committed or pushed
- Still to do before going public: rate limiting, a spending cap, and a host for the FastAPI API and consumer (Vercel covers only the frontend)
- `npm audit` showed 8 vulnerabilities (7 high, 1 critical) that still need review
- `npm run lint` fails on 2 `no-explicit-any` errors in `apps/web/app/page.tsx` (present on main)
