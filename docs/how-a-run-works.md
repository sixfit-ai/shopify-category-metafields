# How a run works

## What happens during a run

There are four phases. Nothing is written to your store until phase 3, and
phase 3 does not begin until you have said yes.

### Phase 0. It confirms the store

Before reading a single product, it tells you where it is and what it intends:

> You're connected to **Northwind Apparel** (northwind-apparel.example), which
> has **248 products**. I'll work on your active and draft products and skip
> archived ones. I'll set each product's category and fill in the product
> details that category expects, such as colour, size and fabric. I won't touch
> product data other apps have added.
>
> Is this the right store?

Wrong store? Say so, and it switches. Nothing has been read or written yet.

### Phase 1. It reads your catalog and your store

Three reads, all of them harmless:

- **Your products**: title, description, product type, vendor, options, current
  category, and the product details that already exist (including other apps',
  so they can be reported to you as untouched).
- **Your product photos**: the first photo of each product is downloaded,
  because some attributes are only ever stated by the picture. `Pattern` is the
  clearest case: descriptions almost never say "solid", but a photo shows plainly whether
  a garment is plain, striped or floral. Claude then actually looks at the photo.
- **Your store's own settings**: which detail fields are switched on, and which
  values your store already holds. This matters more than you would expect, and
  it is why you get asked the questions you get asked in phase 2. See
  [Under the hood](concepts.md#under-the-hood).

Still nothing written.

### Phase 2. It proposes, you approve

It works through your products category by category, choosing values only from
the list Shopify allows for that category, and recording where each value came
from. Then it writes you a plan.

The plan opens with a one-line summary, something like *"3 products; 2
categories set, 1 changed, 0 kept. 34 detail values across 8 fields. 0 new
values needed, 0 fields would have to be switched on. 0 proposals rejected."*
Then it has a section per product looking roughly like this:

| Detail field | Value | Where it came from | Status |
|---|---|---|---|
| Size | Small (S) | option "Size" value "S" | ready |
| Size | Double extra large (XXL) | option "Size" value "2XL" | ready |
| Color | Navy | description: "navy cotton tee" | ready |
| Pattern | Solid | product image shows a plain unpatterned garment | ready |
| Neckline | Crew | description: "crew neck" | ready |
| Care instructions | (blank) | nothing in the product states it | left empty |

Read it. Argue with it. If a category is wrong, a value is wrong, or you would
rather an attribute stayed blank, say so and it rebuilds the plan. Nothing is
hand-edited behind your back. Your corrections go back through the same
validation as everything else.

The plan is also produced as a spreadsheet file (one row per value), so if you
would rather review it in Excel or Google Sheets, or circulate it to someone
else before approving, ask Claude for it.

### Phase 3. It backs up, then writes

Once you approve, it re-reads every affected product fresh, rather than reusing
the copy from phase 1 which could already be minutes stale, and writes a backup.
The backup is then checked to confirm it actually covers every product in the
plan. **If that check fails, nothing is written at all.**

Then the changes go out in this order, because each step depends on the one
before it:

```
1. switch on the detail fields you approved   (store-wide setting)
2. create the new values you approved         (in your store's value lists)
3. set the product categories
4. write the product details
```

Changes go in batches of 25 products at a time, and progress is recorded as it
goes, so an interruption halfway through is something it can pick up from rather
than a mess you have to untangle.

### Phase 4. It verifies and reports

It re-reads every product it touched, compares the result against the plan, and
tells you what landed, what failed, and on which products, by product name
rather than by ID number.

Then it tells you how to undo everything, and what you just gained.

## The three things you approve

A single blanket "yes" is not enough. These three are asked separately because
they carry different kinds of risk.

**1. Category changes.** Every product whose category this run would *change*
is listed with its old path and its new path side by side. Changing a category
moves the product inside Shopify's own taxonomy and in every channel that reads
it, which makes it the most visible thing this tool does. Products that already
have a correct category keep it. Changes are proposed only where the current one
is wrong, always with a written reason. This section gets its own yes, separate
from the rest of the plan.

**2. New values to create in your store.** Shopify's list may have eighteen
necklines; your store holds only the ones you have actually used. If you have
never sold a V-neck, your store has no "V-neck" value, and one has to be created
before any product can point at it. This is routine and harmless, and it is
still listed and approved on its own.

**3. Detail fields to switch on.** Some category detail fields are simply not
enabled in your store yet. Enabling one is a **store-wide configuration change**,
not a change to one product, so this tool never does it on its own and never as
a side effect. You approve each one, or you drop that attribute and leave the
field switched off.

You are also shown any **language mismatches**. If your store calls a size
`0-3 maanden` and Shopify's list calls it `0-3 months`, your existing value is
matched correctly and reused exactly as it is. Nothing is ever renamed or
translated, in either direction.

## Two things to know before you approve

Both of these were discovered by running this against a real live store, not by
reasoning about it. Neither is a reason not to proceed. You are
told them up front, because finding them out afterwards feels like being misled.

**Your other apps may write their own data when a category is set.** On the test
store, setting categories caused the Facebook & Instagram channel to add its own
"Google product category" field to eight products. That is that app doing its
job, correctly. It is outside what this tool manages, and undoing this run does
not remove it.

**The undo is very good, but not perfect.** Every detail value can be put back
exactly as it was, and every category can be put back exactly as it was,
including back to being empty. But if the run adds a detail field that did not
exist on a product at all, undoing **empties** that field rather than removing
it, because Shopify does not permit deleting those fields through this
connection. An emptied field holds nothing and behaves exactly like an unset
one; it just still appears in that product's field list.

## Undoing a run

Ask Claude:

> Undo the run.

It prepares the exact reverse of what it did and, with your confirmation, runs
it. (Mechanically: a script compiles the reversing operations from the backup,
and Claude executes them through the Shopify connector, the same as in phase 3,
so you see what will happen before it does.)

The undo restores every product detail value exactly, restores every category
exactly including back to empty, and removes the values this run created in your
store. With two deliberate limits:

- **A detail field that did not exist before the run is emptied, not removed**,
  for the Shopify reason described just above.
- **Something is deleted only when it is provably safe to delete.** A value or
  field is removed only if this run created it, it holds nothing anyone else put
  there, and no product still points at it. If any of those three is not true, it
  is left in place and reported to you. A leftover empty field is untidy;
  deleting one that holds your data cannot be undone, so it leaves things behind
  rather than risk that.

The undo also needs a fresh read of your store to prove that third condition, so
expect it to read your products again before deleting anything.
