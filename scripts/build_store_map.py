#!/usr/bin/env python3
"""Turn the store's definitions and metaobjects into work/store_map.json.

The store, not the taxonomy index, is the authority on which category
metafields exist and which taxonomy values are writable today. This script
builds that picture:

    metafield key -> the metaobject definition it validates against
                  -> every existing entry, indexed by TaxonomyValue id

A taxonomy value that has no entry here cannot be written until a metaobject is
created for it. build_plan.py uses this to split proposals into "writable now"
and "needs a new metaobject".

Field-name independence
-----------------------
The field holding the taxonomy reference is NOT always called
`taxonomy_reference`. `shopify--color-pattern` uses `color_taxonomy_reference`
(a list) and `pattern_taxonomy_reference`. Fields are therefore matched on
TYPE -- product_taxonomy_value_reference or its list form -- never on name.

Pagination
----------
Both metaobjectDefinitions and metaobjects are paginated. Run each query until
pageInfo.hasNextPage is false and pass every page; pages are merged here.

    query Definitions($after: String) {
      metafieldDefinitions(first: 250, ownerType: PRODUCT, namespace: "shopify",
                           after: $after) {
        nodes { key name type { name } validations { name value } }
        pageInfo { hasNextPage endCursor }
      }
    }

    query Entries($type: String!, $after: String) {
      metaobjects(type: $type, first: 250, after: $after) {
        nodes { id handle fields { key value type } }
        pageInfo { hasNextPage endCursor }
      }
    }

`--print-queries` prints these ready to paste.

Usage
-----
    python3 scripts/build_store_map.py work/raw_store.json
    python3 scripts/build_store_map.py page*.json --stats
    python3 scripts/build_store_map.py --print-queries
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (TAXONOMY_REF_TYPES, dump_json, load_json,  # noqa: E402
                     short_gid, unwrap, work)

QUERIES = '''
# 1. Product metafield definitions in the shopify namespace.
query Definitions($after: String) {
  metafieldDefinitions(first: 250, ownerType: PRODUCT, namespace: "shopify", after: $after) {
    nodes { key name type { name } validations { name value } }
    pageInfo { hasNextPage endCursor }
  }
}

# 2. Metaobject definitions, to learn each one's field shape.
query MetaobjectDefinitions($after: String) {
  metaobjectDefinitions(first: 250, after: $after) {
    nodes { id type name metaobjectsCount fieldDefinitions { key required type { name } } }
    pageInfo { hasNextPage endCursor }
  }
}

# 3. Entries, once per shopify--* type, paged to exhaustion.
query Entries($type: String!, $after: String) {
  metaobjects(type: $type, first: 250, after: $after) {
    nodes { id handle fields { key value type } }
    pageInfo { hasNextPage endCursor }
  }
}
'''


def taxonomy_refs(fields):
    """Every TaxonomyValue id referenced by a metaobject, matched on type."""
    found = []
    for field in fields or []:
        if field.get("type") not in TAXONOMY_REF_TYPES:
            continue
        value = field.get("value")
        if not value:
            continue
        if value.lstrip().startswith("["):
            try:
                found.extend(json.loads(value))
            except ValueError:
                continue
        else:
            found.append(value)
    return [v for v in found if v]


def label_of(fields):
    for field in fields or []:
        if field.get("key") == "label":
            return field.get("value")
    return None


def merge_pages(paths):
    """Accept one combined payload or many per-query pages."""
    merged = {"metafieldDefinitions": [], "metaobjectDefinitions": [],
              "metaobjects": {}, "shop": None}
    for path in paths:
        payload = load_json(path)
        if isinstance(payload, dict) and "metaobjects" in payload \
                and isinstance(payload.get("metaobjects"), dict):
            merged["shop"] = payload.get("shop") or merged["shop"]
            merged["metafieldDefinitions"] += payload.get("metafieldDefinitions") or []
            merged["metaobjectDefinitions"] += payload.get("metaobjectDefinitions") or []
            for key, entries in payload["metaobjects"].items():
                merged["metaobjects"].setdefault(key, []).extend(entries)
            continue
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        for alias, node in (data or {}).items():
            nodes = unwrap(node) or []
            if not nodes:
                continue
            sample = nodes[0]
            if "validations" in sample:
                merged["metafieldDefinitions"] += nodes
            elif "fieldDefinitions" in sample:
                merged["metaobjectDefinitions"] += nodes
            elif "handle" in sample:
                merged["metaobjects"].setdefault(alias, []).extend(nodes)
    return merged


def build(raw):
    mo_defs = {d["type"]: d for d in raw["metaobjectDefinitions"]}
    by_id = {d["id"]: d for d in raw["metaobjectDefinitions"]}

    keys = {}
    for definition in raw["metafieldDefinitions"]:
        key = definition["key"]
        target = None
        for validation in definition.get("validations") or []:
            if validation.get("name") == "metaobject_definition_id":
                target = validation.get("value")
        mo_def = by_id.get(target)
        keys[key] = {
            "name": definition.get("name"),
            "type": (definition.get("type") or {}).get("name"),
            "metaobject_definition_id": target,
            "metaobject_type": mo_def["type"] if mo_def else None,
        }

    entries = {}
    warnings = []
    for mo_type, records in raw["metaobjects"].items():
        # Accept either the real type string or a query alias as the key.
        if mo_type not in mo_defs and records:
            guess = [t for t, d in mo_defs.items()
                     if d["id"] == records[0].get("definitionId")]
            mo_type = guess[0] if guess else mo_type
        index = {}
        for record in records:
            refs = taxonomy_refs(record.get("fields"))
            if not refs:
                warnings.append("%s/%s has no taxonomy reference field"
                                % (mo_type, record.get("handle")))
                continue
            for ref in refs:
                index.setdefault(short_gid(ref), []).append({
                    "metaobject": record["id"],
                    "handle": record.get("handle"),
                    "label": label_of(record.get("fields")),
                })
        entries[mo_type] = index

    return {
        "_shop": raw.get("shop"),
        "_note": "Store-side truth. Regenerate before every plan and every apply.",
        "keys": keys,
        "entries_by_value": entries,
        "metaobject_definitions": {
            d["type"]: {"id": d["id"], "count": d.get("metaobjectsCount"),
                        "fields": [{"key": f["key"],
                        "type": (f.get("type") or {}).get("name"),
                        "required": bool(f.get("required"))}
                       for f in d.get("fieldDefinitions") or []]}
            for d in raw["metaobjectDefinitions"]
        },
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pages", nargs="*")
    parser.add_argument("--out", default=work("store_map.json"))
    parser.add_argument("--print-queries", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.print_queries:
        print(QUERIES)
        return
    if not args.pages:
        parser.error("pass at least one payload, or --print-queries")

    store = build(merge_pages(args.pages))
    dump_json(args.out, store)

    print("wrote %s" % args.out)
    print("  metafield keys defined : %d" % len(store["keys"]))
    print("  metaobject types       : %d" % len(store["metaobject_definitions"]))
    total = sum(len(v) for v in store["entries_by_value"].values())
    print("  writable values today  : %d" % total)
    for warning in store["warnings"]:
        print("  WARNING: %s" % warning)

    if args.stats:
        print("\n  key -> metaobject type (entries):")
        for key in sorted(store["keys"]):
            spec = store["keys"][key]
            mo_type = spec["metaobject_type"]
            count = len(store["entries_by_value"].get(mo_type, {}))
            print("      %-22s %-32s %d" % (key, mo_type, count))


if __name__ == "__main__":
    main()
