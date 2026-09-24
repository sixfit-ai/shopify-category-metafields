#!/usr/bin/env python3
"""Write and verify work/backup.json — the safety net for a run.

Nothing else writes this file, and it is never hand-authored. It must come from
a FRESH read taken immediately before applying, not from the Phase 1 catalog
dump, which may be stale.

It records four things, because a run can change four things:

  products                 category and every shopify.* category metafield
  preexisting_metaobjects  every metaobject id that existed before the run
  preexisting_definitions  which metafield and metaobject definitions existed
  created_by_run           filled in by apply.py, emptied here

`preexisting_metaobjects` is what makes deletion safe later: anything the run
creates is, by definition, not in this list.

Coverage
--------
Pass --plan. The script refuses to write a backup that does not cover every
product the plan touches. If it refuses, fix the read and try again; do not
apply without a verified backup.

Fresh-read queries: the same two used by normalize_catalog.py and
build_store_map.py. `--print-queries` on that script prints them.

Usage
-----
    python3 scripts/backup.py --products work/fresh_products.json \\
        --store-map work/store_map.json --plan work/plan.json
"""

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import dump_json, load_json, work  # noqa: E402


def build(catalog, store_map, plan):
    products = {}
    for product in catalog["products"]:
        products[product["gid"]] = {
            "title": product["title"],
            "category": product.get("category"),
            "metafields": {
                key: {"type": spec["type"], "value": spec["value"]}
                for key, spec in (product.get("metafields") or {}).items()
            },
        }

    preexisting_metaobjects = {}
    for mo_type, by_value in store_map["entries_by_value"].items():
        ids = sorted({e["metaobject"] for entries in by_value.values()
                      for e in entries})
        preexisting_metaobjects[mo_type] = ids

    return {
        "_taken": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_shop": store_map.get("_shop"),
        "_taxonomy_version": plan.get("_taxonomy_version"),
        "_plan_generated": plan.get("_generated"),
        "products": products,
        "preexisting_metaobjects": preexisting_metaobjects,
        "preexisting_definitions": {
            "metafield": sorted(store_map["keys"]),
            "metaobject": sorted(store_map["metaobject_definitions"]),
        },
        "created_by_run": {
            "_note": "Filled in by apply.py as it runs. Rollback removes these.",
            "metaobjects": [],
            "metaobject_definitions": [],
            "metafield_definitions": [],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--products", default=work("fresh_products.json"),
                        help="a FRESH normalize_catalog.py output")
    parser.add_argument("--store-map", default=work("store_map.json"))
    parser.add_argument("--plan", default=work("plan.json"))
    parser.add_argument("--out", default=work("backup.json"))
    args = parser.parse_args()

    catalog = load_json(args.products)
    store_map = load_json(args.store_map)
    plan = load_json(args.plan)

    backup = build(catalog, store_map, plan)

    needed = {p["gid"] for p in plan["products"]}
    covered = set(backup["products"])
    missing = sorted(needed - covered)
    if missing:
        print("REFUSING to write a backup: %d product(s) in the plan are not "
              "in the fresh read." % len(missing), file=sys.stderr)
        for gid in missing[:10]:
            print("  %s" % gid, file=sys.stderr)
        sys.exit(1)

    dump_json(args.out, backup)

    # Read it back from disk, so what is reported is what was stored.
    verify = load_json(args.out)
    values = sum(len(p["metafields"]) for p in verify["products"].values())
    with_category = sum(1 for p in verify["products"].values() if p["category"])
    entries = sum(len(v) for v in verify["preexisting_metaobjects"].values())

    print("wrote and verified %s" % args.out)
    print("  products backed up      : %d" % len(verify["products"]))
    print("  plan products covered   : %d of %d" % (len(needed & covered), len(needed)))
    print("  with a category         : %d" % with_category)
    print("  metafields captured     : %d" % values)
    print("  pre-existing metaobjects: %d" % entries)
    print("  pre-existing definitions: %d metafield, %d metaobject"
          % (len(verify["preexisting_definitions"]["metafield"]),
             len(verify["preexisting_definitions"]["metaobject"])))


if __name__ == "__main__":
    main()
