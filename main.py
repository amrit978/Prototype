"""
Material Code Harmonization - Prototype backend
SIH26099 - AI-Driven Standardization and Harmonization of Material Codes Across CPSEs

Run with:
    uvicorn main:app --reload
Then open http://127.0.0.1:8000 in your browser.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime, timezone
import io

from matching import find_matches

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "harmonization.db"

app = FastAPI(title="Material Code Harmonizer")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS approved_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            a_code TEXT,
            a_description TEXT,
            b_code TEXT,
            b_description TEXT,
            confidence REAL,
            harmonized_code TEXT,
            status TEXT,
            reviewer_name TEXT,
            reviewed_at TEXT
        )
    """)
    # Migrate existing DB — add columns if they don't exist yet
    cur = conn.execute("PRAGMA table_info(approved_matches)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if "reviewer_name" not in existing_cols:
        conn.execute("ALTER TABLE approved_matches ADD COLUMN reviewer_name TEXT")
    if "reviewed_at" not in existing_cols:
        conn.execute("ALTER TABLE approved_matches ADD COLUMN reviewed_at TEXT")
    conn.commit()
    conn.close()


init_db()


class ApprovalRequest(BaseModel):
    a_code: str
    a_description: str
    b_code: str
    b_description: str
    confidence: float
    decision: str           # "approve" or "reject"
    reviewer_name: str = "Anonymous"


class RemoveRequest(BaseModel):
    a_code: str
    b_code: str


def get_data_file(filename: str) -> Path:
    data_path = BASE_DIR / "data" / filename
    if data_path.exists():
        return data_path
    return BASE_DIR / filename


@app.get("/api/materials")
def get_materials():
    """Return the raw material lists for both sample CPSEs (for transparency in the demo)."""
    df_a = pd.read_csv(get_data_file("cpse_a.csv"))
    df_b = pd.read_csv(get_data_file("cpse_b.csv"))
    return {
        "cpse_a": df_a.to_dict(orient="records"),
        "cpse_b": df_b.to_dict(orient="records"),
    }


@app.get("/api/match")
def get_matches(threshold: float = 0.55):
    """Run the matching pipeline and return proposed harmonization matches."""
    import matching
    import importlib
    importlib.reload(matching)
    df_a = pd.read_csv(get_data_file("cpse_a.csv"))
    df_b = pd.read_csv(get_data_file("cpse_b.csv"))
    matches = matching.find_matches(df_a, df_b, threshold=threshold)

    # Mark which ones are already reviewed
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT a_code, b_code, status FROM approved_matches")
    reviewed = {(row[0], row[1]): row[2] for row in cur.fetchall()}
    conn.close()

    for m in matches:
        m["status"] = reviewed.get((m["a_code"], m["b_code"]), "pending")

    return {"count": len(matches), "matches": matches}


@app.post("/api/review")
def review_match(req: ApprovalRequest):
    """Record a human reviewer's approve/reject decision on a proposed match."""
    conn = sqlite3.connect(DB_PATH)
    harmonized_code = f"HRM-{req.a_code}-{req.b_code}" if req.decision == "approve" else None
    reviewed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """INSERT INTO approved_matches
           (a_code, a_description, b_code, b_description, confidence,
            harmonized_code, status, reviewer_name, reviewed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (req.a_code, req.a_description, req.b_code, req.b_description,
         req.confidence, harmonized_code, req.decision,
         req.reviewer_name.strip() or "Anonymous", reviewed_at),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "harmonized_code": harmonized_code}


@app.get("/api/approved")
def get_approved():
    """List all harmonized codes generated so far, including audit trail fields."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT a_code, a_description, b_code, b_description, confidence, "
        "harmonized_code, status, reviewer_name, reviewed_at "
        "FROM approved_matches ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    cols = ["a_code", "a_description", "b_code", "b_description", "confidence",
            "harmonized_code", "status", "reviewer_name", "reviewed_at"]
    return [dict(zip(cols, row)) for row in rows]


@app.post("/api/remove")
def remove_match(req: RemoveRequest):
    """Remove a reviewed match from the log, returning it to pending status in the queue."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "DELETE FROM approved_matches WHERE a_code = ? AND b_code = ?",
        (req.a_code, req.b_code),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


REQUIRED_COLUMNS = {"material_code", "description", "category", "material_type",
                    "dimension", "specification", "application", "unit"}


@app.post("/api/upload/{cpse}")
async def upload_csv(cpse: str, file: UploadFile = File(...)):
    """Upload a new CSV file for CPSE-A or CPSE-B, replacing the existing data."""
    if cpse not in ("a", "b"):
        raise HTTPException(status_code=400, detail="cpse must be 'a' or 'b'")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required columns: {', '.join(sorted(missing))}"
        )

    target = get_data_file(f"cpse_{cpse}.csv")
    with open(target, "wb") as f:
        f.write(contents)

    return {"ok": True, "rows": len(df), "filename": file.filename}


# Serve the frontend
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root():
    html_file = static_dir / "index.html"
    if not html_file.exists():
        html_file = BASE_DIR / "index.html"
    return FileResponse(html_file)

