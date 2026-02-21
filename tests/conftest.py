"""Pytest configuration."""
import os
import sys
from pathlib import Path

# Set required env vars before any vagus imports (needed for layer3.api.auth)
os.environ.setdefault("VAGUS_SECRET_KEY", "test-secret-for-pytest-do-not-use-in-production")
os.environ.setdefault("VAGUS_ADMIN_USERNAME", "admin")
os.environ.setdefault(
    "VAGUS_ADMIN_PASSWORD_HASH",
    "$2b$12$e0Nh76Y6xklm2gwcyNL.J.PSV43visamnmiSTi18FrrU9gvPZPxWm",  # testpassword
)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
