#!/usr/bin/env python3
"""Build the committed taxonomy index from a pinned Shopify taxonomy release.

The upstream release asset is ~4 MB gzipped and ~91 MB expanded, which is far
too large to commit. This script downloads one pinned release, keeps only what
the skill actually needs, and writes a slim index that IS committed, gzipped.

What the skill needs, and nothing else:
  * category id -> name, full name, parent, leaf flag, attribute handles
  * attribute handle -> taxonomy attribute id, name, and its allowed values
  * value -> TaxonomyValue id and English name

Everything else in the upstream file (return reasons, integration mappings,
localized names, extended attribute metadata) is dropped.

The pinned version and source URL are written into the index header so the
provenance of every committed byte is readable without running anything.

Usage
-----
    python3 scripts/build_taxonomy_index.py
    python3 scripts/build_taxonomy_index.py --version 2026-08
    python3 scripts/build_taxonomy_index.py --verticals aa,ae   # smaller index

Re-running with a new --version is the ONLY supported way to change the
index. Never hand-edit taxonomy/index.json.gz.
"""

import argparse
import gzip
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

# Pinned upstream release. Bump deliberately, never silently.
DEFAULT_VERSION = "2026-08"
ASSET = "taxonomy.en.json.gz"
URL_TEMPLATE = (
    "https://github.com/Shopify/product-taxonomy/releases/download/v%s/" + ASSET
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INDEX_PATH = os.path.join(ROOT, "taxonomy", "index.json.gz")


def download(url, dest):
    """Fetch the release asset, reusing an existing download when present."""
    if os.path.exists(dest):
        print("using cached %s (%.1f MB)" % (dest, os.path.getsize(dest) / 1e6))
        return dest
    print("downloading %s" % url)
    with urllib.request.urlopen(url) as response, open(dest, "wb") as handle:
        handle.write(response.read())
    print("  wrote %s (%.1f MB)" % (dest, os.path.getsize(dest) / 1e6))
    return dest


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def build(raw, keep_verticals=None):
    """Reduce the upstream document to the committed index shape.

    Categories reference some attributes by an "extended" handle: a
    category-specific alias of a base attribute, carrying the base attribute's
    id and value list. For example `applique-shape` and `patch-shape` are both
    aliases of `applique-patch-shape`. Aliases appear in a category's attribute
    list but never as top-level entries in the attributes registry, so they are
    resolved here and recorded with a `base` pointer.
    """
    aliases = {}
    for attribute in raw["attributes"]:
        for extended in attribute.get("extended_attributes") or []:
            aliases[extended["handle"]] = {
                "base": attribute["handle"],
                "name": extended.get("name") or attribute["name"],
            }

    categories = {}
    used_handles = set()

    for vertical in raw["verticals"]:
        if keep_verticals and vertical["prefix"] not in keep_verticals:
            continue
        for category in vertical["categories"]:
            handles = [a["handle"] for a in category.get("attributes") or []]
            used_handles.update(handles)
            categories[category["id"]] = {
                "name": category["name"],
                "full_name": category["full_name"],
                "parent": category.get("parent_id"),
                # Upstream `level` disagrees with the Admin API's `level` for the
                # same category, so leafness is derived from children instead.
                "is_leaf": not category.get("children"),
                "attributes": sorted(handles),
            }

    by_handle = {a["handle"]: a for a in raw["attributes"]}
    attributes = {}

    for handle in sorted(used_handles):
        alias = aliases.get(handle)
        source = by_handle.get(aliases[handle]["base"]) if alias else by_handle.get(handle)
        if source is None:
            continue
        entry = {
            "id": source["id"],
            "name": alias["name"] if alias else source["name"],
            "description": source.get("description", ""),
            "values": [
                {"id": v["id"], "name": v["name"]}
                for v in source.get("values") or []
            ],
        }
        if alias:
            # The metafield key for an alias is NOT confirmed to follow the
            # alias handle rather than the base handle; both are recorded so
            # the mapping layer can decide. See docs/design.md.
            entry["base"] = alias["base"]
        attributes[handle] = entry

    missing = sorted(h for h in used_handles if h not in attributes)
    return categories, attributes, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help="taxonomy release to pin (default: %s)" % DEFAULT_VERSION)
    parser.add_argument("--verticals",
                        help="comma-separated vertical prefixes to keep "
                             "(default: all 26)")
    parser.add_argument("--cache-dir", default=os.environ.get("TMPDIR", "/tmp"),
                        help="where to keep the downloaded release asset")
    parser.add_argument("--out", default=INDEX_PATH, help="index path to write")
    args = parser.parse_args()

    url = URL_TEMPLATE % args.version
    archive = os.path.join(args.cache_dir, "taxonomy-%s.en.json.gz" % args.version)
    download(url, archive)

    digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    raw = load(archive)

    if raw.get("version") != args.version:
        sys.exit("version mismatch: asset reports %r, expected %r"
                 % (raw.get("version"), args.version))

    keep = set(filter(None, (args.verticals or "").split(","))) or None
    categories, attributes, missing = build(raw, keep)

    if missing:
        print("WARNING: %d attribute handles referenced by a category are absent "
              "from the attributes registry:" % len(missing), file=sys.stderr)
        for handle in missing[:10]:
            print("  %s" % handle, file=sys.stderr)

    index = {
        "_source": url,
        "_version": raw["version"],
        "_asset": ASSET,
        "_asset_sha256": digest,
        "_generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_generator": "scripts/build_taxonomy_index.py",
        "_note": "Generated file. Do not hand-edit; re-run the generator instead.",
        "_verticals": sorted(keep) if keep else "all",
        "categories": categories,
        "attributes": attributes,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    # Committed gzipped: ~12.4 MB of JSON compresses to ~1.6 MB.
    with gzip.open(args.out, "wt", encoding="utf-8", compresslevel=9) as handle:
        json.dump(index, handle, ensure_ascii=False, sort_keys=True,
                  separators=(",", ":"))
        handle.write("\n")

    leaves = sum(1 for c in categories.values() if c["is_leaf"])
    values = sum(len(a["values"]) for a in attributes.values())
    size = os.path.getsize(args.out)
    print("\nwrote %s" % args.out)
    print("  version    : %s" % raw["version"])
    print("  categories : %d (%d leaf)" % (len(categories), leaves))
    print("  attributes : %d" % len(attributes))
    print("  values     : %d" % values)
    print("  size       : %.1f MB gzipped" % (size / 1e6))


if __name__ == "__main__":
    main()
