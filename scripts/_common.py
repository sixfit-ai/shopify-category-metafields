#!/usr/bin/env python3
"""Shared loaders and paths. Standard library only."""

import gzip
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

INDEX = os.path.join(ROOT, "taxonomy", "index.json.gz")
KEY_MAP = os.path.join(ROOT, "taxonomy", "key_map.json")
KEY_EXCEPTIONS = os.path.join(ROOT, "taxonomy", "key_exceptions.json")
CONFIG = os.path.join(ROOT, "config.json")
WORK = os.path.join(ROOT, "work")
PROMPTS = os.path.join(ROOT, "prompts")
TEMPLATES = os.path.join(ROOT, "templates")

NAMESPACE = "shopify"

# Metaobject field types that hold a taxonomy value reference. The field KEY
# varies by metaobject type -- shopify--color-pattern uses
# color_taxonomy_reference / pattern_taxonomy_reference rather than the usual
# taxonomy_reference -- so fields are matched on type, never on name.
TAXONOMY_REF_TYPES = {
    "product_taxonomy_value_reference",
    "list.product_taxonomy_value_reference",
}


def load_json(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path, data, compact=False):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        if compact:
            json.dump(data, handle, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
        else:
            json.dump(data, handle, ensure_ascii=False, sort_keys=True, indent=1)
        handle.write("\n")


def load_index():
    return load_json(INDEX)


def load_key_map():
    return load_json(KEY_MAP)


def load_config():
    return load_json(CONFIG)


def work(*parts):
    return os.path.join(WORK, *parts)


def short_gid(gid):
    """gid://shopify/TaxonomyValue/6711 -> 6711"""
    return gid.rsplit("/", 1)[-1] if gid else gid


def unwrap(payload, *keys):
    """Accept either a bare list/dict or a raw GraphQL response around it."""
    if isinstance(payload, dict):
        if "data" in payload:
            payload = payload["data"]
        for key in keys:
            if isinstance(payload, dict) and key in payload:
                payload = payload[key]
        if isinstance(payload, dict):
            for key in ("nodes", "edges"):
                if key in payload:
                    payload = payload[key]
                    break
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) \
            and set(payload[0]) == {"node"}:
        payload = [item["node"] for item in payload]
    return payload
