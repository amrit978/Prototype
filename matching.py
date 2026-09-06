"""
Core matching engine for material code harmonization (v2 - structured fields).

Approach:
1. Normalize text fields (expand abbreviations, lowercase, split glued units)
2. Compute TEXT similarity on the free-text description (TF-IDF + cosine)
3. Compute a STRUCTURED similarity score by comparing material_type and
   dimension fields directly after normalization - this is the key upgrade
   over v1, since two items with wildly different descriptions but the same
   material type and dimension are very likely the same physical item.
4. Combine both into one final confidence score.

Comparing structured fields directly is more reliable than pure text matching
because "50mm" vs "50 MM Dia" is trivially the same after normalization, even
when the surrounding sentence is completely reworded.
"""

import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ABBREVIATIONS = {
    r"\bms\b": "mild steel",
    r"\bss\b": "stainless steel",
    r"\bss(\d{3})\b": r"stainless steel \1",
    r"\bcs\b": "carbon steel",
    r"\bci\b": "cast iron",
    r"\bdia\b": "diameter",
    r"\bsch\b": "schedule",
    r"\bnb\b": "nominal bore",
    r"\bcl\b": "class",
    r"\bwnrf\b": "weld neck raised face",
    r"\bhp\b": "horsepower",
    r"\bph\b": "phase",
    r"\bpr\b": "pair",
    r"\bea\b": "each",
    r"\bmm\b": "millimeter",
    r"\bmtr\b": "meter",
    r"\bkg\b": "kilogram",
    r"\bltr\b": "liter",
    r"\bsqm\b": "square meter",
    r"\bsq\.?mm\b": "square millimeter",
    r"\bnos\b": "numbers",
    r"\bqty\b": "quantity",
    r"\bcap\b": "capacity",
    r"\bthk\b": "thick",
    r"\bcolour\b": "color",
    r"\bstd\b": "standard",
}


def normalize(text: str) -> str:
    """Lowercase, expand abbreviations, strip punctuation noise, split glued units, normalize inch/mm dimensions."""
    if not isinstance(text, str):
        return ""
    t = text.lower()
    t = re.sub(r"[-/,#]", " ", t)
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)
    t = re.sub(r"([a-z])(\d)", r"\1 \2", t)
    # Dimension equivalences (Inch to mm)
    t = re.sub(r"\b1\s*(?:inch|in)\b", "25 mm", t)
    t = re.sub(r"\b2\s*(?:inch|in)\b", "50 mm", t)
    t = re.sub(r"\b3\s*(?:inch|in)\b", "80 mm", t)
    t = re.sub(r"\b4\s*(?:inch|in)\b", "100 mm", t)
    t = re.sub(r"\b6\s*(?:inch|in)\b", "150 mm", t)
    t = re.sub(r"\b24\s*(?:inch|in)\b", "600 mm", t)
    for pattern, replacement in ABBREVIATIONS.items():
        t = re.sub(pattern, replacement, t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def field_similarity(a: str, b: str) -> float:
    """
    Compare two short structured fields (material_type or dimension) after
    normalization. Returns 1.0 for an exact match after normalization,
    a partial score for word overlap, or 0.0 for no overlap at all.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    words_a, words_b = set(na.split()), set(nb.split())
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    union = len(words_a | words_b)
    return overlap / union if union else 0.0


def find_matches(df_a, df_b, threshold: float = 0.55,
                  text_weight: float = 0.4, material_weight: float = 0.35,
                  dimension_weight: float = 0.25):
    """
    df_a, df_b: pandas DataFrames with columns
        [material_code, description, category, material_type, dimension,
         specification, application, unit]

    Combines three signals into one confidence score per pair:
      - text_weight: similarity of the free-text description (TF-IDF)
      - material_weight: similarity of the material_type field
      - dimension_weight: similarity of the dimension field

    Returns a list of proposed match dicts, sorted by confidence descending.
    """
    norm_desc_a = [normalize(d) for d in df_a["description"]]
    norm_desc_b = [normalize(d) for d in df_b["description"]]

    vectorizer = TfidfVectorizer(ngram_range=(1, 2))
    all_texts = norm_desc_a + norm_desc_b
    tfidf = vectorizer.fit_transform(all_texts)

    vec_a = tfidf[: len(norm_desc_a)]
    vec_b = tfidf[len(norm_desc_a):]
    text_sim_matrix = cosine_similarity(vec_a, vec_b)

    matches = []
    for i in range(len(df_a)):
        best_j = None
        best_score = 0.0
        best_breakdown = None

        for j in range(len(df_b)):
            text_sim = float(text_sim_matrix[i][j])
            material_sim = field_similarity(
                df_a.iloc[i]["material_type"], df_b.iloc[j]["material_type"]
            )
            dimension_sim = field_similarity(
                df_a.iloc[i]["dimension"], df_b.iloc[j]["dimension"]
            )

            combined = (
                text_weight * text_sim
                + material_weight * material_sim
                + dimension_weight * dimension_sim
            )

            if combined > best_score:
                best_score = combined
                best_j = j
                best_breakdown = {
                    "text_similarity": round(text_sim * 100, 1),
                    "material_similarity": round(material_sim * 100, 1),
                    "dimension_similarity": round(dimension_sim * 100, 1),
                }

        if best_j is not None and best_score >= threshold:
            row_a = df_a.iloc[i]
            row_b = df_b.iloc[best_j]
            matches.append({
                "a_code": row_a["material_code"],
                "a_description": row_a["description"],
                "a_category": row_a["category"],
                "a_material_type": row_a["material_type"],
                "a_dimension": row_a["dimension"],
                "a_unit": row_a["unit"],
                "b_code": row_b["material_code"],
                "b_description": row_b["description"],
                "b_category": row_b["category"],
                "b_material_type": row_b["material_type"],
                "b_dimension": row_b["dimension"],
                "b_unit": row_b["unit"],
                "confidence": round(best_score * 100, 1),
                "breakdown": best_breakdown,
            })

    matches.sort(key=lambda m: m["confidence"], reverse=True)
    return matches
