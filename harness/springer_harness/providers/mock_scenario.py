"""One canned run from plan to complete, used by the test suite and by the TUI build
at step 4, so a person can watch every screen fill with no tokens spent."""

from ..scheduler.plan import CannedPlanner, GateDraft, PlanBatch, UnitDraft
from .mock import Attempt, pr_result


MOCK_MOCKUP = """<!doctype html><meta charset=utf-8><title>Mock direction</title>
<body style="background:#16171A;color:#E4DED2;font:16px/1.5 Menlo,monospace;padding:3rem">
<h1 style="font-size:1.1rem">This is a mock, not a design</h1>
<p style="color:#B7AE9E">The mock provider wrote this page so the review flow can be tried. A real design
agent writes its directions here. Delete docs/design when you are done with the mock.</p>
"""


def demo_script():
    return {
        "spgr-agent-design": [Attempt(writes={"docs/design/index.html": MOCK_MOCKUP})],
        "routine": [Attempt(ticks=2, result=pr_result(1, touched=("apps/web/page.tsx",)))],
        "notable": [Attempt(result=pr_result(2, touched=("packages/ui/b.tsx",), raised_level="L1"))],
        "risky": [Attempt(ticks=2, result=pr_result(3, touched=("packages/auth/session.ts",),
                                                    findings=[{"vertical": "spgr-agent-auth", "rule": "session-expiry",
                                                               "detail": "Sessions must expire."}]))],
        "stacked": [Attempt(result=pr_result(4, touched=("apps/web/login/p.tsx",)))],
    }


def demo_batches():
    return [
        PlanBatch("requirements", "The brief is confirmed. Write the requirements.",
                  [UnitDraft("prd", "spgr-agent-product-manager", "a PRD and a backlog")]),
        PlanBatch("direction", "Requirements are in. Propose directions and options.",
                  [UnitDraft("design", "spgr-agent-design", "three directions", declared_paths=("docs/design/",)),
                   UnitDraft("arch", "spgr-agent-architect", "architecture options", declared_paths=("docs/adr/",),
                             model_tier="opus")]),
        PlanBatch("design-system", "The direction is picked. Build the design system.",
                  [UnitDraft("system", "spgr-agent-design", "tokens as code", declared_paths=("packages/ui/tokens/",))],
                  [GateDraft("direction-review", "Pick an architecture option and a design direction.", holds=("system",),
                             level="L3",
                             options=({"option": "accept", "consequence": "Structure freezes and tokens begin.",
                                       "recommended_because": "It fits the core flows."},),
                             decisions=({"decision_id": "D1", "kind": "design-direction-selection",
                                         "prompt": "Which direction?"},))]),
        PlanBatch("skeleton", "Walk the primary flow end to end.",
                  [UnitDraft("skeleton", "routine", "the primary flow on staging", declared_paths=("apps/web/",))]),
        PlanBatch("development", "Build features. Unrelated work runs beside a held merge.",
                  [UnitDraft("button", "notable", "the button", declared_paths=("packages/ui/b.tsx",)),
                   UnitDraft("auth", "risky", "the session", declared_paths=("packages/auth/",)),
                   UnitDraft("login", "stacked", "the login page", declared_paths=("apps/web/login/",),
                             depends_on=("auth",))]),
    ]


def demo_planner_factory():
    """One planner per run. A restart keeps the planner, as a real Plan reads disk."""
    planners = {}

    def factory(slug, run_id, kind):
        key = (slug, run_id)
        if key not in planners:
            planners[key] = CannedPlanner(demo_batches() if kind == "build" else [
                PlanBatch("discovery", "Research the idea.",
                          [UnitDraft("research", "spgr-agent-discovery", "proposed brief sections")])])
        return planners[key]

    return factory
