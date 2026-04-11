import os
import hashlib
import numpy as np
import pandas as pd
import pytest
from scipy import stats

from config import (
    TARGET_FILE, MD5_FILE,
    EXPECTED_COLUMNS, CRITICAL_COLUMNS, COMPOSITE_KEY,
    VALID_STATUSES, VALID_PAYMENTS, VALID_REGIONS, VALID_CATEGORIES,
    ORDER_ID_REGEX, EMAIL_REGEX, PHONE_REGEX,
    QUANTITY_MIN, QUANTITY_MAX, AGE_MIN, AGE_MAX,
    RATING_MIN, RATING_MAX, PRODUCT_NAME_MAX_LEN,
    TOLERANCE, NULL_RATE_LIMIT, Z_THRESHOLD, MAX_OUTLIER_RATE,
)


# ============================================================================
#  1. ROW COUNT VALIDATION                                         @sanity
# ============================================================================

@pytest.mark.sanity
class TestRowCount:

    def test_target_is_not_empty(self, target_df):
        assert len(target_df) > 0, "Target dataset is empty."

    def test_row_count_expected_minus_target_is_zero(self, expected_df, target_df):
        diff = len(expected_df) - len(target_df)
        assert diff == 0, (
            f"Row count mismatch: expected {len(expected_df)}, "
            f"target {len(target_df)} (diff={diff})."
        )

    def test_row_count_target_minus_expected_is_zero(self, target_df, expected_df):
        diff = len(target_df) - len(expected_df)
        assert diff == 0, (
            f"Target has {diff} extra rows ({len(target_df)} vs {len(expected_df)})."
        )


# ============================================================================
#  2. DATA TYPE VALIDATION                                         @sanity
# ============================================================================

@pytest.mark.sanity
class TestDataType:

    def test_order_date_is_datetime(self, target_df):
        assert pd.api.types.is_datetime64_any_dtype(target_df["ORDER DATE"]), \
            f"ORDER DATE dtype is {target_df['ORDER DATE'].dtype}, expected datetime."

    def test_numeric_columns_are_numeric(self, target_df):
        cols = ["AGE", "QUANTITY", "UNIT PRICE", "TOTAL AMOUNT", "RATING", "SALARY USD"]
        bad = [c for c in cols if not pd.api.types.is_numeric_dtype(target_df[c])]
        assert not bad, f"Expected numeric: {bad}"

    def test_text_columns_are_string(self, target_df):
        cols = ["ORDER ID", "CUSTOMER ID", "CUSTOMER NAME",
                "STATUS", "PAYMENT METHOD", "REGION"]
        bad = [c for c in cols
               if str(target_df[c].dtype) not in ("object", "string", "str")]
        assert not bad, f"Expected string: {bad}"

    
# ============================================================================
#  3. NULL VALUE CHECK                                             @functional
# ============================================================================

@pytest.mark.functional
class TestNullCheck:

    def test_critical_nulls_minus(self, expected_df, target_df):
        for col in CRITICAL_COLUMNS:
            exp = int(expected_df[col].isna().sum())
            tgt = int(target_df[col].isna().sum())
            assert tgt - exp == 0, (
                f"{col}: expected {exp} nulls, target has {tgt}."
            )

    def test_no_column_exceeds_null_rate_limit(self, target_df):
        high = {col: f"{target_df[col].isna().mean():.1%}"
                for col in target_df.columns
                if target_df[col].isna().mean() > NULL_RATE_LIMIT}
        assert not high, f"Columns exceed {NULL_RATE_LIMIT:.0%} null rate: {high}"

    @pytest.mark.parametrize("col", ["ORDER ID", "CUSTOMER ID"])
    def test_no_whitespace_only_values(self, target_df, col):
        bad = target_df[target_df[col].astype(str).str.strip().str.len() == 0]
        assert bad.empty, f"{len(bad)} whitespace-only values in {col}."


# ============================================================================
#  4. REGEX PATTERN VALIDATION                                     @functional
# ============================================================================

@pytest.mark.functional
class TestRegexPattern:

    @pytest.mark.parametrize("col,regex,label", [
        ("ORDER ID",       ORDER_ID_REGEX, "ORDxxx+"),
        ("CUSTOMER EMAIL", EMAIL_REGEX,    "valid email"),
        ("CUSTOMER PHONE", PHONE_REGEX,    "+1XXXXXXXXXX"),
    ])
    def test_regex_minus(self, expected_df, target_df, col, regex, label):
        exp_col = expected_df[col].astype(str)
        tgt_col = target_df[col].astype(str)
        exp_valid = set(exp_col[exp_col.str.match(regex, na=False)])
        tgt_valid = set(tgt_col[tgt_col.str.match(regex, na=False)])
        diff = exp_valid - tgt_valid
        assert len(diff) == 0, (
            f"{len(diff)} valid {col} ({label}) in expected but not target: "
            f"{list(diff)[:5]}"
        )


# ============================================================================
#  5. DATE VALIDATION                                              @functional
# ============================================================================

@pytest.mark.functional
class TestDateValidation:

    def test_null_dates_minus(self, expected_df, target_df):
        exp = int(expected_df["ORDER DATE"].isna().sum())
        tgt = int(target_df["ORDER DATE"].isna().sum())
        assert tgt - exp == 0, (
            f"Null ORDER DATE: expected {exp}, target {tgt}."
        )

    def test_dates_within_2020_to_2030(self, target_df):
        bad = target_df[
            (target_df["ORDER DATE"] < "2020-01-01") |
            (target_df["ORDER DATE"] > "2030-12-31")
        ]
        assert bad.empty, (
            f"{len(bad)} dates outside 2020-2030: {bad['ORDER DATE'].head(3).tolist()}"
        )

    def test_no_future_dates(self, target_df):
        today = pd.Timestamp.today().normalize()
        future = target_df[target_df["ORDER DATE"] > today]
        assert future.empty, f"{len(future)} future dates found."


# ============================================================================
#  6. REFERENTIAL INTEGRITY CHECK                                  @functional
# ============================================================================

@pytest.mark.functional
class TestReferentialIntegrity:

    @pytest.mark.parametrize("col,valid_set", [
        ("STATUS",           VALID_STATUSES),
        ("PAYMENT METHOD",   VALID_PAYMENTS),
        ("REGION",           VALID_REGIONS),
        ("PRODUCT CATEGORY", VALID_CATEGORIES),
    ])
    def test_categorical_minus(self, expected_df, target_df, col, valid_set):
        exp_vals = set(expected_df[col].dropna().unique())
        tgt_vals = set(target_df[col].dropna().unique())
        diff = exp_vals - tgt_vals
        assert len(diff) == 0, f"{col}: missing from target: {diff}"

    def test_no_invalid_categoricals_in_target(self, target_df):
        checks = {
            "STATUS": VALID_STATUSES, "PAYMENT METHOD": VALID_PAYMENTS,
            "REGION": VALID_REGIONS, "PRODUCT CATEGORY": VALID_CATEGORIES,
        }
        for col, valid in checks.items():
            bad = set(target_df[col].dropna().unique()) - valid
            assert not bad, f"{col} has invalid values: {bad}"

    def test_customer_ref_minus(self, expected_df, target_df, validation_rules):
        if validation_rules.get("valid_customer_ids") is None:
            pytest.skip("CUSTOMERS_REF sheet not available.")
        exp_ids = set(expected_df["CUSTOMER ID"].dropna().unique())
        tgt_ids = set(target_df["CUSTOMER ID"].dropna().unique())
        diff = exp_ids - tgt_ids
        assert len(diff) == 0, f"{len(diff)} customer IDs missing: {list(diff)[:10]}"


# ============================================================================
#  7. AGGREGATE RECONCILIATION                                     @functional
# ============================================================================

@pytest.mark.functional
class TestAggregateRecon:

    def test_total_amount_minus(self, expected_df, target_df):
        exp_sum = (expected_df["QUANTITY"].astype(float) * expected_df["UNIT PRICE"]).sum()
        tgt_sum = target_df["TOTAL AMOUNT"].sum()
        diff = abs(exp_sum - tgt_sum)
        assert diff <= TOLERANCE, (
            f"Grand total mismatch: expected {exp_sum:,.2f}, target {tgt_sum:,.2f} "
            f"(diff={diff:,.2f})."
        )

    def test_per_row_total_calculation(self, target_df):
        recalc = (target_df["QUANTITY"].astype(float) * target_df["UNIT PRICE"]).round(2)
        bad = target_df[abs(target_df["TOTAL AMOUNT"] - recalc) > TOLERANCE]
        assert bad.empty, (
            f"{len(bad)} rows have wrong TOTAL. IDs: {bad['ORDER ID'].head(5).tolist()}"
        )

    def test_grand_total_is_positive(self, target_df):
        assert target_df["TOTAL AMOUNT"].sum() > 0


# ============================================================================
#  8. COMPOSITE KEY UNIQUENESS                                     @functional
# ============================================================================

@pytest.mark.functional
class TestCompositeKey:

    def test_composite_key_unique_in_target(self, target_df):
        dupes = target_df[target_df.duplicated(COMPOSITE_KEY, keep=False)]
        assert dupes.empty, f"{len(dupes)} duplicate composite-key rows."

    def test_dedup_count_minus(self, expected_df, target_df):
        exp = len(expected_df.drop_duplicates(COMPOSITE_KEY))
        tgt = len(target_df.drop_duplicates(COMPOSITE_KEY))
        assert exp - tgt == 0, f"Dedup count: expected {exp}, target {tgt}."


# ============================================================================
#  9. DUPLICATE CHECK                                              @data_quality
# ============================================================================

@pytest.mark.data_quality
class TestDuplicateCheck:

    def test_no_full_row_duplicates(self, target_df):
        dupes = target_df[target_df.duplicated(keep=False)]
        assert dupes.empty, f"{len(dupes)} fully duplicate rows."


# ============================================================================
#  10. NUMERIC RANGE CHECK                                         @data_quality
# ============================================================================

@pytest.mark.data_quality
class TestNumericRange:

    @pytest.mark.parametrize("col,lo,hi", [
        ("QUANTITY", QUANTITY_MIN, QUANTITY_MAX),
        ("AGE",      AGE_MIN,      AGE_MAX),
        ("RATING",   RATING_MIN,   RATING_MAX),
    ])
    def test_range_minus(self, expected_df, target_df, col, lo, hi):
        exp = len(expected_df[expected_df[col].between(lo, hi)])
        tgt = len(target_df[target_df[col].between(lo, hi)])
        assert exp - tgt == 0, f"{col} in-range: expected {exp}, target {tgt}."

    def test_unit_price_positive(self, target_df):
        bad = target_df[target_df["UNIT PRICE"] <= 0]
        assert bad.empty, f"{len(bad)} non-positive UNIT PRICE rows."

    def test_salary_positive(self, target_df):
        bad = target_df[target_df["SALARY USD"] <= 0]
        assert bad.empty, f"{len(bad)} non-positive SALARY USD rows."


# ============================================================================
#  11. STRING LENGTH VALIDATION                                    @data_quality
# ============================================================================

@pytest.mark.data_quality
class TestStringLength:

    def test_product_name_within_max_length(self, target_df):
        bad = target_df[target_df["PRODUCT NAME"].str.len() > PRODUCT_NAME_MAX_LEN]
        assert bad.empty, (
            f"{len(bad)} rows exceed {PRODUCT_NAME_MAX_LEN} chars."
        )


# ============================================================================
#  12. OUTLIER DETECTION (Z-score)                                 @data_quality
# ============================================================================

@pytest.mark.data_quality
class TestOutlierDetection:

    @pytest.mark.parametrize("col", [
        "QUANTITY", "UNIT PRICE", "TOTAL AMOUNT", "SALARY USD",
    ])
    def test_zscore_outlier_rate(self, target_df, col):
        values = target_df[col].dropna()
        if len(values) < 2:
            pytest.skip(f"Not enough data in {col}.")
        z = np.abs(stats.zscore(values))
        rate = (z > Z_THRESHOLD).mean()
        assert rate <= MAX_OUTLIER_RATE, (
            f"{col} outlier rate {rate:.1%} exceeds {MAX_OUTLIER_RATE:.0%}."
        )


# ============================================================================
#  13. PARTITION COMPLETENESS                                      @data_quality
# ============================================================================

@pytest.mark.data_quality
class TestPartitionCompleteness:

    def test_no_null_partition_month(self, target_df):
        nulls = int(target_df["PARTITION MONTH"].isna().sum())
        assert nulls == 0, f"{nulls} null PARTITION MONTH rows."

    def test_expected_months_present(self, target_df, validation_rules):
        expected = validation_rules.get("expected_partition_months")
        if expected is None:
            pytest.skip("PARTITION_CHECK not available.")
        actual = set(target_df["PARTITION MONTH"].dropna().astype(str))
        missing = expected - actual
        assert not missing, f"Missing months: {sorted(missing)}"

    def test_each_partition_has_rows(self, target_df):
        counts = target_df.groupby("PARTITION MONTH").size()
        empty = counts[counts == 0]
        assert empty.empty, f"Empty partitions: {empty.index.tolist()}"


# ============================================================================
#  14. SCHEMA DRIFT DETECTION                                      @regression
# ============================================================================

@pytest.mark.regression
class TestSchemaDrift:

    def test_no_missing_columns(self, target_df):
        missing = set(EXPECTED_COLUMNS) - set(target_df.columns)
        assert not missing, f"Missing columns: {sorted(missing)}"

    def test_no_extra_columns(self, target_df):
        extra = set(target_df.columns) - set(EXPECTED_COLUMNS)
        assert not extra, f"Extra columns: {sorted(extra)}"

    def test_column_order(self, target_df):
        assert list(target_df.columns) == EXPECTED_COLUMNS, (
            f"Order mismatch.\nExpected: {EXPECTED_COLUMNS}\n"
            f"Actual: {list(target_df.columns)}"
        )


# ============================================================================
#  15. FILE INTEGRITY (MD5 Hash)                                   @regression
# ============================================================================

@pytest.mark.regression
class TestFileIntegrity:

    def test_target_csv_exists(self):
        assert os.path.exists(TARGET_FILE), f"Not found: {TARGET_FILE}"

    def test_md5_checksum_matches(self, md5_hash_path):
        assert os.path.exists(md5_hash_path), f"MD5 file not found: {md5_hash_path}"
        with open(md5_hash_path) as f:
            stored = f.read().strip()
        h = hashlib.md5()
        with open(TARGET_FILE, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        current = h.hexdigest()
        assert stored == current, (
            f"MD5 mismatch.\nStored:  {stored}\nCurrent: {current}"
        )

    def test_csv_row_count_matches_dataframe(self, target_df):
        with open(TARGET_FILE, "r", encoding="utf-8") as f:
            csv_lines = sum(1 for _ in f) - 1
        assert csv_lines == len(target_df), (
            f"CSV lines {csv_lines} != DataFrame rows {len(target_df)}."
        )
