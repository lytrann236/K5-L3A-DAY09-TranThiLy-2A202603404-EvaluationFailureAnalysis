"""Regression test from docs/trace_case.md: seeded_regression C-002@11.

First wrong step: event 3 `model_override` {"delay_days": 5} -- the ticket's "5 days" overrides the
DB fact (delay_days = 2). FM-03. The step-level grader DbFactKept and the ledger grader
RefundAmountCorrect must catch it on the buggy variant and stay green on `fixed`.
"""
import pytest

pytestmark = pytest.mark.student


def _grade(shape: str):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9 import graders
    from lab9.trace_case import investigate

    case = investigate(shape, "C-002", 11)
    ctx = EvaluatorContext(name="trace_case", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    return case["trial"], graders.DbFactKept().evaluate(ctx).value, graders.RefundAmountCorrect().evaluate(ctx).value


def test_lab9_trace_case_c002_override_is_caught():
    trial, db_fact_kept, amount_ok = _grade("seeded_regression")
    kinds = [e["kind"] for e in trial["events"]]
    assert "model_override" in kinds                     # the first wrong step is present
    assert kinds.index("model_override") < kinds.index("quote")   # ...and happens before the quote
    assert db_fact_kept is False and amount_ok is False


def test_lab9_trace_case_c002_fixed_stays_green():
    trial, db_fact_kept, amount_ok = _grade("fixed")
    assert all(e["kind"] != "model_override" for e in trial["events"])
    assert db_fact_kept is True and amount_ok is True
