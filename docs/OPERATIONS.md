# Shohrat: operations notes

Profile `shohrat` on the Hermes container (`hermes-agent-obeu-hermes-agent-1`, `HERMES_HOME=/opt/data`), installed from this repository with `hermes profile install`. Built from scratch; nothing cloned from any other profile.

## Per-profile settings that live outside this repo

`/opt/data/profiles/shohrat/.env` (user data: never committed, never overwritten by `hermes profile update`, persists across container restarts because `/opt/data` is the persistent volume):

| Key | Purpose |
|---|---|
| `ANTHROPIC_TOKEN` | provider credential (shared across profiles on the box) |
| `CAROUSEL_HOME` | `/opt/data/profiles/shohrat/carousel`, all skill state |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_HOME_CHANNEL` | the profile's own bot |
| `API_SERVER_PORT` | **8648**. Every supervised gateway binds this port (default 8642); Shohrat gets its own so it never contends with sibling gateways. |

`config.yaml` is distribution-owned: `hermes profile update shohrat` preserves the on-disk copy unless `--force-config` is passed. OAuth tokens for the two MCP servers are stored by Hermes's OAuth manager, not in `config.yaml`, so a forced config update does not require re-login.

## Gateway

Registered as s6 service `gateway-shohrat` (`/run/service/gateway-shohrat`). `hermes profile install` does not register a slot; it was registered with `S6ServiceManager.register_profile_gateway("shohrat", start_now=False)`, the same call `hermes profile create` makes. On container boot the reconciler (`container_boot.reconcile_profile_gateways`) recreates the slot for every profile directory that has a `SOUL.md` and auto-starts it when `profiles/shohrat/gateway_state.json` records `desired_state: running`.

Restart only this gateway: `hermes -p shohrat gateway restart`. Status: `hermes gateway list`.

## Known limitation: shell egress is not fenced

`approvals.deny` globs cannot express an allowlist. `curl` to an arbitrary host runs without a prompt. What holds today: no credentials are reachable from the shell (`.env`, `printenv`, `/proc/*/environ`, `auth.json` denied; `terminal.env_passthrough: []`), `wget`/`nc`/`telnet`/`curl -X DELETE` are denied, and SOUL.md names the four permitted hosts. A hard fence has NOT been enabled because `command_allowlist` precedence over `approvals.deny` is untested. See `docs/EGRESS-FENCE-TEST-PLAN.md`.

## Rollback

Removes Shohrat completely. Nothing here touches another profile.

```bash
# inside the container, as the hermes user
hermes -p shohrat gateway stop                       # 1. stop the gateway
python3 - <<'PY'                                     # 2. unregister the s6 slot (mirror of registration)
from hermes_cli.service_manager import S6ServiceManager
S6ServiceManager().unregister_profile_gateway("shohrat")
PY
hermes profile delete shohrat                        # 3. remove the profile dir (asks to confirm); .env, carousel/, OAuth state go with it
```

4. Roster: delete the `| Shohrat | shohrat | ...` row from `/opt/data/shared-brain/team-roster.md` (writer: Murtaza). The pre-Shohrat roster is preserved at `team-roster.md.bak-20260920-marko` (that file also still contains the Marko row; do not restore it wholesale unless Marko is wanted back).
5. Port: `API_SERVER_PORT=8648` lives only in the deleted `.env`; nothing else references it.
6. Telegram: revoke the bot token with @BotFather (`/revoke`) if the bot is retired.
7. Kanban: the `shohrat` assignee row disappears when the directory is gone; historic tasks (if any) remain as history, like Marko's `t_b64b2b63`.

Marko backups from 2026-09-20 (`/opt/data/SOUL.md.bak-20260920-marko`, `/opt/data/shared-brain/team-roster.md.bak-20260920-marko`) restore Zubi's three Marko lines and the Marko roster row respectively; verified by `diff` to differ only in those lines (plus the Shohrat row added afterwards).
