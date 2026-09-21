#!/usr/bin/env python3
"""
Tests for approval_guard.py — detection + task-completion enforcement.

Covers the four required cases: MISSING, PARTIAL, REVISED, COMPLETE approvals,
plus out-of-order action detection and section-10 record completeness.

Run: python3 -m pytest test_approval_guard.py -q     (or: python3 test_approval_guard.py)
No third-party deps; falls back to a built-in runner if pytest is absent.
"""
import json, os, sys, tempfile, importlib.util, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "approval_guard.py")

spec = importlib.util.spec_from_file_location("approval_guard", GUARD)
assert spec and spec.loader, f"cannot load approval_guard from {GUARD}"
ag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ag)

ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()


def _appr(state="pending", ref=""):
    return {"state": state, "ref": ref, "at": ISO if ref else ""}


def base_state(**overrides):
    s = {
        "task_id": "t_test",
        "approvals": {
            "cover": _appr(), "linkedin": _appr(), "instagram": _appr(),
            "facebook": _appr(), "publish": _appr(),
        },
        "actions": [],
        "completion_record": {"approval_reference": "", "posts": []},
        "violations": [],
    }
    s.update(overrides)
    return s


def approve(state, *keys, ref="msg#123"):
    for k in keys:
        state["approvals"][k] = _appr("approved", ref)
    return state


def full_record():
    return {
        "approval_reference": "msg#final-go @2026-09-21T05:00:00Z",
        "posts": [
            {"platform": "linkedin", "post_id": "li_1", "status": "published",
             "published_at": ISO, "url": "https://linkedin.com/feed/update/urn:li:share:1"},
            {"platform": "linkedin_page", "post_id": "li_2", "status": "published",
             "published_at": ISO, "url": "https://linkedin.com/feed/update/urn:li:share:2"},
            {"platform": "instagram", "post_id": "ig_1", "status": "published",
             "published_at": ISO, "url": "https://www.instagram.com/p/AAA/"},
            {"platform": "facebook", "post_id": "fb_1", "status": "published",
             "published_at": ISO, "url": "https://facebook.com/1_2"},
        ],
    }


# ---- CREATIVE / INTERIOR GATE ----------------------------------------------

def test_missing_all_blocks_interiors():
    ok, missing = ag.creative_ready(base_state())
    assert ok is False and set(missing) == set(ag.CREATIVE_ITEMS)

def test_partial_creative_blocks_interiors():
    s = approve(base_state(), "cover", "linkedin")
    ok, missing = ag.creative_ready(s)
    assert ok is False and set(missing) == {"instagram", "facebook"}

def test_complete_creative_allows_interiors():
    s = approve(base_state(), *ag.CREATIVE_ITEMS)
    ok, missing = ag.creative_ready(s)
    assert ok is True and missing == []

def test_approval_without_ref_does_not_count():
    s = base_state()
    s["approvals"]["cover"] = {"state": "approved", "ref": "", "at": ""}  # no reference
    ok, _ = ag.creative_ready(s)
    assert ok is False  # unreferenced approval is not an approval

# ---- REVISED APPROVAL (one item reset, others hold) -------------------------

def test_revised_item_resets_only_itself():
    s = approve(base_state(), *ag.CREATIVE_ITEMS)          # all approved
    s["approvals"]["instagram"] = _appr("pending")         # instagram revised -> pending
    ok, missing = ag.creative_ready(s)
    assert ok is False and missing == ["instagram"]        # only instagram outstanding
    # re-approve it -> ready again
    approve(s, "instagram")
    ok2, _ = ag.creative_ready(s)
    assert ok2 is True

# ---- PUBLISH GATE (separate final approval) --------------------------------

def test_creative_done_but_no_publish_approval_blocks_publish():
    s = approve(base_state(), *ag.CREATIVE_ITEMS)          # creative done, publish pending
    ok, missing = ag.publish_ready(s)
    assert ok is False and missing == ["publish"]

def test_full_approval_allows_publish():
    s = approve(base_state(), *ag.CREATIVE_ITEMS, "publish")
    ok, missing = ag.publish_ready(s)
    assert ok is True and missing == []

# ---- OUT-OF-ORDER ACTION DETECTION -----------------------------------------

def test_interior_tool_before_creative_is_violation():
    s = approve(base_state(), "cover", "linkedin")         # partial
    allowed, reason = ag.check_action(s, "generate_image_batch")
    assert allowed is False and "interior" in reason

def test_publish_tool_before_final_is_violation():
    s = approve(base_state(), *ag.CREATIVE_ITEMS)          # creative ok, no publish approval
    allowed, reason = ag.check_action(s, "blotato_create_post")
    assert allowed is False and "publish" in reason

def test_publish_tool_after_full_approval_allowed():
    s = approve(base_state(), *ag.CREATIVE_ITEMS, "publish")
    allowed, reason = ag.check_action(s, "blotato_create_post")
    assert allowed is True

# ---- COMPLETION VALIDATION (section 10) ------------------------------------

def test_completion_blocked_when_approvals_missing():
    s = base_state()
    s["completion_record"] = full_record()
    ok, errors = ag.validate_completion(s)
    assert ok is False and any("approval missing" in e for e in errors)

def test_completion_blocked_when_record_incomplete():
    s = approve(base_state(), *ag.CREATIVE_ITEMS, "publish")
    rec = full_record()
    del rec["posts"][2]["url"]                             # drop a required field
    s["completion_record"] = rec
    ok, errors = ag.validate_completion(s)
    assert ok is False and any("missing field: url" in e for e in errors)

def test_completion_blocked_when_platform_missing():
    s = approve(base_state(), *ag.CREATIVE_ITEMS, "publish")
    rec = full_record()
    rec["posts"] = [p for p in rec["posts"] if p["platform"] != "facebook"]  # drop facebook
    s["completion_record"] = rec
    ok, errors = ag.validate_completion(s)
    assert ok is False and any("facebook" in e for e in errors)

def test_completion_blocked_on_unresolved_violation():
    s = approve(base_state(), *ag.CREATIVE_ITEMS, "publish")
    s["completion_record"] = full_record()
    s["violations"] = [{"tool": "blotato_create_post", "reason": "published before final approval"}]
    ok, errors = ag.validate_completion(s)
    assert ok is False and any("violation" in e for e in errors)

def test_completion_ok_when_fully_approved_and_recorded():
    s = approve(base_state(), *ag.CREATIVE_ITEMS, "publish")
    s["completion_record"] = full_record()
    ok, errors = ag.validate_completion(s)
    assert ok is True and errors == []

def test_completion_rejects_nonpublished_status():
    s = approve(base_state(), *ag.CREATIVE_ITEMS, "publish")
    rec = full_record()
    rec["posts"][0]["status"] = "failed"
    s["completion_record"] = rec
    ok, errors = ag.validate_completion(s)
    assert ok is False and any("not 'published'" in e for e in errors)


# ---- built-in runner (no pytest needed) ------------------------------------

def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"[PASS] {fn.__name__}"); passed += 1
        except AssertionError as e:
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:
            print(f"[ERROR] {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    return 0 if passed == len(fns) else 1


if __name__ == "__main__":
    sys.exit(_run_all())
