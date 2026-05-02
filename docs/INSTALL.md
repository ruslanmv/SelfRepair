# SelfRepair installation

## TL;DR

```bash
make install-clean       # creates .venv, installs everything cleanly
source .venv/bin/activate
make test
```

That's it. The rest of this document explains why the targets above exist and
what to do when something goes sideways.

## Supported Python

3.11 or 3.12. The `.python-version` file pins 3.12 for pyenv users. SelfRepair
uses standard-library `StrEnum` (3.11+) and `tomllib` (3.11+).

```bash
# pyenv
pyenv install 3.12.7
pyenv local 3.12.7

# uv (faster)
uv venv --python 3.12 .venv
```

## Dependency layout

The base install is intentionally lean. Heavy or churn-prone ecosystems live in
optional extras so they only ship when you need them:

| Extra | When to install | Pulls |
|---|---|---|
| `[dev]` | Anyone running tests or hacking on SelfRepair | pytest, ruff, mypy, pre-commit |
| `[server]` | Running the API/worker against Postgres + Redis | sqlalchemy, alembic, asyncpg, arq, redis, structlog, pyjwt, opentelemetry |
| `[huggingface]` | Discovering and scanning HF repos | huggingface_hub (and its transitive ML stack) |
| `[gitlab]` | Discovering and scanning GitLab repos | python-gitlab |
| `[ollabridge]` | Already pulled by base; alias kept for clarity | httpx |
| `[all]` | Everything | all of the above |

For most users, `[dev,server]` is enough. Add `[huggingface]` if you point
SelfRepair at Hugging Face namespaces.

## Why do I see a `transformers`/`tokenizers` conflict?

```
ERROR: pip's dependency resolver does not currently take into account all the
packages that are installed.
transformers 4.30.2 requires tokenizers!=0.11.3,<0.14,>=0.11.1, but you have
tokenizers 0.21.4 which is incompatible.
```

**This is not caused by SelfRepair** — neither `transformers` nor `tokenizers`
is a SelfRepair dependency. The conflict is in your existing environment
between a stale `transformers` (from June 2023) and a newer `tokenizers` that
something else installed.

Fix it one of three ways:

1. **Use a clean venv** (recommended):
   ```bash
   make install-clean   # wipes .venv and reinstalls
   ```
2. **Upgrade the stale package** in your shared env:
   ```bash
   pip install --upgrade transformers
   ```
3. **Uninstall it** if nothing in your project actually needs it:
   ```bash
   pip uninstall -y transformers
   ```

We also moved `huggingface_hub` to an optional `[huggingface]` extra so
default installs no longer touch the HF dep tree at all.

## With uv (faster)

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev,server]"
```

uv resolves and installs in one shot, skips the redundant uninstall/install
cycles that pip prints, and won't show the noisy pre-existing-conflict warnings
when run against a fresh venv.

## Running the dev stack

```bash
make docker-up       # postgres + redis + api + worker + one-shot migrate
make docker-logs     # tail logs
make docker-down     # tear down (drops the postgres volume)
```

## Common errors and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'sqlalchemy'` | Installed without `[server]` extra | `make install` (which uses `[dev,server]`) |
| `ModuleNotFoundError: No module named 'huggingface_hub'` | Trying to scan HF without the extra | `pip install -e ".[huggingface]"` |
| `psycopg.errors.UndefinedTable: relation "job" does not exist` | Migrations not applied | `make migrate` |
| `redis.exceptions.ConnectionError` | Redis isn't running | `make docker-up` or run a local Redis |
| `pre-commit not found` | Installed `[server]` but not `[dev]` | `make install` (covers both) |
