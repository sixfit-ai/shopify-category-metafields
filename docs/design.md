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
