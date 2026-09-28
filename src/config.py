import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = os.environ.get("DOGFOOD_DB_PATH", str(DATA_DIR / "dogfood.db"))
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")

# Secret key for sessions & cryptographic operations
SECRET_KEY = os.environ.get("SECRET_KEY", "dogfood_super_secret_hackathon_raptors_key_2026")

# Test Auth Tokens recognized by the checker and seed script
TEST_TOKENS = {
    "organizer": "organizer0000000000000000000000000000000",
    "judge_a": "judgea0000000000000000000000000000000000",
    "judge_b": "judgeb0000000000000000000000000000000000",
    "participant": "participant00000000000000000000000000000",
}
