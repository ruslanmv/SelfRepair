# Guided connector setup (Fleet > Settings)

The **Connected services** section in the React console is the place to
configure **OllaBridge Cloud**, **GitPilot**, and **MatrixLab**. The
**Connections** page uses the same wizard and the same saved records.

Choose a provider, configure authentication, then verify. A green
**Connected** state means the credential was accepted by that service.
It does not mean a repair or a sandbox job has already run. Health-only
results are shown as **Reachable**.

Both deployments expose the same `/v1/connections` API:

| Deployment | Where the routes live | Where secrets are stored |
| --- | --- | --- |
| Full FastAPI backend | `selfrepair/api/routes/connections.py` | Postgres `service_connection.secret_enc` (Fernet), one row per organization and provider |
| Hugging Face Space | `deploy/huggingface/webapp/api_v1.py` | The Space database `connections.api_key_enc` (Fernet), one row per user and provider |

The pairing rules, URL checks, and probes are one module:
`deploy/huggingface/webapp/connector_service.py`. The full backend loads
that same file through `selfrepair.connectors.service`.

## OllaBridge Cloud: device pairing

This matches the OllaBridge Cloud contract in `ollabridge-cloud`:

1. Sign in at [OllaBridge Cloud](https://app.ollabridge.com).
2. Start **Device pairing**. The dashboard calls
   `POST /dashboard/start-pairing` and shows a short-lived code such as
   `ABCD-1234` (four letters, four digits, about 10 minutes). That code is
   already linked to the signed-in account. SelfRepair does not generate
   codes and does not know the remaining time.
3. In SelfRepair, open **Fleet > Settings** (or **Connections**) and choose
   **OllaBridge Cloud > Configure**.
4. Choose **Device pairing**, paste the code, and select **Pair & verify**.
5. The SelfRepair backend sends the code to the fixed URL
   `POST https://app.ollabridge.com/device/pair-simple` with a SelfRepair
   client identity. The browser never chooses that host.
6. On success the response contains `device_token`. The server encrypts it
   and stores only the ciphertext. The token is not returned to the browser
   and is not written to logs.
7. The server then calls `GET https://app.ollabridge.com/v1/models` with
   `Authorization: Bearer <device token>`. **Connected** is shown only when
   that authorized model list succeeds. A bare `/health` response stays
   **Reachable** and does not count as model access.

Codes that are expired, already used, unknown, or not linked to a signed-in
account are rejected with a specific message. The used code is not stored.
Five pairing attempts are allowed per user per ten minutes, counted in
process even when Redis is down, and also in Redis when Redis is configured.
A second attempt cannot run while the first is still in flight.

### API key instead of pairing

In the same wizard, choose **API key**. Paste an existing device token or
gateway key and, if needed, a different HTTPS base URL that includes `/v1`.
Leave the token field blank later to keep the saved credential and only
change the URL.

The canonical paired base URL is `https://app.ollabridge.com/v1`.
The dashboard origin used for pairing is `https://app.ollabridge.com`.

## GitPilot

1. Choose **GitPilot > Configure**.
2. Set the HTTPS service root, for example `https://ruslanmv-gitpilot.hf.space`.
   Local HTTP is accepted only for `localhost` when development mode is on.
3. Paste the service access token if GitPilot requires one. Leave it blank
   on a later save to keep the current token.
4. **Save & test** checks `/health` (then `/v1/health`). **Reachable** means
   the process answered. It does **not** mean a repair ran.
5. **Test** repeats that check. **Disconnect** deletes the stored token.

Repair workflows call `POST {base}/repair` with the saved URL and token:

- `selfrepair-repo repair` resolves the saved organization row when
  `SELFREPAIR_ORG_ID` is set, otherwise `GITPILOT_URL` /
  `SELFREPAIR_GITPILOT_URL` and `GITPILOT_TOKEN` /
  `SELFREPAIR_GITPILOT_TOKEN`.
- Reviewer remediation uses the review's organization id, then the same
  environment fallback.
- The Hugging Face health worker uses the newest saved GitPilot credential,
  then `GITPILOT_URL`.

If GitPilot cannot be reached, the client returns an offline stub and the
CLI says the preview is not a completed repair. Reviewer tasks are stored
as `gitpilot_unavailable`, not as a patch.

## MatrixLab

1. Choose **MatrixLab > Configure**.
2. Set the HTTPS service root, for example `https://ruslanmv-matrixlab.hf.space`.
3. Optionally paste `MATRIXLAB_BEARER_TOKEN` (or the Space sandbox token).
4. **Save & test** reads `/capabilities` and `/health`. Profiles returned by
   the service are shown in the detail text. **Reachable** means those
   endpoints answered. A patch was not executed.
5. Disconnect removes the token.

`selfrepair-repo repair` sends `POST /repo/validate-patch` with the saved
URL and bearer token. If the call does not return a real run, the report
says validation was not performed. The Space health worker records
`sandbox_check` from `/capabilities` and sets `workflow_verified` to false.

Environment fallback, when no saved row exists:

- `MATRIXLAB_URL` or `SELFREPAIR_MATRIXLAB_URL`
- `MATRIXLAB_TOKEN`, `SELFREPAIR_MATRIXLAB_TOKEN`, or `MATRIXLAB_BEARER_TOKEN`

## Status values

| Status | When it is shown |
| --- | --- |
| Not configured | No saved check yet |
| Pairing | A pairing request is in progress (not stored after it finishes) |
| Connected | OllaBridge accepted the credential on `/v1/models`, or a protected health route rejected an anonymous call and accepted the token |
| Reachable | The service answered a health or capabilities request. No repair or sandbox job ran |
| Needs attention | The last check failed or the credential was rejected |
| Expired | Reserved for an explicit expiry result |
| Disconnected | The saved credential was removed |

**Last success** is the last check that reached the service. **Last attempt**
is the last check of any outcome. Nothing is polled in the background.

## Secrets and production settings

Set these in the server environment or in the Hugging Face Space secrets.
Do not put tokens in the browser, in git, or in `credential_ref` fields.

| Variable | Role |
| --- | --- |
| `SELFREPAIR_SECRET_KEY` | Fernet key material for connector secrets. `SESSION_SECRET` is the fallback. Required in production before a new token can be saved. |
| `SELFREPAIR_ENV` | `production` outside development. `dev`, `test`, `local`, or `ci` enables the local HTTP and dev-only encryption fallback. |
| `SELFREPAIR_INSECURE_COOKIES` | `1` only for local HTTP. Also enables the dev encryption fallback. |
| `SELFREPAIR_ORG_ID` | Organization whose saved connectors the CLI and healing loop should read. |
| `SELFREPAIR_DATABASE_URL` | Postgres URL for the full backend, including `service_connection`. |
| `OLLABRIDGE_BASE_URL` / `OLLABRIDGE_API_KEY` | Used only when that organization has no saved OllaBridge row. `OPENAI_BASE_URL` and `OPENAI_API_KEY` remain compatible aliases. |
| `GITPILOT_URL` / `GITPILOT_TOKEN` | Fallback when no saved GitPilot row exists. |
| `MATRIXLAB_URL` / `MATRIXLAB_TOKEN` | Fallback when no saved MatrixLab row exists. |
| `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` | Optional Redis rate-limit store for the Space. The in-process limiter still applies if Redis is down. |

A saved row, including a disconnected one, is used instead of the
environment token for that provider. Disconnect does not fall back to a
token that is still sitting in the environment.

The dev encryption key is not used when `SELFREPAIR_ENV` is unset or is
`production`. Rotate a credential by saving a new token, or disconnect and
pair again. Old ciphertext that cannot be decrypted with the current key is
treated as missing; replace the token. Do not log the previous value.

## Security

- Mutations require the session cookie. On the full backend, only an
  organization **admin** can change connectors. Reads and writes are filtered
  by `org_id`. On the Space they are filtered by the signed-in user.
- Cookie mutations with `Origin` or `Sec-Fetch-Site: cross-site` are rejected.
  The Space uses `SameSite=None` so the Hugging Face iframe can send the
  cookie; the origin check is what stops another site from posting a pairing
  code or a token.
- Service URLs must be HTTPS, without userinfo, query, or fragment. Literal
  private, loopback, and link-local addresses are rejected. Before a probe,
  DNS answers that point at those ranges are rejected and redirects are not
  followed. Pairing always uses the fixed OllaBridge host.
- Audit rows record the provider and the status word. They do not record
  tokens or pairing codes.
- Repository platform integrations (GitHub, GitLab, Hugging Face, Bitbucket)
  stay on `/v1/integrations` and still store a credential reference, not the
  service token.

## Verify a real run

A settings check is not enough. After **Connected** or **Reachable**:

1. Run a dry-run repair so GitPilot is actually called:

   ```bash
   export SELFREPAIR_ORG_ID=<org-uuid>   # full backend only
   selfrepair-repo repair https://github.com/example/repo --dry-run
   ```

   The command prints `stubbed=False` only when GitPilot answered `POST /repair`.
   `stubbed=True` means no repair ran.

2. MatrixLab is executed only when `validate-patch` returns a real run.
   The command prints `executed` in that case and `not executed` otherwise.

3. On the Space, a health job attaches `repair` only after `POST /repair`,
   and `sandbox_check.workflow_verified` stays false because that path only
   reads capabilities.

## Local checks and the Space bundle

```bash
cd frontend
npm ci
npm run lint
npm run build
cd ..
pytest tests/unit -q
pytest tests/integration -q
./scripts/build_hf_space.sh
```

Apply the Postgres migration before using the full backend's connector
table:

```bash
alembic upgrade head
```

The Space serves the prebuilt SPA in `deploy/huggingface/webapp/spa`.
`./scripts/build_hf_space.sh` rebuilds the frontend and replaces that
bundle. Commit the updated `spa/` files with the UI change. Do not deploy
or change live credentials from this repository without an explicit approval.

Live pairing still requires a code generated in a signed-in OllaBridge
Cloud session. Do not paste that code, or the resulting device token, into
issues, logs, docs, or tests.
