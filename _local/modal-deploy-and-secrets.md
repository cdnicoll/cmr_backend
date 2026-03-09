# Modal Deploy and Secrets — High-Level Overview

How deployment works and how secrets reach Modal workers.

**Scripts:**
- `src/deployment/deploy.py` — deploy entry point; pushes secrets and runs `modal deploy`
- `scripts/create_modal_secrets.sh` — manual secret creation (prints `modal secret create` commands; use when you need to update secrets without deploying)

**Invocation:** `uv run deploy_dev` or `uv run deploy_prod` (pyproject scripts point to `deploy.py`).

---

## Deploy Flow

1. **Load env** — `deploy.py` loads `.env` (single source of truth for local/dev).
2. **Push secrets** — `push_modal_secrets()` in `deploy.py` runs `modal secret create --force` for each named secret.
3. **Deploy apps** — `modal deploy` runs for `modal_app.py` and `modal_workers.py`.

Secrets are pushed on every deploy so they stay in sync with `.env`. For manual secret updates only, use `scripts/create_modal_secrets.sh` (source `.env` first, then run the printed commands).

---

## Secrets Flow

| Step | What happens |
|------|---------------|
| 1 | `.env` holds credentials and config (DB URLs, API keys, etc.). |
| 2 | `deploy.py` (or manual `scripts/create_modal_secrets.sh`) runs `modal secret create --force` for each named secret, passing key=value pairs from `.env`. |
| 3 | Modal stores these as named secrets (e.g. `supabase-credentials-develop`, `app-config-develop`). |
| 4 | Worker functions declare `secrets=[modal.Secret.from_name("secret-name")]` in their decorator. |
| 5 | When a function runs, Modal injects the secret values as environment variables into the container. |
| 6 | Application code reads them via `os.environ` or a settings layer (e.g. Pydantic). |

---

## Conventions

- **Environment-specific** — Secret names include the environment (e.g. `*-develop`, `*-production`) so dev and prod stay separate.
- **Pre-deploy push** — Secrets are pushed before `modal deploy`; workers always get the latest values.
- **No secrets in code** — Credentials live in `.env` and Modal secrets, never in source.

---

## Adding a New Secret

1. Add the variable to `.env` (and `.env.example`).
2. Add it to `push_modal_secrets()` in `src/deployment/deploy.py` (the appropriate `modal secret create` call). If using manual flow, update `scripts/create_modal_secrets.sh` too.
3. Ensure the worker or API reads it from the environment (no code changes needed if your settings already load from `os.environ`).
