"""Generate the QUILL "big demo" — six professional, multi-page RMF documents
as PDFs, wired with a dense, *deterministic* matrix of cross-document
contradictions so the Visual Grounding canvas shows a rich web of threads.

Why a generator (not hand-written PDFs):
  * The contradictions must be exact — each control's review/retention/test
    cadence is stated with a specific frequency word per document, and the
    cross-document consistency check (Tier 0) fires precisely on those
    mismatches. A generator guarantees the matrix; prose written by hand
    drifts.
  * Reproducible: re-run to regenerate identical PDFs.

Design rules that keep the demo clean:
  * Every conflicting control section contains EXACTLY ONE frequency word
    (the matrix value). All surrounding boilerplate is frequency-free, so no
    accidental tokens pollute the comparison.
  * Role names are identical everywhere ("ISSO") so they never create a
    spurious edge.
  * 3-way controls use three DIFFERENT frequencies, so a wire never points at
    a document that actually agrees with the primary.

Run:  python demo/big-demo/generate.py
Output: demo/big-demo/pdfs/*.pdf  (+ MANIFEST.md)
"""

from __future__ import annotations

import os
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent / "pdfs"

# ── Documents ─────────────────────────────────────────────────────── #
DOCS = {
    "ssp": ("01_System_Security_Plan.pdf",        "System Security Plan",
            "Atlas Logistics Risk Platform (ALRP)",         "Maria Chen, ISSO"),
    "pol": ("02_Information_Security_Policy.pdf",  "Information Security Policy",
            "Enterprise Security Governance",                "Office of the CISO"),
    "run": ("03_Operations_Maintenance_Runbook.pdf", "Operations & Maintenance Runbook",
            "ALRP Production Environment",                   "Platform Operations"),
    "irp": ("04_Incident_Response_Plan.pdf",      "Incident Response Plan",
            "ALRP Security Operations",                      "SOC & IR Team"),
    "cmp": ("05_Configuration_Management_Plan.pdf", "Configuration Management Plan",
            "ALRP Production Baseline",                      "Change Advisory Board"),
    "cms": ("06_Continuous_Monitoring_Strategy.pdf", "Continuous Monitoring Strategy",
            "ALRP Authorization Boundary",                   "ISSO & Assessment Team"),
}

# ── Control catalogue (id -> (name, cadence-sentence template)) ──────── #
# {f} is the frequency slot — the single conflict-bearing word.
CONTROLS = {
    "AC-2":  ("Account Management",
              "Privileged, standard, and service accounts are reviewed {f} by the ISSO to confirm continued need and least-privilege alignment."),
    "AC-6":  ("Least Privilege",
              "Least-privilege role assignments are recertified {f} by the ISSO together with the system owner."),
    "AC-17": ("Remote Access",
              "Remote-access entitlements and VPN allow-lists are reviewed {f} by the network security team."),
    "AT-2":  ("Literacy Training and Awareness",
              "Role-based security awareness training is delivered to all personnel {f}, with completion tracked in the learning management system."),
    "AU-6":  ("Audit Record Review",
              "Audit logs are reviewed for anomalous and unauthorized activity {f} by the on-duty SOC analyst."),
    "AU-11": ("Audit Record Retention",
              "Audit-retention configuration and storage integrity are validated {f} against the documented policy."),
    "CA-7":  ("Continuous Monitoring",
              "The continuous-monitoring control sample is assessed {f} and the results reported to the Authorizing Official."),
    "CM-3":  ("Configuration Change Control",
              "Proposed configuration changes are reviewed and dispositioned by the Change Advisory Board {f}."),
    "CM-8":  ("System Component Inventory",
              "The authoritative system inventory is reconciled {f} against the assets discovered on the network."),
    "CP-9":  ("System Backup",
              "Backup restoration is tested {f} into an isolated recovery environment to confirm recoverability."),
    "IR-3":  ("Incident Response Testing",
              "Incident-response capabilities are exercised through tabletop and functional tests {f}."),
    "IR-6":  ("Incident Reporting",
              "Confirmed incidents are reported to the designated authorities {f} and recorded in the incident-tracking system."),
    "RA-5":  ("Vulnerability Monitoring and Scanning",
              "Authenticated vulnerability scans are executed {f} across every asset inside the authorization boundary."),
    "SI-4":  ("System Monitoring",
              "Security-monitoring detections and dashboards are reviewed {f} by the Security Operations Center."),
    "PM-14": ("Testing, Training, and Monitoring",
              "The enterprise security testing and training program is evaluated for effectiveness {f}."),
}

# ── Contradiction matrix: control -> { doc: frequency } ──────────────── #
# 3-way entries use three distinct frequencies (no wire points at an agreer).
MATRIX = {
    "AC-2":  {"ssp": "monthly",   "pol": "quarterly", "run": "weekly"},
    "AT-2":  {"ssp": "annually",  "pol": "quarterly", "irp": "monthly"},
    "RA-5":  {"ssp": "weekly",    "run": "monthly",   "cmp": "quarterly"},
    "SI-4":  {"cms": "daily",     "run": "weekly",    "pol": "monthly"},
    "AC-6":  {"pol": "quarterly", "ssp": "annually"},
    "AC-17": {"pol": "monthly",   "run": "quarterly"},
    "AU-11": {"ssp": "annually",  "run": "quarterly"},
    "CM-3":  {"cmp": "weekly",    "run": "monthly"},
    "CM-8":  {"cmp": "monthly",   "ssp": "quarterly"},
    "CP-9":  {"run": "monthly",   "cmp": "quarterly"},
    "IR-3":  {"irp": "annually",  "cms": "quarterly"},
    "CA-7":  {"ssp": "monthly",   "cms": "quarterly"},
    "IR-6":  {"irp": "daily",     "ssp": "weekly"},
    "AU-6":  {"run": "daily",     "pol": "weekly"},
    "PM-14": {"pol": "annually",  "cms": "biannually"},
}

# Purpose + mechanism sentences (frequency-free) to flesh out each control.
PURPOSE = {
    "AC-2":  "Account management governs the full lifecycle of identities that can access the system, from provisioning through disablement.",
    "AC-6":  "The principle of least privilege constrains each role to the minimum set of permissions required to perform its function.",
    "AC-17": "Remote access extends the authorization boundary to authenticated users connecting from outside the corporate network.",
    "AT-2":  "Security literacy ensures that every individual with access understands their responsibilities and the threats relevant to their role.",
    "AU-6":  "Audit review converts raw event data into actionable detections by surfacing anomalous and unauthorized behavior.",
    "AU-11": "Audit retention preserves the evidentiary record required for after-the-fact investigation and accountability.",
    "CA-7":  "Continuous monitoring maintains ongoing awareness of the security posture in support of risk-based authorization decisions.",
    "CM-3":  "Configuration change control prevents unauthorized or unreviewed modifications from degrading the security baseline.",
    "CM-8":  "An accurate component inventory is the foundation for vulnerability management, license control, and incident scoping.",
    "CP-9":  "System backup protects the availability of data and configuration against corruption, ransomware, and hardware loss.",
    "IR-3":  "Exercising the response plan validates that people, process, and tooling perform under realistic incident conditions.",
    "IR-6":  "Timely incident reporting satisfies regulatory obligations and enables coordinated response across the enterprise.",
    "RA-5":  "Vulnerability scanning identifies exploitable weaknesses before an adversary can leverage them.",
    "SI-4":  "System monitoring provides the detective controls that surface intrusions and policy violations in near-real time.",
    "PM-14": "A managed testing and training program measures and improves the effectiveness of the security capability over time.",
}
MECHANISM = {
    "AC-2":  "Provisioning is initiated from an approved request and enforced through the enterprise identity provider; the ISSO is accountable for the control.",
    "AC-6":  "Role definitions are maintained in the identity provider and mapped to documented job functions.",
    "AC-17": "All remote sessions traverse the corporate VPN with enforced multi-factor authentication and are logged centrally.",
    "AT-2":  "Curricula are tailored to general users, privileged users, and incident responders, and completion is a condition of continued access.",
    "AU-6":  "Events are aggregated into the SIEM and correlated against detection content aligned to the MITRE ATT&CK matrix.",
    "AU-11": "Records are written to an immutable, access-controlled store with integrity protection enabled.",
    "CA-7":  "Findings are tracked to closure in the plan of action and milestones and summarized for the Authorizing Official.",
    "CM-3":  "Each change carries a documented justification, rollback plan, and security impact analysis before approval.",
    "CM-8":  "Discovery data is collected automatically and reconciled against the authoritative inventory of record.",
    "CP-9":  "Backups are encrypted, replicated across regions, and protected against deletion before their retention expires.",
    "IR-3":  "Exercises cover detection, containment, eradication, and recovery, and lessons learned feed back into the plan.",
    "IR-6":  "Reports follow the severity-based escalation matrix and are delivered through the designated reporting channel.",
    "RA-5":  "Scan results are risk-ranked and remediated within timelines keyed to severity, with exceptions formally accepted.",
    "SI-4":  "Detections forward to an alerting pipeline that pages the on-call analyst, who triages within the documented window.",
    "PM-14": "Program metrics are reviewed by leadership and drive investment in tooling, staffing, and curriculum.",
}

# Frequency-free narrative sections per document, for length + professionalism.
INTRO_SECTIONS = {
    "ssp": [
        ("1. System Identification",
         "The Atlas Logistics Risk Platform (ALRP) is a Moderate-impact information system operating within an approved AWS GovCloud environment. It ingests supplier financial filings, delivery performance data, and open-source intelligence to produce a composite supplier-risk score in support of Defense Logistics Agency procurement decisions. The system processes Controlled Unclassified Information and does not process classified information."),
        ("2. Authorization Boundary",
         "The authorization boundary comprises the ALRP web application, the supplier-risk scoring engine, the managed relational database, the evidence object store, and the administrative interface. Platform services inherited from the cloud service provider are documented as inherited controls and are out of scope for re-assessment in this plan."),
    ],
    "pol": [
        ("1. Purpose and Authority",
         "This Information Security Policy establishes the enterprise requirements that govern the protection of information systems and the data they process. It is issued under the authority of the Chief Information Security Officer and applies to all personnel, contractors, and systems operating within the enterprise."),
        ("2. Scope",
         "The policy applies to all information systems regardless of hosting model, and to all individuals granted access to those systems. Where a system-specific document and this policy both address a requirement, the more stringent provision governs."),
    ],
    "run": [
        ("1. Operational Overview",
         "This runbook documents the day-to-day operational procedures that implement and sustain the security controls of the ALRP production environment. It is maintained by Platform Operations and is the authoritative reference for routine maintenance, monitoring, and recovery activities."),
        ("2. Environment",
         "Production runs as containerized services behind a managed load balancer, with data persisted to an encrypted managed database and an object store. Infrastructure is defined as code and deployed through the controlled pipeline described in the Configuration Management Plan."),
    ],
    "irp": [
        ("1. Plan Purpose",
         "The Incident Response Plan defines how the organization prepares for, detects, analyzes, contains, eradicates, and recovers from security incidents affecting the ALRP. It establishes roles, escalation paths, and reporting obligations for the incident-response lifecycle."),
        ("2. Incident Categories",
         "Incidents are categorized by severity according to confidentiality, integrity, and availability impact. Severity determines the escalation path, the notification timeline, and the level of management engagement required."),
    ],
    "cmp": [
        ("1. Plan Purpose",
         "The Configuration Management Plan governs how the secure baseline of the ALRP is established, documented, and maintained. It defines the change-control process, the inventory of record, and the mechanisms that detect and reconcile drift."),
        ("2. Baseline Definition",
         "The production baseline is expressed as version-pinned infrastructure-as-code together with hardened component images. The baseline is the authoritative definition of the approved configuration state."),
    ],
    "cms": [
        ("1. Strategy Purpose",
         "The Continuous Monitoring Strategy describes how the organization maintains ongoing awareness of the security posture of the ALRP in support of the Authorizing Official's risk-based decisions. It defines the monitored controls, the assessment cadence, and the reporting flow."),
        ("2. Monitoring Scope",
         "Monitoring spans technical detections, control-effectiveness sampling, vulnerability data, and configuration drift. Results are consolidated into a posture report delivered to the Authorizing Official and the system owner."),
    ],
}

# Extra single-document (non-conflicting) controls per doc, for page length.
EXTRA = {
    "ssp": [("PL-2", "System Security Plan", "This plan documents the security controls selected for the system and the rationale for their selection. It is reviewed and updated as the system or its environment changes."),
            ("CA-2", "Control Assessments", "Selected controls are assessed by an independent assessor, and the resulting findings are tracked to closure in the plan of action and milestones.")],
    "pol": [("PS-3", "Personnel Screening", "Individuals are screened commensurate with the sensitivity of the information they will access prior to authorization, and re-screened in accordance with applicable requirements."),
            ("SA-4", "Acquisition Process", "Security requirements are incorporated into acquisition contracts so that delivered components meet the organization's protection needs.")],
    "run": [("MA-2", "Controlled Maintenance", "Maintenance activities are scheduled, approved, and logged, and maintenance personnel are supervised in accordance with their authorization."),
            ("SC-7", "Boundary Protection", "Traffic entering the boundary passes through a web application firewall and a load balancer that terminates transport encryption; egress is restricted to documented service endpoints.")],
    "irp": [("IR-4", "Incident Handling", "The organization handles incidents through a coordinated process spanning preparation, detection and analysis, containment, eradication, recovery, and post-incident activity."),
            ("IR-8", "Incident Response Plan Maintenance", "The plan is maintained as a living document; revisions are distributed to all response stakeholders and incorporated into subsequent exercises.")],
    "cmp": [("CM-2", "Baseline Configuration", "A current, documented baseline configuration is maintained as the authoritative reference for the approved state of the system."),
            ("CM-6", "Configuration Settings", "Mandatory configuration settings are established from hardening benchmarks and enforced through automated configuration management.")],
    "cms": [("CA-5", "Plan of Action and Milestones", "Identified weaknesses are documented with planned remediation and milestones, and progress is tracked to closure."),
            ("CA-6", "Authorization", "The Authorizing Official renders a risk-based authorization decision informed by the continuous-monitoring posture report.")],
}


# ── PDF rendering ─────────────────────────────────────────────────── #
def _ascii(s: str) -> str:
    return (s.replace("—", "--").replace("–", "-")
             .replace("‘", "'").replace("’", "'")
             .replace("“", '"').replace("”", '"')
             .encode("latin-1", "replace").decode("latin-1"))


class DocPDF(FPDF):
    short_title = ""

    def header(self):
        self.set_font("Helvetica", "", 8)
        self.set_text_color(140, 140, 140)
        half = (self.w - self.l_margin - self.r_margin) / 2
        self.cell(half, 6, _ascii(self.short_title), align="L")
        self.cell(half, 6, "CUI", align="R", ln=True)
        self.set_draw_color(210, 210, 210)
        self.line(self.l_margin, 18, self.w - self.r_margin, 18)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"CUI  --  Page {self.page_no()}", align="C")


def _build_doc(doc_key: str) -> None:
    filename, title, subtitle, author = DOCS[doc_key]
    pdf = DocPDF()
    pdf.short_title = f"{title} -- ALRP"
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(22, 16, 22)
    pdf.add_page()

    # Cover block
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(30, 30, 30)
    pdf.multi_cell(0, 10, _ascii(title))
    pdf.ln(1)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 7, _ascii(subtitle))
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(110, 110, 110)
    for line in (f"Prepared by: {author}",
                 "Baseline: NIST SP 800-53 Rev. 5 -- Moderate",
                 "Classification: Controlled Unclassified Information (CUI)",
                 "Status: Draft for pre-adjudication review"):
        pdf.cell(0, 6, _ascii(line), ln=True)
    pdf.ln(8)

    def section(t):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(30, 30, 30)
        pdf.multi_cell(0, 8, _ascii(t))
        pdf.ln(1)

    def body(t):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 10.5)
        pdf.set_text_color(45, 45, 45)
        pdf.multi_cell(0, 5.6, _ascii(t))
        pdf.ln(2.5)

    def control(cid, name, paras):
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 11.5)
        pdf.set_text_color(30, 30, 30)
        pdf.multi_cell(0, 7, _ascii(f"{cid}  {name}"))
        for p in paras:
            body(p)

    # Intro narrative sections
    for t, txt in INTRO_SECTIONS[doc_key]:
        section(t)
        body(txt)

    # Control Implementations
    section("3. Control Implementations")
    # Which controls does THIS doc carry from the matrix?
    doc_controls = [(cid, freqs[doc_key]) for cid, freqs in MATRIX.items() if doc_key in freqs]
    # Stable, family-ish order by control id.
    doc_controls.sort(key=lambda x: x[0])
    for cid, freq in doc_controls:
        name, cadence = CONTROLS[cid]
        paras = [PURPOSE[cid], cadence.format(f=freq), MECHANISM[cid]]
        control(cid, name, paras)

    # Extra single-doc controls for length/realism
    section("4. Supporting Controls")
    for cid, name, txt in EXTRA[doc_key]:
        control(cid, name, [txt])

    OUT.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT / filename))
    return filename, len(doc_controls)


def _write_manifest(stats):
    # Build expected-edge list for verification.
    lines = ["# Big-demo contradiction manifest", "",
             "Auto-generated by generate.py. Each row is a control whose review/",
             "retention/test cadence is stated *differently* across documents — Tier 0",
             "cross-document consistency flags each one, and the Visual Grounding view",
             "draws a thread between the conflicting passages.", "",
             "## Documents", ""]
    for k, (fn, title, sub, author) in DOCS.items():
        n = dict(stats).get(fn, 0)
        lines.append(f"- **{fn}** — {title} ({n} matrixed controls)")
    lines += ["", "## Contradiction matrix", "",
              "| Control | " + " | ".join(DOCS.keys()) + " |",
              "|" + "---|" * (len(DOCS) + 1)]
    edge_count = 0
    for cid, freqs in MATRIX.items():
        row = [cid]
        for k in DOCS:
            row.append(freqs.get(k, "·"))
        lines.append("| " + " | ".join(row) + " |")
        distinct = set(freqs.values())
        # wires drawn = (number of docs) - 1 from the primary to each other
        if len(distinct) > 1:
            edge_count += max(0, len(freqs) - 1)
    lines += ["", f"**Conflicting controls:** {sum(1 for f in MATRIX.values() if len(set(f.values()))>1)}",
              f"**Approx. threads drawn:** {edge_count}", "",
              "## How to run the demo", "",
              "1. `rm -rf /tmp/big-demo && mkdir -p /tmp/big-demo`",
              "2. In the UI: Packages -> + New package -> name it 'Big Demo'.",
              "3. Open it -> Watch folder -> `/tmp/big-demo`.",
              "4. `cp demo/big-demo/pdfs/*.pdf /tmp/big-demo/` (drop all six at once).",
              "5. Wait for analysis (Tier 0 is near-instant; Tier 2 adds minutes).",
              "6. Open the package -> click the file rows to confirm findings, then",
              "   open **Grounded view** to see the full web of contradiction threads."]
    (Path(__file__).resolve().parent / "MANIFEST.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    stats = []
    for key in DOCS:
        fn, n = _build_doc(key)
        stats.append((fn, n))
        print(f"wrote {fn}  ({n} matrixed controls)")
    _write_manifest(stats)
    print(f"\nManifest written. PDFs in {OUT}")
