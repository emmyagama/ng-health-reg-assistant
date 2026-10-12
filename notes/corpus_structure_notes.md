# Corpus Structure Notes

Quick skim of each PDF in `data/raw/` noting structural markers that will
matter for chunking (Parts/Sections, table of contents, schedules,
annexes). Several of the Nigerian Federal Acts are scans of the printed
Official Gazette — they contain **no embedded text layer**, so their
structure is described from the visual page renders rather than via
text extraction.

---

## hefamaa_quickguide.pdf
- **Type:** Informal user-guide / portal walkthrough (19 pages,
  Lagos State HEFAMAA e-registration portal, dated Feb 2022).
- **Structure:** Heavily visual / screenshot-driven. Each page is one
  "How it works – <step>" screen (Register Profile → Verify Profile →
  Dashboard → Register Facility → Facility Types → Uploading Letter
  of Intent → …).
- **Numbered Parts / Sections:** **No.** No PART / SECTION / Chapter
  numbering is used; instead steps are presented as a sequence of
  illustrated walk-through pages, with one page listing facility types
  as a flat numbered list (1. Hospital … 20. Mortuary) — that is a list
  of categories, not a legal section hierarchy.
- **Has a table of contents:** **No** (cover + step pages, no TOC page).
- **Schedules / Annexes / Appendices:** **No** — ends after upload /
  document-submission screens; no appendices.
- **Notable:** Every page is an image of the portal UI with overlaid
  text callouts; body text is short captions. The text layer is
  extractable (pypdf/pymupdf can read it) but sparse. Expect chunker to
  treat the whole document as `FULL_DOCUMENT` (no regex-recognisable
  section headers), but short pages/chunks will chunk cleanly at
  paragraph breaks.

---

## mlscn_guidelines.pdf
- **Type:** MLSCN National Guidelines for Setting up a Medical
  Laboratory in Nigeria (Dec 2012), 11 pages.
- **Structure:** Numbered decimal sections (1.0 INTRODUCTION,
  2.0 CATEGORIES OF LABORATORY SERVICES, 3.0 LABORATORY SPACE,
  4.0 QUALITY SYSTEM REQUIREMENTS … up to 9.0 EQUIPMENT/INSTRUMENT/
  SUPPLIES), with sub-clauses like 4.1, 8.3.1. Clauses align to the
  12 Quality System Essentials.
- **Numbered Parts / Sections:** Numbered **sections** (1.0–9.0) with
  decimal sub-sections. No PART (Roman-numeral) divisions.
- **Has a table of contents:** **Yes** — a labelled "TABLE OF CONTENT"
  on page 3 listing Forward, Acknowledgement, Abbreviation, TOC,
  Introduction, and each numbered section with page numbers.
- **Schedules / Annexes / Appendices:** **Yes — three appendices**
  (`APPENDIX 1`, `APPENDIX 2`, `APPENDIX 3`). Appendix 1 is a
  checklist of equipment by specialty; Appendix 2 is a list of tests
  for each laboratory level (Primary/Secondary/Tertiary) in
  multi-column table form; Appendix 3 appears to be the list of
  contributors/acknowledgement panel at the end.
- **Notable:** Contains multi-column comparison tables (Primary vs
  Secondary vs Tertiary lab specs) which PDF extraction may flatten.
  The decimal numbering (`4.1`, `8.3.1`) is ideal for the chunker's
  `Section 4.3` pattern, but the bare single-digit `1.`/`2.` forms in
  equipment lists may also match as pseudo-headers.

---

## national_health_act_2014_compressed.pdf
- **Type:** National Health Act, 2014 — Federal Republic of Nigeria
  Official Gazette No. 145, Vol. 101 (Lagos, 27 Oct 2014), 40 pages.
- **Structure:** Classic enacted-Act layout, published as a Gazette
  supplement (Act No. 8; pages A139–A172).
- **Numbered Parts / Sections:** **Yes.** Opens with an "ARRANGEMENT
  OF SECTIONS" that groups numbered sections into **PART I … PART V**
  (Roman-numeral Parts). Visible Parts from the Arrangement page:
  - Part I — Responsibility for Health and Eligibility for Health
    Services and Establishment of National Health System (Sections
    1–11)
  - Part II — Health Establishments and Technologies (Sections 12–19)
  - Part III — Rights and Obligations of Users and Healthcare
    Personnel (Sections 20–22; continues on later pages)
  Sections run at least into the 40s (an Interpretation clause is
  visible near the end).
- **Has a table of contents:** The "Arrangement of Sections" page
  (page A139) acts as the TOC, listing every section by number and
  title within its Part. There is no separate TOC beyond that.
- **Schedules / Annexes / Appendices:** The gazette's certification /
  enactment page is at the end; no separate Schedules were visible in
  the last pages inspected. If any schedule exists it is on the pages
  not sampled (likely Schedule is just the assent page at the end).
  **No Annexes / Appendices** visible.
- **Notable:** **Scanned image PDF — no embedded text layer**
  (pymupdf reports 0 text characters, 1 image per page). Will require
  OCR before the chunker can parse its structure; the PART/SECTION
  regex will not fire on raw extracted text until OCR is applied.

---

## ndpa_2023.pdf
- **Type:** Nigeria Data Protection Act, 2023 — 47 pages; published as
  a Bill/Act with explanatory memorandum and "Arrangement of
  Sections".
- **Structure:** Same Gazette-style Act layout as the National Health
  Act 2014: opens with an EXPLANATORY MEMORANDUM, then an
  "Arrangement of Sections" listing Parts (Roman) and numbered
  sections (Arabic).
- **Numbered Parts / Sections:** **Yes — Parts I through XII**
  (PART I OBJECTIVES AND APPLICATION; PART II ESTABLISHMENT OF THE
  NIGERIA DATA PROTECTION COMMISSION AND ITS GOVERNING COUNCIL;
  PART III APPOINTMENT OF THE NATIONAL COMMISSIONER…; PART IV
  FINANCIAL PROVISIONS; PART V PRINCIPLES AND LAWFUL BASIS GOVERNING
  PROCESSING OF PERSONAL DATA; PART VI RIGHTS OF A DATA SUBJECT;
  PART VII DATA SECURITY; PART VIII CROSS-BORDER TRANSFERS OF
  PERSONAL DATA; PART IX REGISTRATION AND FEES; PART X ENFORCEMENT;
  PART XI LEGAL PROCEEDINGS; PART XII MISCELLANEOUS PROVISIONS).
  Sections numbered sequentially 1–60 across the Parts.
- **Has a table of contents:** The "Arrangement of Sections" (early
  pages, visible on page 2) serves as the TOC; no separate contents
  page.
- **Schedules / Annexes / Appendices:** No SCHEDULE/ANNEX heading
  visible in the TOC pages or the last page (which is the Clerk's
  certification signature page). Appears to be 60 sections in 12
  Parts with no schedules/annexes.
- **Notable:** **Scanned image PDF — no embedded text layer** (0 text
  chars, 1 image per page). Requires OCR for chunking. The
  explanatory memorandum is a single short un-numbered page before
  the TOC.

---

## ndpc_guidance_2024.pdf
- **Type:** NDPC Guidance Notice NDPC/HQ/GN/VOL.03/B/24 —
  "Registration of Data Controllers and Data Processors of Major
  Importance", dated 19 Dec 2024, 6 pages.
- **Structure:** Short regulatory notice written in WHEREAS / AND
  WHEREAS / CONSIDERING / NOTING / FURTHER CONSIDERING / THUS
  preamble form, followed by numbered operative paragraphs.
- **Numbered Parts / Sections:** **Numbered paragraphs 1–7** (e.g.
  "1. Designation of Data Controllers and Data Processors of Major
  Importance", "2. Classification …", "3. Specific Types … and their
  Fees", "4. Data Controllers that are Not of Major Importance",
  "5. Statutory Obligations …", "7. Data Processing Fees").
  Sub-clauses use (1)/(2)/(3)/(a)/(b)/(c) and Roman i/ii/iii numbering.
  No PART divisions. The notice explicitly cites Sections 5d, 6(c),
  44, 45 and 65 of the NDPA 2023.
- **Has a table of contents:** **No.** It is a 6-page notice; no TOC.
- **Schedules / Annexes / Appendices:** **No.**
- **Notable:** Born-digital PDF with a clean extractable text layer;
  the simple numbered-paragraph format (1., 2., 3. … on short lines)
  will match the chunker's "12." heading pattern — expect each
  top-level numbered paragraph to be detected as its own section.

---

## nhia_act_2022.pdf
- **Type:** National Health Insurance Authority Act, 2022 — Federal
  Republic of Nigeria Official Gazette No. 95, Vol. 109 (Lagos,
  24 May 2022), Act No. 17, pages A625–A652, 31 pages.
- **Structure:** Same Gazette Act layout as the 2014 National Health
  Act: cover page → "Arrangement of Sections" (TOC) → numbered
  sections grouped into Parts → assent page.
- **Numbered Parts / Sections:** **Yes.** Visible from the
  Arrangement of Sections page (page A625):
  - Part I — Establishment of the National Health Insurance Authority
    (Sections 1–12)
  - Part II — Types of Health Insurance Schemes (Sections 13–23)
  - Part III — Implementation of Basic Health Care Provision Fund
    and Establishment of Vulnerable Group Fund (Sections 24–27
    visible, further sections continue)
  Parts continue to cover offences/penalties, financial provisions,
  etc. The long title notes that this Act repeals the National Health
  Insurance Scheme Act Cap. N42 LFN 2004.
- **Has a table of contents:** The "Arrangement of Sections" page
  serves as the TOC; no separate contents page.
- **Schedules / Annexes / Appendices:** The final page (visible) is a
  **SCHEDULE** table (columns: Short Title, Long Title, Summary of
  Contents, Date Passed by Senate, Date Passed by House of
  Representatives) — so at least one Schedule is present. No other
  annexes visible.
- **Notable:** **Scanned image PDF — no embedded text layer** (0 text
  chars). Requires OCR for automated chunking.

---

## nhia_operational_guidelines_2023.pdf
- **Type:** NHIA Operational Guidelines 2023 (NHIA corporate cover
  with medical imagery; ISBN: 978 2397 245), 22 pages; CamScanner
  watermark visible on image-only pages.
- **Structure:** Formal published guidelines with front matter +
  numbered Sections with two-level decimal sub-sections
  (1.1, 1.2, …, 2.2.1, 2.2.2 …).
- **Numbered Parts / Sections:** **Yes.** The visible Table of
  Contents page (labelled "TABLE OF CONTENTS" in red, page iii)
  lists:
  - Front matter: Foreword, Preface, Acknowledgements, Abbreviations,
    Definition of Key Terms
  - **SECTION 1: GOVERNANCE** (1.1–1.11: Introduction, Vision/Mission,
    Core Values, Administrative Structures, Functions &
    Responsibilities, HIUOR, NMSI, Strategic Plan, Funding,
    Accountability, Review of Guidelines)
  - **SECTION 2: SCHEMES AND PROGRAMMES** (2.1 Introduction,
    2.2 Contributory Social Health Insurance Scheme (CSHIS), with
    2.2.1–2.2.4 sub-entries, 2.3 Public/Organised Private Sector,
    2.4 Armed Forces/Police/Uniformed Services, …)
  Sections continue beyond the visible TOC page. No Roman-numeral
  PART divisions — top-level uses "SECTION N: TITLE" format.
- **Has a table of contents:** **Yes** — a formal, large TOC (page iii)
  with Roman-numeral front matter and Arabic-numeral sections to 2.x.
- **Schedules / Annexes / Appendices:** Not visible in the pages
  inspected (cover through early Section 2); TOC continues on later
  pages I didn't fully render. TBC — expect possible annexes/appendices
  at the back (forms, lists of facilities, fee schedules) given it is
  an operational guidelines document, but none confirmed.
- **Notable:** Appears to be a **phone-photo CamScanner scan**
  (pymupdf reports only ~240 text chars across 22 pages, most of
  which is the literal string "CamScanner"). The cover/copyright/TOC
  pages render as images; body pages likely also image-only. Requires
  OCR for extraction.

---

## who_lqms_handbook.pdf
- **Type:** WHO Laboratory Quality Management System Handbook
  (Version 1.1, 2011), 248 pages — the largest document in the
  corpus.
- **Structure:** Full-length training handbook organised around the
  CLSI 12 Quality System Essentials framework. Uses WHO's
  "chapter-section" style with hyphenated sub-section numbering:
  top-level chapters numbered 1–15, with sub-sections like 1-1, 1-2,
  … 7-3, 14-4 (NOT the decimal `1.1`/`4.3` style used elsewhere in
  the corpus).
- **Numbered Parts / Sections:** **Chapters 1–15** (numbered), plus
  sub-sections using "N-M" numbering (e.g. 6 Process control—
  introduction to quality control; 7 Process control—QC for
  quantitative tests; 8 Process control—QC for qualitative and
  semi-quantitative tests; 13 Customer service; 14 Occurrence
  management, etc.). No PART/SECTION legal-act divisions; this is a
  handbook chapter format.
- **Has a table of contents:** **Yes — a detailed, multi-page
  Table of Contents** (pp. 3–5) listing Acknowledgements, Foreword,
  Key words, all 15 chapters and every sub-section with page
  numbers.
- **Schedules / Annexes / Appendices:** **Glossary** at p. 223 is
  listed in the TOC; no separate "Annex" or "Appendix" entries found
  in the TOC. No annexes/appendices visible in the TOC scan; the back
  matter ends with blank NOTES pages (246–248).
- **Notable:** Born-digital PDF with clean extractable text (≈440k
  characters). The chapter/sub-section numbering uses hyphens
  (`1-1`, `7-5`) rather than dots, so the chunker's current
  `Section 4.3` and `12.` patterns **will not match** these headings
  directly — the document will likely either fall back to
  `FULL_DOCUMENT` or pick up incidental numbered lists. (If this
  matters, we may want to extend `_SECTION_PATTERNS` with a
  `\d+-\d+` chapter-subsection pattern; flagging here.)

---

## Cross-document observations

| Document                       | Text layer? | Parts | Sections | TOC | Schedules/Annexes |
|--------------------------------|-------------|-------|----------|-----|--------------------|
| hefamaa_quickguide.pdf         | Yes (sparse)| no    | no       | no  | none |
| mlscn_guidelines.pdf           | Yes         | no    | decimal §§ (1.0–9.0, 4.1, 8.3.1) | yes | 3 appendices |
| national_health_act_2014…      | **No (scan)** | Roman Parts I–V | numbered §§ 1–40+ | Arrangement-of-Sections page | assent page |
| ndpa_2023.pdf                  | **No (scan)** | Roman Parts I–XII | numbered §§ 1–60 | Arrangement-of-Sections page | none visible |
| ndpc_guidance_2024.pdf         | Yes         | no    | numbered ¶¶ 1–7 + (a)/(b)/(c), i/ii/iii | no | none |
| nhia_act_2022.pdf              | **No (scan)** | Roman Parts (I–III + more) | numbered §§ 1–27+ visible | Arrangement-of-Sections page | at least 1 SCHEDULE |
| nhia_operational_guidelines…   | **No (CamScanner scan)** | no | SECTION 1/2/… with decimal sub§§ (1.1, 2.2.1…) | yes | TBC |
| who_lqms_handbook.pdf          | Yes         | chapters 1–15 | hyphenated sub§§ (1-1, 7-3, 14-2) | yes (detailed, multi-page) | glossary only |

- Four of eight documents (the three Gazette Acts + NHIA operational
  guidelines) are **image-only scans** and will need OCR before the
  regex-based section splitter can find Part/Section markers.
- The born-digital documents use **three different heading numbering
  conventions**:
  - MLSCN, NDPC guidance — decimal (`1.0`, `4.1`, `1.`) — matches the
    chunker's current patterns.
  - NHIA operational guidelines — capitalized `SECTION N:` with
    decimal sub-sections — matches if `SECTION`/`Section` regex is
    active (it is).
  - WHO handbook — hyphenated (`1-1`, `7-5`) — **not matched** by
    current regex; will fall to FULL_DOCUMENT.
