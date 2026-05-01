# API Reference

Start the backend:

```bash
uvicorn backend.app.main:app --reload
```

## Health

```bash
curl http://localhost:8000/health
```

## Full repository inference

```bash
curl -X POST http://localhost:8000/repo/inference \
  -H 'Content-Type: application/json' \
  -d '{"repo_url":"https://github.com/org/repo.git","branch":"main","repair_mode":"dry_run"}'
```

## Agent / A2A style endpoint

```bash
curl -X POST http://localhost:8000/v1/rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"1","method":"repo.selfrepair","params":{"repo_url":"https://github.com/org/repo.git"}}'
```
