#!/usr/bin/env python3
"""Validate proposals against the taxonomy and the store, and emit the plan.

This script makes NO decisions about what a product is. Claude authors
work/proposals.json; this is the gate that decides which of those proposals may
reach the store.

Inputs
------
work/products.json     from normalize_catalog.py
work/store_map.json    from build_store_map.py  (the store is authoritative)
work/proposals.json    authored by Claude:

    { "gid://shopify/Product/1": {
        "category": "gid://shopify/TaxonomyCategory/aa-1-13-8",
        "category_reason": "product_type 'tshirts'",
        "attributes": {
          "neckline": [ {"value": "Crew", "source": "description: \\"crew neck\\""} ]
        } } }

Rejection rules, all enforced here and none in Claude's head
-----------------------------------------------------------
  unknown_category        category id absent from the taxonomy index
  category_not_leaf       category has children; only leaves may be assigned
  attribute_not_in_category   attribute is not declared by the chosen category
  unknown_value           value is not an allowed value of that attribute
  duplicate_value         same value proposed twice for one attribute
  already_set             product already has a value and overwrite is off
  missing_source          no source recorded for a value
  unresolved_attribute    an extended attribute neither handle resolves for

Values that pass validation are then split by what the store can do today:
  writable      an entry exists -> goes into the metafield write
  needs_entry   no entry -> listed under new_metaobjects for separate approval
  no_definition -> listed under definitions_to_enable for separate approval

Outputs
-------
work/plan.json   execution input
work/plan.csv    one row per value, for spreadsheets
work/plan.md     human-readable summary for merchant review

Exit status 0 when a plan was written, 1 when nothing survived.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (NAMESPACE, dump_json, load_config, load_index,  # noqa: E402
                     load_json, load_key_map, short_gid, work)


def reject(bucket, gid, title, attribute, value, code, detail):
    bucket.append({"gid": gid, "title": title, "attribute": attribute,
                   "value": value, "code": code, "detail": detail})


class Planner:
    def __init__(self, index, key_map, store_map, config):
        self.index = index
        self.key_map = key_map
        self.store = store_map
        self.config = config
        self.rejected = []
        self.unresolved = []
        self.new_entries = {}
        self.blocked_entries = {}
        self.need_definitions = {}
        self.proposals = {}

    def proposal_for(self, gid):
        return self.proposals.get(gid)

    # -- key and attribute resolution ------------------------------------

    def metafield_key(self, handle):
        """Resolve an attribute handle to the metafield key this store uses.

        Extended attributes are aliases; the taxonomy does not say whether the
        key follows the alias or its base. Resolve it against the store, and if
        neither is defined there, refuse to guess.
        """
        mapped = self.key_map["attribute_to_key"].get(handle, handle)
        candidates = [mapped]
        base = (self.index["attributes"].get(handle) or {}).get("base")
        if base:
            candidates.append(self.key_map["attribute_to_key"].get(base, base))

        for candidate in candidates:
            if candidate in self.store["keys"]:
                return candidate, None
        # Nothing in the store. If it is an alias we cannot tell which key is
        # right, so it is unresolved rather than merely missing a definition.
        if base:
            return None, ("unresolved_attribute",
                          "extended attribute; neither '%s' nor '%s' is defined "
                          "in this store, and the taxonomy does not say which "
                          "the metafield key follows"
                          % (candidates[0], candidates[-1]))
        return mapped, ("no_definition",
                        "shopify.%s is not enabled in this store" % mapped)

    def has_value(self, product, key):
        """Whether the product's metafield actually holds anything.

        A rollback cannot delete a category metafield -- metafieldsDelete is
        refused on the `shopify` namespace for this connector -- so it clears it
        to `[]` instead. That empty row must count as UNSET, otherwise the
        residue of one rolled-back run would permanently block the next one from
        filling the same attribute.
        """
        spec = (product.get("metafields") or {}).get(key)
        if spec is None:
            return False
        raw = (spec.get("value") or "").strip()
        if raw in ("", "[]", "null"):
            return False
        try:
            return bool(json.loads(raw))
        except ValueError:
            return True

    def allowed_values(self, handle):
        attribute = self.index["attributes"].get(handle)
        if not attribute:
            return {}
        return {v["name"]: v["id"] for v in attribute["values"]}

    def required_reference_fields(self, mo_type):
        """Required taxonomy-reference fields of a metaobject type.

        Most types have exactly one. `shopify--color-pattern` has two, both
        required: creating a colour entry also demands a Base pattern. Verified
        on a live store -- omitting it fails with "Base pattern can't be blank".
        """
        definition = self.store["metaobject_definitions"].get(mo_type) or {}
        return [f for f in definition.get("fields") or []
                if f.get("required") and f.get("type") in
                ("product_taxonomy_value_reference",
                 "list.product_taxonomy_value_reference")]

    def reference_field(self, mo_type, handle):
        """Which metaobject field carries the taxonomy reference, and its shape.

        Usually `taxonomy_reference`. `shopify--color-pattern` instead has
        `color_taxonomy_reference` (a list) and `pattern_taxonomy_reference`,
        so the attribute handle picks between them. Never hardcode the name.
        """
        definition = self.store["metaobject_definitions"].get(mo_type) or {}
        candidates = [f for f in definition.get("fields") or []
                      if f.get("type") in
                      ("product_taxonomy_value_reference",
                       "list.product_taxonomy_value_reference")]
        if not candidates:
            return None, False
        if len(candidates) > 1:
            prefixed = [f for f in candidates
                        if f["key"].startswith(handle.replace("-", "_"))
                        or f["key"].startswith(handle)]
            if len(prefixed) == 1:
                candidates = prefixed
            else:
                return None, False
        field = candidates[0]
        return field["key"], field["type"].startswith("list.")

    def companions(self, mo_type, primary_field, handle, product, category):
        """Fill the OTHER required reference fields of a new metaobject.

        A companion is only ever taken from a value the merchant's own proposal
        supplies for the same product, or from an explicit config default. It is
        never invented -- an unfilled companion blocks the entry instead.
        """
        filled, missing = [], []
        for field in self.required_reference_fields(mo_type):
            if field["key"] == primary_field:
                continue
            # Which taxonomy attribute feeds this field? Field keys are of the
            # form "<attribute>_taxonomy_reference".
            attribute = field["key"].replace("_taxonomy_reference", "").replace("_", "-")
            proposed = (self.proposal_for(product["gid"]) or {}) \
                .get("attributes", {}).get(attribute)
            chosen = None
            if proposed:
                first = proposed[0]
                chosen = first.get("value") if isinstance(first, dict) else first
                origin = "proposed for this product"
            if chosen is None:
                default = (self.config.get("companion_defaults") or {}).get(
                    "%s.%s" % (mo_type, field["key"]))
                if default:
                    chosen, origin = default, "config companion_defaults"
            allowed = self.allowed_values(attribute) if attribute in \
                category["attributes"] else self.allowed_values(attribute)
            if chosen is None or chosen not in allowed:
                missing.append({
                    "field": field["key"], "attribute": attribute,
                    "detail": "required by '%s' and not supplied; set "
                              "companion_defaults[\"%s.%s\"] in config.json or "
                              "propose a '%s' value for this product"
                              % (mo_type, mo_type, field["key"], attribute)})
                continue
            filled.append({"field": field["key"], "attribute": attribute,
                           "value": chosen, "value_id": allowed[chosen],
                           "is_list": field["type"].startswith("list."),
                           "source": origin})
        return filled, missing

    def entry_for(self, key, value_id):
        spec = self.store["keys"].get(key)
        if not spec:
            return None
        mo_type = spec.get("metaobject_type")
        entries = self.store["entries_by_value"].get(mo_type, {})
        found = entries.get(short_gid(value_id))
        return found[0] if found else None

    # -- per product ------------------------------------------------------

    def plan_product(self, product, proposal):
        gid, title = product["gid"], product["title"]
        current = product.get("category")
        chosen = proposal.get("category") or current

        if not chosen:
            reject(self.rejected, gid, title, None, None, "unknown_category",
                   "no category proposed and none set on the product")
            return None

        category = self.index["categories"].get(chosen)
        if category is None:
            reject(self.rejected, gid, title, None, chosen, "unknown_category",
                   "not present in taxonomy index %s" % self.index["_version"])
            return None
        if not category["is_leaf"]:
            reject(self.rejected, gid, title, None, chosen, "category_not_leaf",
                   "'%s' has child categories" % category["full_name"])
            return None

        if current and self.config["keep_existing_category"] \
                and proposal.get("category") in (None, current):
            category_action = "keep"
        elif current == chosen:
            category_action = "keep"
        elif current:
            category_action = "change"
        else:
            category_action = "set"

        entry = {
            "gid": gid,
            "title": title,
            "category": {
                "action": category_action,
                "from": current,
                # A catalog read can come back without fullName; the index has
                # it, and a blank "before" path in the plan is unreadable.
                "from_name": (product.get("category_full_name")
                              or (self.index["categories"].get(current) or {})
                              .get("full_name") or ""),
                "to": chosen,
                "to_name": category["full_name"],
                "reason": proposal.get("category_reason", ""),
            },
            "metafields": [],
        }

        for handle, items in (proposal.get("attributes") or {}).items():
            self.plan_attribute(entry, product, category, handle, items)
        return entry

    def plan_attribute(self, entry, product, category, handle, items):
        gid, title = product["gid"], product["title"]

        if handle not in category["attributes"]:
            reject(self.rejected, gid, title, handle, None,
                   "attribute_not_in_category",
                   "'%s' does not declare this attribute" % category["name"])
            return

        # A companion-only attribute never writes a metafield of its own. Its
        # value lives INSIDE the primary attribute's metaobject as a required
        # reference field -- `pattern` inside a `shopify--color-pattern` entry.
        # Emitting it here would write the shared key twice, second write wins.
        companion_only = self.key_map.get("companion_only_attributes") or {}
        if handle in companion_only:
            entry["metafields"].append({
                "key": companion_only[handle], "attribute": handle,
                "action": "companion_only", "values": [],
                "note": "supplies the required %s field inside the '%s' entry; "
                        "it does not write a metafield of its own"
                        % (handle, self.key_map["primary_attribute"]
                           .get(companion_only[handle], "primary")),
            })
            return

        key, problem = self.metafield_key(handle)
        if problem and problem[0] == "unresolved_attribute":
            self.unresolved.append({"gid": gid, "title": title,
                                    "attribute": handle, "detail": problem[1]})
            reject(self.rejected, gid, title, handle, None, *problem)
            return

        allowed = self.allowed_values(handle)
        already = self.has_value(product, key)
        if already and not self.config["overwrite_existing_metafields"]:
            reject(self.rejected, gid, title, handle, None, "already_set",
                   "shopify.%s already has a value; overwrite is off" % key)
            return

        values, seen = [], set()
        for item in items or []:
            name = item.get("value") if isinstance(item, dict) else item
            source = item.get("source", "") if isinstance(item, dict) else ""

            if name not in allowed:
                reject(self.rejected, gid, title, handle, name, "unknown_value",
                       "not an allowed value of '%s'" % handle)
                continue
            if name in seen:
                reject(self.rejected, gid, title, handle, name, "duplicate_value",
                       "proposed more than once")
                continue
            if not source:
                reject(self.rejected, gid, title, handle, name, "missing_source",
                       "every value must record the product field it came from")
                continue
            seen.add(name)

            value_id = allowed[name]
            record = {"name": name, "value_id": value_id, "source": source}

            if problem and problem[0] == "no_definition":
                record["status"] = "no_definition"
                self.need_definitions.setdefault(key, {
                    "key": key, "attribute": handle,
                    "reason": problem[1], "needed_by": []})
                if gid not in self.need_definitions[key]["needed_by"]:
                    self.need_definitions[key]["needed_by"].append(gid)
            else:
                found = self.entry_for(key, value_id)
                if found:
                    record["status"] = "writable"
                    record["metaobject"] = found["metaobject"]
                    if found.get("label") and found["label"] != name:
                        record["label_mismatch"] = found["label"]
                else:
                    mo_type = self.store["keys"][key]["metaobject_type"]
                    ref_field, is_list = self.reference_field(mo_type, handle)
                    if ref_field is None:
                        record["status"] = "unresolved_reference_field"
                        self.unresolved.append({
                            "gid": gid, "title": title, "attribute": handle,
                            "detail": "cannot tell which field of '%s' carries "
                                      "the taxonomy reference for this "
                                      "attribute; entry not proposed" % mo_type})
                        values.append(record)
                        continue
                    companions, missing = self.companions(
                        mo_type, ref_field, handle, product, category)
                    if missing:
                        record["status"] = "blocked_new_entry"
                        record["missing_companion"] = missing
                        slot = self.blocked_entries.setdefault(
                            (mo_type, value_id),
                            {"metaobject_type": mo_type, "label": name,
                             "attribute": handle, "taxonomy_value": value_id,
                             "missing": missing, "needed_by": []})
                        if gid not in slot["needed_by"]:
                            slot["needed_by"].append(gid)
                        values.append(record)
                        continue
                    record["status"] = "needs_entry"
                    slot = self.new_entries.setdefault(
                        (mo_type, value_id),
                        {"metaobject_type": mo_type, "key": key,
                         "attribute": handle, "label": name,
                         "taxonomy_value": value_id,
                         "reference_field": ref_field,
                         "reference_is_list": is_list,
                         "companions": companions,
                         "needed_by": []})
                    if gid not in slot["needed_by"]:
                        slot["needed_by"].append(gid)
            values.append(record)

        if not values:
            behavior = self.config["no_match_behavior"]
            default = (self.config.get("defaults_by_attribute") or {}).get(handle)
            if behavior == "use_default" and default and default in allowed:
                values.append({"name": default, "value_id": allowed[default],
                               "source": "config default (no product evidence)",
                               "status": "default"})
                found = self.entry_for(key, allowed[default])
                if found:
                    values[-1]["status"] = "writable"
                    values[-1]["metaobject"] = found["metaobject"]
            else:
                entry["metafields"].append({
                    "key": key, "attribute": handle, "action": "leave_empty",
                    "values": [],
                    "note": "no allowed value matched" if behavior == "leave_empty"
                            else "no allowed value matched and no usable default",
                })
                return

        entry["metafields"].append({
            "key": key,
            "attribute": handle,
            "action": "overwrite" if already else "set",
            "values": values,
        })


def write_csv(path, plan):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product", "title", "metafield_key", "attribute",
                         "value", "taxonomy_value_id", "status", "source"])
        for product in plan["products"]:
            for metafield in product["metafields"]:
                if not metafield["values"]:
                    writer.writerow([product["gid"], product["title"],
                                     metafield["key"], metafield["attribute"],
                                     "", "", metafield["action"],
                                     metafield.get("note", "")])
                for value in metafield["values"]:
                    writer.writerow([product["gid"], product["title"],
                                     metafield["key"], metafield["attribute"],
                                     value["name"], value["value_id"],
                                     value["status"], value["source"]])


def write_md(path, plan):
    out = []
    add = out.append
    counts = plan["summary"]

    add("# Category and metafield plan\n")
    add("Store: **%s** · taxonomy `%s` · generated %s\n"
        % (plan["_shop"], plan["_taxonomy_version"], plan["_generated"]))
    add("**Nothing here has been written.** This is a proposal.\n")

    add("## In one line\n")
    add("%d products; %d categories set, %d changed, %d kept. "
        "%d metafield values across %d metafields. "
        "%d new metaobject entries needed, %d definitions would have to be enabled. "
        "%d proposals rejected.\n"
        % (counts["products"], counts["category_set"], counts["category_change"],
           counts["category_keep"], counts["values"], counts["metafields"],
           len(plan["new_metaobjects"]), len(plan["definitions_to_enable"]),
           counts["rejected"]))

    changed = [p for p in plan["products"]
               if p["category"]["action"] == "change"]
    if changed:
        add("## Category changes — approve these separately\n")
        add("A changed category moves the product within Shopify's own taxonomy "
            "and in every channel that reads it. It is the most visible thing "
            "this run does. Read this section on its own and approve it "
            "separately from the rest of the plan.\n")
        add("| Product | From | To |")
        add("|---|---|---|")
        for product in changed:
            category = product["category"]
            add("| %s | %s<br>`%s` | **%s**<br>`%s` |"
                % (product["title"], category["from_name"], category["from"],
                   category["to_name"], category["to"]))
        add("")
        for product in changed:
            add("- **%s** — %s" % (product["title"],
                                   product["category"]["reason"]))
        add("")

    add("## Products\n")
    for product in plan["products"]:
        category = product["category"]
        add("### %s\n" % product["title"])
        add("`%s`\n" % product["gid"])
        reason = category["reason"] or "_no reason given_"
        if category["action"] == "set":
            add("**Category — set**\n")
            add("| | Path | Id |")
            add("|---|---|---|")
            add("| before | _(none)_ | — |")
            add("| after | %s | `%s` |" % (category["to_name"], category["to"]))
            add("\nWhy: %s\n" % reason)
        elif category["action"] == "change":
            add("**Category — changed**\n")
            add("| | Path | Id |")
            add("|---|---|---|")
            add("| before | %s | `%s` |"
                % (category["from_name"], category["from"]))
            add("| after | %s | `%s` |" % (category["to_name"], category["to"]))
            add("\nWhy: %s\n" % reason)
        else:
            add("**Category — unchanged**\n")
            add("| | Path | Id |")
            add("|---|---|---|")
            add("| kept | %s | `%s` |" % (category["to_name"], category["to"]))
            add("\nWhy: %s\n" % reason)

        writable = [m for m in product["metafields"] if m["values"]]
        companions = [m for m in product["metafields"]
                      if m.get("action") == "companion_only"]
        empty = [m for m in product["metafields"]
                 if not m["values"] and m.get("action") != "companion_only"]
        if writable:
            add("")
            add("| Metafield | Value | From | Status |")
            add("|---|---|---|---|")
            for metafield in writable:
                for value in metafield["values"]:
                    flag = {"writable": "ready", "needs_entry": "**new entry**",
                            "no_definition": "**definition off**",
                            "default": "default"}.get(value["status"], value["status"])
                    note = ""
                    if value.get("label_mismatch"):
                        note = " ⚠ store label is `%s`" % value["label_mismatch"]
                    add("| `shopify.%s` | %s | %s | %s%s |"
                        % (metafield["key"], value["name"],
                           value["source"], flag, note))
        if empty:
            add("")
            for metafield in empty:
                add("- `shopify.%s` — left empty (%s)"
                    % (metafield["key"], metafield.get("note", "")))
        if companions:
            add("")
            for metafield in companions:
                add("- `%s` — feeds `shopify.%s`; it has no metafield of its own"
                    % (metafield["attribute"], metafield["key"]))
        add("")

    if plan["new_metaobjects"]:
        add("## New metaobject entries to create\n")
        add("These taxonomy values have no entry in this store yet. Creating "
            "them is a **separate approval**; nothing else in the plan depends "
            "on approving all of them.\n")
        add("| Metaobject type | Label | Taxonomy value | Needed by |")
        add("|---|---|---|---|")
        for record in plan["new_metaobjects"]:
            add("| `%s` | %s | `%s` | %d product(s) |"
                % (record["metaobject_type"], record["label"],
                   short_gid(record["taxonomy_value"]), len(record["needed_by"])))
        add("")

    if plan["blocked_new_metaobjects"]:
        add("## Blocked — new entries that cannot be created yet\n")
        add("Creating these needs a value this skill will not invent. Supply it "
            "and re-plan, or drop the attribute.\n")
        add("| Metaobject type | Label | Missing | Needed by |")
        add("|---|---|---|---|")
        for record in plan["blocked_new_metaobjects"]:
            add("| `%s` | %s | %s | %d product(s) |"
                % (record["metaobject_type"], record["label"],
                   "; ".join(m["detail"] for m in record["missing"]),
                   len(record["needed_by"])))
        add("")

    if plan["definitions_to_enable"]:
        add("## Metafield definitions to enable\n")
        add("These category metafields are not turned on in this store. "
            "Enabling one changes store-wide configuration, not a single "
            "product, and it is **never done automatically**. Approve each "
            "explicitly, or drop the attribute from the plan.\n")
        add("| Metafield | Attribute | Needed by |")
        add("|---|---|---|")
        for record in plan["definitions_to_enable"]:
            add("| `shopify.%s` | %s | %d product(s) |"
                % (record["key"], record["attribute"], len(record["needed_by"])))
        add("")

    if plan["unresolved"]:
        add("## Could not resolve\n")
        add("Extended taxonomy attributes whose metafield key cannot be "
            "determined from this store. Not guessed, not written.\n")
        for record in plan["unresolved"]:
            add("- **%s** — `%s`: %s"
                % (record["title"], record["attribute"], record["detail"]))
        add("")

    if plan["rejected"]:
        add("## Rejected proposals\n")
        add("| Product | Attribute | Value | Why |")
        add("|---|---|---|---|")
        for record in plan["rejected"]:
            add("| %s | %s | %s | `%s` — %s |"
                % (record["title"], record["attribute"] or "—",
                   record["value"] or "—", record["code"], record["detail"]))
        add("")

    if plan["skipped_metafields"]:
        add("## Left untouched\n")
        add("Metafields outside the category scope. Never read, never written.\n")
        for key, count in sorted(plan["skipped_metafields"].items()):
            add("- `%s` — %d product(s)" % (key, count))
        add("")

    add("## Tags\n")
    add("This skill does not read or write tags. No tag is touched by this plan.\n")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--products", default=work("products.json"))
    parser.add_argument("--store-map", default=work("store_map.json"))
    parser.add_argument("--proposals", default=work("proposals.json"))
    parser.add_argument("--out-dir", default=work())
    args = parser.parse_args()

    index = load_index()
    key_map = load_key_map()
    store_map = load_json(args.store_map)
    config = load_config()
    catalog = load_json(args.products)
    proposals = load_json(args.proposals)

    by_gid = {p["gid"]: p for p in catalog["products"]}
    planner = Planner(index, key_map, store_map, config)
    planner.proposals = {k: v for k, v in proposals.items()
                         if not k.startswith("_")}

    products = []
    for gid, proposal in proposals.items():
        if gid.startswith("_"):
            continue
        product = by_gid.get(gid)
        if product is None:
            reject(planner.rejected, gid, "(unknown)", None, None,
                   "unknown_product", "not in %s" % args.products)
            continue
        entry = planner.plan_product(product, proposal)
        if entry and (entry["metafields"] or entry["category"]["action"] != "keep"):
            products.append(entry)

    skipped = {}
    for product in catalog["products"]:
        for key in product.get("skipped_metafields") or []:
            skipped[key] = skipped.get(key, 0) + 1

    summary = {
        "products": len(products),
        "category_set": sum(1 for p in products if p["category"]["action"] == "set"),
        "category_change": sum(1 for p in products if p["category"]["action"] == "change"),
        "category_keep": sum(1 for p in products if p["category"]["action"] == "keep"),
        "metafields": sum(len(p["metafields"]) for p in products),
        "values": sum(len(m["values"]) for p in products for m in p["metafields"]),
        "rejected": len(planner.rejected),
    }

    plan = {
        "_generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_shop": store_map.get("_shop"),
        "_taxonomy_version": index["_version"],
        "_namespace": NAMESPACE,
        "_config": {k: config[k] for k in
                    ("no_match_behavior", "keep_existing_category",
                     "overwrite_existing_metafields")},
        "summary": summary,
        "products": products,
        "new_metaobjects": sorted(planner.new_entries.values(),
                                  key=lambda r: (r["metaobject_type"], r["label"])),
        "blocked_new_metaobjects": sorted(
            planner.blocked_entries.values(),
            key=lambda r: (r["metaobject_type"], r["label"])),
        "definitions_to_enable": sorted(planner.need_definitions.values(),
                                        key=lambda r: r["key"]),
        "unresolved": planner.unresolved,
        "rejected": planner.rejected,
        "skipped_metafields": skipped,
    }

    os.makedirs(args.out_dir, exist_ok=True)
    dump_json(os.path.join(args.out_dir, "plan.json"), plan)
    write_csv(os.path.join(args.out_dir, "plan.csv"), plan)
    write_md(os.path.join(args.out_dir, "plan.md"), plan)

    print("wrote plan.json, plan.csv, plan.md to %s\n" % args.out_dir)
    print("  products in plan       : %d" % summary["products"])
    print("    category set         : %d" % summary["category_set"])
    print("    category changed     : %d" % summary["category_change"])
    print("    category kept        : %d" % summary["category_keep"])
    print("  metafields             : %d" % summary["metafields"])
    print("  values                 : %d" % summary["values"])
    print("  new metaobject entries : %d" % len(plan["new_metaobjects"]))
    print("  blocked new entries    : %d" % len(plan["blocked_new_metaobjects"]))
    print("  definitions to enable  : %d" % len(plan["definitions_to_enable"]))
    print("  unresolved attributes  : %d" % len(plan["unresolved"]))
    print("  rejected               : %d" % summary["rejected"])

    if not products:
        print("\nnothing survived validation")
        sys.exit(1)


if __name__ == "__main__":
    main()
