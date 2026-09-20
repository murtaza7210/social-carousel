# social-carousel

Interview-first social carousel publisher, packaged as a skill for Claude Code and Hermes.

## What it does

Turns one topic into a designed, published carousel. On first use it interviews you once (brand, handle, audience, voice, look, call to action, platforms, approval mode) and saves a profile. On every run after that it asks only for a topic, writes a 6 to 8 slide deck, renders the slides with Higgsfield `gpt_image_2` on a style-anchor chain so every deck matches the last, builds 1080x1350 finals, writes per-platform captions, publishes through Blotato, and verifies the live post URLs. Two permanent rules: LinkedIn always goes to both the personal profile and the configured company page, and an angle that overlaps the post log is refused with a differentiated alternative proposed instead.

## Layout

```
distribution.yaml, profile.yaml, config.yaml, SOUL.md   Hermes distribution "shohrat" (repo root, as `hermes profile install` expects)
skills/social-carousel/SKILL.md              the skill
skills/social-carousel/scripts/finalize_slides.py   fit-and-pad raws to 1080x1350 finals + contact sheet
skills/social-carousel/profile.example.json  schema of the runtime profile (empty values)
```

## Dependencies

| Dependency | Why | Where |
|---|---|---|
| Higgsfield MCP | renders slides with `gpt_image_2` | `https://mcp.higgsfield.ai/mcp` |
| Blotato MCP | hosts images, publishes, verifies | `https://mcp.blotato.com/mcp` (REST fallback: `https://backend.blotato.com/v2` with a `blotato-api-key` header) |
| Python 3 + Pillow | `finalize_slides.py` | `pip install pillow` |
| curl | uploads to presigned URLs, downloads raws | system |

Both MCP servers must be connected in the agent's environment. Without Pillow the skill posts 1:1 raws instead of 4:5 finals.

## Runtime state

Everything the skill writes lives in `$CAROUSEL_HOME` (default `./carousel` when unset):

```
$CAROUSEL_HOME/profile.json          brand, voice, look, targets, account ids, style anchor
$CAROUSEL_HOME/post-log.md           one row per published run: date, platforms, topic, URLs
$CAROUSEL_HOME/<date>-<slug>/        COPY.md, raws, finals, contact sheet for one deck
```

None of this is committed. `.gitignore` excludes it. `profile.example.json` documents the schema; you do not need to copy it, the skill's first-run interview creates `profile.json`.

## Install

Claude Code:

```bash
git clone https://github.com/murtaza7210/social-carousel.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/social-carousel/skills/social-carousel" ~/.claude/skills/social-carousel
export CAROUSEL_HOME=~/carousel
```

The skill then appears as `/social-carousel`.

Hermes (inside the Hermes container, as the `hermes` user):

```bash
hermes profile install https://github.com/murtaza7210/social-carousel -y
hermes profile info shohrat
```

This creates `$HERMES_HOME/profiles/shohrat/` from the manifest only; nothing is cloned from another profile. Then, per profile: put `ANTHROPIC_*`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` in `profiles/shohrat/.env`, add the two MCP servers (`hermes mcp add higgsfield --url https://mcp.higgsfield.ai/mcp --auth oauth`, same for `blotato`) and complete `hermes mcp login` for each, set `CAROUSEL_HOME=/opt/data/profiles/shohrat/carousel` in `.env`, and start the gateway.

## How Hermes invokes it

Route the task to the **Shohrat** profile (`shohrat`). First run: "make a carousel" triggers the interview. Every run after: give it a topic, for example "make a carousel on why one agent beats five". It writes, renders, shows the contact sheet and captions, waits for approval (profile default `review`), publishes, and reports one verified URL per target.

## Keep out of git

- `profile.json` (account ids, handle, brand data) and `post-log.md`
- Blotato API keys, Higgsfield credentials, presigned upload URLs
- Every generated image (raws, finals, contact sheets)
- `.env` files

Credentials never enter the skill at all; they live in the MCP server connections.

## Operations

Runtime notes for the deployed profile (per-profile `.env` keys including `API_SERVER_PORT=8648`, gateway registration, the egress limitation, and rollback): [docs/OPERATIONS.md](docs/OPERATIONS.md). Egress-fence test plan, not applied: [docs/EGRESS-FENCE-TEST-PLAN.md](docs/EGRESS-FENCE-TEST-PLAN.md).
