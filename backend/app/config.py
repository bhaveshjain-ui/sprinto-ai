import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # backend/
PROMPTS = ROOT / "prompts"

CRITERIA = [
    "funding_stage",
    "saas",
    "audit_signals",
    "employee_count",
    "customers",
    "industry",
    "cloud",
]
EXTRA_CRITERIA = ["competitor"]  # checked once; a verified hit is a verified negative
ALL_CRITERIA = CRITERIA + EXTRA_CRITERIA


def load_config() -> dict:
    load_dotenv(ROOT.parent / ".env")
    load_dotenv(ROOT / ".env")
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        if default is not None:
            return default
        raise RuntimeError(f"{name} is not set (add it to .env)")
    return val


def has_env(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())
