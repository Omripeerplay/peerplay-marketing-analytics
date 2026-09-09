#!/usr/bin/env python3
"""
Isolated unit tests for the MergeCoins two-threshold logic added to main.py:
  - mergecoins_segment_reward()          (chapter-band -> segment/reward lookup)
  - build_mergecoins_payload()           (dashboard payload for the two-marker UI)
  - _crossed_chapter_before_deadline()   (the shared crossing-time helper used by
                                           both target and checkpoint overdue checks)
  - the two-threshold payout DECISION TREE inside check_progress() / verify_all_progress()

WHY this doesn't `import main`: main.py imports fastapi + google.cloud at module level, neither of
which is installed in this environment (Python 3.9, no venv here) — `import main` raises
ModuleNotFoundError before a single line of business logic runs. (test_mergecash.py works around
this the same way, via string-matching against the source rather than executing it.)

WHY this doesn't hand-copy the function bodies either: a hand copy silently drifts from the real code
the moment someone edits main.py without updating the test — worse than no test, because it keeps
passing while testing something that no longer exists. Instead, the three function-level tests below
extract the EXACT current source text of each function straight out of main.py via `ast` and `exec()`
it in a minimal stub namespace, so they always run the real, current implementation.

The payout decision tree (check_progress / verify_all_progress) is NOT extracted this way — those
functions are FastAPI route handlers wired directly to Firestore/BigQuery/fraud-check/email side
effects, so literal extraction would require stubbing most of the app. Instead, `decide_check_progress`
and `decide_verify_all_progress` below are plain-Python mirrors of exactly that branching, written by
reading the real functions line for line (see the comment above each mirror for the main.py section it
tracks). If that branching in main.py ever changes, these mirrors — and the tests below — must be
updated to match, the same caveat tests/test_mergecoins.js already carries for app.js.

Run: python3 test_mergecoins_new_logic.py
"""
import ast
import os
import sys
import typing
from datetime import date, datetime, timedelta, timezone

MAIN_PY = os.path.join(os.path.dirname(__file__), "main.py")
SOURCE = open(MAIN_PY).read()
TREE = ast.parse(SOURCE)

PASS = 0
FAIL = 0
RESULTS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(("PASS", name, detail))
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        RESULTS.append(("FAIL", name, detail))
        print(f"  ✗ {name} — {detail}")


def section(name):
    print(f"\n{'=' * 60}\n  {name}\n{'=' * 60}")


def _extract(name):
    """Return the exact current source text of the top-level function/assignment `name` in main.py."""
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SOURCE, node)
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.get_source_segment(SOURCE, node)
    raise AssertionError(f"{name!r} not found as a top-level def/assignment in main.py "
                          f"— was it renamed or removed? Update this test.")


class _StubLogger:
    def warning(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


NAMESPACE = {
    "Optional": typing.Optional,
    "datetime": datetime, "timedelta": timedelta, "timezone": timezone, "date": date,
    "logger": _StubLogger(),
    "T": lambda name: name,
    "bq_param": lambda name, typ, val: (name, typ, val),
}

for _name in ("SEGMENT_BUCKETS", "mergecoins_segment_reward", "_crossed_chapter_before_deadline",
              "build_mergecoins_payload"):
    exec(compile(_extract(_name), MAIN_PY, "exec"), NAMESPACE)

SEGMENT_BUCKETS = NAMESPACE["SEGMENT_BUCKETS"]
mergecoins_segment_reward = NAMESPACE["mergecoins_segment_reward"]
_crossed_chapter_before_deadline = NAMESPACE["_crossed_chapter_before_deadline"]
build_mergecoins_payload = NAMESPACE["build_mergecoins_payload"]


# ── 1. mergecoins_segment_reward ────────────────────────────────────────────

def test_segment_reward():
    section("1. mergecoins_segment_reward — chapter-band lookup")

    test("chapter 49 (just below the 50-135 range) -> None",
         mergecoins_segment_reward(49) is None)
    test("chapter 0 -> None", mergecoins_segment_reward(0) is None)
    test("negative chapter -> None", mergecoins_segment_reward(-5) is None)
    test("chapter 130 (just above the range — SEGMENT_BUCKETS' last band tops out at 129, the same "
         "boundary assign_segment() has always used) -> None",
         mergecoins_segment_reward(130) is None)
    test("chapter 500 (far above) -> None", mergecoins_segment_reward(500) is None)

    r50 = mergecoins_segment_reward(50)
    test("chapter 50 (lower boundary of first band) -> 50_to_65 / $10",
         r50 == {"segment_id": "50_to_65", "reward_amount": 10.0}, str(r50))

    r59 = mergecoins_segment_reward(59)
    test("chapter 59 (upper boundary of first band) -> still 50_to_65",
         r59 == {"segment_id": "50_to_65", "reward_amount": 10.0}, str(r59))

    r60 = mergecoins_segment_reward(60)
    test("chapter 60 (lower boundary of second band) -> 60_to_75 / $20, no stale-bump into the first band",
         r60 == {"segment_id": "60_to_75", "reward_amount": 20.0}, str(r60))

    r129 = mergecoins_segment_reward(129)
    test("chapter 129 (upper boundary of the whole range) -> 120_to_135 / $50",
         r129 == {"segment_id": "120_to_135", "reward_amount": 50.0}, str(r129))

    # Every band in SEGMENT_BUCKETS must be reachable and return floats, never ints/strings.
    for lo, hi, _old_target, seg_id, reward in SEGMENT_BUCKETS:
        mid = (lo + hi) // 2
        r = mergecoins_segment_reward(mid)
        test(f"band {seg_id} reachable at its midpoint (chapter {mid})",
             r is not None and r["segment_id"] == seg_id and r["reward_amount"] == float(reward),
             str(r))
        test(f"band {seg_id} reward_amount is a float, not the raw int from SEGMENT_BUCKETS",
             isinstance(r["reward_amount"], float))

    # No gaps or overlaps across the whole 50-129 range.
    gap_free = all(mergecoins_segment_reward(ch) is not None for ch in range(50, 130))
    test("every chapter from 50 to 129 inclusive resolves to a band (no gaps)", gap_free)


# ── 2. build_mergecoins_payload ──────────────────────────────────────────────

def test_build_mergecoins_payload():
    section("2. build_mergecoins_payload — dashboard payload for the two-marker UI")

    test("milestone=None -> None (no crash on a brand-new user with no milestone doc)",
         build_mergecoins_payload(None, 80, 74) is None)

    test("milestone without is_mergecoins -> None (original single-milestone offer, unaffected)",
         build_mergecoins_payload({"target_chapter": 80, "reward_amount": 5}, 80, 74) is None)

    test("is_mergecoins=True but no checkpoint_chapter -> None (defensive: never half-render the UI)",
         build_mergecoins_payload(
             {"is_mergecoins": True, "target_chapter": 89, "reward_amount": 5}, 80, 74
         ) is None)

    full_milestone = {
        "is_mergecoins": True, "target_chapter": 89, "reward_amount": 5.0,
        "checkpoint_chapter": 85, "checkpoint_reward_amount": 2.7,
    }

    below = build_mergecoins_payload(full_milestone, 80, 74)
    test("below checkpoint -> checkpoint_reached is False",
         below is not None and below["checkpoint_reached"] is False, str(below))
    test("below checkpoint -> all raw fields pass through unchanged",
         below == {
             "current_chapter": 80, "start_chapter": 74, "checkpoint_chapter": 85,
             "checkpoint_reward_amount": 2.7, "target_chapter": 89, "reward_amount": 5.0,
             "checkpoint_reached": False,
         }, str(below))

    at_boundary = build_mergecoins_payload(full_milestone, 85, 74)
    test("current_chapter == checkpoint_chapter exactly -> NOT reached (must strictly EXCEED, "
         "matching the backend's `max_chapter > checkpoint_chapter` payout gate)",
         at_boundary["checkpoint_reached"] is False, str(at_boundary))

    past = build_mergecoins_payload(full_milestone, 86, 74)
    test("current_chapter one past checkpoint_chapter -> reached",
         past["checkpoint_reached"] is True, str(past))

    none_current = build_mergecoins_payload(full_milestone, None, 74)
    test("current_chapter=None -> treated as 0, never crashes comparing None > int",
         none_current["current_chapter"] == 0 and none_current["checkpoint_reached"] is False,
         str(none_current))

    none_start = build_mergecoins_payload(full_milestone, 80, None)
    test("start_chapter=None -> treated as 0 rather than propagating None to the frontend",
         none_start["start_chapter"] == 0, str(none_start))


# ── 3. _crossed_chapter_before_deadline ──────────────────────────────────────

class _Row:
    def __init__(self, crossed_at):
        self.crossed_at = crossed_at


def test_crossed_chapter_before_deadline():
    section("3. _crossed_chapter_before_deadline — shared overdue crossing-time check")

    deadline = datetime(2026, 9, 1, tzinfo=timezone.utc)

    NAMESPACE["bq_query"] = lambda *a, **k: [_Row(datetime(2026, 8, 30, tzinfo=timezone.utc))]
    test("crossed well before the deadline -> True",
         _crossed_chapter_before_deadline("p1", 80, deadline) is True)

    NAMESPACE["bq_query"] = lambda *a, **k: [_Row(datetime(2026, 9, 1, tzinfo=timezone.utc))]
    test("crossed exactly AT the deadline -> True (<=, not <)",
         _crossed_chapter_before_deadline("p1", 80, deadline) is True)

    NAMESPACE["bq_query"] = lambda *a, **k: [_Row(datetime(2026, 9, 2, tzinfo=timezone.utc))]
    test("crossed after the deadline -> False",
         _crossed_chapter_before_deadline("p1", 80, deadline) is False)

    NAMESPACE["bq_query"] = lambda *a, **k: [_Row(None)]
    test("no crossing row found (MIN() over zero matching rows) -> False, not a crash",
         _crossed_chapter_before_deadline("p1", 80, deadline) is False)

    naive_crossed = datetime(2026, 8, 30)  # no tzinfo
    NAMESPACE["bq_query"] = lambda *a, **k: [_Row(naive_crossed)]
    test("naive (tz-less) crossed_at from BQ is treated as UTC, not left broken for comparison",
         _crossed_chapter_before_deadline("p1", 80, deadline) is True)

    def _boom(*a, **k):
        raise RuntimeError("BQ is down")
    NAMESPACE["bq_query"] = _boom
    test("BQ failure -> fails OPEN (pays the player) rather than silently denying a real reward",
         _crossed_chapter_before_deadline("p1", 80, deadline) is True)


# ── 4. Payout decision tree (plain-Python mirrors — see module docstring) ───

def decide_check_progress(max_chapter, target_chapter, checkpoint_chapter, is_expired_now):
    """Mirrors main.py check_progress()'s branch structure after the 2026-09-09 rewrite:
    max_chapter > target -> completion (regardless of expiry); else if expired, checkpoint if
    crossed, else plain expiry; else no-op (still pending)."""
    if max_chapter > target_chapter:
        return "completion"
    if is_expired_now:
        if checkpoint_chapter and max_chapter > checkpoint_chapter:
            return "checkpoint"
        return "expired"
    return "no_action"


def decide_verify_all_progress(max_chapter, target_chapter, checkpoint_chapter, is_overdue,
                                crossed_target_in_time=True, crossed_checkpoint_in_time=True):
    """Mirrors main.py verify_all_progress()'s per-user branch structure after the 2026-09-09
    rewrite: full target first (with the overdue rollup-lag crossing-time guard), then the
    checkpoint fallback for an overdue miss (with its own crossing-time guard), else no-op."""
    if max_chapter > target_chapter:
        if is_overdue and not crossed_target_in_time:
            return "expired"
        return "completion"
    if is_overdue:
        if checkpoint_chapter and max_chapter > checkpoint_chapter:
            if not crossed_checkpoint_in_time:
                return "expired"
            return "checkpoint"
        return "expired"
    return "no_action"


def test_payout_decision_tree():
    section("4. Two-threshold payout decision tree")

    # -- check_progress (live, on-demand endpoint) --
    test("check_progress: full target reached, offer not expired -> completion",
         decide_check_progress(90, 89, 85, False) == "completion")
    test("check_progress: full target reached even though ALSO expired -> still completion "
         "(completion is checked before expiry, by design)",
         decide_check_progress(90, 89, 85, True) == "completion")
    test("check_progress: checkpoint crossed, target missed, expired -> checkpoint",
         decide_check_progress(86, 89, 85, True) == "checkpoint")
    test("check_progress: checkpoint crossed, target missed, NOT expired -> no_action "
         "(still time on the clock, nothing to pay or expire yet)",
         decide_check_progress(86, 89, 85, False) == "no_action")
    test("check_progress: neither threshold crossed, expired -> expired",
         decide_check_progress(80, 89, 85, True) == "expired")
    test("check_progress: neither threshold crossed, not expired -> no_action",
         decide_check_progress(80, 89, 85, False) == "no_action")
    test("check_progress: original single-milestone offer (checkpoint_chapter=None), expired, "
         "target missed -> expired, never crashes on `None and ...`",
         decide_check_progress(80, 89, None, True) == "expired")
    test("check_progress: current_chapter exactly ON the checkpoint (not past it), expired -> "
         "expired, not checkpoint (must strictly exceed)",
         decide_check_progress(85, 89, 85, True) == "expired")

    # -- verify_all_progress (4h batch scheduler) --
    test("verify_all_progress: full target reached, not overdue -> completion",
         decide_verify_all_progress(90, 89, 85, is_overdue=False) == "completion")
    test("verify_all_progress: full target reached, overdue, crossed before deadline -> "
         "completion (rescued from rollup lag)",
         decide_verify_all_progress(90, 89, 85, is_overdue=True,
                                     crossed_target_in_time=True) == "completion")
    test("verify_all_progress: full target reached, overdue, but crossed AFTER the deadline -> "
         "expired, not paid",
         decide_verify_all_progress(90, 89, 85, is_overdue=True,
                                     crossed_target_in_time=False) == "expired")
    test("verify_all_progress: checkpoint crossed, target missed, overdue, crossed before "
         "deadline -> checkpoint",
         decide_verify_all_progress(86, 89, 85, is_overdue=True,
                                     crossed_checkpoint_in_time=True) == "checkpoint")
    test("verify_all_progress: checkpoint crossed, target missed, overdue, crossed AFTER the "
         "deadline -> expired, not paid",
         decide_verify_all_progress(86, 89, 85, is_overdue=True,
                                     crossed_checkpoint_in_time=False) == "expired")
    test("verify_all_progress: neither threshold crossed, overdue -> expired",
         decide_verify_all_progress(80, 89, 85, is_overdue=True) == "expired")
    test("verify_all_progress: neither threshold crossed, not overdue -> no_action (stays active)",
         decide_verify_all_progress(80, 89, 85, is_overdue=False) == "no_action")
    test("verify_all_progress: original single-milestone offer (checkpoint_chapter=None), "
         "overdue, target missed -> expired, never crashes on `None and ...`",
         decide_verify_all_progress(80, 89, None, is_overdue=True) == "expired")


if __name__ == "__main__":
    test_segment_reward()
    test_build_mergecoins_payload()
    test_crossed_chapter_before_deadline()
    test_payout_decision_tree()

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    sys.exit(1 if FAIL else 0)
