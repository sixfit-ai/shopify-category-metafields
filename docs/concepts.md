# Concepts

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

## Under the hood

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
