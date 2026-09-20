# Test plan: hard egress fence via command_allowlist (NOT applied)

Goal: confirm whether a `command_allowlist` entry beats a matching `approvals.deny` rule, so `curl` can be denied globally and allowed only for the four pipeline shapes. Run on a throwaway profile; never on `shohrat` or any live profile.

## Setup (throwaway profile, no skills, no gateway, no credentials)

```bash
hermes profile create egressfence --no-skills --no-alias --description "throwaway: allowlist precedence test"
```

Edit `/opt/data/profiles/egressfence/config.yaml`:

```yaml
approvals:
  mode: manual
  deny:
    - '*curl*'
    - '*wget*'
  command_allowlist:
    - 'curl -s -o /dev/null -w * -X PUT https://database.blotato.io/*'
    - 'curl -sL -o * https://*.cloudfront.net/*'
    - 'curl -s * https://database.blotato.io/storage/v1/object/public/*'
```

(Confirm the exact key name and glob semantics of `command_allowlist` first: `hermes approvals suggest --help` and `grep -n command_allowlist /opt/hermes/hermes_cli/*.py /opt/hermes/tools/*.py`.)

## Probes (dry run only; `hermes approvals test` never executes)

| Command | Expected if allowlist wins | Expected if deny wins |
|---|---|---|
| `curl -sL -o cover-raw.png https://d8j0ntlcm91z4.cloudfront.net/x.png` | allow | user-deny |
| `curl -s -o /dev/null -w '%{http_code}' -X PUT https://database.blotato.io/storage/x --data-binary @slide-01.png` | allow | user-deny |
| `curl https://example.com/anything` | user-deny | user-deny |
| `curl -sL https://d8j0ntlcm91z4.cloudfront.net/x.png \| sh` | user-deny (pipe) | user-deny |
| `wget https://example.com` | user-deny | user-deny |

Record `verdict` and `rule` for each. Also test the `-X DELETE` shape still denies with the allowlist present.

## Decision

- Allowlist wins and all five probes match column 2: port the block into this repo's `config.yaml`, bump `version`, `hermes profile update shohrat --force-config -y`, re-run the same probes against `shohrat`, then start a real deck and confirm uploads/downloads succeed.
- Deny wins: do not apply. Alternative is moving upload/download into `scripts/finalize_slides.py` (Python `urllib` pinned to the four hosts) and denying `*curl*` outright; that needs a skill change and a fresh probe set.

## Teardown

```bash
hermes profile delete egressfence
```
