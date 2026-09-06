# Material Code Harmonizer - SIH26099 Prototype

**Problem Statement:** AI-Driven Standardization and Harmonization of Material Codes Across CPSEs (Ministry of Petroleum & Natural Gas)

---

## Note on the data

The files `cpse_a.csv` and `cpse_b.csv` are **synthetic, illustrative data** - not real records from any actual CPSE.
Real material master data is internal, confidential procurement data and is not publicly available.

The synthetic data was built to realistically represent the *kind* of naming inconsistencies that genuinely occur
across different companies' ERP systems for common oil & gas industry materials (pipes, valves, flanges, pumps,
cables, safety equipment, etc.). State clearly in your pitch that this is representative demo data, not real CPSE data.
If you can get sanitized sample data from a mentor or SIH nodal contact, swap it in.

---

## What this prototype does

1. Loads two CSV files representing two different CPSEs' material catalogs
2. Normalizes text (expands abbreviations like "MS" -> "mild steel", splits glued number+unit tokens like "50mm" -> "50 mm")
3. Converts descriptions into TF-IDF vectors and computes cosine similarity between every item in CPSE-A against every item in CPSE-B
4. Surfaces proposed matches above a confidence threshold in a review dashboard
5. Lets a human reviewer approve or reject each match - approved matches get a generated harmonized code logged to SQLite
6. Records a full **audit trail** of every decision: who reviewed it, and when

This is intentionally a **transparent, explainable** approach (TF-IDF + cosine similarity) rather than a deep learning
black box. For a government procurement use case, being able to explain *why* two items were matched is a genuine
strength worth highlighting in your pitch.

---

## How to run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open **http://127.0.0.1:8000** in your browser.

> `python-multipart` is required for CSV file uploads and is included in `requirements.txt`.

---

## Features

### Dashboard

| Feature | Description |
|---|---|
| Overview stats | Live count of proposed matches, approved, and pending |
| Similarity threshold slider | Adjust the confidence cutoff live and re-run matching |
| Proposed Matches table | CPSE-A vs CPSE-B pairs with full confidence score breakdown |
| Harmonization Log | All reviewed decisions with Reviewer and When columns |
| Audit Trail | Chronological timeline of every approve/reject action |

### CSV Upload (Data Sources panel)

- Replace either CPSE dataset at runtime by uploading a new `.csv` file (drag & drop or click)
- Required columns: `material_code, description, category, material_type, dimension, specification, application, unit`
- Matching pipeline re-runs automatically after a successful upload

### CSV Explorer (read-only, separate section)

- Load *any* CSV locally to inspect its rows entirely client-side - nothing is sent to the server
- Each row is annotated **Matched** or **No match** based on whether its `material_code` appears in current results
- Filter buttons: All / Matched / Not matched
- Summary bar shows filename, total rows, matched count, and unmatched count

### Audit Trail & History

- Every decision records the **reviewer name** and an **ISO 8601 timestamp** (UTC)
- Shown in the Harmonization Log table as Reviewer and When columns
- Dedicated Audit Trail panel shows a visual timeline (oldest to newest) with colour-coded icons
- Existing database records are auto-migrated when the schema is upgraded - no data loss on restart

### Reviewer Name - Mandatory

- The 'Reviewing as' field must be filled before any Approve or Reject action is allowed
- Minimum 2 characters required
- If the field is empty when acting: the bar shakes, turns red, and a warning hint appears
- The name is persisted in `localStorage` so it survives page refreshes

### Dark / Light Mode

- Toggle button in the top-right of the header (pill switch with animated knob)
- Smooth CSS-variable-driven transition between a warm off-white light theme and a deep dark theme
- All UI elements adapt via CSS custom properties - no hardcoded colours
- Preference is saved in `localStorage` and restored on reload

---

## Suggested demo flow for judges

1. Enter your name in the **Reviewing as** field
2. Show the two raw CPSE CSVs - point out the inconsistent naming conventions
3. Load the dashboard and show it auto-detects proposed matches above the threshold
4. Approve a high-confidence match - watch the harmonized code appear in the log and audit trail
5. Reject a lower-confidence one to show human oversight is real, not cosmetic
6. Move the threshold slider to show how the match count scales
7. Toggle dark mode
8. Drop one of the CSV files into the **CSV Explorer** to show the match overlay feature

---

## Project structure

```
.
|-- main.py            # FastAPI backend - API routes, SQLite DB, file serving
|-- matching.py        # Matching pipeline (TF-IDF, cosine similarity, score breakdown)
|-- index.html         # Frontend - single-file SPA (vanilla HTML / CSS / JS)
|-- cpse_a.csv         # Sample CPSE-A material catalog (synthetic demo data)
|-- cpse_b.csv         # Sample CPSE-B material catalog (synthetic demo data)
|-- harmonization.db   # SQLite database - auto-created on first run
`-- requirements.txt   # Python dependencies
```

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/match?threshold=0.55` | Run matching pipeline and return proposed pairs |
| POST | `/api/review` | Submit an approve/reject decision with reviewer name |
| GET | `/api/approved` | Fetch all reviewed decisions (includes audit fields) |
| POST | `/api/remove` | Remove a decision and re-queue the pair as pending |
| POST | `/api/upload/{a|b}` | Upload a new CSV to replace CPSE-A or CPSE-B data |
| GET | `/api/materials` | Return raw material lists for both CPSEs |

---

## Extending further

- Swap TF-IDF for sentence-transformer embeddings for better semantic matching
- Add authentication and roles (reviewer vs admin) for a more realistic enterprise feel
- Map harmonized codes to an actual standard like UNSPSC for real-world alignment
- Add export to CSV or Excel for the harmonization log
- Support matching across more than two CPSEs simultaneously
- Add email/Slack notifications when a match is approved
