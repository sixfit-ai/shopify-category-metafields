# Design — shopify-category-metafields

Phase 1 output. No product writes have been made. This records what was
verified against the Admin API and the Pancake Clothing dev store, and the
design that follows from it.

## What this skill does

Assigns each product a category from Shopify's Standard Product Taxonomy, then
fills that category's category metafields. It never touches tags. The tag
skill (`shopify-tag-architect`) is a separate, untouched skill.

## The write chain

A category metafield value is not text. It is a reference to a metaobject,
which in turn references a taxonomy value:

```
taxonomy index            attribute.values[].id      gid://shopify/TaxonomyValue/6711  ("Crew")
                                   |
                                   |  match on metaobject field `taxonomy_reference`
                                   v
store metaobject          shopify--neckline/crew     gid://shopify/Metaobject/508541436231
                                   |
                                   |  metaobject id goes into the metafield value
                                   v
product metafield         shopify.neckline           ["gid://shopify/Metaobject/508541436231"]
                          type: list.metaobject_reference
```

Three consequences:

1. **Values must be resolved per store, at run time.** The metaobject ids are
   store-local. They cannot be baked into the committed index.
2. **Match on `taxonomy_reference`, never on `label`.** Pancake's size entries
   are Dutch (`0-3-maanden`, `2-3-jaar`); their labels do not equal the English
   taxonomy names, but their `taxonomy_reference` does resolve correctly.
3. **A value with no metaobject entry cannot be written until one exists.**

## Mutations

| Operation | Mutation | Notes |
|---|---|---|
| Write category | `productUpdate` + `ProductInput.category` | Scalar field; only included fields change |
| Write metafield | `metafieldsSet` | Targeted by ownerId + namespace + key |
| Remove metafield | `metafieldsDelete` | Needed by rollback when a metafield did not exist before |
| Create a value | `metaobjectCreate` on `shopify--<key>` | Verified to work; see below |
| Enable a definition | `standardMetafieldDefinitionEnable` | namespace `shopify`, key, ownerType `PRODUCT` |

**`productSet` is forbidden.** Shopify's own documentation: *"For list fields:
Creates new entries, updates existing entries, and deletes existing entries
that aren't included in the mutation's input. Common examples of list fields
include collections, metafields, and variants."* Using it would silently delete
every metafield not named in the input — on Pancake that is the entire `sixfit`
and `mc-facebook` namespaces.

**`productUpdate` is allowed only for the `category` field.** The tag skill's
rule against `productUpdate` exists because `ProductInput.tags` replaces the
whole tag list. That hazard is specific to the `tags` field, not the mutation.
This skill never sends `tags`.

## Definition bootstrap (verified 2026-09-24 on Pancake)

A store that has never used a given category metafield has neither the metafield
definition nor the metaobject definition. Test: `shopify.size-type` existed as
neither.

```
standardMetafieldDefinitionEnable(namespace: "shopify", key: "size-type",
                                  ownerType: PRODUCT)
  -> created MetafieldDefinition/458666934599
     type: list.metaobject_reference
     validations: metaobject_definition_id = MetaobjectDefinition/40267120967
```

The metaobject definition `shopify--size-type` was **auto-provisioned** by that
single call — it did not exist before. It arrived **empty** (`metaobjectsCount:
0`), with `createdByApp` attributed to the calling app. So the help-centre claim
that category metafields "have default entries" does not hold: enabling a
definition creates no entries at all.

Bootstrap order for a virgin store is therefore:

1. `standardMetafieldDefinitionEnable` — creates both definitions
2. `metaobjectCreate` per value actually needed — creates the entries
3. `metafieldsSet` — points the product at those entries

### Rollback asymmetry — important

`metafieldDefinitionDelete` is **denied** to this connector app:

> Access denied for metafieldDefinitionDelete field. Required access: API client
> to have access to the resource type associated with the metafield definition.

`metaobjectDefinitionDelete` **is** permitted, and per Shopify's docs deleting a
metaobject definition also deletes its metaobjects and the associated metafield
definitions. That is the only available undo, and it is what reverted the test:
deleting `MetaobjectDefinition/40267120967` removed the `shopify.size-type`
metafield definition with it, restoring the store exactly.

Rollback must therefore undo definitions via `metaobjectDefinitionDelete`, and
only for definitions this skill created. A definition that already existed is
never deleted — it may hold merchant data under other products.

## Backup schema

Written before any mutation, from a fresh read. Rollback must restore the store
exactly, so the backup covers four things, not one.

```json
{
  "_taken": "2026-09-24T10:00:00Z",
  "_shop": "pancakeclothing.com",
  "_taxonomy_version": "2026-08",

  "products": {
    "gid://shopify/Product/10945977581895": {
      "title": "Pancake Mama Duck",
      "category": "gid://shopify/TaxonomyCategory/aa-1-13-8",
      "metafields": {
        "shopify.neckline": {
          "type": "list.metaobject_reference",
          "value": "[\"gid://shopify/Metaobject/508541436231\"]"
        },
        "shopify.size": { "type": "...", "value": "..." }
      }
    }
  },

  "preexisting_metaobjects": {
    "shopify--neckline": ["gid://shopify/Metaobject/508541436231"]
  },

  "preexisting_definitions": {
    "metafield": ["shopify.neckline", "shopify.size"],
    "metaobject": ["shopify--neckline", "shopify--size"]
  },

  "created_by_run": {
    "_note": "Filled in during apply, not at backup time. Rollback removes these.",
    "metaobjects": [],
    "metaobject_definitions": []
  }
}
```

Rules:

- `category: null` is recorded as null, and rollback writes it back to null.
  A product that had no category must end with no category.
- A metafield absent at backup time is absent from `metafields`. Rollback
  removes it with `metafieldsDelete` rather than setting an empty value.
- `preexisting_metaobjects` is what makes `created_by_run` trustworthy: anything
  not in the pre-existing list and created during the run is ours to delete.
- Only `shopify.*` keys that map to a category attribute are captured. Keys in
  `out_of_scope_keys` (`shopify.disclosure`, `shopify.unavailable_reason`) and
  every other namespace (`sixfit`, `mc-facebook`) are neither read nor written,
  and appear in the report as skipped.

## Committed artifacts

| Path | What | Size |
|---|---|---|
| `taxonomy/index.json` | Generated slim index, pinned to v2026-08 | 12.4 MB |
| `taxonomy/key_exceptions.json` | Hand-maintained mapping exceptions | small |
| `taxonomy/key_map.json` | Generated attribute -> metafield key map | ~400 KB |

The 91 MB upstream file is never committed; `scripts/build_taxonomy_index.py`
downloads it on demand and caches it outside the repo.

## Mapping: generated, with curated exceptions

Of 236 sampled `standardMetafieldDefinitionTemplates` in the `shopify`
namespace with owner `PRODUCT`, **232 keys equal the taxonomy attribute handle
exactly.** The four that do not:

| Template key | Why |
|---|---|
| `color-pattern` | Collapses two taxonomy attributes, `color` and `pattern`, into one metafield |
| `bakeware-pieces-included` | Renamed; taxonomy calls it `bakeware-items-included` |
| `disclosure` | Not a category metafield at all |
| `unavailable_reason` | Not a category metafield at all |

So the map is generated as identity and the exception file carries only these.
The store remains authoritative at run time.

## Extended attributes

314 attribute handles referenced by categories do not appear in the upstream
attributes registry. They are **extended attributes** — category-specific
aliases of a base attribute, sharing its id and values. For example
`applique-shape` and `patch-shape` are both aliases of `applique-patch-shape`
(`TaxonomyAttribute/2314`, 10 values). All 314 resolve. The index records the
alias with a `base` pointer.

## `color-pattern` is doubly special

Besides collapsing two attributes into one key, its metaobject does not carry
the usual `taxonomy_reference` field. Every other `shopify--*` type verified has
exactly two fields, `label` and `taxonomy_reference`. `shopify--color-pattern`
instead has five:

```
label                       single_line_text_field
color                       color
image                       file_reference
color_taxonomy_reference    list.product_taxonomy_value_reference
pattern_taxonomy_reference  product_taxonomy_value_reference
```

So value resolution cannot assume the field name. Read the metaobject
definition's `fieldDefinitions` and match on the field whose type is
`product_taxonomy_value_reference` or `list.product_taxonomy_value_reference`,
rather than hardcoding `taxonomy_reference`.

## Round-trip verification (read direction)

Resolving every category metafield on *Pancake Mama Duck* back through the
committed index: **11 of 11 resolved, 0 unresolved** (`color-pattern` handled
separately, per above).

```
size                 -> Double extra large (XXL), Extra large (XL), Large (L), ...
neckline             -> Crew
fabric               -> Bamboo, Cotton
care-instructions    -> Dryer safe, Machine washable, Tumble dry
```

Note the store's metaobject labels (`2XL`) differ from the taxonomy names
(`Double extra large (XXL)`) — more evidence that matching must go through
taxonomy value ids, never labels.

## Open questions — DOĞRULANAMADI

1. **Metafield key for an extended attribute.** Whether a category using
   `applique-shape` writes to `shopify.applique-shape` or to
   `shopify.applique-patch-shape` is not confirmed. No test category was
   available on Pancake. The index carries both handles so either resolution is
   possible; resolve by reading the store's definitions before writing.

2. **Whether `standardMetafieldDefinitionEnable` is appropriate to call
   automatically.** It was verified to work, but it changes store-wide
   configuration, not one product. Treated in this design as requiring explicit
   merchant approval, listed separately in the plan.

3. **Value coverage for a large catalog.** Resolving values requires reading
   every existing metaobject per type. For types with many entries this needs
   pagination; no limit problems were observed at Pancake's scale (max 24
   entries) but it is untested at scale.

---

# Phase 3 pilot — live run findings (2026-09-24)

A two-product pilot (PROBE D, PROBE G) was run end to end against Pancake
Clothing: backup → create 7 metaobjects → set 2 categories → set 5 metafields →
rollback. Everything the skill itself writes was restored. Two things were not,
and both are limits of the environment rather than bugs in the plan.

## 1. `metafieldsDelete` is refused on the `shopify` namespace

```
metafieldsDelete(metafields: [{ownerId, namespace: "shopify", key: "size"}, ...])
  -> "Access to this namespace and key on Metafields for this resource type
      is not allowed."
```

The connector can WRITE category metafields but cannot DELETE them. A metafield
this skill created therefore cannot be removed by rollback. The best available
undo is `metafieldsSet` with `value: "[]"`, which was verified to work: the row
survives holding an empty list, carrying no values.

Consequence for the acceptance criterion "rollback restores metafields exactly":
values are restored exactly, but a metafield that did not exist before the run
is left present-and-empty rather than absent. `rollback.py` now emits the empty
clear and warns about the residue instead of emitting a delete that fails.

### Future improvement — a custom app with delete scope

This limit is a property of the connector, not of Shopify. A custom app granted
`write_metafields` for the `shopify` namespace on products would be able to call
`metafieldsDelete` and make rollback byte-exact. Worth doing if exact restoration
ever becomes a hard requirement; until then the empty-list clear is the ceiling,
and the run report must say so.

## 2. Setting a category makes other apps write

After the two categories were set, both products gained a metafield this skill
never wrote:

```
mc-facebook.google_product_category = "212"   (PROBE D)
mc-facebook.google_product_category = "5410"  (PROBE G)
```

The Meta/Facebook channel app reacted to the category change and wrote its own
mapping. It persisted after rollback, because it belongs to another app and this
skill neither reads nor writes that namespace.

This is worth telling the merchant before applying: assigning categories can
cause connected sales-channel apps to update their own product data, and this
skill cannot undo those side effects.

## What WAS restored exactly

| | before | after rollback |
|---|---|---|
| Categories (both pilot products) | `null` | `null` |
| Categories (other 10 products) | unchanged | unchanged |
| Tags (all 12 products) | baseline | identical |
| `shopify--size` entry count | 24 | 24 |
| All 14 metaobject definition counts | baseline | identical |
| Product metafield definitions | 12 | 12 |
| `sixfit.*` on both products | present | unchanged |

## Bug found and fixed by the pilot

Re-planning mid-run (create metaobjects → re-read → plan again) turned the
already-applied category actions into `keep`, so rollback computed zero
categories to restore. The checkpoint now accumulates `touched_products` across
re-plans, and rollback restores the category of anything the run touched
regardless of what the latest plan says.

---

# Is an empty `[]` metafield harmless? (verified 2026-09-24)

The claim needed testing, because rollback leaves these behind. Tested against
the live Pancake store using the residue from the pilot run.

## Admin API — VERIFIED harmless

An absent metafield and an emptied one are distinguishable, but the emptied one
carries nothing:

```
absent :  product.metafield(namespace:"shopify", key:"neckline")  ->  null
emptied:  product.metafield(namespace:"shopify", key:"size")      ->  { value: "[]",
                                                                        references: null }
populated:                                                        ->  { value: "[...]",
                                                                        references: {nodes:[...]} }
```

`references` is **null**, not an empty list. Anything consuming references —
which is how every renderer and exporter reads a `list.metaobject_reference` —
sees nothing at all.

## Automatic collections — VERIFIED cannot be affected

```
metafieldDefinition(shopify.size).capabilities.smartCollectionCondition.enabled = false
metafieldDefinition(shopify.size).capabilities.adminFilterable.enabled          = false
```

Category metafields are not usable as automatic-collection conditions on this
store, so an empty one cannot pull a product into or out of a collection.

## Storefront filters — NOT APPLICABLE on this store, DOĞRULANAMADI in general

The live storefront's collection page offers only **Beschikbaarheid**
(availability) and **Prijs** (price). No metafield-backed filter is configured,
so an empty category metafield changes nothing here. Whether a store that HAS
configured a Size or Colour filter would render an empty value as a blank facet
is **DOĞRULANAMADI** — it could not be tested without such a filter configured.
The definition's `storefront: PUBLIC_READ` access means the empty metafield IS
readable by the Storefront API, so a theme that renders the field without
checking for emptiness could show a blank row.

## Admin product page — DOĞRULANAMADI

Not verified. Reaching the admin product page requires signing in to Shopify
admin, and entering credentials is out of scope. The expected behaviour is that
the field appears in the product's Metafields section with no value selected —
the same as any defined-but-unset metafield — but this was not observed.

## Google / Meta feeds — DOĞRULANAMADI

Not verified. The feeds are generated inside the Google and Meta channel apps
and are not readable through the Admin API. Since `references` resolves to null,
an exporter reading references would see no value; an exporter reading the raw
`value` string would see the literal `[]`. Which of those the channel apps do
was not determined.

## One thing that was NOT harmless, and is now fixed

An empty metafield counts as a SET metafield to `metafieldsCount`, and — more
importantly — the planner initially treated it as `already_set` under
`overwrite_existing_metafields: false`. The residue of one rolled-back run would
therefore have permanently blocked the next run from filling that attribute.
`build_plan.py` now treats `[]`, `""` and `null` as unset.

## Updated acceptance criterion

> Rollback restores every category and every `shopify.*` category metafield
> **value** exactly, restores a category back to none where there was none, and
> deletes every metaobject the run created. A metafield that did **not exist**
> before the run is left present with an empty value rather than removed,
> because `metafieldsDelete` is refused on the `shopify` namespace for this
> connector. An emptied metafield resolves to no references, cannot drive an
> automatic collection, and is treated as unset by later runs. Side effects
> written by other apps in response to a category change — such as
> `mc-facebook.google_product_category` — are outside the skill's scope and are
> not reverted.
