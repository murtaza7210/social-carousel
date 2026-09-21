#!/usr/bin/env python3
"""
approval_guard.py — Detection + task-completion enforcement for the social-carousel skill.

WHAT THIS IS (read honestly):
  This is DETECTION and TASK-COMPLETION enforcement, NOT hard prevention of MCP calls.
  Shohrat renders via the Higgsfield MCP server and publishes via the Blotato MCP server,
  which the agent can invoke directly. This guard cannot physically block an MCP tool call.
  What it CAN do, deterministically:
    - Refuse to bless task completion unless every required approval state is APPROVED
      and the full section-10 completion record is present and well-formed.
    - Detect an out-of-order action (interior generation before the 4 creative approvals,
      or publishing before the separate final approval) by comparing the recorded
      action-log against the approval states, and emit a machine-readable VIOLATION that
      the skill is instructed to surface to Zubi.
  A true fail-closed design (route publishing through a local script that solely holds the
  Blotato path) is documented separately in docs/FAIL-CLOSED-WRAPPER.md and is NOT built here.

STATE FILE: <deck>/approval_state.json  (schema in approval_state.example.json)
  {
    "task_id": "t_...",
    "approvals": {
      "cover":     {"state":"pending|approved", "ref": "<approval reference>", "at":"<iso8601>"},
      "linkedin":  {"state":..., "ref":..., "at":...},
      "instagram": {"state":..., "ref":..., "at":...},
      "facebook":  {"state":..., "ref":..., "at":...},
      "publish":   {"state":..., "ref":..., "at":...}      # the SEPARATE final gate
    },
    "actions": [ {"tool":"generate_image_batch|blotato_create_post|...", "at":"<iso>"} , ...],
    "completion_record": {                                  # section 10 schema
      "approval_reference": "...",
      "posts": [ {"platform":"linkedin","post_id":"...","status":"published",
                  "published_at":"<iso>","url":"https://..."} , ... ],
    },
    "violations": [ ... ]                                   # appended by check_action
  }

CREATIVE_ITEMS gate interior generation; PUBLISH gate gates publishing.
Exit codes: 0 = OK/approved for the requested check; 2 = blocked/violation; 3 = bad input.
"""
import argparse, json, sys, datetime

CREATIVE_ITEMS = ["cover", "linkedin", "instagram", "facebook"]
ALL_APPROVALS = CREATIVE_ITEMS + ["publish"]

# Tools that must not run before their gate.
INTERIOR_TOOLS = {"generate_image_batch"}                      # interiors: needs 4 creative approvals
PUBLISH_TOOLS = {"blotato_create_post", "posts", "create_post"}  # publish: needs final approval

REQUIRED_POST_FIELDS = ["platform", "post_id", "status", "published_at", "url"]
# The four platform surfaces every complete run must record (linkedin personal + page count as two).
REQUIRED_PLATFORMS = ["linkedin", "linkedin_page", "instagram", "facebook"]


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"state file is not valid JSON: {e}"}))
        sys.exit(3)


def _approved(state, key):
    a = (state.get("approvals") or {}).get(key) or {}
    return a.get("state") == "approved" and bool(a.get("ref"))


def creative_ready(state):
    """All four creative items approved (with a reference)."""
    missing = [k for k in CREATIVE_ITEMS if not _approved(state, k)]
    return (len(missing) == 0), missing


def publish_ready(state):
    """Creative gate passed AND the separate final publish approval recorded."""
    c_ok, missing = creative_ready(state)
    if not c_ok:
        return False, [f"creative:{m}" for m in missing]
    if not _approved(state, "publish"):
        return False, ["publish"]
    return True, []


def check_action(state, tool):
    """Detect an out-of-order tool call. Returns (allowed, reason)."""
    t = tool.strip()
    if t in INTERIOR_TOOLS:
        ok, missing = creative_ready(state)
        if not ok:
            return False, f"interior-generation tool '{t}' called before creative approval; missing: {missing}"
    if t in PUBLISH_TOOLS:
        ok, missing = publish_ready(state)
        if not ok:
            return False, f"publish tool '{t}' called before approvals; missing: {missing}"
    return True, ""


def validate_completion(state):
    """
    Hard task-completion gate. Returns (ok, errors[]).
    Task MUST NOT be completed if any approval or any section-10 record field is missing.
    """
    errors = []

    # 1. All five approvals present.
    for k in ALL_APPROVALS:
        if not _approved(state, k):
            errors.append(f"approval missing or unreferenced: {k}")

    # 2. Completion record present + section-10 schema complete.
    rec = state.get("completion_record") or {}
    if not rec.get("approval_reference"):
        errors.append("completion_record.approval_reference missing")
    posts = rec.get("posts") or []
    if not posts:
        errors.append("completion_record.posts empty (no tool-returned publish records)")
    seen_platforms = set()
    for i, p in enumerate(posts):
        for f in REQUIRED_POST_FIELDS:
            if not p.get(f):
                errors.append(f"posts[{i}] missing field: {f}")
        if p.get("url") and not str(p["url"]).startswith("http"):
            errors.append(f"posts[{i}].url is not a real URL: {p.get('url')!r}")
        if p.get("status") and p["status"] != "published":
            errors.append(f"posts[{i}].status is {p['status']!r}, not 'published'")
        if p.get("platform"):
            seen_platforms.add(p["platform"])
    # 3. All four required platform surfaces recorded.
    for plat in REQUIRED_PLATFORMS:
        if plat not in seen_platforms:
            errors.append(f"no published record for required platform: {plat}")

    # 4. Any recorded violation blocks completion.
    for v in (state.get("violations") or []):
        errors.append(f"unresolved violation: {v}")

    return (len(errors) == 0), errors


def main():
    ap = argparse.ArgumentParser(description="social-carousel approval guard (detection + completion enforcement)")
    ap.add_argument("--state", required=True, help="path to approval_state.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_int = sub.add_parser("gate-interiors", help="exit 0 only if all 4 creative items approved")
    p_pub = sub.add_parser("gate-publish", help="exit 0 only if creative + final publish approval recorded")
    p_act = sub.add_parser("check-action", help="detect an out-of-order tool call; records a violation if so")
    p_act.add_argument("--tool", required=True)
    p_comp = sub.add_parser("validate-completion", help="exit 0 only if all approvals + full section-10 record present")

    args = ap.parse_args()
    state = _load(args.state)
    if state is None:
        print(json.dumps({"ok": False, "error": f"no state file at {args.state}; create it before rendering"}))
        sys.exit(2)

    if args.cmd == "gate-interiors":
        ok, missing = creative_ready(state)
        print(json.dumps({"ok": ok, "gate": "interiors", "missing": missing}))
        sys.exit(0 if ok else 2)

    if args.cmd == "gate-publish":
        ok, missing = publish_ready(state)
        print(json.dumps({"ok": ok, "gate": "publish", "missing": missing}))
        sys.exit(0 if ok else 2)

    if args.cmd == "check-action":
        allowed, reason = check_action(state, args.tool)
        if not allowed:
            viol = {
                "tool": args.tool, "reason": reason,
                "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            state.setdefault("violations", []).append(viol)
            with open(args.state, "w") as f:
                json.dump(state, f, indent=2)
            print(json.dumps({"ok": False, "violation": viol,
                              "alert_zubi": True,
                              "message": "VIOLATION: out-of-order tool call recorded. Surface to Zubi."}))
            sys.exit(2)
        print(json.dumps({"ok": True, "tool": args.tool}))
        sys.exit(0)

    if args.cmd == "validate-completion":
        ok, errors = validate_completion(state)
        print(json.dumps({"ok": ok, "errors": errors}))
        sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
