import os
from dotenv import load_dotenv

load_dotenv()

CREDENTIALS: dict[str, dict[str, dict[str, str]]] = {
    "장금상선": {
        "TEXA": {"id": os.getenv("SK_TEXA_ID", ""), "pw": os.getenv("SK_TEXA_PW", "")},
        "TRIT": {"id": os.getenv("SK_TRIT_ID", ""), "pw": os.getenv("SK_TRIT_PW", "")},
        "GLOD": {"id": os.getenv("SK_GLOD_ID", ""), "pw": os.getenv("SK_GLOD_PW", "")},
        "FLOR": {"id": os.getenv("SK_FLOR_ID", ""), "pw": os.getenv("SK_FLOR_PW", "")},
        "GESE": {"id": os.getenv("SK_GESE_ID", ""), "pw": os.getenv("SK_GESE_PW", "")},
    },
    "흥아라인": {
        "TEXA": {"id": os.getenv("HA_TEXA_ID", ""), "pw": os.getenv("HA_TEXA_PW", "")},
        "TRIT": {"id": os.getenv("HA_TRIT_ID", ""), "pw": os.getenv("HA_TRIT_PW", "")},
        "GOLD": {"id": os.getenv("HA_GOLD_ID", ""), "pw": os.getenv("HA_GOLD_PW", "")},
        "FLOR": {"id": os.getenv("HA_FLOR_ID", ""), "pw": os.getenv("HA_FLOR_PW", "")},
        "GESE": {"id": os.getenv("HA_GESE_ID", ""), "pw": os.getenv("HA_GESE_PW", "")},
    },
}


def get_credential(company: str, lessor: str) -> dict[str, str]:
    return CREDENTIALS.get(company, {}).get(lessor, {})
