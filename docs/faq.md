# Frequently asked

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

**Can I run it again later for new products?** Yes. Any detail field that
already has a value is reported as "already set" and left alone. A repeat run
fills only the fields that are still empty, on new products and on older ones
alike.

**Does it work for stores that are not clothing?** Yes. The category list covers
14,606 categories across every vertical Shopify defines: furniture, food,
electronics, pet supplies and the rest. Apparel happens to have the most
attributes, which is why it makes the clearest examples.

**Does it cost anything?** The tool is free and MIT-licensed. You pay only for
your normal Claude usage.

**Where does my store data go?** To Claude and nowhere else. Claude reads your
catalog through the Shopify connector, the same way it handles anything else you
share in a conversation. The helper scripts run inside Claude's own code environment
(on your computer, if you use Claude Code) and contact no outside service. The only thing they download is your own product photos, from
Shopify's image servers.
