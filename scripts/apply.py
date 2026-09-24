#!/usr/bin/env python3
"""Compile the plan into ready-to-run batches. Executes nothing.

Claude passes each batch's `mutation` and `variables` to the Shopify MCP
`graphql_mutation` tool, then records the outcome here. Splitting compilation
from execution keeps every write reviewable before it happens.

Stages, in order. Each is a separate approval; a later stage may not run until
the one it depends on has.

  0  definitions   standardMetafieldDefinitionEnable  -- only with --enable-definitions
  1  metaobjects   metaobjectCreate for values the store lacks
  2  categories    productUpdate, `category` field only
  3  metafields    metafieldsSet

Why these mutations and not others
----------------------------------
`productSet` is never used. It deletes list fields absent from its input, and
metafields are a list field, so one call would wipe every namespace this skill
is meant to leave alone. `productUpdate` is used ONLY to write `category`; it
never carries `tags`, which it would otherwise overwrite wholesale.

Stage 1 writes back into the backup's `created_by_run`, which is what lets
rollback delete exactly what this run created and nothing else.

Usage
-----
    python3 scripts/apply.py                       # compile all stages
    python3 scripts/apply.py --stage metafields
    python3 scripts/apply.py --mark-applied 3
    python3 scripts/apply.py --mark-failed 3 --note "throttled"
    python3 scripts/apply.py --record-created work/created.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (NAMESPACE, dump_json, load_config, load_json,  # noqa: E402
                     work)

STAGES = ("definitions", "metaobjects", "categories", "metafields")


def chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def doc_definitions(batch):
    decls, body, variables = [], [], {}
    for i, record in enumerate(batch, start=1):
        key = "k%d" % i
        decls.append("$%s: String!" % key)
        body.append('  d%d: standardMetafieldDefinitionEnable('
                    'namespace: "%s", key: $%s, ownerType: PRODUCT) { '
                    'createdDefinition { id key '
                    'validations { name value } } '
                    'userErrors { field message code } }'
                    % (i, NAMESPACE, key))
        variables[key] = record["key"]
    return ("mutation EnableDefinitions(%s) {\n%s\n}"
            % (", ".join(decls), "\n".join(body)), variables)


def doc_metaobjects(batch):
    decls, body, variables = [], [], {}
    for i, record in enumerate(batch, start=1):
        var = "m%d" % i
        decls.append("$%s: MetaobjectCreateInput!" % var)
        body.append("  e%d: metaobjectCreate(metaobject: $%s) { "
                    "metaobject { id handle type } "
                    "userErrors { field message code } }" % (i, var))
        # The reference field name is resolved per metaobject type by
        # build_plan.py -- shopify--color-pattern uses color_taxonomy_reference
        # (a list) rather than taxonomy_reference -- so it is never hardcoded.
        reference = record["reference_field"]
        value = record["taxonomy_value"]
        if record.get("reference_is_list"):
            value = json.dumps([value])
        fields = [
            # Label is the English taxonomy name. Existing entries in other
            # languages are never renamed; see the plan's label warnings.
            {"key": "label", "value": record["label"]},
            {"key": reference, "value": value},
        ]
        # Types with more than one REQUIRED taxonomy reference need the others
        # too: shopify--color-pattern refuses a colour without a Base pattern.
        # build_plan.py resolved these from the merchant's own proposal.
        for companion in record.get("companions") or []:
            companion_value = companion["value_id"]
            if companion.get("is_list"):
                companion_value = json.dumps([companion_value])
            fields.append({"key": companion["field"], "value": companion_value})
        variables[var] = {"type": record["metaobject_type"], "fields": fields}
    return ("mutation CreateMetaobjects(%s) {\n%s\n}"
            % (", ".join(decls), "\n".join(body)), variables)


def doc_categories(batch):
    decls, body, variables = [], [], {}
    for i, record in enumerate(batch, start=1):
        pid, cat = "p%d" % i, "c%d" % i
        decls.append("$%s: ID!, $%s: ID!" % (pid, cat))
        body.append("  u%d: productUpdate(product: {id: $%s, category: $%s}) { "
                    "product { id title category { id fullName } } "
                    "userErrors { field message } }" % (i, pid, cat))
        variables[pid] = record["gid"]
        variables[cat] = record["category"]
    return ("mutation SetCategories(%s) {\n%s\n}"
            % (", ".join(decls), "\n".join(body)), variables)


def doc_metafields(batch):
    variables = {"metafields": [
        {"ownerId": record["gid"], "namespace": NAMESPACE,
         "key": record["key"], "type": record["type"],
         "value": json.dumps(record["metaobjects"])}
        for record in batch
    ]}
    document = ("mutation SetMetafields($metafields: [MetafieldsSetInput!]!) {\n"
                "  metafieldsSet(metafields: $metafields) {\n"
                "    metafields { id namespace key }\n"
                "    userErrors { field message code }\n"
                "  }\n}")
    return document, variables


def collect(plan, config, enable_definitions):
    """Turn the plan into per-stage operation lists."""
    stages = {name: [] for name in STAGES}

    if enable_definitions:
        stages["definitions"] = list(plan["definitions_to_enable"])

    if config["create_missing_metaobjects"]:
        stages["metaobjects"] = list(plan["new_metaobjects"])

    for product in plan["products"]:
        category = product["category"]
        if category["action"] in ("set", "change"):
            stages["categories"].append({"gid": product["gid"],
                                         "title": product["title"],
                                         "category": category["to"]})

    for product in plan["products"]:
        for metafield in product["metafields"]:
            ready = [v for v in metafield["values"] if v.get("metaobject")]
            if not ready or len(ready) != len(metafield["values"]):
                # Incomplete until its metaobjects exist; apply.py is re-run
                # after stage 1 with a refreshed store map and plan.
                continue
            stages["metafields"].append({
                "gid": product["gid"],
                "title": product["title"],
                "key": metafield["key"],
                "type": "list.metaobject_reference",
                "metaobjects": [v["metaobject"] for v in ready],
            })
    return stages


BUILDERS = {"definitions": doc_definitions, "metaobjects": doc_metaobjects,
            "categories": doc_categories, "metafields": doc_metafields}


def compile_batches(stages, size, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    manifest, number = [], 0
    for name in STAGES:
        operations = stages[name]
        if not operations:
            continue
        for batch in chunk(operations, size):
            number += 1
            document, variables = BUILDERS[name](batch)
            path = os.path.join(out_dir, "batch_%03d.json" % number)
            dump_json(path, {
                "batch": number, "stage": name, "operations": len(batch),
                "mutation": document, "variables": variables,
                "items": batch,
            })
            manifest.append({"batch": number, "stage": name,
                             "operations": len(batch), "file": path,
                             "status": "pending"})
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", default=work("plan.json"))
    parser.add_argument("--out-dir", default=work("batches"))
    parser.add_argument("--checkpoint", default=work("checkpoint.json"))
    parser.add_argument("--backup", default=work("backup.json"))
    parser.add_argument("--stage", choices=STAGES, help="compile one stage only")
    parser.add_argument("--enable-definitions", action="store_true",
                        help="include stage 0; requires explicit approval")
    parser.add_argument("--mark-applied", type=int)
    parser.add_argument("--mark-failed", type=int)
    parser.add_argument("--note", default="")
    parser.add_argument("--record-created",
                        help="JSON of metaobject ids this run created, to merge "
                             "into the backup's created_by_run")
    args = parser.parse_args()

    if args.mark_applied or args.mark_failed:
        checkpoint = load_json(args.checkpoint)
        number = args.mark_applied or args.mark_failed
        for record in checkpoint["batches"]:
            if record["batch"] == number:
                record["status"] = "applied" if args.mark_applied else "failed"
                record["note"] = args.note
                record["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dump_json(args.checkpoint, checkpoint)
        print("batch %d marked %s" % (number, "applied" if args.mark_applied
                                      else "failed"))
        return

    if args.record_created:
        created = load_json(args.record_created)
        backup = load_json(args.backup)
        bucket = backup["created_by_run"]
        for field in ("metaobjects", "metaobject_definitions",
                      "metafield_definitions"):
            for item in created.get(field, []):
                if item not in bucket[field]:
                    bucket[field].append(item)
        dump_json(args.backup, backup)
        print("recorded %d metaobject(s), %d metaobject definition(s) as "
              "created by this run"
              % (len(bucket["metaobjects"]),
                 len(bucket["metaobject_definitions"])))
        return

    plan = load_json(args.plan)
    config = load_config()
    stages = collect(plan, config, args.enable_definitions)
    if args.stage:
        stages = {name: (ops if name == args.stage else [])
                  for name, ops in stages.items()}

    manifest = compile_batches(stages, config["batch_size"], args.out_dir)

    # A run is often re-planned mid-flight (create metaobjects, re-read, plan
    # again), and the later plan no longer shows the categories the earlier one
    # set. The checkpoint therefore ACCUMULATES every product this run has
    # touched, so rollback restores them even after a re-plan.
    touched = set()
    if os.path.exists(args.checkpoint):
        touched.update(load_json(args.checkpoint).get("touched_products") or [])
    touched.update(p["gid"] for p in plan["products"])

    dump_json(args.checkpoint, {
        "_created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_plan_generated": plan.get("_generated"),
        "touched_products": sorted(touched),
        "batches": manifest,
    })

    print("compiled %d batch(es) into %s\n" % (len(manifest), args.out_dir))
    for name in STAGES:
        count = sum(r["operations"] for r in manifest if r["stage"] == name)
        batches = sum(1 for r in manifest if r["stage"] == name)
        flag = ""
        if name == "definitions" and not args.enable_definitions:
            flag = "  (skipped — needs --enable-definitions and explicit approval)"
        print("  %-12s %3d operation(s) in %d batch(es)%s"
              % (name, count, batches, flag))

    pending = [r for r in manifest if r["stage"] == "metafields"]
    incomplete = sum(
        1 for p in plan["products"] for m in p["metafields"]
        if m["values"] and any(not v.get("metaobject") for v in m["values"]))
    if incomplete:
        print("\n  %d metafield(s) are held back until their metaobjects exist."
              % incomplete)
        print("  Run stage 'metaobjects', re-read the store, rebuild the plan,")
        print("  then run apply.py again to pick them up.")
    if not pending and not incomplete:
        print("\n  nothing to write")


if __name__ == "__main__":
    main()
