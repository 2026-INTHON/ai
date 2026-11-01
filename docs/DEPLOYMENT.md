# Development and deployment

Speech assets are indexed in the private persistent AI volume at `/data/speech-cache.db`. `speech_assets` stores normalized text, provider, model, voice ID and effective synthesis settings; `speech_tags` links character, personality, emotion, reaction, recovery stage, pack and speed. Match the effective voice settings before calling a paid provider. Existing `selected-voice-v2` MP3s are adopted without regeneration; older incompatible narrator voices are not substituted. Cache hits bypass quota reservations. Missing files are regenerated on demand.

The service-authenticated `POST /v1/speech/cache/index` accepts up to 500 known synthesis requests and indexes existing files only; it cannot generate or spend credits. `GET /v1/speech/cache/stats` returns counts by voice without utterance text. These internal endpoints are not public FE catalog APIs. Runtime Typecast limit is 20,000 new characters per Korea calendar day; provider account credit limits still apply.

`feat/*` → PR to `develop` → checks → merge → release PR to `main` → checks → verified GitHub Release → VM deployment (within about 1 minute plus build time).

- `main`: production. `develop`: default integration branch. Use `feat/<topic>` for new features and `fix/<topic>` for fixes.
- Existing feature branches remain available; do not force-push or delete teammates' branches.
- CI runs on pushes and PRs. Deployment releases are created only from `main` after the check job succeeds. Pull requests never deploy.
- Manual rerun: Actions → AI checks → Run workflow → select `main`.
- The VM polls public, verified deployment releases over HTTPS. GitHub does not require inbound SSH access or a cloud management key.
- Source packaging uses `git archive`; ignored `.env`, local keys, database files and caches are excluded. Keep runtime secrets only in the VM's existing environment files.
- Host paths: `/srv/inthon/releases/ai/current`, `/srv/inthon/ai/.env` (BE/AI), deployment status `/srv/inthon/deployments/ai.json`.
- VM commands: `sudo systemctl status malo-deploy.timer`, `sudo journalctl -u malo-deploy.service -n 100`, `sudo docker compose -f /srv/inthon/compose.yaml ps`.
- Services build serially, preserve data volumes and environment files, and must pass a health check. A failed health check restores the previous image and source link.
- The VM auto-shutdown schedule still applies. Releases remain published while the VM is off; deployment resumes after it starts.

Frontend listens on VM loopback port 8080 and is served through the existing HTTPS gateway. API, docs, AI and model paths retain their existing routes. The HTTP 8080 listener is intended for VM checks or an SSH tunnel; microphone testing uses HTTPS.

The frontend repository has `VM_SSH_PRIVATE_KEY` for the FE developer's `malo-fe` SSH account. The account has no Docker group membership and may invoke only the frontend deployment command through sudo. Use this key only privately; never commit it. An FE developer on another network must have their public IP added to the existing Azure SSH allowlist before direct SSH access is possible.
