# PROPOSED (NOT IMPLEMENTED): true fail-closed publish wrapper

Status: **DESIGN ONLY.** Do not implement without separate explicit approval from Murtaza.
The shipped enforcement (`scripts/approval_guard.py`) is **detection + task-completion
enforcement**, not hard prevention. This document specifies what a genuinely fail-closed
design would require, so the decision is informed.

## Why the current guard is not fail-closed
Shohrat renders via the Higgsfield MCP server and publishes via the Blotato MCP server. The
agent calls those tools directly. Nothing forces the agent through a local checkpoint, so a
guard the agent is merely *instructed* to run before an MCP call is still procedural — it can
be skipped. `approval_guard.py` therefore DETECTS and records violations and blocks task
completion; it cannot PREVENT an out-of-order MCP publish.

## What true fail-closed requires
Remove the agent's direct publish/interior MCP access and make a **local wrapper script the
sole path** to Blotato (and optionally Higgsfield batch). The wrapper refuses to act unless
`approval_state.json` shows the required approvals; since there is no other route, "skip the
gate" becomes impossible.

### Technical changes
1. **Remove Blotato from Shohrat's MCP reach.** Delete the Blotato server from the profile's
   MCP config so `blotato_create_post` etc. are not callable tools. (Higgsfield may stay if
   only publishing must be gated; to gate interiors too, remove `generate_image_batch` access
   and route it through the wrapper as well.)
2. **Wrapper script `scripts/publish.py`** — the only component holding the Blotato path:
   - reads `approval_state.json`; runs the same `gate-publish` / `validate` logic;
   - exits non-zero and publishes nothing if any approval is missing;
   - performs the REST publish itself and writes the section-10 record from the API responses.
3. **Credential isolation (key must NOT reach the agent chat / Zubi):**
   - Store `BLOTATO_API_KEY` so only the wrapper process reads it — e.g. an egress-proxy
     credential injection (iron-proxy) that adds the header at the network boundary, OR a
     root-owned env file readable only by the wrapper's exec context, never printed.
   - The agent invokes `publish.py` with NO key argument; the key is injected out of band.
   - Zubi never gets the key (unchanged from today).

### Feasibility
- Medium. The REST contract is already documented in SKILL.md §8, so the wrapper is a
  straightforward port. The harder part is credential injection that the agent truly cannot
  read — egress-proxy injection is the clean answer and matches the existing "never handles
  API keys" posture.
- Cost: one script + MCP-config change + an egress rule. No new services.

### Rollback
- Fully reversible: restore the Blotato MCP server entry in the profile config and remove
  `publish.py` from the execution path. Because this is distribution-owned, rollback = revert
  the commit and `hermes profile update shohrat`. No data migration; `approval_state.json`
  remains compatible.

### Residual risk even when fail-closed
- The agent could still write a wrong CAPTION into an approved slot; approval is of content the
  human saw, so human review remains the real control for correctness.
- If Higgsfield stays direct, interiors can still be generated early (wasteful, not harmful);
  gate them through the wrapper too if that matters.

## Recommendation
Adopt only if a real out-of-order publish occurs despite the detection layer, or if the cost of
a wrong live post is high enough to justify removing agent publish autonomy. Until then, the
detection + completion-enforcement layer plus per-run human approval is the proportionate control.
