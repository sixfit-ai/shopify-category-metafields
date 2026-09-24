#!/usr/bin/env python3
"""Generate the taxonomy-attribute -> Shopify-metafield-key map.

The map is generated, not hand-written: for almost every taxonomy attribute the
metafield key is simply the attribute handle. Only the exceptions are curated,
in taxonomy/key_exceptions.json.

    attribute handle  ->  metafield key under namespace "shopify"
    color             ->  color-pattern     (collapsed: shares with `pattern`)
    pattern           ->  color-pattern     (collapsed)
    neckline          ->  neckline          (identity, the common case)

This map is a planning aid. The store is the authority: at run time, read
metafieldDefinitions(ownerType: PRODUCT, namespace: "shopify") and use each
definition's validations.metaobject_definition_id to find the metaobject
definition whose entries a value must resolve to. Where the store disagrees
with this map, the store wins and the difference is reported.

Usage
-----
    python3 scripts/build_key_map.py
    python3 scripts/build_key_map.py --check     # verify, write nothing
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import KEY_EXCEPTIONS, KEY_MAP, load_index, load_json  # noqa: E402

EXCEPTIONS = KEY_EXCEPTIONS
OUT = KEY_MAP


def build(index, exceptions):
    collapsed = {k: v for k, v in exceptions["collapsed"].items()
                 if not k.startswith("_")}
    renamed = {k: v for k, v in exceptions["renamed"].items()
               if not k.startswith("_")}

    attribute_to_key = {}
    for handle in sorted(index["attributes"]):
        attribute_to_key[handle] = renamed.get(handle, handle)
    for key, spec in collapsed.items():
        for handle in spec["attributes"]:
            attribute_to_key[handle] = key

    # Reverse view: every attribute feeding a given key. A key with more than
    # one attribute must have its values merged before writing.
    key_to_attributes = {}
    for handle, key in attribute_to_key.items():
        key_to_attributes.setdefault(key, []).append(handle)

    multi = {k: sorted(v) for k, v in key_to_attributes.items() if len(v) > 1}

    return {
        "_generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_generator": "scripts/build_key_map.py",
        "_taxonomy_version": index["_version"],
        "_namespace": "shopify",
        "_note": "Generated. Edit taxonomy/key_exceptions.json, then re-run.",
        "_authority": exceptions["_authority"],
        "out_of_scope_keys": exceptions["not_category_metafields"]["keys"],
        "multi_attribute_keys": multi,
        "attribute_to_key": attribute_to_key,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed map is current; write nothing")
    args = parser.parse_args()

    index = load_index()
    exceptions = load_json(EXCEPTIONS)
    built = build(index, exceptions)

    if args.check:
        if not os.path.exists(OUT):
            sys.exit("missing %s - run without --check" % OUT)
        current = load_json(OUT)
        drift = [k for k in ("attribute_to_key", "multi_attribute_keys",
                             "out_of_scope_keys", "_taxonomy_version")
                 if current.get(k) != built[k]]
        if drift:
            sys.exit("key_map.json is stale, differs in: %s" % ", ".join(drift))
        print("key_map.json is current (%d attributes)"
              % len(built["attribute_to_key"]))
        return

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(built, handle, ensure_ascii=False, sort_keys=True, indent=1)
        handle.write("\n")

    print("wrote %s" % OUT)
    print("  attributes mapped : %d" % len(built["attribute_to_key"]))
    print("  collapsed keys    : %d" % len(built["multi_attribute_keys"]))
    for key, handles in sorted(built["multi_attribute_keys"].items()):
        print("      %s <- %s" % (key, ", ".join(handles)))
    print("  out of scope      : %s" % ", ".join(built["out_of_scope_keys"]))


if __name__ == "__main__":
    main()
