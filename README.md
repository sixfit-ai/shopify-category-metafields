# shopify-category-metafields

A Claude skill that assigns every product a category from **Shopify's Standard
Product Taxonomy** and fills that category's **category metafields** — colour,
size, fabric, neckline, sleeve length, care instructions, and whatever else the
category defines.


## Why this matters

Category metafields are what storefront filters read, what Google Merchant
Center and Meta map product attributes from, and what Shopify's own search and
recommendations index. A product with no category has none of that.

## What makes it harder than it looks

A category metafield value is not text. It is a reference to a **metaobject**,
which references a **taxonomy value**:

```
taxonomy value   gid://shopify/TaxonomyValue/6711   "Crew"
      ↓          matched on the metaobject's taxonomy_reference field
store metaobject gid://shopify/Metaobject/508541436231   shopify--neckline/crew
      ↓          the metaobject id is the metafield value
product          shopify.neckline = ["gid://shopify/Metaobject/508541436231"]
```

Three things follow, and the skill is built around them:

- **Values are store-local.** The metaobject ids differ per store, so they are
  resolved at run time, never baked in.
- **Entries do not pre-exist.** A store can have one neckline entry where the
  taxonomy has eighteen. Missing ones are created — as a separately approved
  step.

## Safety

- `productSet` is **never** used. It deletes list fields absent from its input,
  and metafields are a list field — one call would wipe other apps' namespaces.
- `productUpdate` is used **only** for the `category` field.
- Nothing is written before a verified backup exists.
- Rollback restores categories (including back to none), restores metafield
  values exactly, and removes the metaobjects this run created. A metafield that
  did not exist before is emptied rather than deleted — see Known limits.
- A metaobject definition is deleted only if this run created it, it holds no
  entry from anyone else, and no product references it. Otherwise it is left in
  place and reported.

## The taxonomy index

The upstream release is 91 MB expanded and is never committed. A generator pins
one release and reduces it to what the skill needs:

```
python3 scripts/build_taxonomy_index.py --version 2026-08
```

The result — `taxonomy/index.json.gz`, **1.6 MB** — holds 14,606 categories and
81,518 attribute values, and records its source URL, version, and the upstream
asset's SHA-256 in its header.

## Run shape

```
normalize_catalog.py   reshape the fetched catalog
fetch_images.py        download product photos, so `pattern` has real evidence
build_store_map.py     what this store can write today
build_prompts.py       one prompt per category, with allowed values
  → you choose categories and values → work/proposals.json
build_plan.py          validate; write plan.json / plan.csv / plan.md
backup.py              fresh read, verified coverage
apply.py               staged batches: definitions → metaobjects → categories → metafields
rollback.py            the exact reverse, with a deletion guard
```

Every script is standard library only and takes `--help`. Nothing calls Shopify
directly; Claude runs the queries through the Shopify MCP connector and the
scripts reshape, validate, and compile.

## Configuration

`config.json`. The one most likely to be changed:

```json
"no_match_behavior": "leave_empty"
```

`leave_empty` (default) writes nothing when no allowed value matches the
product, and reports it. `use_default` writes a value from
`defaults_by_attribute`, but only when that value is itself allowed for the
attribute.

## Known limits

Found by running this against a live store, not by reasoning about it. All three
are properties of the environment; the skill reports each rather than hiding it.

**Rollback empties, it cannot delete.** `metafieldsDelete` is refused on the
`shopify` namespace for the Shopify MCP connector:

> Access to this namespace and key on Metafields for this resource type is not
> allowed.

So a metafield that did not exist before a run is left present with an empty
value (`[]`) rather than removed. Values are restored exactly; categories are
restored exactly, including back to none. An emptied metafield resolves to no
references and is treated as unset by later runs. A custom app with delete scope
would close this gap — see `docs/design.md`.

**Setting a category makes other apps write.** On the test store, categorising
products caused the Meta channel app to add its own
`mc-facebook.google_product_category` to eight of them. That is the app doing
its job, it is outside this skill's namespace, and it is not reverted by
rollback. The merchant is told this before approving.

**Some values need a companion.** `shopify--color-pattern` requires both a base
colour and a base pattern; Shopify rejects a colour entry without one ("Base
pattern can't be blank"). When a new colour is needed, the plan also needs a
pattern with its own evidence — usually the product photo. Without it the value
is reported as blocked rather than invented.

## Licence

MIT.
