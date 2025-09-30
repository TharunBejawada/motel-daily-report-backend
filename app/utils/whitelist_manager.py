import json
import os
from functools import lru_cache

WHITELIST_PATH = os.getenv("WHITELIST_PATH", "whitelist.json")

@lru_cache(maxsize=1)
def _load_whitelist():
    if not os.path.exists(WHITELIST_PATH):
        return {"vendors": [], "domains": []}
    with open(WHITELIST_PATH, "r") as f:
        data = json.load(f)
    return {
        "vendors": [v.lower().strip() for v in data.get("vendors", [])],
        "domains": [d.lower().strip() for d in data.get("domains", [])],
    }

# def is_whitelisted(sender_email: str | None) -> bool:
#     if not sender_email:
#         return False
#     s = sender_email.lower()
#     wl = _load_whitelist()
#     if any(v in s for v in wl["vendors"]):
#         return True
#     # basic domain check
#     at = s.rfind("@")
#     if at != -1:
#         dom = s[at+1:]
#         return dom in wl["domains"]
#     return False

def is_whitelisted(sender_email: str | None) -> bool:
    if not sender_email:
        return False
    s = sender_email.lower().strip()
    wl = _load_whitelist()
    return s in wl["vendors"]

