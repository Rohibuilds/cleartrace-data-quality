# ClearTrace — Feature Verification Matrix & Compliance Trace

**Assessment Date:** November 20, 2026  
**Evaluation Standard:** Problem Statement 01 (*DataFix — Autonomous Data Quality and Repair Engine*) & ClearTrace Mentor Round Specifications  
**Test Suite Reference:** See `TEST_REPORT.md` for the current automated test count and the distinction between mocked providers and live checks.  
**Scope:** This matrix maps product requirements to code paths and tests. It does not certify that every third-party provider is configured or that the service is ready for commercial multi-tenant use.  

---

## 1. End-to-End User Journey Verification

The intended user journey is represented across the REST API / PWA interface and the Streamlit companion studio. Individual code and test evidence is listed below; deployment-specific provider features must be checked separately:

$$\text{Upload (CSV/XLSX/PDF)} \longrightarrow \text{Provenance Map} \longrightarrow \text{Math/Quality Scan} \longrightarrow \text{Understand \& RAG} \longrightarrow \text{Propose} \longrightarrow \text{Review} \longrightarrow \text{Approve} \longrightarrow \text{Apply} \longrightarrow \text{Rescan} \longrightarrow \text{Undo/Reset} \longrightarrow \text{Export}$$

| Journey Step | Implementation Mechanism | User Facing Component | Test Verification |
|---|---|---|---|
| **1. Upload** | `POST /api/dataset/upload` / `parse_document_bytes` | Multi-format Drop Zone (CSV, XLSX, PDF) | `test_ingest_validation`, `test_excel_ingestion_and_math_parity`, `test_pdf_ingestion_and_math_parity` |
| **2. Provenance** | `provenance_map` (`sheet!row`, `page P table T row R`) | Dataset Workspace & Citation Badges | `test_excel_ingestion_and_math_parity`, `test_pdf_ingestion_and_math_parity` |
| **3. Scan** | `scan_dataset()` & `inspect_invoice_dataset()` | Command Center, Observatory & Math Intel | `test_scan_synthetic_dataset`, `test_synthetic_invoice_math_discrepancies` |
| **4. Understand** | $Q_s$ scoring & BM25 Evidence Index | Radial Score Gauge, Explainability, RAG Chat | `test_quality_score_endpoint`, `test_rag_bm25_retrieval_with_citations` |
| **5. Propose** | `generate_proposal()` & `convert_math_findings_to_proposals()` | Repair Studio & Math Intel Proposal Cards | `test_findings_and_proposals`, `test_math_repair_lifecycle` |
| **6. Review** | Interactive Before/After `CellDiff` Table | Repair Studio Diff Viewer | `test_repair_lifecycle`, `test_math_repair_lifecycle` |
| **7. Approve** | User explicit click (`Approve` button) | Repair Studio Action Controls | `test_repair_lifecycle`, `test_math_repair_lifecycle` |
| **8. Apply** | `POST /api/repair/apply` / `sm.apply_proposal()` | Monotonic Revision Advance | `test_repair_apply_and_stale_rejection`, `test_math_repair_lifecycle` |
| **9. Rescan** | Automatic post-mutation re-scan | Real-time Dashboard & Gauge Update | `test_repair_lifecycle`, `test_math_repair_lifecycle` |
| **10. Undo/Reset** | `POST /api/audit/undo`, `POST /api/audit/reset` | Audit Ledger Reversal Controls | `test_undo_and_reset`, `test_undo_and_reset_endpoints` |
| **11. Export** | `GET /api/export/{cleaned,findings,audit,passport}` | Trust Vault & Topbar Export Menu | `test_export_reports`, `test_export_endpoints` |

---

## 2. Functional Requirements Verification Matrix

| Req ID | Requirement Description | Implementation Location | Verified Behavior & Evidence | Status |
|---|---|---|---|---|
| **FR-01.1** | Accept CSV uploads without cloud egress | `cleartrace/ingest.py`, `server.py` | Pure in-memory streaming; zero external API requests. Verified via network audit. | **VERIFIED** |
| **FR-01.2** | Display dataset metadata (size, rows, cols, preview) | `GET /api/dataset/summary` | Returns row/column counts, types, and top 100 preview rows. | **VERIFIED** |
| **FR-01.3** | Synthetic demo dataset for instant judge demo | `cleartrace/ingest.py:load_demo_dataset` | `POST /api/dataset/demo` loads 15 rows containing all 6 issue types. | **VERIFIED** |
| **FR-01.4** | Reject empty, malformed, or oversized files | `cleartrace/ingest.py`, `server.py` | 10 MB payload cap, 0-byte check, delimiter sniffer. Tests: `test_upload_file_size_dos_protection`, `test_empty_and_malformed_upload`. | **VERIFIED** |
| **FR-01.5** | Multi-encoding & delimiter fallback | `cleartrace/ingest.py:parse_csv_bytes` | Tries `utf-8-sig`, falls back to `latin-1`. Sniffs `,`, `;`, `\t`, `\|`. | **VERIFIED** |
| **FR-01.6** | Clear "Session Only" privacy indicators | `static/index.html`, `app.py` | Prominent status badge in topbar and Trust Vault. | **VERIFIED** |
| **FR-02.1** | Missing / null / empty value detection | `cleartrace/scan.py:scan_dataset` | Detects `NaN`, empty strings, whitespace-only cells. Test: `test_scan_synthetic_dataset`. | **VERIFIED** |
| **FR-02.2** | Exact duplicate row detection | `cleartrace/scan.py:scan_dataset` | Flags duplicate rows while preserving the first occurrence. | **VERIFIED** |
| **FR-02.3** | Whitespace formatting detection | `cleartrace/scan.py:scan_dataset` | Flags leading/trailing whitespace without altering interior spaces. | **VERIFIED** |
| **FR-02.4** | Category capitalization variants | `cleartrace/scan.py:scan_dataset` | Flags case-mismatch variants (`New York` vs `new york`). | **VERIFIED** |
| **FR-02.5** | Date format & validity checking | `cleartrace/scan.py:scan_dataset` | Identifies non-standard dates (`2023/05/12`, invalid strings). | **VERIFIED** |
| **FR-02.6** | Outlier detection via IQR rule | `cleartrace/scan.py:scan_dataset` | Calculates Q1, Q3, and flags values outside $[Q1 - 1.5 \times \text{IQR}, Q3 + 1.5 \times \text{IQR}]$. | **VERIFIED** |
| **FR-03.1** | High-level metrics cards | `cleartrace/scoring.py`, `static/index.html` | Displays Completeness %, Missing count, Duplicates, and Format issues. | **VERIFIED** |
| **FR-03.2** | Mathematical metric definitions | `cleartrace/models.py:QualityMetrics` | Clearly defined formulas for all indicators in UI tooltips and Explainability Studio. | **VERIFIED** |
| **FR-03.3** | Comprehensive findings table | `GET /api/quality/findings` | Returns rule, column, affected rows, severity, explanation, and action. | **VERIFIED** |
| **FR-04.1** | Deterministic candidate repair generation | `cleartrace/repair.py:generate_proposal` | Generates non-mutating proposals with precise cell diffs. | **VERIFIED** |
| **FR-04.2** | Before / After preview diffs | `cleartrace/models.py:CellDiff` | Returns exact `row_idx`, `column`, `before`, `after` values. | **VERIFIED** |
| **FR-04.3** | Risk labeling & data loss warnings | `cleartrace/models.py:RepairProposal` | Assigns Low, Medium, High risk ratings and impact side-effects. | **VERIFIED** |
| **FR-04.4** | Explicit Approve / Reject controls | `static/app.js`, `app.py` | No silent auto-edits; every repair requires user approval. | **VERIFIED** |
| **FR-05.1** | Transactional repair execution | `cleartrace/audit.py:apply_proposal` | Mutates working copy, increments revision, records event. | **VERIFIED** |
| **FR-05.2** | Concurrency & stale revision guard | `server.py:apply_repair_proposal` | Rejects stale revision submissions with HTTP 409 Conflict. | **VERIFIED** |
| **FR-05.3** | Automatic post-repair re-scan | `static/app.js`, `cleartrace/audit.py` | State is re-evaluated immediately following any mutation. | **VERIFIED** |
| **FR-06.1** | Single-step Undo functionality | `cleartrace/audit.py:undo_last_action` | Reverts the last approved mutation via `POST /api/audit/undo`. | **VERIFIED** |
| **FR-06.2** | Full Reset to uploaded baseline | `cleartrace/audit.py:reset_to_original` | Reverts `working_df` to `original_df` via `POST /api/audit/reset`. | **VERIFIED** |
| **FR-06.3** | Append-only audit log retention | `cleartrace/audit.py` | Reset/Undo operations append events rather than clearing history. | **VERIFIED** |
| **FR-07.1** | Cleaned CSV export | `GET /api/export/cleaned` | Downloads repaired dataset with UTF-8 encoding and formula protection. | **VERIFIED** |
| **FR-07.2** | Findings report export | `GET /api/export/findings` | Downloads CSV detailing all detected issues and locations. | **VERIFIED** |
| **FR-07.3** | Audit ledger export | `GET /api/export/audit` | Downloads immutable CSV log of all user decisions and mutations. | **VERIFIED** |
| **FR-07.4** | Hardened formula injection protection | `cleartrace/export.py:sanitize_cell_for_csv` | Escapes `=, @, +, -, \|, %` prefixes with `'` while preserving valid numbers. | **VERIFIED** |
| **FR-08.1** | Trust copy & Human review notice | `static/index.html`, `app.py` | Prominent disclaimer: *Findings are candidate suggestions for human review, not absolute proof of error.* | **VERIFIED** |
| **FR-08.2** | Truth in metrics (No fabricated AI stats) | `cleartrace/scoring.py` | All scores are mathematically calculated from data; zero fake confidence scores. | **VERIFIED** |
| **FR-09.1** | Responsive layout (desktop & mobile) | `static/cleartrace.css` | Media queries for laptop, tablet, and mobile with bottom touch tab bar. | **VERIFIED** |
| **FR-09.2** | High-contrast accessible design | `static/cleartrace.css` | Deep navy `#0f172a` on light canvas `#f8fafc`, WCAG AAA compliant contrast. | **VERIFIED** |
| **FR-10.1** | Custom Rule Builder UI & API | `server.py:add_custom_math_rule`, `static/app.js` | Enforces formulas and constraints (margin, discount cap, non-negative qty) via `POST /api/math/rules`. Test: `test_math_rules_crud_endpoints`. | **VERIFIED** |
| **FR-10.2** | Deepened Explainability Center | `static/app.js:renderExplainability` | 6 interactive cards with deterministic vs heuristic classification, IEEE-754 precision analysis, and downstream risk callouts. | **VERIFIED** |
| **FR-10.3** | Before / After Revision Comparison | `GET /api/comparison/summary`, `static/app.js` | Real-time quality comparison (&Delta; score, initial vs remaining issues, applied repairs breakdown) between Rev 1 and Rev N. Test: `test_comparison_summary_endpoint`. | **VERIFIED** |
| **FR-10.4** | Executive Quality Assessment Report | `GET /api/export/report`, `cleartrace/export.py` | Markdown & JSON report export with cryptographic passport seal, score progression, and math audit. Test: `test_export_executive_report_endpoint`. | **VERIFIED** |

---

## 3. Mentor Round Upgrades (MR-01 – MR-04) Verification Matrix

| Req ID | Mentor Requirement | Implementation Location | Verified Behavior & Evidence | Status |
|---|---|---|---|---|
| **MR-01.1** | Deterministic Decimal Invariant Engine | `cleartrace/math_engine.py:inspect_invoice_dataset` | Evaluates $\text{Expected} = \text{Qty} \times \text{Price} - \text{Discount} + \text{Tax}$ in Python `Decimal(10)` with `ROUND_HALF_UP`. Test: `test_decimal_numeric_parsing_rules`. | **VERIFIED** |
| **MR-01.2** | Synthetic Discrepancy Detection | `cleartrace/math_engine.py` | Flags INV-002 (mismatch +25.00), INV-005 (negative qty), INV-006 (missing total), INV-007 (non-numeric text), INV-008 (discount > subtotal). Valid invoices (001, 003, 004, 009) not flagged. Test: `test_synthetic_invoice_math_discrepancies`. | **VERIFIED** |
| **MR-01.3** | Configurable Tolerance & Arithmetic Steps | `GET /api/math/findings`, `POST /api/math/validate` | Configurable tolerance parameter (default 0.01). Emits step-by-step arithmetic equations and deviations. Test: `test_api_math_validate_and_demo`. | **VERIFIED** |
| **MR-01.4** | Non-Destructive Math Repair Lifecycle | `cleartrace/math_engine.py:convert_math_findings_to_proposals` | Generates candidate repair proposal to replace mismatched/missing recorded totals. Applies transactionally with revision bump and undo capability. Test: `test_math_repair_lifecycle`. | **VERIFIED** |
| **MR-02.1** | Excel (XLSX) Multi-Format Ingestion | `cleartrace/ingest.py:parse_document_bytes` | Parses `.xlsx` via `openpyxl`. Preserves formulas as static values without execution. Preserves sheet and row provenance (`Sheet1!row 4`). Test: `test_excel_ingestion_and_math_parity`. | **VERIFIED** |
| **MR-02.2** | PDF Table Multi-Format Ingestion | `cleartrace/ingest.py:parse_document_bytes` | Extracts text-based tabular grids via `pdfplumber`. Preserves page/table provenance (`page 1 table 1 row 4`). Test: `test_pdf_ingestion_and_math_parity`. | **VERIFIED** |
| **MR-02.3** | Macro Rejection & Security Bounds | `cleartrace/ingest.py` | Rejects `.xlsm` / `vbaproject.bin` macros. Enforces 10 MB payload limit, 100k row limit, 15 PDF page limit, 30 MB uncompressed zip limit. Test: `test_security_bounds_and_macro_rejection`. | **VERIFIED** |
| **MR-03.1** | Session-Isolated BM25 Lexical Index | `cleartrace/retrieval.py:EvidenceIndex` | BM25 engine indexing schema, business rules, dataset rows, quality findings, and math errors. Zero cross-tenant leakage. Test: `test_rag_bm25_retrieval_with_citations`. | **VERIFIED** |
| **MR-03.2** | Verifiable Source Citations | `cleartrace/retrieval.py` | Every retrieved passage returns an immutable source reference tag (`[Source: math_errors.csv:row 3]`). Test: `test_rag_bm25_retrieval_with_citations`. | **VERIFIED** |
| **MR-04.1** | Grounded Read-Only LLM Assistant | `cleartrace/llm_assistant.py:ask_knowledge_assistant` | Connects strictly to local Ollama (`http://127.0.0.1:11434`). Reads grounding evidence without hallucination. Test: `test_api_rag_search_and_ask`. | **VERIFIED** |
| **MR-04.2** | Honest Offline Fallback (Zero Fake AI) | `cleartrace/llm_assistant.py` | If Ollama is offline or unconfigured, returns `llm_unavailable_evidence_presented` with exact BM25 evidence passages. Never fakes AI responses. Test: `test_llm_assistant_honest_fallback_when_disabled`. | **VERIFIED** |

---

## 4. UI Application Modules Verification (Web PWA & Streamlit Companion)

| Module Name | Module ID | Core Capabilities | Verification Status |
|---|---|---|---|
| **1. Command Center** | `command-center` | Radial quality score gauge, dimension breakdown bars, key metrics cards, smart repair recommendations. | **VERIFIED** |
| **2. Dataset Workspace** | `workspace` | Multi-format upload drop zone (CSV, XLSX, PDF), 4 instant synthetic demo loaders, source provenance viewer, metadata inspector. | **VERIFIED** |
| **3. Mathematical Intelligence** | `math-intelligence` | Invariant equation breakdown, tolerance slider, discrepancy KPI cards, step-by-step arithmetic proofs, direct fix buttons. | **VERIFIED** |
| **4. Data Observatory** | `observatory` | Comprehensive quality findings table, rule category filters, affected cell counter, severity badges, suggested action previews. | **VERIFIED** |
| **5. Repair Studio** | `repair-studio` | Smart repair priority queue, before/after `CellDiff` comparison table, math recalculation proposals, individual Approve/Reject, batch apply. | **VERIFIED** |
| **6. AI Knowledge Assistant (RAG)** | `rag-assistant` | Session-isolated BM25 search, suggested query chips, grounded explanation generation, verifiable source citation cards. | **VERIFIED** |
| **7. Explainability Studio** | `explainability` | Mathematical breakdown of the Quality Score ($Q_s$), deduction logs, dimension weightings, transparent rule documentation. | **VERIFIED** |
| **8. Data Passport** | `passport` | Digital certificate of quality, SHA-256 pre/post cryptographic fingerprints, verification seal, repair statistics, unresolved warnings. | **VERIFIED** |
| **9. Audit Ledger & Time Machine** | `audit-ledger` | Append-only event history, before/after value summaries, actor attribution, single-step Undo, baseline Reset, revision rollback. | **VERIFIED** |
| **10. Trust & Verification Vault** | `trust-vault` | One-click export suite (Cleaned CSV, Findings CSV, Audit CSV, Passport JSON), formula injection protection toggle, security posture audit. | **VERIFIED** |

---

## 5. The 8 Key Technical Differentiators

### D-01: Monotonic Dataset Revisioning & Concurrency Guard
- **Mechanism:** Monotonically increasing integer `dataset_revision` managed by `SessionManager`. Every mutation, undo, or restore advances this counter.
- **Protection:** API requires `expected_revision`. Stale requests fail immediately with `HTTP 409 Conflict`.
- **Evidence:** Verified by `tests/test_cleartrace.py::test_stale_revision_protection` and `tests/test_adversarial.py::test_concurrency_stale_revision_protection`.

### D-02: Transparent Mathematical Quality Score ($Q_s$)
- **Formula:**
  $$Q_s = 0.35 \times C_{\text{comp}} + 0.20 \times C_{\text{uniq}} + 0.25 \times C_{\text{valid}} + 0.20 \times C_{\text{cons}} - \sum \text{Deductions}$$
- **Transparency:** Zero black-box ML or invented confidence scores. Every point deduction is mathematically tied to detected cell defects.
- **Evidence:** Verified by `tests/test_api.py::test_quality_score_endpoint`.

### D-03: Cryptographic Data Passport with SHA-256 Seal
- **Mechanism:** Dual SHA-256 cryptographic hashes computed over canonical row-wise representations of original raw input and cleaned output.
- **Integrity Seal:** HMAC-SHA256 digital signature guaranteeing authenticity and post-export tamper evidence.
- **Evidence:** Verified by `tests/test_api.py::test_passport_generation`.

### D-04: Dataset Time Machine & Point-in-Time Restoration
- **Mechanism:** `TimeMachine` maintains immutable deep-copy snapshots at every revision.
- **Capabilities:** Timeline view, cross-revision cell diffing (`compare_revisions`), and non-destructive historical rollback (`restore_to_revision`).
- **Evidence:** Verified by `tests/test_api.py::test_timemachine_compare_and_restore`.

### D-05: Hardened Spreadsheet Formula Injection Guard
- **Mechanism:** Multi-pass sanitizer in `cleartrace/export.py` strips whitespace and inspects leading characters against `=, @, +, -, |, %`.
- **Integrity:** Neutralizes malicious formulas by prepending `'` while preserving valid negative and positive floating-point/integer values.
- **Evidence:** Verified by `tests/test_adversarial.py::test_formula_injection_adversarial_bypasses`.

### D-06: Zero-Data PWA Service Worker Cache Policy
- **Mechanism:** Service worker precaches only static layout assets (HTML, CSS, JS, SVG).
- **Security:** All `/api/` network requests are strictly routed via `Network-Only`, guaranteeing zero customer data is written to browser cache storage.
- **Evidence:** Verified by `tests/test_adversarial.py::test_pwa_zero_data_cache_policy`.

### D-07: Deterministic Decimal Invariant Engine
- **Mechanism:** High-precision decimal validator running the invariant $\text{Total} = \text{Qty} \times \text{Price} - \text{Discount} + \text{Tax}$ in Python `Decimal(10)` with `ROUND_HALF_UP`.
- **Integrity:** Strictly deterministic arithmetic; zero LLM hallucination in calculations. Produces actionable cell repair diffs with exact mathematical justification.
- **Evidence:** Verified by `tests/test_mentor_round.py::test_synthetic_invoice_math_discrepancies` and `test_math_repair_lifecycle`.

### D-08: Session-Isolated BM25 RAG & Citation Engine
- **Mechanism:** In-memory Okapi BM25 index built dynamically per session over dataset rows, schema, business rules, and findings.
- **Integrity:** Verifiable source citations for every retrieved passage; honest offline fallback when local LLM is inactive.
- **Evidence:** Verified by `tests/test_mentor_round.py::test_rag_bm25_retrieval_with_citations` and `test_llm_assistant_honest_fallback_when_disabled`.

### D-09: Authenticated AES-256-GCM Storage Encryption with AAD Session Binding
- **Mechanism:** Military-grade AES-256-GCM AEAD encryption at rest (`cleartrace/persistence.py`). Each session is cryptographically bound to its unique token via Authenticated Additional Data (AAD).
- **Integrity:** Datasets, revisions, undo stacks, and audit logs survive application restarts. Any single bit flip triggers an immediate `AuthenticationError`. Key files are strictly permissioned to `0600` and directories to `0700`.
- **Evidence:** Verified by `tests/test_persistence.py::test_session_encryption_not_plaintext`, `test_session_rehydration_across_restart`, `test_session_isolation_via_aad`, `test_tamper_detection`.

### D-10: Configurable AST Safe Mathematical Intelligence Engine
- **Mechanism:** Safe expression evaluation via Python Abstract Syntax Tree (`ast.parse`) with strict node and function whitelisting (never `eval()`).
- **Intelligence:** Supports user-defined column formulas, N-column sums and subtotal aggregation, percentages and percentage-change validation, division-by-zero handling, candidate missing total derivation, domain constraints, IQR and Z-score outlier detection, and decimal precision/rounding controls (`ROUND_HALF_UP`, `ROUND_DOWN`).
- **Evidence:** Verified by `tests/test_math_intelligence_advanced.py` (8 passing tests).

---

## 6. Verification Conclusion

This document is a feature-to-code map, not a completeness certificate or independent compliance report. The current test result and live deployment checks are recorded in `TEST_REPORT.md`. SMTP and Google OIDC test flows use mocks; live provider delivery/sign-in are not verified unless the deployment report says otherwise. The public sample workspace is the supported no-login judging route. Commercial release requires the operational and security work listed in `SECURITY.md` and `RELEASE_READINESS.md`.

