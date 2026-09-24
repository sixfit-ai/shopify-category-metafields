#!/usr/bin/env python3
"""Normalize the fetched catalog into work/products.json.

This script never calls Shopify. Claude pages through the catalog with
graphql_query and saves the result; this reshapes it.

The query to run, paged until pageInfo.hasNextPage is false:

    query Catalog($first: Int!, $after: String) {
      products(first: $first, after: $after) {
        nodes {
          id title descriptionHtml productType vendor status
          options { name values }
          category { id fullName isLeaf }
          metafields(first: 50) {
            nodes { namespace key type value }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }

Fetch ALL namespaces, not just `shopify`. Only `shopify` category keys are
read and written, but the others must be seen in order to report them as
skipped. Pass every page's payload; they are concatenated. Every other namespace is recorded as skipped and
never touched.

Usage
-----
    python3 scripts/normalize_catalog.py work/raw_products.json
    python3 scripts/normalize_catalog.py page1.json page2.json --stats
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (NAMESPACE, dump_json, load_config, load_json,  # noqa: E402
                     load_key_map, unwrap, work)


class _Stripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def strip_html(html):
    if not html:
        return ""
    stripper = _Stripper()
    stripper.feed(html)
    return re.sub(r"\s+", " ", "".join(stripper.parts)).strip()


def normalize(product, out_of_scope_keys):
    category = product.get("category") or {}
    options = [{"name": (o.get("name") or "").strip(),
                "values": list(o.get("values") or [])}
               for o in product.get("options") or []]

    mine, skipped = {}, []
    for metafield in unwrap(product.get("metafields") or {}, "metafields") or []:
        namespace = metafield.get("namespace")
        key = metafield.get("key")
        if namespace != NAMESPACE:
            skipped.append("%s.%s" % (namespace, key))
            continue
        if key in out_of_scope_keys:
            # In the shopify namespace but not a category metafield.
            skipped.append("%s.%s" % (namespace, key))
            continue
        mine[key] = {"type": metafield.get("type"),
                     "value": metafield.get("value")}

    return {
        "gid": product["id"],
        "title": product.get("title") or "",
        "description": strip_html(product.get("descriptionHtml")),
        "product_type": (product.get("productType") or "").strip(),
        "vendor": (product.get("vendor") or "").strip(),
        "status": (product.get("status") or "").strip(),
        "options": options,
        "option_names": [o["name"] for o in options],
        "category": category.get("id"),
        "category_full_name": category.get("fullName"),
        "category_is_leaf": category.get("isLeaf"),
        "metafields": mine,
        "skipped_metafields": sorted(skipped),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pages", nargs="+", help="raw page payload(s)")
    parser.add_argument("--out", default=work("products.json"))
    parser.add_argument("--status", help="comma-separated statuses, or 'all'")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    config = load_config()
    out_of_scope = set(load_key_map()["out_of_scope_keys"])

    if args.status == "all":
        scope = None
    elif args.status:
        scope = {s.strip().upper() for s in args.status.split(",")}
    else:
        scope = {s.upper() for s in config["status_scope"]}

    raw = []
    for page in args.pages:
        payload = load_json(page)
        raw.extend(unwrap(payload, "products") or [])

    records, dropped = [], Counter()
    for product in raw:
        record = normalize(product, out_of_scope)
        if scope and record["status"] and record["status"].upper() not in scope:
            dropped[record["status"]] += 1
            continue
        records.append(record)

    dump_json(args.out, {
        "_scope": sorted(scope) if scope else "all",
        "_dropped_by_status": dict(dropped),
        "products": records,
    })

    print("wrote %s" % args.out)
    print("  products kept    : %d" % len(records))
    if dropped:
        print("  dropped by status: %s"
              % ", ".join("%s=%d" % kv for kv in sorted(dropped.items())))

    if args.stats:
        with_cat = sum(1 for r in records if r["category"])
        print("\n  with a category  : %d" % with_cat)
        print("  without category : %d" % (len(records) - with_cat))
        skipped = Counter(k for r in records for k in r["skipped_metafields"])
        if skipped:
            print("\n  metafields skipped (never read or written):")
            for key, count in skipped.most_common():
                print("      %-34s %d product(s)" % (key, count))
        cats = Counter(r["category_full_name"] for r in records if r["category"])
        if cats:
            print("\n  existing categories:")
            for name, count in cats.most_common():
                print("      %-62s %d" % (name, count))


if __name__ == "__main__":
    main()
