# Fill category metafields — {{CATEGORY_NAME}}

Category: **{{CATEGORY_FULL_NAME}}**
Category id: `{{CATEGORY_ID}}`
Taxonomy: Shopify Standard Product Taxonomy `{{TAXONOMY_VERSION}}`

You are filling category metafields for products in this category. Read the
product's own fields and choose values. You are not writing anything — your
output is a proposal that a validator checks before anything reaches the store.

## The one rule

**Choose only from the allowed values listed below. Never invent a value, never
paraphrase one, never translate one.** A value you write that is not on the list
is rejected by `build_plan.py` and never reaches the store.

Copy the value's **name exactly as written**, including capitalisation and
punctuation. `V-neck` is not `V neck`. `Double extra large (XXL)` is not `XXL`.

## What to read

Use only these, in this order of trust:

1. **Product options** — option names and values. The most reliable signal.
2. **Product type** and **title**.
3. **Description** — real statements only. "Soft cotton tee" tells you the
   fabric; "feels amazing" tells you nothing.
4. **The product image**, downloaded to `work/images/<product id>.png` by
   `scripts/fetch_images.py`. **Open the file and look at it.** An image is
   legitimate evidence for what it actually shows: a plainly single-coloured
   garment supports `Solid` for pattern; a visible stripe supports `Striped`.
   It is not evidence for anything the image cannot show, such as fabric, care
   instructions or stretch level. Never treat a filename or alt text as having
   seen the picture.

If the product does not say, do not guess. Leaving an attribute empty is a
correct answer, and far better than a wrong value.

## Colour needs a pattern

`shopify.color-pattern` is one metafield fed by TWO taxonomy attributes,
`color` and `pattern`, and Shopify requires **both** when a new colour entry has
to be created. Proposing `color` alone for a value this store does not already
have will block that value: the plan will not invent a pattern for you.

So when you propose a `color` the store lacks, propose a `pattern` for the same
product too, with its own evidence. `Solid` is the common answer for plain
garments — but only say so when the description, the option values or an image
actually shows a plain garment. If nothing supports a pattern, leave both out
and let the value stay blocked; a blocked value is reported, a fabricated one is
a defect.

## Recording your reasoning

For every value you choose, record which product field it came from. The plan
shows this to the merchant, so it must be specific:

- good: `option "Size" values`, `description: "organic cotton"`, `title`
- useless: `inferred`, `obvious`, `from the product`

## Attributes for this category

{{ATTRIBUTES}}

## Output

Append to `work/proposals.json`, keyed by product id:

```json
{
  "{{EXAMPLE_GID}}": {
    "category": "{{CATEGORY_ID}}",
    "category_reason": "product_type 'tshirts' and title say t-shirt",
    "attributes": {
      "neckline": [{"value": "Crew", "source": "description: \"crew neck\""}]
    }
  }
}
```

Every attribute value is a list, even when there is only one — the metafields
are list-typed. Omit an attribute entirely rather than writing an empty list.
