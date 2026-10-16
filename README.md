# Shopify Product Categories & Product Details

**What this does:** it goes through your Shopify products, gives each one the
correct **product category** from Shopify's own official category
list, and then fills in the **product details** that category expects: colour,
size, fabric, neckline, sleeve length, care instructions, age group, and so on.

You do this by talking to Claude in ordinary English. You do not write code. You
do not need to understand Shopify's API. You will be shown everything before it
is written, you approve it, and you can undo it afterwards.

---

## What problem this solves

Storefront filters, Google Shopping, Meta catalogs and Shopify search all read
a product's **category** and its **category details** (size, colour, fabric and
so on). On most stores those fields are empty, so every one of those channels
has nothing to work with. Filling them in by hand takes days. This does it in
one conversation.

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

## How it works

### 1. Install and verify

**Install**

1. Download `shopify-category-metafields.skill` from the
   [Releases page](../../releases).
2. Add it to Claude:
   - **Claude app or claude.ai:** Settings > Capabilities > Skills, then upload
     the file.
   - **Claude Code:** run
     `unzip ~/Downloads/shopify-category-metafields.skill -d ~/.claude/skills/`
     and restart Claude Code.
3. In Claude's connector settings, turn on the **Shopify** connector and log in
   to your store.

**Verify**

- The skill is listed under Settings > Capabilities > Skills. In Claude Code,
  the folder `~/.claude/skills/shopify-category-metafields/` exists.
- Ask Claude "Which Shopify store are you connected to?" It should answer with
  your store's name.
- Run `python3 --version` in Terminal (`python --version` on Windows). It
  should print 3.8 or higher.

More detail is in [Setup, step by step](#setup-step-by-step).

### 2. Run the prompt

Tell Claude what you want in ordinary English. It confirms your store, reads
your catalog and your store's settings, and fetches your product images itself.
You don't run anything. The photos are evidence: some details, `Pattern` above
all, appear only in the picture.

<img src="docs/media/2-run-the-prompt.gif" alt="Running the prompt" width="520">

### 3. Answer the questions

You see every proposed category and value, with where each one came from, and
approve them. Nothing is written to your store before this point.

<img src="docs/media/3-answer-the-questions.gif" alt="Answering the approval questions" width="520">

### 4. Metafields are written

The categories and product details are written, checked against the plan, and
show up in your Shopify admin.

<img src="docs/media/4-metafields-are-written.png" alt="A product's category metafields filled in, in the Shopify admin" width="520">

### 5. Get your score

Check how complete your product data is now at
[sixfit.ai/metafield-check](https://sixfit.ai/metafield-check).

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

## Undoing a run

Ask Claude:

> Undo the run.

It shows you the exact reverse of what it did and runs it once you confirm.
[How a run works](docs/how-a-run-works.md#undoing-a-run) covers what can and
cannot be put back.

---

## What it will never do

- **Touch another app's data.** Anything outside Shopify's own standard
  fields, such as your Meta channel's fields, your reviews app or your own
  custom fields, is reported to you as skipped and left exactly alone.
- **Invent a value.** Every value comes from Shopify's own list, at one pinned
  version. A value that is not on that category's allowed list is rejected
  outright, not rounded to the nearest thing.
- **Guess.** An attribute your product does not evidence is left empty and
  reported. (You can configure a fallback instead, see [Settings](docs/settings.md).)
- **Change store-wide settings on its own**, or as a side effect of anything else.
- **Write anything before a verified backup exists.**
- **Rename, translate, or reword your existing values.**
- **Use the one Shopify operation that could wipe your other apps' data.** There
  is a Shopify write operation that silently deletes any product fields missing
  from its input. This tool never uses it. See
  [For developers](docs/developers.md#safety-rules-built-into-the-code)
  for the specifics.

---

## More documentation

- [How a run works](docs/how-a-run-works.md): the four phases, the three
  approvals, and undoing a run.
- [Settings](docs/settings.md): what you can change in `config.json`.
- [Troubleshooting](docs/troubleshooting.md)
- [Frequently asked](docs/faq.md)
- [Concepts](docs/concepts.md): the terms used in the plan, and how a value is
  stored in Shopify.
- [For developers](docs/developers.md): the scripts, the safety rules in the
  code, the taxonomy index, and known limits.

---

## Licence

MIT.
