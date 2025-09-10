import json
from datetime import datetime, timedelta, timezone
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def _load(path):
    with open(path, "r") as f:
        return json.load(f)

PRODUCTS = _load(os.path.join(DATA_DIR, "products.json"))
ORDERS = _load(os.path.join(DATA_DIR, "orders.json"))

def product_search(query, price_max=None, tags=None):
    """
    Search products:
    - Respect price_max (if provided)
    - if tags provided, match when ANY tag overlaps (case-insensitive)
    - also allow loose text match on title from the query
    """
    tags = [t.lower() for t in (tags or [])]
    q = (query or "").lower()

    results = []
    for p in PRODUCTS:
        if price_max is not None and p["price"] > price_max:
            continue

        title_match = any(tok in p["title"].lower() for tok in re.split(r"[^\w]+", q) if tok)
        tag_match = any(t in [pt.lower() for pt in p["tags"]] for t in tags) if tags else False

        # If tags provided, require at least a tag match; otherwise title match is enough
        match = tag_match or (not tags and title_match)
        if match:
            results.append(p)

    # sort by price ascending for determinism
    results.sort(key=lambda x: x["price"])
    return results

def size_recommender(user_inputs):
    """
    Very simple heuristic focusing on M vs L.
    """
    ui = (user_inputs or "").lower()
    if "m" in ui and "l" in ui:
        return "You’re between M/L—go with L for a relaxed fit; choose M for a closer fit."
    if "l" in ui:
        return "You prefer L—this style runs true to size."
    if "m" in ui:
        return "You prefer M—this style runs true to size."
    return "This style is typically true to size."

def eta(zip_code):
    """
    Rule-based ETA; any zip provided → 2–5 business days (deterministic).
    """
    return "2–5 business days" if zip_code else "3–7 business days"

def order_lookup(order_id, email):
    """
    Secure lookup with normalization.
    """
    if not order_id or not email:
        return None
    oid = order_id.strip().upper()
    em = email.strip().lower()
    for o in ORDERS:
        if o["order_id"].upper() == oid and o["email"].lower() == em:
            return o
    return None

def _parse_iso_any(timestamp: str) -> datetime:
    """
    Robust ISO parser:
    - accepts 'Z' or '+00:00' or naive (assumed UTC)
    - returns timezone-aware UTC datetime
    """
    ts = timestamp.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def order_cancel(order_id, created_at_iso, now=None):
    """
    Enforce strict 60-minute rule.
    Allowed only if time_delta < 60 minutes.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    created_at = _parse_iso_any(created_at_iso)
    delta = now - created_at

    if delta < timedelta(minutes=60):
        return {"cancel_allowed": True, "reason": "within 60 min"}
    return {"cancel_allowed": False, "reason": ">60 min"}
