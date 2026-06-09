"""Phase II — synonym-aware cross-artifact consistency (FR-XA-01).

Proves that the synonym table prevents false-positive contradictions on
equivalent expressions, while still catching genuine disagreements.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import build_context, create_app  # noqa: E402
from tests.conftest import MockAnalyzer              # noqa: E402

ADMIN = {"X-QUILL-Role": "admin", "X-QUILL-Tenant": "default"}
ENG = {"X-QUILL-Role": "engineer", "X-QUILL-Tenant": "default"}
VIEWER = {"X-QUILL-Role": "viewer", "X-QUILL-Tenant": "default"}


def _hdr(tenant: str, role: str = "engineer"):
    return {"X-QUILL-Role": role, "X-QUILL-Tenant": tenant}


@pytest.fixture
def client():
    ctx = build_context(analyzer=MockAnalyzer())
    return TestClient(create_app(ctx))


def _upload_text(client, name: str, body: str, tenant: str = "default") -> str:
    """Upload an in-memory artifact built from `body` (lets us shape exactly
    the AC-2 narrative we want for the test)."""
    import io
    r = client.post("/artifacts",
                    files={"file": (name, io.BytesIO(body.encode()), "text/markdown")},
                    headers=_hdr(tenant))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_equivalent_phrases_do_not_false_positive_a_contradiction(client):
    """`quarterly` and `every 90 days` are the same thing; no `inconsistent`
    finding should appear after synonym normalization."""
    # Package with two artifacts using equivalent-but-different surface forms
    pkg = client.post("/packages", json={"name": "Equivalents"}, headers=ENG).json()
    a1 = _upload_text(
        client, "ssp.md",
        "# SSP\n## AC-2 Account Management\n\nAccount types: privileged, standard. "
        "The Information System Security Officer reviews accounts quarterly.\n"
    )
    a2 = _upload_text(
        client, "arch.md",
        "# Architecture\n## AC-2 Account Management\n\nAccount types include "
        "privileged and standard. The ISSO reviews accounts every 90 days.\n"
    )
    client.post(f"/packages/{pkg['id']}/artifacts/{a1}", headers=ENG)
    client.post(f"/packages/{pkg['id']}/artifacts/{a2}", headers=ENG)

    run = client.post(f"/packages/{pkg['id']}/runs", headers=ENG).json()
    fs = client.get(f"/runs/{run['id']}/findings", headers=VIEWER).json()
    inconsistent_ac2 = [f for f in fs
                        if f["type"] == "inconsistent" and f["control_id"] == "AC-2"]
    assert not inconsistent_ac2, (
        "expected no AC-2 inconsistency after synonym normalization "
        f"(quarterly ≡ every 90 days, ISSO ≡ Information System Security Officer); "
        f"got {len(inconsistent_ac2)}"
    )


def test_genuine_contradiction_still_caught(client):
    """`quarterly` vs `annually` is a real contradiction — must still fire."""
    pkg = client.post("/packages", json={"name": "Real Conflict"}, headers=ENG).json()
    a1 = _upload_text(
        client, "ssp.md",
        "# SSP\n## AC-2 Account Management\n\nThe ISSO reviews accounts quarterly.\n"
    )
    a2 = _upload_text(
        client, "arch.md",
        "# Architecture\n## AC-2 Account Management\n\nThe ISSO reviews accounts annually.\n"
    )
    client.post(f"/packages/{pkg['id']}/artifacts/{a1}", headers=ENG)
    client.post(f"/packages/{pkg['id']}/artifacts/{a2}", headers=ENG)

    run = client.post(f"/packages/{pkg['id']}/runs", headers=ENG).json()
    fs = client.get(f"/runs/{run['id']}/findings", headers=VIEWER).json()
    inconsistent_ac2 = [f for f in fs
                        if f["type"] == "inconsistent" and f["control_id"] == "AC-2"]
    assert inconsistent_ac2, (
        f"expected an AC-2 contradiction (quarterly vs annually); got types="
        f"{[f['type'] for f in fs]}"
    )


def test_role_synonyms_unify_across_artifacts(client):
    """`ISSO` vs `Information System Security Officer` are the same role. The
    synonym table proves this via `find_canonical_phrases`."""
    # Quick path: hit the synonym engine directly through the in-process Synonyms
    from backend.services.analysis.synonyms import load_synonyms
    s = load_synonyms(ROOT / "config" / "synonyms.yaml")
    text_a = "The ISSO reviews accounts quarterly."
    text_b = "The Information System Security Officer reviews accounts quarterly."
    assert s.find_canonical_phrases(text_a) == s.find_canonical_phrases(text_b)
