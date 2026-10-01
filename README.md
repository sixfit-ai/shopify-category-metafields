# Shopify Product Categories & Product Details

**What this does:** it goes through your Shopify products, gives each one the
correct **product category** from Shopify's own official category
list, and then fills in the **product details** that category expects: colour,
size, fabric, neckline, sleeve length, care instructions, age group, and so on.

You do this by talking to Claude in ordinary English. You do not write code. You
do not need to understand Shopify's API. You will be shown everything before it
is written, you approve it, and you can undo it afterwards.

---

## Contents

- [What problem this solves](#what-problem-this-solves)
- [What a finished product looks like](#what-a-finished-product-looks-like)
- [What you need before you start](#what-you-need-before-you-start)
- [Setup, step by step](#setup-step-by-step)
- [Your first run](#your-first-run)
- [What happens during a run](#what-happens-during-a-run)
- [The three things you approve](#the-three-things-you-approve)
- [Two things to know before you approve](#two-things-to-know-before-you-approve)
- [Undoing a run](#undoing-a-run)
- [What it will never do](#what-it-will-never-do)
- [Settings you might want to change](#settings-you-might-want-to-change)
- [If something goes wrong](#if-something-goes-wrong)
- [Frequently asked](#frequently-asked)
- [Word list](#word-list)
- [How it actually works](#how-it-actually-works)
- [For developers](#for-developers)

---

## What problem this solves

Shopify has one official list of what products are, called the Standard Product
Taxonomy. When a product sits in the right place on that list, the category
brings a set of defined attributes with it: a t-shirt has a neckline and a
sleeve length, a dog bed does not. Filling those attribute values in is what
makes the following actually work:

| What you see | What is reading your data behind it |
|---|---|
| Storefront filters ("Filter by size / colour / material") | the category product details |
| Google Merchant Center / Google Shopping attributes | the standard category and its attributes |
| Meta (Facebook & Instagram) catalog fields | the same standard category list |
| Shopify search, related products, recommendations | the category and attributes Shopify indexes |
| Shopify Flow rules, Markets, most third-party apps | the same fields |

If the **Product category** field on your products is blank, none of the above
has anything to work with. That is the normal state for most stores, and for
every store that migrated in from another platform. A category detail is a
structured value that every sales channel understands, which is what makes it
usable outside your own theme.

Typical symptoms that lead people here:

- Filters on your storefront are empty, half-empty, or filter on the wrong things.
- Google Merchant Center says *missing attributes* or *incomplete product data*,
  or files your products under a category that makes no sense.
- Meta catalog items get limited reach or never get approved.
- Shopify's own search and "you may also like" feel random.
- You have thousands of products and no appetite for editing them one at a time.

---

## What a finished product looks like

Before:

```
Product        Classic Crew Tee
Category       (empty)
Details        (none)
```

After:

```
Product        Classic Crew Tee
Category       Apparel & Accessories > Clothing > Clothing Tops > T-Shirts

Details        Size                 Small (S), Medium (M), Large (L), Extra large (XL)
               Color                Navy
               Pattern              Solid
               Fabric               Cotton
               Neckline             Crew
               Sleeve length type   Short
               Target gender        Unisex
               Age group            Adults
               Care instructions    Machine washable
```

Three things worth noticing, because they describe how the whole tool behaves:

1. **The value names are Shopify's exact names, not yours.** It writes
   `Double extra large (XXL)`, not `XXL`. `Crew`, not `crew neck`. That exactness
   is what makes the data machine-readable for Google and Meta.
2. **Every value came from something your product already said**, whether that
   was an option name or value, the product type, a factual sentence in the
   description, or the product photo. You are told the source of every single
   value before anything is written.
3. **If your product does not say, the field is left empty on purpose** and
   reported to you. An empty field is a correct answer. A guessed one is a
   defect that ends up in Google.

---

## What you need before you start

**1. A Shopify store you have admin access to.**

**2. Claude, with the Shopify connector switched on and connected to that
store.** The connector is the official Shopify connection inside Claude. Nothing
in this project ever contacts Shopify by itself. Claude does all the reading and
writing through that connector, using your own Shopify permissions. There is no
API key to create, no app to install in Shopify, and nothing to paste anywhere.

**3. Python 3.8 or newer**, on the computer or environment where Claude is
running. Python does the boring, exact parts: reshaping data, validating every
proposed value, and writing out the plan. It needs nothing installed alongside
it: no pip, no libraries, no internet access of its own.

To check whether you already have it:

- **Mac:** open the **Terminal** app (press ⌘ + Space, type "Terminal", press
  Enter), type `python3 --version` and press Enter. If you see something like
  `Python 3.11.6`, you are done.
- **Windows:** open **PowerShell** from the Start menu, type `python --version`
  and press Enter. If it is missing or older than 3.8, install it from
  [python.org/downloads](https://www.python.org/downloads/) and tick
  "Add Python to PATH" during setup.

**4. Time.** For a first run on a few hundred products, set aside an hour. Most
of that is you reading the plan. The writing itself takes minutes.

**Strongly recommended for a first run:** point it at a Shopify **development
store**, or ask it to work on a handful of products only, before you let it near
your whole catalog.

---

## Setup, step by step

### Step 1. Download the skill file

If you have never used GitHub: this page you are reading is the project's home
page, and the file you need is attached to its latest release.

1. Look at the right-hand side of this page for the **Releases** heading, and
   click it. (Or go straight to the [Releases page](../../releases).)
2. Click the newest release at the top.
3. Under **Assets**, click **`shopify-category-metafields.skill`**. It downloads
   like any other file, usually into your Downloads folder.

That one file contains everything: the instructions Claude follows, Shopify's
category list, and the helper scripts. It is just a zip file with a different
name, so your browser or operating system may warn you about an unfamiliar file
type. That is expected.

### Step 2. Give the file to Claude

**If you use Claude in your browser or the desktop app:**

1. Open **Settings**.
2. Go to **Capabilities > Skills** (the exact wording moves around slightly
   between versions; look for "Skills").
3. Choose to upload a skill, and pick the `.skill` file you just downloaded.

It now appears in your list of skills. You do not have to switch it on manually
in a conversation. Claude reaches for it on its own when you describe this kind
of work.

**If you use Claude Code (the terminal version):**

Put the bundle into your skills folder. In Terminal:

```
unzip ~/Downloads/shopify-category-metafields.skill -d ~/.claude/skills/
```

That creates `~/.claude/skills/shopify-category-metafields/`. Restart Claude
Code and the skill is available.

### Step 3. Connect your Shopify store

In Claude's connector settings, enable the **Shopify** connector and connect it
to your store. Claude will ask you to log in to Shopify and approve access on
the normal Shopify permission screen.

If you manage more than one store, do not worry about picking the right one
here. The skill's very first action is to tell you which store it is connected
to and wait for you to confirm, and it can switch stores on your word.

### Step 4. Make sure Python is there

Covered above. If `python3 --version` prints a version number, you are ready.

---

## Your first run

Open a conversation with Claude and say what you want in your own words. Any of
these work:

> Categorise my products and fill in their details.

> My products are missing attributes and Google keeps rejecting them.

> The filters on my storefront don't work. Can you fix the product data behind
> them?

> Set the product category and fill in colour, size and fabric for my apparel.

For a careful first run, say so explicitly:

> Start with just the 10 products in my "Tees" collection so I can see what you
> do before we run the whole catalog.

You do not need to name the skill, mention metafields, or use any special
syntax.

---

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
  [How it actually works](#how-it-actually-works).

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

---

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

---

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

---

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

---

## What it will never do

- **Touch another app's data.** Anything outside Shopify's own standard
  fields, such as your Meta channel's fields, your reviews app or your own
  custom fields, is reported to you as skipped and left exactly alone.
- **Invent a value.** Every value comes from Shopify's own list, at one pinned
  version. A value that is not on that category's allowed list is rejected
  outright, not rounded to the nearest thing.
- **Guess.** An attribute your product does not evidence is left empty and
  reported. (You can configure a fallback instead, see below.)
- **Change store-wide settings on its own**, or as a side effect of anything else.
- **Write anything before a verified backup exists.**
- **Rename, translate, or reword your existing values.**
- **Use the one Shopify operation that could wipe your other apps' data.** There
  is a Shopify write operation that silently deletes any product fields missing
  from its input. This tool never uses it. See
  [For developers](#safety-rules-built-into-the-code) for the specifics.

---

## Settings you might want to change

The behaviour lives in a file called `config.json` inside the skill folder. You
do not have to edit it by hand. You can just tell Claude what you want ("don't
guess target gender, leave it blank", "don't change any category that is already
set") and it will configure the run accordingly. For reference, in plain terms:

| Setting | Default | What it means |
|---|---|---|
| `no_match_behavior` | `leave_empty` | When nothing in the product evidences an attribute: write nothing and report it. Change to `use_default` to write a fallback value instead, and only ever a value that is genuinely allowed for that attribute. |
| `defaults_by_attribute` | empty | Your fallback values, used only when the setting above is `use_default`. For example, `target-gender: Unisex`. |
| `status_scope` | `ACTIVE`, `DRAFT` | Which products count. Archived products are excluded. |
| `keep_existing_category` | `true` | A product that already has a category keeps it, unless the plan explicitly overrides it with a stated reason. |
| `overwrite_existing_metafields` | `false` | A detail that already has a value is left alone and reported as "already set". Set to `true` to allow replacing existing values. |
| `batch_size` | `25` | How many products are written per request. |
| `create_missing_metaobjects` | `true` | Whether the plan may propose creating values your store does not hold yet. Always a separate approval regardless of this setting. |
| `enable_missing_definitions` | `false` | Records that you approved switching on store-wide detail fields. Never a shortcut around being asked. |
| `metaobject_label_language` | `taxonomy_english` | New values this tool creates are labelled with Shopify's English name. Your existing values are never renamed or translated. |

---

## If something goes wrong

**Claude does not seem to use the skill.** Say what you want more concretely,
such as "set the Shopify product category on my products and fill in the category
details", or name it outright: "use the shopify-category-metafields skill".
Check that the skill shows up in your skills list and that the Shopify connector
is connected.

**"python3: command not found" or similar.** Python is not installed, or not on
the system path. Install it from
[python.org/downloads](https://www.python.org/downloads/). On Windows, tick
"Add Python to PATH" during setup, then start a new terminal window.

**It is connected to the wrong store.** Tell it so in phase 0, before anything
is read. It can switch stores. If you only notice later, stop it and ask it to
switch; nothing is written before your approval anyway.

**The run stopped halfway through writing.** Ask Claude to continue. Progress is
checkpointed batch by batch, so it resumes from where it stopped rather than
redoing or double-writing anything.

**Shopify throttled it / some batches failed.** Failures are reported per batch
and per product. Ask it to retry the failed ones. A failed batch changed nothing.

**A detail field you expected is missing from the plan.** Most likely either
that field is not switched on in your store (it will be listed in the
"fields to switch on" section awaiting your approval), or the attribute does not
belong to the category that product was assigned, or nothing in the product
evidenced a value. All three cases are reported in the plan. Ask Claude which
one applies.

**Google or Meta still complains after a successful run.** Those channels
re-sync on their own schedule, usually within a day or two. Also check that the
specific attributes each channel requires were actually fillable for your
products; the plan's "left empty" entries tell you what your product data does
not yet state.

**You changed your mind about the whole thing.** See
[Undoing a run](#undoing-a-run). The backup is kept as a file, so this works
later in the conversation too, not only immediately afterwards.

---

## Frequently asked

**Will my customers see a difference?** Your product titles, descriptions,
prices and images are untouched. What changes is the structured data
behind filters, channels and search. If your theme shows a specification table
built from product details, that table will start filling in, which is usually
the point.

**Can I run it on only part of my catalog?** Yes. Ask for one collection, one
product type, one vendor, or a named list of products, and only those are read
and changed.

**What if a product already has the right category?** It keeps it. By default
existing categories are left alone, and a change is only ever proposed where the
current one is wrong, with a reason you can read.

**What about stores not in English?** It works. Matching goes through
Shopify's internal value identifiers, never through the visible label, so a
Dutch, Turkish or German store's existing values are recognised and reused as
they are. Values this tool newly creates get Shopify's English name as a label;
your existing ones are never renamed.

**Can I run it again later for new products?** Yes. Products whose details are
already set are reported as "already set" and skipped, so a repeat run naturally
picks up only what is new.

**Does it work for stores that are not clothing?** Yes. The category list covers
14,606 categories across every vertical Shopify defines: furniture, food,
electronics, pet supplies and the rest. Apparel happens to have the most
attributes, which is why it makes the clearest examples.

**Does it cost anything?** The tool is free and MIT-licensed. You pay only for
your normal Claude usage.

**Is my store data sent anywhere else?** No. Your catalog is read by Claude
through the Shopify connector, and the helper scripts used during a run do their
work locally. The only thing any of them downloads is your own product photos,
from Shopify's own image servers.

---

## Word list

Terms you will meet while reading the plan, in plain language.

**Product category**: your product's position on Shopify's one official list of
what things are, e.g. *Apparel & Accessories > Clothing > Clothing Tops >
T-Shirts*. One per product.

**Standard Product Taxonomy**: the name of that official list. Shopify publishes
it, updates it a few times a year, and every sales channel reads it.

**Category metafield / product detail**: the attribute fields a category brings
with it: size, colour, fabric, neckline. "Metafield" is Shopify's word for them;
this README mostly says "product detail".

**Attribute**: one of those fields, e.g. *Neckline*. **Value**: one allowed
answer for it, e.g. *Crew*.

**Metaobject / value entry**: the record inside *your* store that represents one
allowed value. This is why a value sometimes has to be "created" before it can
be used: Shopify's list has the value, your store does not hold it yet.

**Metafield definition**: the switch that makes a detail field exist in your
store at all. Turning one on is a store-wide setting.

**Connector (MCP)**: the official Shopify connection inside Claude, through
which all reading and writing happens, using your own Shopify permissions.

---

## How it actually works

This section explains why you are asked for three separate approvals instead of
one. You do not need it to use the tool.

A category detail's value is not text. It is a reference to a record in *your*
store, which in turn references an entry in Shopify's taxonomy:

```
Shopify's taxonomy   gid://shopify/TaxonomyValue/6711         "Crew"
       |             matched on the entry's taxonomy reference
your store's entry   gid://shopify/Metaobject/508541436231     shopify--neckline/crew
       |             that entry's id is what gets written to the product
your product         shopify.neckline = [gid://shopify/Metaobject/508541436231]
```

That indirection has three consequences, and they shape the whole run:

- **Values are specific to your store.** Those ids are different in every
  Shopify store, so they are looked up live during the run and never assumed.
- **Values do not pre-exist.** Your store may hold one neckline where Shopify's
  list has eighteen. The missing ones must be created first, which is why that
  is its own approval step.
- **Labels can be anything; identifiers cannot.** Matching always goes through
  the taxonomy identifier, which is why a store in any language works and why
  nothing of yours gets renamed.

---

## For developers

### Division of labour

No script in this repository ever contacts Shopify. Claude performs every read
and every write through the Shopify MCP connector; the scripts reshape what came
back, validate proposals, and **compile** ready-to-run GraphQL operations that
Claude then executes. `apply.py` and `rollback.py` write batch files and execute
nothing. That split is what makes every write reviewable before it happens.

### Run shape

```
normalize_catalog.py   reshape the fetched catalog pages into work/products.json
fetch_images.py        download the first product photo, so `pattern` has real evidence
build_store_map.py     what this store can write today (--print-queries prints the reads)
build_prompts.py       one prompt per category, with every allowed value marked
                       [writable] / [new] / [blocked]
  -> categories and values are chosen -> work/proposals.json
build_plan.py          validate every proposal; write plan.json / plan.csv / plan.md
backup.py              fresh read, coverage-verified; refuses to under-cover the plan
apply.py               compile staged batches:
                       definitions -> metaobjects -> categories -> metafields
rollback.py            compile the exact reverse, behind a deletion guard
snapshot.py            capture / diff, to prove a rollback restored the store
```

Every script is standard library only and takes `--help`.

Stage 0 of `apply.py` (`standardMetafieldDefinitionEnable`) is compiled only
when `--enable-definitions` is passed, which is the recorded form of explicit
merchant approval.

### Safety rules built into the code

- **`productSet` is never used.** It deletes list fields absent from its input,
  and metafields are a list field, so one call would wipe every other app's
  namespace.
- **`productUpdate` is used only for the `category` field.**
- Metafields outside the `shopify` namespace are never touched. Neither are
  `shopify.disclosure` or `shopify.unavailable_reason`. They live in that
  namespace but are not category metafields.
- `standardMetafieldDefinitionEnable` is store-wide and never runs without
  per-definition approval.
- No mutation is compiled before `work/backup.json` exists and verifies.
- Validation is in `build_plan.py`, not in the model's head. Rejection reasons:
  `unknown_category`, `category_not_leaf`, `attribute_not_in_category`,
  `unknown_value`, `duplicate_value`, `already_set`, `missing_source`,
  `unresolved_attribute`. Only leaf categories may be assigned, and a value with
  no recorded source is rejected.

### The taxonomy index

The upstream taxonomy release is 91 MB expanded and is never committed. A
generator pins one release and reduces it to what the skill needs:

```
python3 scripts/build_taxonomy_index.py --version 2026-08
```

The result, `taxonomy/index.json.gz`, is **1.5 MB** and holds 14,606 categories
(11,942 of them leaves), 8,500 attributes and 81,518 attribute values. Its
header records the source URL, the version, and the SHA-256 of the upstream
asset.

`taxonomy/key_map.json` maps taxonomy attribute handles to metafield keys;
`taxonomy/key_exceptions.json` holds the few hand-verified cases where the key
is not the handle. Both are regenerated by `build_key_map.py` and are
release-specific, so re-verify them when re-pinning.

### Known limits

Found by running this against a live store, not by reasoning about it. All three
are properties of the environment; the skill reports each rather than hiding it.

**Rollback empties, it cannot delete.** `metafieldsDelete` is refused on the
`shopify` namespace for the Shopify MCP connector:

> Access to this namespace and key on Metafields for this resource type is not
> allowed.

So a metafield that did not exist before a run is left present holding an empty
list (`[]`) rather than removed. Values are restored exactly; categories are
restored exactly, including back to none. An emptied metafield resolves to no
references and is treated as unset by later runs. A custom app with delete scope
would close this gap. See `docs/design.md`.

**Deleting definitions only works through the metaobject definition.**
`metafieldDefinitionDelete` is denied to this connector, while
`metaobjectDefinitionDelete` is permitted and cascades to its entries and its
metafield definition. That cascade is the only undo available, and is why
rollback deletes a definition only when this run created it, every entry it
holds was created by this run, and no product references it. The third check requires
a current read (`--current-products`, `--current-store-map`). Anything failing a
check is left in place and reported.

**Setting a category makes other apps write.** On the test store, categorising
products caused the Meta channel app to add its own
`mc-facebook.google_product_category` to eight of them. That is the app doing
its job, it is outside this skill's namespace, and it is not reverted by
rollback. The merchant is told this before approving.

**Some values need a companion.** `shopify--color-pattern` is one metafield fed
by two taxonomy attributes and requires both a base colour and a base pattern;
Shopify rejects a colour entry without one ("Base pattern can't be blank"). When
a new colour is needed, the plan also needs a pattern with its own evidence,
usually the product photo. Without it the value is reported as blocked rather
than invented.

---

## Licence

MIT.
