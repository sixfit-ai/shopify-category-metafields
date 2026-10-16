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
