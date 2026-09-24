#!/usr/bin/env python3
"""Emit the mutations that restore the exact pre-run state. Executes nothing.

Reads work/backup.json and emits, in this order:

  1  metafields   restore every shopify.* category metafield to its backed-up
                  value; metafieldsDelete for any that did not exist before
  2  categories   productUpdate back to the backed-up category
  3  metaobjects  metaobjectDelete for entries this run created
  4  definitions  metaobjectDefinitionDelete for definitions this run created

Why definitions are deleted through the metaobject definition
-------------------------------------------------------------
`metafieldDefinitionDelete` is not available to this connector app (verified:
"Access denied"). `metaobjectDefinitionDelete` is, and per Shopify's docs it
also removes the metaobjects and the associated metafield definitions. That
cascade is the only undo available, which makes it powerful enough to be
dangerous, hence the guard below.

The deletion guard
------------------
A metaobject definition is deleted ONLY when all three hold:

  (a) it is listed in backup.created_by_run.metaobject_definitions
  (b) every entry it now contains was created by this run
  (c) no product references it

Any definition failing any check is left alone and reported as a warning. The
store keeps an object this run created, which is untidy; deleting a definition
that holds merchant data would be unrecoverable. Untidy wins.

Check (c) needs a current read. Supply it with --current-products (a
normalize_catalog.py output taken now) and --current-store-map; without them
the check cannot pass and no definition is deleted.

Usage
-----
    python3 scripts/rollback.py
    python3 scripts/rollback.py --current-products work/now_products.json \\
        --current-store-map work/now_store.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import NAMESPACE, dump_json, load_config, load_json, work  # noqa: E402


def chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def restore_operations(backup, plan):
    """What has to change to put every planned product back."""
    sets, deletes, categories = [], [], []
    touched = {p["gid"]: p for p in plan["products"]}

    for gid, product in backup["products"].items():
        if gid not in touched:
            continue
        planned_keys = {m["key"] for m in touched[gid]["metafields"]}
        before = product["metafields"]

        for key in sorted(planned_keys):
            if key in before:
                sets.append({"gid": gid, "title": product["title"], "key": key,
                             "type": before[key]["type"],
                             "value": before[key]["value"]})
            else:
                # It did not exist before the run. Restoring means removing it,
                # not writing an empty value.
                deletes.append({"gid": gid, "title": product["title"],
                                "key": key})

        planned_category = touched[gid]["category"]
        if planned_category["action"] in ("set", "change"):
            categories.append({"gid": gid, "title": product["title"],
                               "category": product["category"]})
    return sets, deletes, categories


def guard_definitions(backup, current_products, current_store):
    """Apply the three checks. Returns (deletable, warnings)."""
    created_defs = backup["created_by_run"]["metaobject_definitions"]
    created_entries = set(backup["created_by_run"]["metaobjects"])
    deletable, warnings = [], []

    for definition in created_defs:
        mo_type = definition.get("type") if isinstance(definition, dict) \
            else definition
        mo_id = definition.get("id") if isinstance(definition, dict) else None
        label = mo_type or mo_id

        # (a) created by this run -- true by construction, restated for clarity
        if not (mo_type or mo_id):
            warnings.append("unnamed definition entry in created_by_run; skipped")
            continue

        if current_store is None or current_products is None:
            warnings.append(
                "%s: not deleted. A current read is required to prove no "
                "product references it; pass --current-products and "
                "--current-store-map." % label)
            continue

        # (b) every entry it now holds was created by this run
        now = current_store["entries_by_value"].get(mo_type, {})
        present = {e["metaobject"] for entries in now.values() for e in entries}
        foreign = sorted(present - created_entries)
        if foreign:
            warnings.append(
                "%s: not deleted. It holds %d entr(y/ies) this run did not "
                "create, e.g. %s. Deleting it would destroy them."
                % (label, len(foreign), foreign[0]))
            continue

        # (c) no product references it
        key_for_type = [k for k, spec in current_store["keys"].items()
                        if spec.get("metaobject_type") == mo_type]
        referencing = []
        for product in current_products["products"]:
            for key in key_for_type:
                if key in (product.get("metafields") or {}):
                    referencing.append(product["gid"])
        if referencing:
            warnings.append(
                "%s: not deleted. %d product(s) still reference it, e.g. %s. "
                "Restore those metafields first."
                % (label, len(referencing), referencing[0]))
            continue

        deletable.append({"type": mo_type, "id": mo_id})
    return deletable, warnings


def doc_metafields_set(batch):
    variables = {"metafields": [
        {"ownerId": r["gid"], "namespace": NAMESPACE, "key": r["key"],
         "type": r["type"], "value": r["value"]} for r in batch]}
    return ("mutation RestoreMetafields($metafields: [MetafieldsSetInput!]!) {\n"
            "  metafieldsSet(metafields: $metafields) {\n"
            "    metafields { id namespace key }\n"
            "    userErrors { field message code }\n  }\n}"), variables


def doc_metafields_delete(batch):
    variables = {"metafields": [
        {"ownerId": r["gid"], "namespace": NAMESPACE, "key": r["key"]}
        for r in batch]}
    return ("mutation RemoveMetafields($metafields: [MetafieldIdentifierInput!]!) {\n"
            "  metafieldsDelete(metafields: $metafields) {\n"
            "    deletedMetafields { ownerId namespace key }\n"
            "    userErrors { field message }\n  }\n}"), variables


def doc_categories(batch):
    decls, body, variables = [], [], {}
    for i, record in enumerate(batch, start=1):
        pid, cat = "p%d" % i, "c%d" % i
        decls.append("$%s: ID!, $%s: ID" % (pid, cat))
        body.append("  r%d: productUpdate(product: {id: $%s, category: $%s}) { "
                    "product { id category { id } } "
                    "userErrors { field message } }" % (i, pid, cat))
        variables[pid] = record["gid"]
        # null restores "no category", which is the correct pre-run state for a
        # product that had none.
        variables[cat] = record["category"]
    return ("mutation RestoreCategories(%s) {\n%s\n}"
            % (", ".join(decls), "\n".join(body)), variables)


def doc_metaobject_delete(batch):
    decls, body, variables = [], [], {}
    for i, mo_id in enumerate(batch, start=1):
        var = "i%d" % i
        decls.append("$%s: ID!" % var)
        body.append("  d%d: metaobjectDelete(id: $%s) { deletedId "
                    "userErrors { field message code } }" % (i, var))
        variables[var] = mo_id
    return ("mutation DeleteMetaobjects(%s) {\n%s\n}"
            % (", ".join(decls), "\n".join(body)), variables)


def doc_definition_delete(batch):
    decls, body, variables = [], [], {}
    for i, record in enumerate(batch, start=1):
        var = "i%d" % i
        decls.append("$%s: ID!" % var)
        body.append("  d%d: metaobjectDefinitionDelete(id: $%s) { deletedId "
                    "userErrors { field message code } }" % (i, var))
        variables[var] = record["id"]
    return ("mutation DeleteMetaobjectDefinitions(%s) {\n%s\n}"
            % (", ".join(decls), "\n".join(body)), variables)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backup", default=work("backup.json"))
    parser.add_argument("--plan", default=work("plan.json"))
    parser.add_argument("--out-dir", default=work("rollback"))
    parser.add_argument("--current-products")
    parser.add_argument("--current-store-map")
    args = parser.parse_args()

    backup = load_json(args.backup)
    plan = load_json(args.plan)
    config = load_config()
    size = config["batch_size"]

    current_products = load_json(args.current_products) if args.current_products else None
    current_store = load_json(args.current_store_map) if args.current_store_map else None

    sets, deletes, categories = restore_operations(backup, plan)
    created_entries = list(backup["created_by_run"]["metaobjects"])
    deletable, warnings = guard_definitions(backup, current_products, current_store)

    os.makedirs(args.out_dir, exist_ok=True)
    manifest, number = [], 0

    def emit(stage, batches, builder):
        nonlocal number
        for batch in batches:
            number += 1
            document, variables = builder(batch)
            path = os.path.join(args.out_dir, "rollback_%03d.json" % number)
            dump_json(path, {"batch": number, "stage": stage,
                             "operations": len(batch), "mutation": document,
                             "variables": variables})
            manifest.append({"batch": number, "stage": stage,
                             "operations": len(batch), "file": path,
                             "status": "pending"})

    emit("metafields_restore", chunk(sets, size), doc_metafields_set)
    emit("metafields_remove", chunk(deletes, size), doc_metafields_delete)
    emit("categories_restore", chunk(categories, size), doc_categories)
    emit("metaobjects_delete", chunk(created_entries, size), doc_metaobject_delete)
    emit("definitions_delete", chunk(deletable, size), doc_definition_delete)

    dump_json(os.path.join(args.out_dir, "manifest.json"), {
        "_created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_backup_taken": backup["_taken"],
        "batches": manifest,
        "warnings": warnings,
    })

    print("compiled %d rollback batch(es) into %s\n" % (len(manifest), args.out_dir))
    print("  metafields to restore   : %d" % len(sets))
    print("  metafields to remove    : %d" % len(deletes))
    print("  categories to restore   : %d" % len(categories))
    print("  metaobjects to delete   : %d" % len(created_entries))
    print("  definitions to delete   : %d" % len(deletable))
    if warnings:
        print("\n  WARNINGS — left in place on purpose:")
        for warning in warnings:
            print("    %s" % warning)


if __name__ == "__main__":
    main()
