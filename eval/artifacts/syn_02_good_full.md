# SSP Excerpt — Strong Implementation

## AC-2 Account Management

The organization manages the following account types: privileged administrator
accounts, standard user accounts, and service accounts. The Information System
Security Officer (ISSO) role is responsible for account provisioning and
de-provisioning. Accounts are reviewed quarterly for compliance, and an automated
identity-governance tool enforces least-privilege policy and disables dormant
accounts after 35 days.

## AU-2 Event Logging

The system logs the following event types: authentication successes and failures,
privilege escalations, and configuration changes. Logs are retained for 365 days.
A SIEM review mechanism alerts the security team on anomalies.

## IA-2 Identification and Authentication (Organizational Users)

All organizational users are issued unique credentials. The authenticator types
include PIV smart cards and password+OTP. MFA scope covers all privileged and
remote access sessions.

## CM-2 Baseline Configuration

A current baseline configuration is maintained for each system component. The
baseline reference is the central CMDB; change control routes deviations through
the CCB.

## SC-7 Boundary Protection

External system boundaries are monitored and controlled via perimeter firewalls
and an IDS sensor. The boundary components include the edge firewall, DMZ proxy,
and a monitoring mechanism (SIEM) that ingests boundary telemetry.

## SI-4 System Monitoring

The system is monitored to detect attacks and indicators of potential attacks.
Monitoring objectives include unauthorized access, malware activity, and lateral
movement. The alerting mechanism is the SIEM, which notifies the SOC.
