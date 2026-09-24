# Video shoot — runbook

Three products on the Pancake dev store. Everything here was measured, not
estimated.

## Products

| Product | Why it is in the shot |
|---|---|
| **Pancake Family Ducks** | The category change. Three size options, three people in the photo, currently filed as a children's t-shirt. |
| **PROBE D Size numeric UK** | The clean path. Seven new metaobject entries created from nothing. |
| **PROBE C Color and Size** | Optional third. The validator rejecting an invented value, and a colour that needs a pattern. |

## Before the camera rolls

Everything below is safe to do in advance and saves dead air. None of it writes
to the store.

```
cd shopify-category-metafields

# 1. Images. 45 MB across 12 products; pre-fetching removes a download AND lets
#    you confirm the photos are the ones you expect.
python3 scripts/fetch_images.py

# 2. Confirm the committed artifacts are current, so CI-style surprises do not
#    happen mid-take.
python3 scripts/build_key_map.py --check

# 3. Capture the baseline you will diff against afterwards.
#    (Already captured: work/snap_pancake_baseline.json)
```

**Do not run `scripts/build_taxonomy_index.py` on camera.** It downloads a 4 MB
release asset and expands 91 MB. The index is committed; there is nothing to
rebuild.

## What is actually slow

| Step | Measured | Notes |
|---|---|---|
| Load the taxonomy index | 0.10 s | 14,606 categories, gzipped |
| `build_prompts.py` | 0.14 s | |
| `build_plan.py` | 0.13 s | |
| `fetch_images.py`, cold | 1.2 s for 3 | 0.08 s once cached |
| Catalog read via MCP | a few seconds | one page for 12 products |
| Store map via MCP | a few seconds | definitions + one aliased entries query |
| **Looking at a product photo** | **the slowest step** | 3–4 MB PNG each; this is a vision call per image |
| **Writing the proposals** | **the other slow step** | the model reasoning over each product |

The Python is not the bottleneck — it is under a fifth of a second everywhere.
The two things that will visibly pause are the model looking at photos and the
model writing `work/proposals.json`. Both are the interesting part, so they are
worth showing rather than hiding; just know they are not bugs.

If you want them shorter: pre-fetch the images (above) and keep the shot to two
products instead of three.

## After the shoot — put the store back

Run in this order. The first two commands write nothing; they compile the
mutations for review.

```
# 1. Re-read the store as it now stands
#    (run the catalog and store-map queries, save to work/raw_products.json
#     and work/raw_store.json, then:)
python3 scripts/normalize_catalog.py work/raw_products.json --out work/now_products.json
python3 scripts/build_store_map.py  work/raw_store.json    --out work/now_store.json

# 2. Compile the rollback
python3 scripts/rollback.py \
    --current-products work/now_products.json \
    --current-store-map work/now_store.json

# 3. Execute each work/rollback/rollback_*.json in order through
#    graphql_mutation, checking userErrors on every alias.

# 4. Re-read once more, then prove the store is back
python3 scripts/snapshot.py capture \
    work/raw_products.json work/raw_store.json work/raw_tags.json \
    --out work/snap_after.json

python3 scripts/snapshot.py diff \
    work/snap_pancake_baseline.json work/snap_after.json
```

`diff` exits 0 and prints `IDENTICAL` when categories, `shopify.*` metafields,
metaobject counts, definitions, tags and every other namespace match the
baseline. It exits 1 and lists every difference otherwise.

**Two differences are expected and are not failures**, both documented in
`docs/design.md`:

- any `shopify.*` metafield the run created is left present with value `[]`,
  because `metafieldsDelete` is refused on that namespace for this connector;
- `mc-facebook.google_product_category` may appear on the products whose
  category was set, written by the Meta channel app, not by this skill.

The baseline in `work/snap_pancake_baseline.json` already contains the residue
from the earlier verification run, so a clean shoot-and-rollback should diff
against it with only the new run's residue showing.
