#!/usr/bin/env python3
"""Render a per-category prompt from templates/category_prompt.md.

One file per category, written to prompts/<category-id>.md. Each carries that
category's attributes and the complete list of allowed values, so the model
filling metafields never has to recall a value list or reach for the index.

The rendered prompt marks, per attribute, whether the store can write a value
today:

    [writable]  an entry already exists for this value
    [new]       writing it means creating a metaobject entry first
    [blocked]   the metafield definition is not enabled in this store

`--store-map` supplies that status. Without it every value is rendered plain,
which is fine for review but not for planning.

Usage
-----
    python3 scripts/build_prompts.py --category gid://shopify/TaxonomyCategory/aa-1-13-8
    python3 scripts/build_prompts.py --from-products work/products.json \
        --store-map work/store_map.json
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (PROMPTS, TEMPLATES, load_index, load_json,  # noqa: E402
                     load_key_map, short_gid)

TEMPLATE = os.path.join(TEMPLATES, "category_prompt.md")
MAX_VALUES_INLINE = 400


def status_of(key, value_id, store_map):
    if store_map is None:
        return ""
    if key not in store_map["keys"]:
        return " [blocked]"
    mo_type = store_map["keys"][key]["metaobject_type"]
    entries = store_map["entries_by_value"].get(mo_type, {})
    return " [writable]" if short_gid(value_id) in entries else " [new]"


def render_attributes(category, index, key_map, store_map):
    blocks = []
    for handle in category["attributes"]:
        attribute = index["attributes"].get(handle)
        if attribute is None:
            blocks.append("### `%s`\n\nDOĞRULANAMADI — this attribute is not in "
                          "the taxonomy index. Skip it.\n" % handle)
            continue
        key = key_map["attribute_to_key"].get(handle, handle)
        shared = key_map["multi_attribute_keys"].get(key)

        header = "### %s" % attribute["name"]
        meta = ["taxonomy handle `%s`" % handle, "metafield `shopify.%s`" % key]
        if attribute.get("base"):
            meta.append("alias of `%s`" % attribute["base"])
        if shared:
            meta.append("shares this metafield with %s"
                        % ", ".join("`%s`" % h for h in shared if h != handle))

        lines = [header, "", "*%s*" % " · ".join(meta), ""]
        if attribute.get("description"):
            lines += [attribute["description"], ""]

        values = attribute["values"]
        if not values:
            lines.append("_No choice list — this attribute takes a measurement, "
                         "not one of a fixed set. Skip it._")
        elif len(values) > MAX_VALUES_INLINE:
            lines.append("_%d values, too many to inline. Consult the index._"
                         % len(values))
        else:
            lines.append("Allowed values (%d):" % len(values))
            lines.append("")
            for value in values:
                lines.append("- `%s`%s" % (value["name"],
                                           status_of(key, value["id"], store_map)))
        blocks.append("\n".join(lines) + "\n")
    return "\n".join(blocks)


def render(category_id, index, key_map, store_map, example_gid):
    category = index["categories"][category_id]
    template = open(TEMPLATE, encoding="utf-8").read()
    return (template
            .replace("{{CATEGORY_ID}}", category_id)
            .replace("{{CATEGORY_NAME}}", category["name"])
            .replace("{{CATEGORY_FULL_NAME}}", category["full_name"])
            .replace("{{TAXONOMY_VERSION}}", index["_version"])
            .replace("{{EXAMPLE_GID}}", example_gid)
            .replace("{{ATTRIBUTES}}",
                     render_attributes(category, index, key_map, store_map)))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--category", action="append", default=[],
                        help="category id; repeatable")
    parser.add_argument("--from-products",
                        help="render for every category present in this file")
    parser.add_argument("--store-map", help="work/store_map.json")
    parser.add_argument("--out-dir", default=PROMPTS)
    args = parser.parse_args()

    index = load_index()
    key_map = load_key_map()
    store_map = load_json(args.store_map) if args.store_map else None

    wanted = list(args.category)
    example = "gid://shopify/Product/0"
    if args.from_products:
        products = load_json(args.from_products)["products"]
        wanted += [p["category"] for p in products if p.get("category")]
        if products:
            example = products[0]["gid"]

    seen, ordered = set(), []
    for category_id in wanted:
        if category_id not in seen:
            seen.add(category_id)
            ordered.append(category_id)

    if not ordered:
        parser.error("nothing to render: pass --category or --from-products")

    os.makedirs(args.out_dir, exist_ok=True)
    for category_id in ordered:
        if category_id not in index["categories"]:
            print("  SKIP %s — not in the taxonomy index" % category_id)
            continue
        text = render(category_id, index, key_map, store_map, example)
        name = short_gid(category_id) + ".md"
        path = os.path.join(args.out_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        category = index["categories"][category_id]
        print("  %-14s %-58s %d attrs  %5.1f KB"
              % (name, category["name"], len(category["attributes"]),
                 len(text) / 1024))

    print("\nwrote %d prompt(s) to %s" % (len(ordered), args.out_dir))


if __name__ == "__main__":
    main()
