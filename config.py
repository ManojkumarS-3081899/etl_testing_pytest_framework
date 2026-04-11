import os

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(BASE_DIR, "data", "source",
                           "ETL_Validation_Dataset_2000rows 1.xlsx")
TARGET_DIR  = os.path.join(BASE_DIR, "data", "target")
TARGET_FILE = os.path.join(TARGET_DIR, "orders_clean.csv")
MD5_FILE    = os.path.join(TARGET_DIR, "orders_clean.md5")

# ── Valid categorical values ─────────────────────────────────────────────────
VALID_STATUSES   = {"Completed", "Pending", "Cancelled", "Processing",
                    "Shipped", "Delivered", "Returned"}
VALID_PAYMENTS   = {"Credit Card", "Debit Card", "UPI", "Cash", "Net Banking"}
VALID_REGIONS    = {"North", "South", "East", "West", "Central"}
VALID_CATEGORIES = {"Electronics", "Furniture", "Books", "Sports",
                    "Clothing", "Food", "Pharma"}

# ── Regex patterns ───────────────────────────────────────────────────────────
ORDER_ID_REGEX = r"^ORD\d{3,}$"
EMAIL_REGEX    = r"^[\w\.-]+@[\w\.-]+\.\w{2,}$"
PHONE_REGEX    = r"^\+1\d{10}$"

# ── Schema ───────────────────────────────────────────────────────────────────
EXPECTED_COLUMNS = [
    "ORDER ID", "CUSTOMER ID", "CUSTOMER NAME", "CUSTOMER EMAIL",
    "CUSTOMER PHONE", "AGE", "ORDER DATE", "PRODUCT NAME",
    "PRODUCT CATEGORY", "QUANTITY", "UNIT PRICE", "TOTAL AMOUNT",
    "RATING", "SALARY USD", "STATUS", "PAYMENT METHOD",
    "REGION", "PARTITION MONTH",
]

CRITICAL_COLUMNS = [
    "ORDER ID", "CUSTOMER ID", "CUSTOMER NAME", "ORDER DATE",
    "PRODUCT NAME", "QUANTITY", "UNIT PRICE", "STATUS",
]

# ── Numeric boundaries ──────────────────────────────────────────────────────
QUANTITY_MIN         = 1
QUANTITY_MAX         = 50
AGE_MIN              = 18
AGE_MAX              = 80
RATING_MIN           = 1
RATING_MAX           = 5
PRODUCT_NAME_MAX_LEN = 50

# ── Thresholds ───────────────────────────────────────────────────────────────
Z_THRESHOLD      = 3.0
MAX_OUTLIER_RATE  = 0.10
TOLERANCE         = 0.01
NULL_RATE_LIMIT   = 0.05

# ── Composite key ────────────────────────────────────────────────────────────
COMPOSITE_KEY = ["ORDER ID", "PRODUCT NAME"]
