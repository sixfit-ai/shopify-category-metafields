#!/usr/bin/env python3
"""Capture a comparable snapshot of everything a run can change, and diff two.

Used to prove that a rollback restored the store exactly. It covers the four
things the skill can touch, plus the two it must NOT touch:

  categories           per product
  shopify.* metafields per product (category keys only)
  metaobject counts    per type
  definition lists     metafield and metaobject
  tags                 must be identical before and after   <- must not change
  other metafields     sixfit.*, mc-facebook.*, ...          <- must not change

Usage
-----
    python3 scripts/snapshot.py capture raw_products.json raw_store.json raw_tags.json \\
        --out work/snap_before.json
    python3 scripts/snapshot.py diff work/snap_before.json work/snap_after.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import NAMESPACE, dump_json, load_json, unwrap  # noqa: E402


def capture(products_payload, store_payload, tags_payload):
    products = unwrap(products_payload, "products") or []
    snapshot = {"products": {}, "tags": {}, "other_metafields": {}}

    for product in products:
        gid = product["id"]
        category = (product.get("category") or {}).get("id")
        mine, other = {}, {}
        for metafield in unwrap(product.get("metafields") or {}, "metafields") or []:
            name = "%s.%s" % (metafield["namespace"], metafield["key"])
            if metafield["namespace"] == NAMESPACE:
                mine[metafield["key"]] = metafield.get("value")
            else:
                other[name] = metafield.get("value")
        snapshot["products"][gid] = {"title": product.get("title"),
                                     "category": category,
                                     "metafields": mine}
        snapshot["other_metafields"][gid] = other

    for product in unwrap(tags_payload, "products") or []:
        snapshot["tags"][product["id"]] = sorted(product.get("tags") or [])

    store = store_payload
    snapshot["metaobject_counts"] = {
        d["type"]: d.get("metaobjectsCount")
        for d in store.get("metaobjectDefinitions") or []}
    snapshot["definitions"] = {
        "metafield": sorted(d["key"] for d in store.get("metafieldDefinitions") or []),
        "metaobject": sorted(d["type"] for d in store.get("metaobjectDefinitions") or []),
    }
    return snapshot


def diff_maps(before, after, label, out):
    keys = sorted(set(before) | set(after))
    for key in keys:
        a, b = before.get(key), after.get(key)
        if a != b:
            out.append("%s | %s | %r -> %r" % (label, key, a, b))


def diff(before, after):
    problems = []

    for gid in sorted(set(before["products"]) | set(after["products"])):
        old = before["products"].get(gid, {})
        new = after["products"].get(gid, {})
        title = old.get("title") or new.get("title") or gid
        if old.get("category") != new.get("category"):
            problems.append("CATEGORY  | %s | %r -> %r"
                            % (title, old.get("category"), new.get("category")))
        diff_maps(old.get("metafields", {}), new.get("metafields", {}),
                  "METAFIELD | %s" % title, problems)
        diff_maps(before["other_metafields"].get(gid, {}),
                  after["other_metafields"].get(gid, {}),
                  "CUSTOM-MF | %s" % title, problems)
        if before["tags"].get(gid) != after["tags"].get(gid):
            problems.append("TAGS      | %s | %r -> %r"
                            % (title, before["tags"].get(gid),
                               after["tags"].get(gid)))

    diff_maps(before["metaobject_counts"], after["metaobject_counts"],
              "MO-COUNT ", problems)
    for kind in ("metafield", "metaobject"):
        a = set(before["definitions"][kind])
        b = set(after["definitions"][kind])
        for item in sorted(a - b):
            problems.append("DEFINITION| %s | removed: %s" % (kind, item))
        for item in sorted(b - a):
            problems.append("DEFINITION| %s | added:   %s" % (kind, item))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture")
    cap.add_argument("products")
    cap.add_argument("store")
    cap.add_argument("tags")
    cap.add_argument("--out", required=True)

    dif = sub.add_parser("diff")
    dif.add_argument("before")
    dif.add_argument("after")

    args = parser.parse_args()

    if args.command == "capture":
        snapshot = capture(load_json(args.products), load_json(args.store),
                           load_json(args.tags))
        dump_json(args.out, snapshot)
        print("captured %s" % args.out)
        print("  products        : %d" % len(snapshot["products"]))
        print("  with a category : %d"
              % sum(1 for p in snapshot["products"].values() if p["category"]))
        print("  shopify.* fields: %d"
              % sum(len(p["metafields"]) for p in snapshot["products"].values()))
        print("  other-namespace : %d"
              % sum(len(v) for v in snapshot["other_metafields"].values()))
        print("  tagged products : %d"
              % sum(1 for t in snapshot["tags"].values() if t))
        print("  metaobject types: %d" % len(snapshot["metaobject_counts"]))
        return

    problems = diff(load_json(args.before), load_json(args.after))
    if not problems:
        print("IDENTICAL — no difference in categories, shopify.* metafields, "
              "metaobject counts, definitions, tags, or custom metafields.")
        return
    print("%d DIFFERENCE(S):\n" % len(problems))
    for problem in problems:
        print("  %s" % problem)
    sys.exit(1)


if __name__ == "__main__":
    main()
