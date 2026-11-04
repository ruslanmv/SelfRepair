# Guided connector setup (Fleet > Settings)

The **Connected services** section in the React console is the single place to
configure **OllaBridge Cloud**, **GitPilot**, and **MatrixLab**. The dedicated
**Connections** navigation item uses the same UI and saved records.

## OllaBridge Cloud: device pairing (recommended)

1. Sign in to [OllaBridge Cloud](https://app.ollabridge.com) and start its
   **Device Pairing** flow. Generate a fresh, short-lived code. SelfRepair does
   **not** generate pairing codes or know their expiration time.
2. In **Fleet > Settings**, choose **OllaBridge Cloud > Manage** (or
   **Add connector > OllaBridge Cloud**).
3. Choose **Device pairing**, enter the 8-character dashboard code (a dash is
   optional), and select **Pair & verify**.
4. SelfRepair sends the code from its own backend to
   `POST https://app.ollabridge.com/device/pair-simple`. If accepted, the
   returned device token is encrypted on the server. The browser never receives
   the device token.
5. The service checks authenticated `/v1/models` access and displays the
   result. If the gateway is reachable but model access cannot be verified,
   the UI reports **not verified**, not falsely **connected**.

The pairing flow uses the canonical API root
`https://app.ollabridge.com/v1`. The Cloud dashboard URL (used for pairing)
is `https://app.ollabridge.com`.

If you have an existing gateway API key, switch the wizard to **API key**.
You can also configure a custom OllaBridge endpoint with this method.

## GitPilot and MatrixLab

Select a service, set the HTTPS service root URL, optionally supply its
service token, and choose **Save & test**. Existing encrypted tokens are
retained when the token field is left empty. **Test** rechecks the saved
endpoint. **Disconnect** deletes the stored secret and resets its status.

Connection status reflects the **last test**, not a background heartbeat.
A health-only response does not prove OllaBridge model authorization.

## Security and operations

- Production must configure `SELFREPAIR_SECRET_KEY` (or `SESSION_SECRET`)
  in the Hugging Face Space secrets. Do not rely on the development fallback.
- The webapp stores connection keys using the existing Fernet encryption.
  The JSON API returns only `has_secret` and a masked value, not plaintext.
- Device pairing is session-authenticated and rate-limited per user to
  **five attempts per ten minutes**.
- The pairing server URL is fixed in the backend; the browser cannot choose
  an arbitrary host to exchange a code with.
- Connection URLs must be HTTPS. HTTP is permitted for localhost only when
  `SELFREPAIR_INSECURE_COOKIES=1` (local development).
- Connection save, pairing and disconnect operations are audit logged.
- **Account, GitHub, GitLab, Hugging Face and Bitbucket** credential-reference
  settings are separate from the three service connections.
- The standalone full-stack FastAPI service currently has a different
  `/v1/integrations` API (credential references). The interactive service
  connector endpoints in this change are implemented in the **Hugging Face
  webapp** at `deploy/huggingface/webapp/api_v1.py`. Do not assume the full
  FastAPI backend supports the new endpoints.

## Build and deployment

The Hugging Face Space serves a **checked-in, prebuilt SPA** in
`deploy/huggingface/webapp/spa`. Editing `frontend/src` alone does not
update the deployed screen. After pulling/merging this change, rebuild and
sync the bundle **before deploying**:

```bash
cd frontend
npm ci
npm run lint
npm run build
cd ..
pytest tests/unit/test_hf_space_api.py -q
./scripts/build_hf_space.sh
```

Commit the resulting files under `deploy/huggingface/webapp/spa` when
updating the Hugging Face Space repository. Verify that its
`spa/index.html` references the freshly generated assets.

Never copy a live pairing code or access token into a GitHub issue, log,
documentation, or test fixture.
