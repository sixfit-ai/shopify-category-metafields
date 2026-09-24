---
name: shopify-category-metafields
description: >-
  Assign every product a category from Shopify's Standard Product Taxonomy and
  fill that category's category metafields, through the Shopify MCP connector.
  Use when a merchant wants their products categorised, says their products have
  no category or the wrong one, wants product attributes like colour, size,
  fabric, neckline or sleeve length filled in, asks why their products are
  rejected or miscategorised in Google Shopping or Meta catalogs, wants filters
  on their storefront to work, or wants their catalog data to match Shopify's
  standard taxonomy. This applies even when the merchant never says "metafield"
  — "categorise my products", "fill in my product details", "my products are
  missing attributes", or "Google says my product data is incomplete" are all
  this skill. This skill does not touch tags.
---

# Shopify category and category metafields

Shopify's Standard Product Taxonomy gives every product a category, and each
category defines the attributes that describe it — a T-shirt has a neckline and
a sleeve length; a dog bed does not. Those attributes are stored as **category
metafields**. Filling them is what makes storefront filters work, what Google
Merchant Center and Meta read, and what Shopify's own search uses.

This skill assigns the category and fills those metafields. **It never reads or
writes tags.**

## How to talk to the merchant

Assume they are not technical. They run a shop.

- Plain English. No GraphQL, no GIDs, no "mutations" unless they ask.
- Say "product category" not "taxonomy node". Say "product detail" not
  "metafield" unless they use the word first.
- Show products by title, never by ID. Never show raw JSON.

## What makes this skill different from tagging

A tag is free text. A category metafield is not: its value is a reference to a
**metaobject**, which in turn references a **taxonomy value**. Writing "V-neck"
means finding — or creating — the store's `shopify--neckline` entry whose
`taxonomy_reference` is the taxonomy's V-neck value, then pointing the product's
`shopify.neckline` metafield at that entry.

That indirection drives the whole design. You cannot invent a value; you can
only select one the taxonomy allows, and then only write it once an entry for it
exists in this store.

---

## Critical constraints

Never violate these.

- **Never use `productSet`.** It deletes list fields absent from its input, and
  metafields are a list field. One call wipes every namespace this skill is
  meant to leave alone.
- **Use `productUpdate` only for the `category` field.** Never let it carry
  `tags`; `ProductInput.tags` replaces the entire tag list.
- **Never write a value that is not in `taxonomy/index.json.gz`.** The plan
  rejects them; do not work around the rejection.
- **Never touch a metafield outside the `shopify` namespace.** Also never touch
  `shopify.disclosure` or `shopify.unavailable_reason` — they live in that
  namespace but are not category metafields.
- **Never call `standardMetafieldDefinitionEnable` without explicit approval.**
  It changes store-wide configuration, not one product.
- **Never run a mutation before `work/backup.json` is written and verified.**
- **Never touch a tag.** Not to read, not to write.

---

## Phase 0 — Preflight

1. `get-shop-info`. Confirm which store is connected and its product count.
2. State it back, with the scope, and stop:

   > You're connected to **Pancake Clothing** (pancakeclothing.com), which has
   > **12 products**.
   >
   > I'll work on your active and draft products and skip archived ones. I'll
   > set each product's category and fill in the product details that category
   > expects — colour, size, fabric and so on. I won't touch your tags, and I
   > won't touch product data other apps have added.
   >
   > Is this the right store?

3. Wait. Use `switch-shop` if it is wrong.

Read nothing else yet. Write nothing.

---

## Phase 1 — Read the catalog and the store

Two reads, both paginated to exhaustion.

**The catalog.** Fetch every product with `id`, `title`, `descriptionHtml`,
`productType`, `vendor`, `status`, `options { name values }`,
`category { id fullName isLeaf }`, and `metafields(first: 50)`. Fetch **all**
namespaces, not just `shopify` — the others must be seen so they can be reported
as untouched. Save each page, then:

```
python3 scripts/normalize_catalog.py work/raw_products.json --stats
```

**The images.** Some attributes are only ever stated by the picture — `pattern`
above all. Fetch them now so they can be looked at in Phase 2:

```
python3 scripts/fetch_images.py
```

**The store.** The store, not the taxonomy file, decides what is writable today.

```
python3 scripts/build_store_map.py --print-queries    # prints the three queries
python3 scripts/build_store_map.py work/raw_store.json --stats
```

This yields, per metafield key, the metaobject definition it validates against
and every existing entry indexed by taxonomy value. A value with no entry cannot
be written until one is created.

Report what you found in plain English: how many products have a category, how
many do not, and which product details are already filled in.

---

## Phase 2 — Choose categories and values

### Generate the prompts first

```
python3 scripts/build_prompts.py --from-products work/products.json \
    --store-map work/store_map.json
```

One file per category under `prompts/`, listing that category's attributes,
every allowed value, and whether each value is `[writable]`, `[new]`, or
`[blocked]`. **Work from that file.** Do not recall value lists from memory —
the names are exact and unobvious (`Double extra large (XXL)`, not `XXL`).

### Choosing the category

Pick the most specific **leaf** category the evidence supports. A product that is
clearly a t-shirt but might be adult or children's goes to the parent-level
t-shirt category, not a guessed child.

**If the product already has a category and it is correct, keep it.** Only
propose a change when the current one is wrong, and say why.

### Choosing values

Read, in this order of trust:

1. **Options** — names and values. The most reliable signal.
2. **Product type** and **title**.
3. **Description** — real statements only. "Soft cotton tee" gives you the
   fabric; "feels amazing" gives you nothing.
4. **The product image**, at `work/images/<product id>.png`. **Open it and look
   at it** — do not infer from the filename or the alt text. A photo is evidence
   for what it shows: whether a garment is plain, striped or floral, and
   sometimes its colour. It is never evidence for fabric, care instructions or
   stretch level. Record what you saw: `product image shows a plain unpatterned
   garment`.

**`pattern` in particular usually has no textual source.** Descriptions almost
never say "solid". If you are proposing a colour the store does not stock yet,
you need a pattern too (see below), and the image is normally the only honest
place to get it. If the image does not settle it, leave both out.

Rules:

- Only values from the category's own attribute lists.
- Record, for every value, the product field it came from. `option "Size" value
  "S"` is a source; `inferred` is not, and is rejected.
- **When the product does not say, leave it empty.** An empty attribute is a
  correct answer. A guessed one is a defect that reaches Google.
- Never translate a value. Never reword one.

Write `work/proposals.json`, then:

```
python3 scripts/build_plan.py
```

### Walk the merchant through `work/plan.md`

It has a section per product, plus three sections that each need their own
decision:

- **New metaobject entries to create** — taxonomy values this store has never
  used. Creating them is normal, but it is a separate approval.
- **Metafield definitions to enable** — category metafields not turned on in
  this store. Store-wide change. Never automatic. Approve individually or drop
  the attribute.
- **Could not resolve** — attributes whose metafield key cannot be determined.
  Never guessed, never written.

Also read out the **label mismatch** warnings. If this store calls a size
`0-3 maanden` and the taxonomy calls it `0-3 months`, the existing entry is
reused as-is. Nothing is renamed or translated.

### Tell the merchant these two things before they approve

Both were observed on a live store. Say them plainly; neither is a reason not
to proceed, but a merchant who hears them afterwards will feel misled.

> **Two things to know before I start.**
>
> First, setting a product's category can make your other connected apps update
> their own data. On this store the Facebook & Instagram channel added its own
> "Google product category" field to the products I categorised. That is that
> app doing its job, but it is outside what I manage — if you later undo my
> changes, those fields stay.
>
> Second, my undo is not quite perfect. I can put every value back exactly as it
> was, and I can put the category back to exactly what it was, including back to
> having none. But if I add a product detail that did not exist at all before,
> undoing empties it rather than removing it — Shopify does not let me delete
> those fields through this connection. An emptied field holds nothing and
> behaves as unset; it just still appears in your product's field list.

**Require an explicit yes.** Iterate on the proposals and re-run
`build_plan.py`; never hand-edit the plan.

### Category changes need their own yes

`plan.md` opens with a **Category changes** section listing every product whose
category this run would change, old path and new path side by side. A changed
category is the single most visible thing this skill does — it moves the product
in Shopify's own taxonomy and in every channel that reads it. Walk that section
separately and get a separate yes for it, even when the merchant has already
approved the rest of the plan.

---

## Phase 3 — Back up, then apply

### Back up — always

Re-read every product in the plan, fresh. Then:

```
python3 scripts/backup.py --products work/fresh_products.json \
    --store-map work/store_map.json --plan work/plan.json
```

It captures categories, `shopify.*` metafields, which metaobjects and
definitions already existed, and refuses to write if the read misses any product
the plan touches. **If it refuses, stop.** Fix the read.

### Apply in stages

```
python3 scripts/apply.py
```

Stages run in order, each its own approval:

| Stage | Mutation | Notes |
|---|---|---|
| 0 definitions | `standardMetafieldDefinitionEnable` | only with `--enable-definitions` and explicit approval |
| 1 metaobjects | `metaobjectCreate` | creates the values the store lacks |
| 2 categories | `productUpdate` (category only) | |
| 3 metafields | `metafieldsSet` | |

For each batch: pass its `mutation` and `variables` to `graphql_mutation`, check
`userErrors` for **every alias**, then record it:

```
python3 scripts/apply.py --mark-applied 3
python3 scripts/apply.py --mark-failed 3 --note "throttled"
```

**After stage 1, record what you created** — this is what makes rollback safe:

```
python3 scripts/apply.py --record-created work/created.json
```

Then re-read the store, re-run `build_store_map.py` and `build_plan.py`, and run
`apply.py` again to pick up the metafields that were held back waiting for their
entries.

### On errors

- **Throttled** — stop, wait, retry the same batch with backoff (2s, 4s, 8s,
  16s). Do not move on.
- **Some aliases failed** — record which products, keep going, report in Phase 4.
- **Merchant interrupts** — the checkpoint means you resume, not restart.

---

## Phase 4 — Verify, report, and offer the undo

1. Re-read every affected product's category and `shopify.*` metafields.
2. Diff against the plan. Report what landed, what failed, and on which products.
3. Confirm tags are unchanged — read them once, before and after, and say so.

Then:

> Everything is saved in `work/backup.json`. If you want any of this undone, run
> `python3 scripts/rollback.py` and I'll put your categories and product details
> back exactly as they were.

### Rollback

```
python3 scripts/rollback.py --current-products work/now_products.json \
    --current-store-map work/now_store.json
```

It restores metafields, restores categories including back to none, deletes
the metaobjects this run created, and — only then — considers definitions.

**A metafield that did not exist before the run is emptied, not removed.**
`metafieldsDelete` is refused on the `shopify` namespace for this connector
("Access to this namespace and key on Metafields for this resource type is not
allowed"), so rollback writes `[]` instead. The field holds no values and
resolves to no references, but the row remains. Say so when you report the
rollback; do not claim the store is byte-identical when it is not.

**A metaobject definition is deleted only when all three hold:**

1. this run created it,
2. every entry it now holds was created by this run,
3. no product references it.

Deleting a metaobject definition cascades to its entries and its metafield
definition, which is the only undo available — `metafieldDefinitionDelete` is
denied to this connector. That cascade is why the guard exists. Anything failing
a check is left in place and reported. A leftover empty definition is untidy;
deleting one holding merchant data is unrecoverable.

Pass the current reads. Without them check 3 cannot pass and nothing is deleted.

Close with what this improves, in their terms:

- **Storefront filters work.** Filters read category metafields, not tags.
- **Google and Meta stop rejecting listings.** Both map product attributes from
  the standard taxonomy.
- **Shopify search and recommendations get better**, because products are
  described in the vocabulary Shopify itself indexes.

---

## Known pitfalls

Each was found against a live store.

### `productSet` destroys metafields

Shopify's docs: *"For list fields: Creates new entries, updates existing
entries, and deletes existing entries that aren't included in the mutation's
input. Common examples of list fields include collections, metafields, and
variants."* One call removes every metafield you did not name — including other
apps' namespaces. Use `metafieldsSet`.

### Values are metaobjects, not text

`shopify.neckline` is `list.metaobject_reference`. Its value is a JSON array of
metaobject GIDs. There is no way to write the string "Crew".

### Entries do not pre-exist

A store can have 1 neckline entry where the taxonomy has 18. Enabling a standard
definition provisions the metaobject definition but creates **zero** entries.
Anything not already there must be created.

### Match on taxonomy value, never on label

Store labels are merchant-authored and often localised. Pancake's sizes are
Dutch (`0-3 maanden`). The `taxonomy_reference` field still resolves correctly;
the label does not. Never match on the label, and never rename one.

### The reference field is not always called `taxonomy_reference`

`shopify--color-pattern` has `color_taxonomy_reference` (a list) and
`pattern_taxonomy_reference`. Read the metaobject definition's fields and match
on **type**, not name.

### Attribute handle is not always the metafield key

Taxonomy `color` and `pattern` both write to `shopify.color-pattern`. See
`taxonomy/key_exceptions.json`. The store's own definitions are authoritative.

---

## Files

| File | Purpose |
|---|---|
| `taxonomy/index.json.gz` | Pinned taxonomy index (v2026-08), 1.6 MB gzipped. Generated. |
| `taxonomy/key_map.json` | Attribute → metafield key. Generated. |
| `taxonomy/key_exceptions.json` | The few cases where key ≠ handle. Hand-maintained. |
| `config.json` | Run configuration, including `no_match_behavior`. |
| `templates/category_prompt.md` | The per-category prompt template. |
| `prompts/<category>.md` | Generated per-category prompts. |
| `work/products.json` | Normalized catalog. |
| `work/store_map.json` | What this store can write today. |
| `work/proposals.json` | Your decisions. You write this. |
| `work/plan.{json,csv,md}` | The reviewable plan. |
| `work/backup.json` | The safety net. |
| `work/batches/`, `work/rollback/` | Ready-to-run mutations. |

| Script | Does |
|---|---|
| `build_taxonomy_index.py` | Rebuilds the index from a pinned release. |
| `build_key_map.py` | Regenerates the key map. |
| `normalize_catalog.py` | Reshapes the fetched catalog. |
| `build_store_map.py` | Reads definitions and entries; `--print-queries`. |
| `build_prompts.py` | Renders per-category prompts. |
| `build_plan.py` | Validates proposals; writes the plan. |
| `backup.py` | Writes and verifies the backup. |
| `apply.py` | Compiles staged batches; tracks the checkpoint. |
| `rollback.py` | Compiles the restore, with the deletion guard. |

Every script takes `--help`. Standard library only.
