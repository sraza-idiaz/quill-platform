"""Phase I quality gates locked as a regression test (docs/04 §7)."""
import pytest

from eval.harness.run_eval import evaluate


@pytest.mark.asyncio
async def test_phase1_gates_on_synthetic_corpus():
    s = await evaluate(analyzer_name="mock", write=False)
    m = s["metrics"]
    g = s["gates"]
    # Hard Phase I gates
    assert m["deficiency_detection_recall"] >= 0.80, m
    assert m["false_positive_rate"]         <= 0.20, m
    assert m["traceability"]                == 1.00, m
    assert g["calibration_demonstrated"], m["calibration"]
    # Coverage + inconsistency must work
    assert m["coverage_recall"]      == 1.00, m
    assert m["inconsistency_recall"] >= 0.80, m
    assert s["all_gates_passed"]
