# Troubleshooting

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
[Undoing a run](how-a-run-works.md#undoing-a-run). The backup is kept as a file, so this works
later in the conversation too, not only immediately afterwards.
