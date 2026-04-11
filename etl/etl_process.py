"""
ETL Pipeline  —  Extract → Transform → Load
=============================================
Usage:
    python etl/etl_process.py

Behaviour:
    • If target CSV already exists  → prints a data summary and exits.
    • If target CSV does NOT exist  → runs the full pipeline and saves output.
"""

import os
import sys
import hashlib
import pandas as pd

# ── Project root on sys.path ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    SOURCE_FILE, TARGET_DIR, TARGET_FILE, MD5_FILE,
    VALID_STATUSES, VALID_PAYMENTS, VALID_REGIONS, VALID_CATEGORIES,
    CRITICAL_COLUMNS, COMPOSITE_KEY,
    EMAIL_REGEX, PHONE_REGEX,
    QUANTITY_MIN, QUANTITY_MAX, AGE_MIN, AGE_MAX,
    RATING_MIN, RATING_MAX, PRODUCT_NAME_MAX_LEN,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  EXTRACT
# ═══════════════════════════════════════════════════════════════════════════════

def extract() -> pd.DataFrame:
    df = pd.read_excel(SOURCE_FILE, sheet_name="ORDERS_RAW",
                       header=1, dtype=str)
    print(f"[EXTRACT]   {len(df):,} rows read from source")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  TRANSFORM
# ═══════════════════════════════════════════════════════════════════════════════

def transform(df: pd.DataFrame,
              valid_customer_ids: set | None = None) -> pd.DataFrame:
    before = len(df)

    # 1. Strip whitespace from all text columns
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    # 2. Cast integer columns (invalid → NaN)
    for col in ["AGE", "QUANTITY", "RATING"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # 3. Cast decimal columns
    for col in ["UNIT PRICE", "TOTAL AMOUNT", "SALARY USD"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 4. Parse ORDER DATE (invalid → NaT)
    df["ORDER DATE"] = pd.to_datetime(df["ORDER DATE"], errors="coerce")

    # 5. Drop rows where critical columns are null
    df = df.dropna(subset=CRITICAL_COLUMNS)

    # 6. Drop duplicate composite key
    df = df.drop_duplicates(subset=COMPOSITE_KEY, keep="first")

    # 7. Keep only valid categoricals
    df = df[df["STATUS"].isin(VALID_STATUSES)]
    df = df[df["PAYMENT METHOD"].isin(VALID_PAYMENTS)]
    df = df[df["REGION"].isin(VALID_REGIONS)]
    df = df[df["PRODUCT CATEGORY"].isin(VALID_CATEGORIES)]

    # 8. No future dates
    df = df[df["ORDER DATE"] <= pd.Timestamp.today().normalize()]

    # 9. Numeric range filters
    df = df[df["QUANTITY"].between(QUANTITY_MIN, QUANTITY_MAX)]
    df = df[df["UNIT PRICE"] > 0]
    df = df[df["RATING"].between(RATING_MIN, RATING_MAX)]
    df = df[df["AGE"].between(AGE_MIN, AGE_MAX)]
    df = df[df["SALARY USD"] > 0]

    # 10. Regex filters
    df = df[df["CUSTOMER EMAIL"].str.match(EMAIL_REGEX, na=False)]
    df = df[df["CUSTOMER PHONE"].str.match(PHONE_REGEX, na=False)]

    # 11. String length filter
    df = df[df["PRODUCT NAME"].str.len() <= PRODUCT_NAME_MAX_LEN]

    # 12. Referential integrity — customer ID
    if valid_customer_ids is not None:
        df = df[df["CUSTOMER ID"].isin(valid_customer_ids)]

    # 13. Recalculate TOTAL AMOUNT = QUANTITY × UNIT PRICE
    df["TOTAL AMOUNT"] = (df["QUANTITY"].astype(float) * df["UNIT PRICE"]).round(2)

    df = df.reset_index(drop=True)
    print(f"[TRANSFORM] {before - len(df):,} rows removed  |  "
          f"{len(df):,} clean rows remain")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  LOAD
# ═══════════════════════════════════════════════════════════════════════════════

def load(df: pd.DataFrame) -> None:
    os.makedirs(TARGET_DIR, exist_ok=True)
    df.to_csv(TARGET_FILE, index=False)
    print(f"[LOAD]      {len(df):,} rows saved → {TARGET_FILE}")

    checksum = compute_md5(TARGET_FILE)
    with open(MD5_FILE, "w") as f:
        f.write(checksum)
    print(f"[LOAD]      MD5 checksum saved → {MD5_FILE}")


def compute_md5(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
#  PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

def run_pipeline() -> pd.DataFrame:
    df = extract()

    # Load reference table for customer-ID validation
    try:
        cref = pd.read_excel(SOURCE_FILE, sheet_name="CUSTOMERS_REF",
                             header=1, dtype=str)
        valid_customer_ids = set(
            cref["CUSTOMER ID"].dropna().str.strip().tolist()
        )
    except Exception:
        valid_customer_ids = None

    df = transform(df, valid_customer_ids=valid_customer_ids)
    load(df)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
#  TARGET CHECK  —  skip ETL if target already exists
# ═══════════════════════════════════════════════════════════════════════════════

def check_existing_target() -> None:
    print("=" * 60)
    print("  TARGET DATA SUMMARY")
    print("=" * 60)

    df = pd.read_csv(TARGET_FILE)
    print(f"\n  Rows    : {len(df):,}")
    print(f"  Columns : {len(df.columns)}")

    # Null summary
    nulls = df.isnull().sum()
    cols_with_nulls = nulls[nulls > 0]
    if cols_with_nulls.empty:
        print("  Nulls   : None")
    else:
        print(f"  Nulls   : {len(cols_with_nulls)} column(s) have nulls")
        for col, cnt in cols_with_nulls.items():
            print(f"            • {col}: {cnt}")

    # Data-type summary
    print("\n  Data Types:")
    for col in df.columns:
        print(f"    {col:<22s}  {df[col].dtype}")

    # MD5
    if os.path.exists(MD5_FILE):
        with open(MD5_FILE) as f:
            stored = f.read().strip()
        current = compute_md5(TARGET_FILE)
        match = "✓ matches" if stored == current else "✗ MISMATCH"
        print(f"\n  MD5     : {stored}  ({match})")

    print("\n" + "=" * 60)
    print("  Target file already exists — ETL skipped.")
    print("  Delete the target file to force a fresh ETL run.")
    print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  ETL PIPELINE")
    print("=" * 60)

    if os.path.exists(TARGET_FILE):
        check_existing_target()
    else:
        print("\n  Target file not found — running full ETL pipeline ...\n")
        run_pipeline()
        print("\n  ETL pipeline completed successfully.")
