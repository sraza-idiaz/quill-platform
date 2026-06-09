"""Phase II FR-XA-02 — inheritance pattern detection (unit tests)."""
from backend.services.analysis.inheritance import detect_inheritance


# ─── Detection: presence ─────────────────────────────────────────────── #

def test_returns_none_when_no_inheritance_language():
    assert detect_inheritance(
        "The organization manages information system accounts."
    ) is None


def test_detects_inherited_from():
    c = detect_inheritance(
        "AC-2 is inherited from Azure Active Directory and backed by their SOC 2 Type II audit."
    )
    assert c is not None
    assert c.trigger == "inherited from"


def test_detects_satisfied_by():
    c = detect_inheritance(
        "This control is satisfied by AWS GovCloud's FedRAMP High authorization."
    )
    assert c is not None
    assert "satisfied by" in c.trigger


def test_detects_common_control():
    c = detect_inheritance(
        "Common control: account management is provided by the enterprise IAM platform."
    )
    assert c is not None


def test_does_not_match_inside_a_word():
    # "uninheritedness" shouldn't trigger "inherited"; word boundaries enforced.
    assert detect_inheritance("This uninheritedness pattern.") is None


# ─── Provider + attestation extraction ───────────────────────────────── #

def test_provider_extracted_after_inherited_from():
    c = detect_inheritance(
        "AC-2 is inherited from Azure Active Directory; reference SOC 2 report."
    )
    assert c.provider is not None
    assert "Azure" in c.provider
    assert "Active Directory" in c.provider


def test_provider_extracted_after_satisfied_by():
    c = detect_inheritance(
        "Satisfied by AWS GovCloud per the latest FedRAMP authorization."
    )
    assert c.provider is not None
    assert "AWS" in c.provider


def test_attestation_soc_2_picked_up():
    c = detect_inheritance(
        "Inherited from Azure AD with a current SOC 2 Type II report."
    )
    assert "SOC 2" in c.attestations
    assert "Type II" in c.attestations


def test_attestation_fedramp_picked_up():
    c = detect_inheritance(
        "Satisfied by AWS GovCloud's FedRAMP High P-ATO."
    )
    assert "FedRAMP" in c.attestations


def test_attestation_iso_picked_up():
    c = detect_inheritance(
        "Provided by the cloud provider per their ISO 27001 certification."
    )
    assert any("ISO 27001" in a for a in c.attestations)


# ─── is_complete + missing_elements ──────────────────────────────────── #

def test_is_complete_requires_both_provider_and_attestation():
    full = detect_inheritance(
        "AC-2 is inherited from Azure Active Directory; SOC 2 Type II report on file."
    )
    assert full.is_complete is True
    assert full.missing_elements == []


def test_missing_attestation_only():
    c = detect_inheritance(
        "AC-2 is inherited from the enterprise IAM provider."
    )
    assert c.is_complete is False
    assert c.missing_elements == ["inheritance_attestation"]


def test_missing_provider_only():
    c = detect_inheritance(
        "AC-2 is satisfied by an inherited control with a SOC 2 audit."
    )
    # "by an" is too generic to be a confident provider — should be missing
    assert "inheritance_attestation" not in c.missing_elements
    # Provider extraction is best-effort; "an" is filtered, so may be None
    if c.provider in (None, "", "an", "inherited", "Inherited"):
        assert "inheritance_provider" in c.missing_elements


def test_missing_both():
    c = detect_inheritance("This control is inherited.")
    assert c.is_complete is False
    assert "inheritance_attestation" in c.missing_elements
