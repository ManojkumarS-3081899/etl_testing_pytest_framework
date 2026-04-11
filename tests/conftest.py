import os
import sys
import pytest
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    SOURCE_FILE, TARGET_FILE, MD5_FILE,
    VALID_STATUSES, VALID_PAYMENTS, VALID_REGIONS, VALID_CATEGORIES,
    CRITICAL_COLUMNS, COMPOSITE_KEY,
    EMAIL_REGEX, PHONE_REGEX,
    QUANTITY_MIN, QUANTITY_MAX, AGE_MIN, AGE_MAX,
    RATING_MIN, RATING_MAX, PRODUCT_NAME_MAX_LEN,
)


@pytest.fixture(scope="session")
def source_df() -> pd.DataFrame:
    
    return pd.read_excel(SOURCE_FILE, sheet_name="ORDERS_RAW",
                         header=1, dtype=str)


@pytest.fixture(scope="session")
def target_df() -> pd.DataFrame:
    
    assert os.path.exists(TARGET_FILE), (
        f"Target file not found: {TARGET_FILE}\n"
        "Run  python etl/etl_process.py  first."
    )
    df = pd.read_csv(TARGET_FILE, dtype={"CUSTOMER PHONE": str})
    for col in ["AGE", "QUANTITY", "RATING"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ["UNIT PRICE", "TOTAL AMOUNT", "SALARY USD"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "ORDER DATE" in df.columns:
        df["ORDER DATE"] = pd.to_datetime(df["ORDER DATE"], errors="coerce")
    return df


@pytest.fixture(scope="session")
def expected_df(source_df, validation_rules) -> pd.DataFrame:
    
    df = source_df.copy()

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    for col in ["AGE", "QUANTITY", "RATING"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ["UNIT PRICE", "TOTAL AMOUNT", "SALARY USD"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ORDER DATE"] = pd.to_datetime(df["ORDER DATE"], errors="coerce")

    df = df.dropna(subset=CRITICAL_COLUMNS)
    df = df.drop_duplicates(subset=COMPOSITE_KEY, keep="first")

    df = df[df["STATUS"].isin(VALID_STATUSES)]
    df = df[df["PAYMENT METHOD"].isin(VALID_PAYMENTS)]
    df = df[df["REGION"].isin(VALID_REGIONS)]
    df = df[df["PRODUCT CATEGORY"].isin(VALID_CATEGORIES)]

    df = df[df["ORDER DATE"] <= pd.Timestamp.today().normalize()]

    df = df[df["QUANTITY"].between(QUANTITY_MIN, QUANTITY_MAX)]
    df = df[df["UNIT PRICE"] > 0]
    df = df[df["RATING"].between(RATING_MIN, RATING_MAX)]
    df = df[df["AGE"].between(AGE_MIN, AGE_MAX)]
    df = df[df["SALARY USD"] > 0]

    df = df[df["CUSTOMER EMAIL"].str.match(EMAIL_REGEX, na=False)]
    df = df[df["CUSTOMER PHONE"].str.match(PHONE_REGEX, na=False)]
    df = df[df["PRODUCT NAME"].str.len() <= PRODUCT_NAME_MAX_LEN]

    valid_ids = validation_rules.get("valid_customer_ids")
    if valid_ids is not None:
        df = df[df["CUSTOMER ID"].isin(valid_ids)]

    df["TOTAL AMOUNT"] = (df["QUANTITY"].astype(float) * df["UNIT PRICE"]).round(2)
    return df.reset_index(drop=True)


@pytest.fixture(scope="session")
def validation_rules() -> dict:
    
    rules = {"valid_customer_ids": None, "expected_partition_months": None}
    try:
        cref = pd.read_excel(SOURCE_FILE, sheet_name="CUSTOMERS_REF",
                             header=1, dtype=str)
        rules["valid_customer_ids"] = set(
            cref["CUSTOMER ID"].dropna().str.strip().tolist()
        )
    except Exception:
        print("Warning: CUSTOMERS_REF sheet not found, skipping referential integrity")
    try:
        pc = pd.read_excel(SOURCE_FILE, sheet_name="PARTITION_CHECK",
                           header=1, dtype=str)
        months = pc["EXPECTED MONTH"].dropna().astype(str)
        months = months[months.str.match(r"^\d{4}-\d{2}$")]
        rules["expected_partition_months"] = set(months.tolist())
    except Exception:
        print("Warning: PARTITION_CHECK sheet not found, skipping partition completeness check")
    return rules


@pytest.fixture(scope="session")
def md5_hash_path() -> str:
    return MD5_FILE
