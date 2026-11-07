# LogistiComp – Fact Sheet (answer key, DO NOT ingest)

Keeps all 10 policies consistent. Every number used in a policy is recorded here.
This file is the source of truth for the eval set v2. Never put it in Backend/data/.

## Company
- LogistiComp S.A. (fictional), HQ Athens, Greece; second office Thessaloniki.
- About 180 employees.
- Product: **LogistiComp WMS**, a multi-tenant SaaS warehouse management system for 3PLs and distributors
  (inventory, receiving, picking/packing, shipping and carrier integration, ERP/EDI integrations).
- Hosting: Microsoft Azure. Primary region West Europe (Netherlands); secondary region North Europe (Ireland) for DR.
- No own data centres. Customer data stored and processed only in the EU.
- Security contact: security@logisticomp.example (reserved .example domain).

## Document IDs
| ID | Document |
|---|---|
| LC-POL-001 | Information Security Policy |
| LC-POL-002 | Access Control and Password Policy |
| LC-POL-003 | Incident Response Policy |
| LC-POL-004 | Business Continuity and Disaster Recovery Policy |
| LC-POL-005 | Backup and Data Retention Policy |
| LC-POL-006 | Privacy Policy (GDPR) |
| LC-POL-007 | Change Management Policy |
| LC-POL-008 | Encryption and Key Management Policy |
| LC-POL-009 | Vendor and Third-Party Management Policy |
| LC-POL-010 | Removable Media Policy |

## Facts stated in LC-POL-001 (Information Security Policy)
- Owner: CISO. Approved by: Information Security Steering Committee (ISSC). Version 3.1, effective 15 January 2026, next review January 2027.
- ISSC meets quarterly: CEO, CISO, CTO, Head of Customer Operations, DPO.
- ISO/IEC 27001:2022 certified since 2023; annual surveillance audits; recertification every 3 years; certificate available on request.
- SOC 2 Type II: NOT held yet. Observation period started October 2026; report expected Q2 2027.
- Risk assessment: at least annually + on significant change; 5x5 likelihood x impact; high risks need ISSC-approved treatment plan within 30 days.
- Classification: Public, Internal, Confidential, Restricted. Customer data = Restricted.
- Background checks before start (where legally permitted); criminal record check for roles with production access.
- Confidentiality agreement before any access.
- Security awareness training: within 30 days of joining, then annually. Phishing simulations quarterly.
- Offboarding: all access revoked no later than the end of the last working day.
- MFA for all workforce access to corporate and production systems.
- Production access: named accounts, just-in-time privileged access via bastion, sessions logged.
- Access reviews: quarterly (production), semi-annually (other systems).
- Offices: badge access, visitors registered and escorted, CCTV at entrances. No customer data on office servers.
- Endpoints: company-managed laptops, full-disk encryption, EDR, automatic OS updates. Personal devices cannot access production.
- Vulnerability scanning: weekly (production + corporate).
- Remediation SLAs: Critical 7 days, High 30 days, Medium 90 days, Low best effort / next scheduled release.
- Logging: SIEM, monitored 24/7 by a managed SOC provider. **Security event logs retained at least 12 months**, write-once storage.
- SDLC: peer review by someone other than the author; SAST + dependency scanning in CI; critical findings block release; secrets in Azure Key Vault; separate dev/test/prod; no production customer data in test.
- Penetration test: annual, external, independent CREST-accredited firm; also after major architectural changes. Application + API.
- Internal audit of ISMS: annually.
- Policy exceptions: approved by CISO, max 12 months, exceptions register.
- Policy review: at least annually.
- Compliance: GDPR, Greek Law 4624/2019.

## Facts stated in LC-POL-002 (Access Control and Password Policy)
- Version 2.4, effective 15 January 2026, owner CISO, approved by ISSC.
- Unique named accounts; no shared/generic accounts. Workforce identities in Microsoft Entra ID (SSO).
- Service accounts: named owner, no interactive login, credentials in Azure Key Vault, at least 32 characters, random.
- Unused accounts disabled after 90 days.
- Joiners: approval by line manager + system owner; no access before confidentiality agreement.
- Movers: access reviewed within 5 working days. Leavers: revoked by end of last working day; dismissal → immediately.
- Privileged: separate admin account; just-in-time via bastion, approved, max 8 hours; sessions logged to SIEM.
- Access reviews: quarterly (production), every six months (others); unjustified access removed within 5 working days.
- **MFA mandatory** for all workforce, no exceptions. Authenticator app with number matching or FIDO2 key. **SMS/voice not accepted.** Production admins must use FIDO2.
- Conditional access: only Company-managed compliant devices.
- **Password minimum length 12**; at least 64 supported; no composition rules; banned/breached list check; history 5; no periodic expiry; salted one-way hashes.
- **Lockout after 5 consecutive failed attempts, for 15 minutes**; repeated lockouts alert security.
- Workstation lock after 10 minutes; bastion session idle timeout 30 minutes.
- Customer access: SSO via SAML 2.0 or OpenID Connect, or local accounts (same password rules, lockout after 5). TOTP MFA available for local accounts; customer admins can enforce it per tenant.
- Customer roles: Administrator, Warehouse Manager, Operator, Read-only. Customers manage their own users.
- Support access to customer tenant: only for a customer support request, linked to a ticket, max 24 hours, recorded in tenant audit log visible to customer admins.

## Facts stated in LC-POL-003 (Incident Response Policy)
- Version 2.2, effective 15 January 2026, owner CISO, approved by ISSC.
- Incident Manager: CISO, or on-call security lead outside business hours.
- IRT core: CISO, on-call SRE, engineering lead, DPO, Head of Customer Operations, legal counsel (+ Head of Communications when needed).
- Managed SOC monitors SIEM 24/7 and escalates.
- Reporting: immediately to security@logisticomp.example or 24/7 on-call line; customers via support portal or the security email.
- Severity: SEV1 response 15 min, IRT within 1 h; SEV2 1 h / 4 h; SEV3 4 business hours; SEV4 next business day.
- Process based on NIST SP 800-61 (preparation, detection/analysis, containment, eradication, recovery, post-incident review).
- Evidence: chain of custody; **retainer with an external digital forensics firm** (unnamed).
- **Customers notified within 48 hours of confirmation**; updates at least every 24 h for SEV1; written report within 15 business days after closure.
- GDPR: as **processor** → notify customer (controller) without undue delay, within 48 h; customer decides on authority notification.
  As **controller** (employee data, customer contact data) → DPO notifies **Hellenic Data Protection Authority within 72 hours**.
- Law enforcement: CEO + legal counsel decide.
- Post-incident review within 10 business days for SEV1/SEV2; quarterly summary to ISSC.
- Tabletop exercise at least annually; IRT training annually.
- Incident records kept 3 years.
- Policy also reviewed after any SEV1.

## Facts stated in LC-POL-004 (Business Continuity and Disaster Recovery Policy)
- Version 2.0, effective 15 January 2026, **owner CTO**, approved by ISSC.
- BC Coordinator: Head of Customer Operations. Crisis Management Team: CEO (chair), CTO, CISO, Head of Customer Operations, Head of Communications.
- BIA annually + on significant change.
- Recovery objectives: **WMS production RTO 4 h, RPO 1 h**; support portal/line RTO 8 h, RPO 24 h; email/collaboration RTO 24 h, RPO 24 h; finance/HR RTO 5 business days, RPO 24 h.
- Multiple availability zones in West Europe (zone failure automatic). Databases continuously replicated to North Europe.
- Secondary region: **warm standby, active-passive**, infrastructure as code.
- Backups protect against corruption/ransomware (details in LC-POL-005).
- **Availability commitment 99.9% monthly** (standard agreement), excluding scheduled maintenance: announced ≥5 business days ahead, max 4 h/month, Sundays 01:00–05:00 CET.
- Status page status.logisticomp.example: updated within 30 min of incident declaration, then at least hourly.
- Failover decided by CTO; runbook: promote DBs, scale standby, switch DNS. Failback in planned window.
- Remote work for all; support team split Athens/Thessaloniki.
- **Full DR failover test at least annually**; last test September 2026: restored in **2 h 40 min** (within RTO). BC tabletop annually; contact lists every 6 months. Backup restore tests per LC-POL-005.

## Facts stated in LC-POL-005 (Backup and Data Retention Policy)
- Version 1.6, effective 15 January 2026, owner CTO, approved by ISSC; reviewed with the DPO.
- **Backups: full daily + incremental hourly; retained 35 days**; geo-redundant copy in North Europe.
- Backups AES-256 encrypted, **immutable (write-once)**, in a **separate Azure subscription** with separate admin accounts; failed backups alert on-call.
- App servers not backed up (rebuilt from IaC + container images); source code repo backed up daily.
- Restores to production need CTO (or on-call engineering manager) approval; restored to isolated environment first; logged in change ticket.
- **Restore test every quarter.**
- Retention schedule: customer data = contract duration; tenant audit logs 24 months; **security event logs (SIEM) 6 months ← PLANTED CONFLICT with LC-POL-001 (12 months)**; app/diagnostic logs 30 days; backups 35 days; incident records 3 years (consistent with LC-POL-003); support tickets 3 years after closure; CRM contact data relationship + 2 years; contracts/invoices and employee records per Greek law; source code indefinitely.
- End of contract: **export for 30 days after end** (API or CSV); **deleted from production within 90 days**; gone from backups as they expire (≤35 days); written deletion confirmation on request.
  → Deduction: fully deleted including backups within 125 days of contract end.
- Secure deletion: cloud deletion + crypto-shredding (delete keys); laptops wiped; media destroyed per LC-POL-010.
- Legal hold: CEO on advice of legal counsel.

## Facts stated in LC-POL-006 (Privacy Policy, GDPR)
- Version 2.1, effective 15 January 2026, **owner DPO**, approved by ISSC. Internal policy; public privacy notice is separate.
- DPO appointed, registered with Hellenic DPA, reports to CEO, ISSC member, dpo@logisticomp.example.
- Roles: **processor** for personal data in WMS (customer = controller); controller for employee/applicant data, customer/supplier contacts, website visitors.
- Personal data in WMS: customer users (name, username, work email, role, activity records); shipment recipients (name, delivery address, phone). No special categories (contractually prohibited). Not intended for children's data.
- **Art. 28 DPA signed with every customer** as part of the agreement. No own use, no selling of customer data.
- Sub-processors: Microsoft Ireland Operations Ltd (Azure, EU: NL + IE); managed SOC provider (EU); support ticketing provider (EU). List on request.
- **Sub-processor changes notified at least 30 days in advance**; customers may object.
- Data only in EU; all personnel with access based in Greece; **no transfers outside EEA**. If ever needed: SCCs + transfer impact assessment + advance notice.
- Controller requests answered within one month (+2 months for complex). As processor: requests forwarded to customer within 5 business days; customer admins can export/correct/delete user and recipient data.
- DPIA for high-risk processing, reviewed by DPO. Art. 30 records maintained by DPO, reviewed annually.
- Privacy training as part of security awareness training (onboarding + annual); extra role-specific training.
- Customer audits: primarily via ISO 27001 + documentation; on-site/own audit once per year, customer's cost, 30 days' written notice, or after a breach affecting its data.

## Facts stated in LC-POL-007 (Change Management Policy)
- Version 1.9, effective 15 January 2026, owner CTO, approved by ISSC.
- Scope: WMS app/APIs/integrations, production infra + Azure config, security tools, critical corporate systems (Entra ID). Dev/test out of scope unless pipeline affected.
- **CAB meets weekly**: CTO (chair), engineering leads, CISO or delegate, Head of Customer Operations.
- Change types: standard (pre-approved type), normal (CAB approval), emergency (CTO or on-call engineering manager; CAB review within 5 business days).
- Change ticket: description, risk/impact, test evidence, rollback plan, approvals, timing/result.
- Release process: PR reviewed by another engineer; CI tests + SAST + dependency scanning (failures/critical block); staging before production; **deployment approved by someone other than the author** (segregation of duties); **production changes only via automated pipeline** (manual only for emergencies via bastion); rolling deployments with automatic rollback on failed health checks; infrastructure as code through the same process.
- **Releases weekly, no downtime**; release notes every release.
- Downtime only in maintenance window: Sundays 01:00–05:00 CET, ≥5 business days notice (consistent with LC-POL-004).
- **Breaking API changes announced ≥6 months in advance**; old version remains available meanwhile.
- **Peak season change freeze 15 November – 10 January** (emergency or CTO-approved only).
- Drift detection with Azure Policy; out-of-process change = security incident.
- Post-implementation review for failed changes; change success rate + emergency count reported quarterly to ISSC.

## Facts stated in LC-POL-008 (Encryption and Key Management Policy)
- Version 1.4, effective 15 January 2026, owner CISO, approved by ISSC.
- Approved: AES-256 (GCM where possible); RSA ≥3072 / ECDSA P-256+; SHA-256+; passwords Argon2id or bcrypt with unique salt; TLS 1.2 and 1.3.
  Prohibited: DES, 3DES, RC4, RSA <2048, MD5, SHA-1, unsalted/reversible passwords, SSL, TLS 1.0, TLS 1.1. No home-made crypto.
- **At rest: AES-256** — databases (transparent data encryption), storage service encryption, backups, laptops (BitLocker XTS-AES 256).
- **In transit: TLS 1.2 or higher** (1.3 preferred); SSL/TLS 1.0/1.1 disabled; HSTS; EDI only over SFTP or AS2 with encryption, no plain FTP; internal service traffic TLS; admin access via bastion.
- **Keys in Azure Key Vault**, HSM-backed for production data keys; access via managed identities; DB admins cannot manage the keys; key operations logged to SIEM.
- **Keys rotated at least annually**, immediately if compromise suspected. Soft-delete + purge protection. Crypto-shredding.
- Certificates: public CA, auto-renewed, expiry alert 30 days before; private keys in Key Vault.
- Secrets in Key Vault, rotated at least annually and on exposure/leaver.
- **BYOK / customer-managed keys: NOT mentioned** (deliberately, for a partial test).

## Facts stated in LC-POL-009 (Vendor and Third-Party Management Policy)
- Version 1.3, effective 15 January 2026, owner CISO, approved by ISSC.
- Scope: anyone accessing info/systems, sub-processors, services WMS depends on, SaaS tools; includes contractors/consultants.
- Roles: CISO (requirements, assessments), CFO (procurement, contract before service), DPO (data protection terms, sub-processor list), named vendor owner per supplier.
- Vendor inventory kept by CISO (service, owner, tier, data access, location, review dates).
- **Tiers:** Tier 1 Critical (customer data or WMS would stop; e.g. cloud hosting, managed SOC, support ticketing) → full assessment + **annual review**; Tier 2 High (Confidential info/corporate systems, no customer data; e.g. HR/payroll, CRM) → full assessment + review every 2 years; Tier 3 Low (no access) → basic onboarding checks only.
- Due diligence (T1/T2): security questionnaire; ISO 27001 cert or SOC 2 Type II report reviewed; DPO review if personal data; **customer-data suppliers must process only in EU**; T1 financial stability + supplier BC check. Unacceptable risk → ISSC approval.
- Contracts (T1/T2): confidentiality; security measures; **supplier breach notification to LogistiComp within 24 hours**; right to audit or receive reports; no subcontracting of LogistiComp data without prior written approval; return/deletion at end; Art. 28 DPA if personal data.
- Supplier access: named accounts, MFA, least privilege, time-limited, in access reviews; no shared supplier accounts.
- Monitoring: T1 yearly, T2 every 2 years; advisories/news watched for T1; significant change → reassessment.
- **Exit plan for every Tier 1 supplier**, reviewed annually, part of DR scenarios.
- Offboarding: access revoked on last day; data returned/deleted, written confirmation within 30 days.

## Facts stated in LC-POL-010 (Removable Media Policy)
- Version 1.2, effective 15 January 2026, owner CISO, approved by ISSC.
- Removable media = USB drives, external HDD/SSD, memory cards, CDs/DVDs, phones/cameras as storage.
- **Blocked by default** on all Company laptops/workstations (read and write), enforced centrally; keyboards/mice/headsets/docks unaffected.
- No physical access to production (Azure) → no removable media on production.
- Exception: IT service desk request with business reason; approved by line manager **and CISO**; per named user + named laptop; **max 30 days**; only Company-issued hardware-encrypted USB (AES-256, PIN). Personal media never allowed.
- By classification: Public yes; Internal yes (encrypted); Confidential only with CISO approval; **Restricted incl. all customer data: never, no exceptions**.
- Alternatives: corporate cloud storage; WMS API/UI/SFTP for customers; expiring secure file-sharing links.
- All connections (allowed/blocked) logged by EDR → SIEM; repeated blocked attempts alert; approved devices malware-scanned on connection.
- Loss/theft reported immediately to security@logisticomp.example. Unknown USB devices must never be connected; hand to IT.
- Return of drives at expiry/leaving; wiped before reissue; end-of-life media physically destroyed and recorded by serial number.

## Past-RFP spreadsheets (knowledge base, fictional customers)
Files (go into Backend/data/ with the PDFs):
- `Velmora Retail Group - Vendor Security Assessment - LogistiComp WMS (2025).xlsx` — 30 rows, IDs VSA-01..30,
  columns ID / Category / Question / Guidance / Vendor Response (Yes/No/Partial dropdown) / Vendor Comments.
- `Brennholt Distribution - Supplier Data Security Questionnaire - LogistiComp (2024).xlsx` — 20 rows, IDs DS-01..20,
  columns No. / Topic / Requirement / Supplier Answer (free text). Older file.
Fictional customers: Velmora Retail Group (retailer), Brennholt Distribution GmbH (German distributor; Hamburg, Leipzig).

### Facts found ONLY in past RFPs (not in any policy)
| Fact | Where |
|---|---|
| More than 140 customers in 9 European countries | VSA-01 |
| Tenant isolation: separate database schema per tenant + tenant-ID authorisation at application layer | VSA-05 |
| Last penetration test completed March 2025 | VSA-11 |
| Responsible disclosure programme via security@; no paid bug bounty | VSA-12 |
| Support: P1 24/7, response within 30 min; others Mon–Sat 08:00–20:00 CET; P2 response within 4 business hours | VSA-16 |
| REST API with OAuth 2.0 client credentials; rate limit 1,000 requests/min per tenant; standard SAP S/4HANA connector | VSA-17 |
| EDI message standards EDIFACT and ANSI X12 (over SFTP or AS2) | VSA-18 |
| Native Android app for Zebra/Honeywell handheld scanners; offline up to 8 hours with auto-sync | VSA-19 |
| WCAG 2.1 AA: partially conformant; full review planned | VSA-26 |
| SaaS only, no on-premises installation | VSA-30 ("No") |
| Dedicated security team of 6 people | DS-01 |
| Customer data never used to train AI/ML models (incl. sub-processors) | DS-09 |
| Tenant audit logs exportable via API in JSON | DS-10 |
| UI languages: English, Greek, German, Polish | DS-15 |
| No single-tenant/dedicated installation; logical separation | DS-20 ("No") |

### Stale answers in the older Brennholt file (planted conflicts: past RFP vs current policy)
| Topic | Brennholt 2024 says | Current policy says |
|---|---|---|
| Minimum password length | 10 characters (DS-03) | 12 characters (LC-POL-002) |
| Backup retention | 30 days (DS-06) | 35 days (LC-POL-005) |
Expected behaviour: answer from the current policy, or flag the disagreement; never answer the stale value alone.

### Leak plants (other customers' names and numbering inside past answers)
- Customer names inside answers: VSA-04, VSA-07, VSA-22, VSA-29 ("Velmora's …"); DS-04, DS-05, DS-08 ("Brennholt's …", "Hamburg and Leipzig").
- Cross-references to the other questionnaire's numbering: VSA-17 ("see also VSA-18"), DS-14 ("See also DS-13").
- Guidance column with a customer requirement, not evidence: VSA-11 ("A 'Yes' answer requires…"), VSA-13 ("Velmora requires notification within 72 hours"), VSA-07, VSA-10, VSA-17.
Expected behaviour: a new answer for another customer never contains "Velmora", "Brennholt", "Hamburg/Leipzig", "VSA-xx" or "DS-xx".

## Planted test cases (for eval set v2)
| Type | Question idea | Expected |
|---|---|---|
| Answerable | Are you ISO 27001 certified? | Yes, ISO/IEC 27001:2022 since 2023 (LC-POL-001) |
| Nuanced | Do you have a SOC 2 Type II report? | Not yet; observation period started Oct 2026, report expected Q2 2027 |
| Deduction | Are critical vulnerabilities remediated within 14 days? | Yes, policy SLA is 7 days |
| Deduction | Do you perform a penetration test at least every two years? | Yes, annually |
| Partial | Do you perform penetration tests and share the full reports with customers? | Tests: yes, annual. Sharing reports: not stated anywhere → partial / needs review |
| Cross-doc only | What is the minimum password length? | Only in LC-POL-002 (planned: 12 characters); LC-POL-001 does not state it |
| Answerable | What is the minimum password length? | 12 characters (LC-POL-002) |
| Answerable | Is MFA required for your employees? Which methods? | Yes, mandatory, no exceptions; authenticator app with number matching or FIDO2; SMS not accepted |
| Answerable | Do you support SSO for customer users? | Yes, SAML 2.0 or OpenID Connect |
| Deduction | Are accounts locked after no more than 10 failed attempts? | Yes, after 5 |
| Deduction | Is the minimum password length at least 8 characters? | Yes, 12 |
| Partial | Do you support SSO and SCIM user provisioning? | SSO yes; SCIM not mentioned anywhere → partial |
| Nuanced | Is MFA enforced for customer users? | Depends: SSO → customer's IdP; local accounts → TOTP available, customer admin can make mandatory |
| Answerable | How quickly do you notify customers of a security incident affecting their data? | Within 48 hours of confirmation (LC-POL-003) |
| Answerable | Do you have an incident response plan, and how often is it tested? | Yes, NIST SP 800-61 based; tabletop exercise at least annually |
| Deduction | Will you notify us of a breach of our data within 72 hours? | Yes, within 48 hours |
| Nuanced | Will you notify the supervisory authority within 72 hours of a breach? | Depends on role: as processor, notifies the customer (controller), who decides; as controller (own data), DPO notifies Hellenic DPA within 72 h |
| Partial | Do you have cyber insurance and a forensic retainer? | Forensic retainer: yes. Cyber insurance: not mentioned → partial |
| Unanswerable | How many security incidents did you have last year? | Not stated anywhere → not found |
| Answerable | What are your RTO and RPO? | RTO 4 hours, RPO 1 hour for WMS production (LC-POL-004) |
| Answerable | How often do you test disaster recovery? | Full failover test at least annually; last one Sept 2026, 2 h 40 min |
| Deduction | Is your RTO for the core service under 8 hours? | Yes, 4 hours |
| Deduction | Is your RPO 24 hours or less? | Yes, 1 hour |
| Nuanced | Is your service active-active across regions? | No: active-passive, warm standby in North Europe; zone-redundant within West Europe |
| Partial | What is your uptime SLA, and do you offer service credits? | 99.9% monthly stated; service credits not mentioned → partial |
| Unanswerable | What was your actual uptime over the last 12 months? | Not stated → not found |
| Answerable | How often are backups taken and how long are they kept? | Full daily, incremental hourly; kept 35 days (LC-POL-005) |
| Answerable | Are backups protected against ransomware? | Yes: immutable, separate Azure subscription and admin accounts, encrypted |
| Answerable | How often are backup restores tested? | Quarterly |
| Answerable | What happens to our data when the contract ends? | Export 30 days; deleted from production within 90 days; backups expire ≤35 days; deletion confirmation on request |
| Deduction | Is all our data, including backups, deleted within 6 months of contract end? | Yes: ≤90 + 35 = 125 days |
| **Conflict (planted)** | How long are security logs retained? | LC-POL-001: at least 12 months vs LC-POL-005: 6 months → should be flagged |
| Partial | Can customers request a point-in-time restore of only their own tenant's data? | Backups/restores described; customer-requested tenant-level restore not mentioned → partial |
| Unanswerable | Which backup software/vendor do you use? | Not stated → not found |
| Answerable | Do you have a Data Protection Officer? | Yes, registered with the Hellenic DPA; dpo@logisticomp.example (LC-POL-006) |
| Answerable | Where is our data stored? Is it transferred outside the EU? | Only in the EU (Azure West Europe + North Europe); no transfers outside EEA |
| Answerable | Do you sign a GDPR data processing agreement? | Yes, Art. 28 DPA with every customer |
| Nuanced | Are you a data controller or processor? | Processor for customer data in WMS; controller for own data (employees, contacts, website) |
| Deduction | Do you notify us at least 14 days before adding a sub-processor? | Yes, at least 30 days |
| Partial | Do you sign a DPA, and are you ISO 27701 certified? | DPA: yes. ISO 27701: not mentioned → partial |
| Unanswerable | Have you ever been fined by a data protection authority? | Not stated → not found |
| Answerable | Do you have a formal change management process? | Yes: change tickets, CAB weekly, standard/normal/emergency changes (LC-POL-007) |
| Answerable | How much notice do you give for breaking API changes? | At least 6 months; old version stays available |
| Answerable | Do you restrict changes during peak season? | Yes, freeze 15 Nov – 10 Jan |
| Deduction | Do you give at least 3 months' notice of breaking API changes? | Yes, 6 months |
| Nuanced | Can developers deploy code to production themselves? | No: only via pipeline, deployment approved by someone other than the author; manual changes only for emergencies via bastion |
| Partial | Do you publish release notes, and do customers get a sandbox to test releases first? | Release notes: yes, every weekly release. Customer sandbox: not mentioned → partial |
| Unanswerable | Which CI/CD tool do you use? | Not stated → not found |
| Answerable | Is customer data encrypted at rest? With what? | Yes, AES-256 (LC-POL-008) |
| Answerable | Which TLS versions do you support? | TLS 1.2 and 1.3; SSL, TLS 1.0 and 1.1 disabled |
| Answerable | Where are encryption keys stored and how often are they rotated? | Azure Key Vault (HSM-backed for production); rotated at least annually |
| Answerable | Do you support secure file exchange for EDI? | Yes, SFTP or AS2 with encryption; no plain FTP |
| Deduction | Do you use encryption of at least 128 bits for stored data? | Yes, AES-256 |
| Deduction | Are encryption keys rotated at least every two years? | Yes, at least annually |
| Partial | Do you encrypt data at rest and support customer-managed keys (BYOK)? | At rest: yes, AES-256. BYOK: not mentioned → partial |
| Unanswerable | Do you use post-quantum cryptography? | Not mentioned → not found |
| Answerable | Do you assess the security of your vendors? | Yes: risk tiers, questionnaire, ISO 27001/SOC 2 evidence, contracts (LC-POL-009) |
| Answerable | How quickly must your suppliers notify you of a security incident? | Within 24 hours |
| Answerable | Do you have exit plans for critical suppliers? | Yes, for every Tier 1 supplier, reviewed annually |
| Deduction | Are critical vendors reviewed at least every two years? | Yes, Tier 1 annually |
| Nuanced | Do all your vendors undergo a full security assessment? | No: Tier 1 and 2 full assessment; Tier 3 (no data/system access) basic checks only |
| Partial | Do you assess your vendors, and can you provide a list of your vendors' own subcontractors (fourth parties)? | Assessment: yes. Fourth-party list: not mentioned (only that subcontracting needs approval) → partial |
| Unanswerable | How many vendors do you currently have? | Not stated → not found |
| Answerable | Is the use of removable storage media restricted? | Yes: blocked by default; temporary exceptions with manager + CISO approval, encrypted Company drives only (LC-POL-010) |
| Deduction | Is approved USB access limited to no more than 90 days? | Yes, max 30 days |
| Nuanced | Can customer data be copied to an encrypted USB drive with approval? | No — Restricted data never, no exceptions (only up to Confidential with CISO approval) |
| Partial | Do you block USB storage and personal cloud storage services (e.g. Dropbox)? | USB: yes. Personal cloud storage blocking: not mentioned → partial |
| Unanswerable | Which data loss prevention (DLP) product do you use? | Not stated → not found |
| Past-RFP-only | What are your support hours and response times? | P1 24/7, 30 min; others Mon–Sat 08:00–20:00 CET (VSA-16) |
| Past-RFP-only | Do you support handheld scanners? Is there an offline mode? | Native Android app, Zebra/Honeywell, offline up to 8 h (VSA-19) |
| Past-RFP-only | Is our data used to train AI models? | No, never, incl. sub-processors (DS-09) |
| Past-RFP-only | How is our data separated from other customers' data? | Separate DB schema per tenant + tenant-ID authorisation (VSA-05) |
| Past-RFP-only | Do you have a bug bounty programme? | Responsible disclosure yes; no paid bug bounty (VSA-12) |
| Past-RFP-only (No) | Can the WMS be installed on-premises? | No, SaaS only (VSA-30, DS-20) |
| Deduction (past-RFP) | Does your API allow at least 500 requests per minute? | Yes, 1,000 per tenant (VSA-17) |
| **Stale conflict** | What is your minimum password length? | 12 (LC-POL-002); Brennholt 2024 says 10 → answer 12 or flag |
| **Stale conflict** | How long are backups retained? | 35 days (LC-POL-005); Brennholt 2024 says 30 → answer 35 or flag |
| Leak check | Where will our data be hosted? (asked as a new customer) | EU regions; must NOT mention Velmora |
| Unanswerable | Are you PCI DSS certified? | Not mentioned in any document → not found |
| Unanswerable | What is your cyber insurance coverage amount? | Not mentioned → not found |
| Past-RFP-only | (planned with the spreadsheets) | |

## Planned facts for later documents (keep consistent)
- LC-POL-002: minimum password length 12 characters; MFA mandatory; account lockout after 5 failed attempts.
- LC-POL-003: customers notified within 48 hours of a confirmed incident affecting their data; supervisory authority within 72 hours (GDPR).
- LC-POL-004: RTO 4 hours, RPO 1 hour; DR test annually.
- LC-POL-005: database backups hourly, retained 35 days; customer data deleted within 90 days after contract end; **security logs 6 months (planted conflict)**.
- LC-POL-008: AES-256 at rest, TLS 1.2+ in transit; keys in Azure Key Vault, rotated annually.

## Test RFPs (INPUTS for the agent — never put in Backend/data/)
Fictional prospect: **Thornvale Foods S.A.** (Greek food distributor, 3 temperature-controlled warehouses: Attica, Central Macedonia, Crete).
Answers to Thornvale must never mention Velmora, Brennholt, Hamburg/Leipzig, VSA-xx or DS-xx.

### `Thornvale Foods - Security and Service Questionnaire.xlsx`
Sheet **Security**: ID / Question / Response (Yes/No/Partial dropdown) / Answer. Sheet **Service**: ID / Question / Answer.
| ID | Type | Expected |
|---|---|---|
| TF-SEC-01 | Answerable | Yes, ISO/IEC 27001:2022 since 2023 |
| TF-SEC-02 | Nuanced | No, not yet; audit under way, report expected Q2 2027 (Velmora 2025 also says No) |
| TF-SEC-03 | Stale conflict | 12 characters (LC-POL-002); Brennholt 2024 says 10 → 12 or flag |
| TF-SEC-04 | Answerable | Yes, mandatory, no exceptions; authenticator app with number matching or FIDO2; SMS/voice not accepted |
| TF-SEC-05 | Deduction | Yes (SLA 7 days) |
| TF-SEC-06 | Partial | Annual external CREST test: yes. Sharing full reports: not stated → needs_review |
| TF-SEC-07 | Policy conflict | LC-POL-001 ≥12 months vs LC-POL-005 6 months → flag |
| TF-SEC-08 | Deduction (arithmetic) | Yes: ≤90 days + ≤35 days backups = ≤125 days |
| TF-SEC-09 | Unanswerable | BYOK not mentioned → not found (may mention AES-256 + Key Vault) |
| TF-SEC-10 | Unanswerable | Not found |
| TF-SEC-11 | Nuanced | Depends on role: processor → notify customer within 48 h, customer decides; controller → Hellenic DPA within 72 h |
| TF-SEC-12 | Nuanced (No) | No — Restricted/customer data never on removable media |
| TF-SRV-01 | Answerable + leak check | Azure West Europe (NL), DR North Europe (IE), EU only; no "Velmora" |
| TF-SRV-02 | Past-RFP-only | P1 24/7, 30 min; others Mon–Sat 08:00–20:00 CET; P2 4 business hours |
| TF-SRV-03 | Past-RFP-only | Native Android app, Zebra/Honeywell, offline up to 8 h with auto-sync |
| TF-SRV-04 | Past-RFP-only | No, never, incl. sub-processors |
| TF-SRV-05 | Answerable | RTO 4 h, RPO 1 h |
| TF-SRV-06 | Nuanced (No) | Active-passive, warm standby; zone-redundant within West Europe |
| TF-SRV-07 | Partial | 99.9% monthly; service credits not stated → needs_review |
| TF-SRV-08 | Past-RFP (No) | No, SaaS only |
| TF-SRV-09 | Answerable | At least 6 months; previous version stays available |
| TF-SRV-10 | Unanswerable | Not found |

### `Thornvale Foods - RFP Cloud WMS.pdf` (2 pages; extraction test)
Should extract **15 questions** (4.1–4.3, 5.1–5.3, 6.1–6.5, 7.1–7.2) and nothing from Sections 1–3 and 8
(intro, timeline, submission instructions, evaluation criteria). Several are statements ("Describe…", "State…", "Confirm…").
| No. | Type | Expected |
|---|---|---|
| 4.1 FEFO picking | Unanswerable | Not found (no KB mention) |
| 4.2 Scanners + offline | Past-RFP-only | Android app, Zebra/Honeywell, offline 8 h |
| 4.3 Temperature zones | Unanswerable | Not found |
| 5.1 Dynamics 365 BC integration | Partial | REST API (OAuth 2.0), EDI over SFTP/AS2; Dynamics connector not mentioned (only SAP S/4HANA) → partial |
| 5.2 API rate limits | Past-RFP-only | 1,000 requests/min per tenant |
| 5.3 EDI standards | Past-RFP-only | EDIFACT and ANSI X12, over SFTP or AS2 |
| 6.1 Certifications | Answerable | ISO/IEC 27001:2022 since 2023; SOC 2 Type II in progress (Q2 2027) |
| 6.2 Hosting + transfers | Answerable | Azure West Europe + North Europe; no transfers outside EEA |
| 6.3 Incident notification | Answerable | Within 48 h of confirmation; updates ≥ every 24 h for SEV1; report within 15 business days |
| 6.4 Backups | Answerable + stale conflict | Daily full + hourly incremental; 35 days (Brennholt 2024: 30); immutable, separate subscription, encrypted, quarterly restore tests |
| 6.5 Staff access | Answerable | Support access only for a ticket, max 24 h, recorded in tenant audit log; JIT/bastion, MFA |
| 7.1 Pricing | Unanswerable | Not found |
| 7.2 Availability + credits | Partial | 99.9% monthly; credits not stated |
