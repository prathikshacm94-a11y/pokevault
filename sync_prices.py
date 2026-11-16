#!/usr/bin/env python3
"""
Poke Vault price updater.

Downloads every English Pokemon TCG set, its sealed products and its hit cards,
with current TCGplayer market prices, from tcgcsv.com (a free daily mirror of
TCGplayer data). Saves everything to data.js next to this file so index.html
can show it.

Run once a day at most. The data only changes once a day.
"""

import json
import os
import re
import sys
import time
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
import urllib.request
from datetime import datetime, timezone

BASE = os.environ.get("POKEVAULT_BASE", "https://tcgcsv.com/tcgplayer")
CATEGORY = 3  # Pokemon (English). Japanese is a separate category.
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data.js")

# Card rarities that are NOT hits. Everything else counts as a hit.
NOT_HIT = {"", "common", "uncommon", "rare", "code card", "none"}
# A card of any rarity worth at least this much also shows as a hit.
VALUE_HIT = 20.0


def get(url, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PokeVault/1.0 (personal use)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def ext(product):
    out = {}
    for item in product.get("extendedData") or []:
        out[(item.get("name") or "").lower()] = item.get("value") or ""
    return out


def classify(name):
    n = name.lower()
    if "code card" in n:
        return None
    if re.search(r"\bcase\b", n):
        return "Case"
    if "elite trainer box" in n:
        return "Elite Trainer Box"
    if "booster bundle" in n:
        return "Booster Bundle"
    if "booster box" in n or "booster display" in n:
        return "Booster Box"
    if "blister" in n or "checklane" in n or re.search(r"\b[23][ -]pack\b", n):
        return "Blister"
    if "booster pack" in n or "sleeved booster" in n or re.search(r"\bbooster$", n) or n.endswith(" pack"):
        return "Booster Pack"
    if re.search(r"\btins?\b", n):
        return "Tin"
    if "build & battle" in n or "build and battle" in n:
        return "Build & Battle"
    if re.search(r"deck|trainer kit", n):
        return "Deck"
    if re.search(r"collection|box|premium|bundle|chest|set\b", n):
        return "Collection / Box"
    return "Other"


def best_price(rows):
    """Pick the price row with the highest market price."""
    best = None
    for p in rows:
        mp = p.get("marketPrice")
        if mp is None:
            mp = p.get("midPrice")
        if mp is None:
            continue
        if best is None or mp > best[0]:
            best = (mp, p.get("lowPrice"), p.get("subTypeName") or "")
    return best


def r2(x):
    return None if x is None else round(float(x), 2)


def main():
    print("Downloading the list of English Pokemon sets...")
    groups = get(f"{BASE}/{CATEGORY}/groups")["results"]
    print(f"Found {len(groups)} sets. Downloading products and prices (takes a few minutes)...")

    sets, sealed, hits = [], [], []
    failed = []
    for i, g in enumerate(groups, 1):
        gid = g["groupId"]
        name = g.get("name") or ""
        sys.stdout.write(f"\r  [{i}/{len(groups)}] {name[:50]:<50}")
        sys.stdout.flush()
        try:
            products = get(f"{BASE}/{CATEGORY}/{gid}/products")["results"]
            prices = get(f"{BASE}/{CATEGORY}/{gid}/prices")["results"]
        except Exception as e:
            failed.append(name)
            continue

        by_id = {}
        for p in prices:
            by_id.setdefault(p["productId"], []).append(p)

        n_sealed = n_hits = 0
        top = 0.0
        for p in products:
            pid = p["productId"]
            e = ext(p)
            bp = best_price(by_id.get(pid, []))
            mp, lp, sub = bp if bp else (None, None, "")
            pname = p.get("name") or ""
            is_card = "number" in e or "rarity" in e
            if is_card:
                rarity = e.get("rarity", "")
                if rarity.lower() in NOT_HIT and not (mp and mp >= VALUE_HIT):
                    continue
                if "code card" in pname.lower():
                    continue
                hits.append({
                    "id": pid, "g": gid, "n": pname, "num": e.get("number", ""),
                    "r": rarity, "img": p.get("imageUrl") or "", "mp": r2(mp),
                    "lp": r2(lp), "sub": sub, "url": p.get("url") or "",
                })
                n_hits += 1
                if mp:
                    top = max(top, mp)
            else:
                t = classify(pname)
                if not t:
                    continue
                sealed.append({
                    "id": pid, "g": gid, "n": pname, "t": t,
                    "img": p.get("imageUrl") or "", "mp": r2(mp), "lp": r2(lp),
                    "url": p.get("url") or "",
                })
                n_sealed += 1

        sets.append({
            "id": gid, "n": name, "a": g.get("abbreviation") or "",
            "d": (g.get("publishedOn") or "")[:10], "ns": n_sealed, "nh": n_hits,
            "top": r2(top) if top else None,
        })
        time.sleep(0.15)  # be polite to the free service

    data = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sets": sets, "sealed": sealed, "hits": hits,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.POKE_DATA = ")
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        f.write(";\n")

    print(f"\n\nDone! {len(sets)} sets, {len(sealed)} sealed products, {len(hits)} hit cards.")
    if failed:
        print(f"Could not download {len(failed)} sets (try again later): {', '.join(failed[:10])}")
    print("Now open index.html in your browser (or refresh it if it is already open).")


if __name__ == "__main__":
    main()
