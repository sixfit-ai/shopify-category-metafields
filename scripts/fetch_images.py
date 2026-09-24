#!/usr/bin/env python3
"""Download each product's first image so its visual attributes can be judged.

Some category attributes are only ever stated by the picture. `pattern` is the
clearest case: a description rarely says "solid", but the photo shows plainly
whether a garment is plain, striped or floral. Without the image the value has
to be guessed, and guessing is exactly what this skill refuses to do.

So the flow is: fetch the images, LOOK at them, and record "product image shows
a plain unpatterned garment" as the source. Never record an image as the source
for something an image cannot show -- fabric, care instructions, stretch.

Images are written to work/images/<product id>.<ext> and are gitignored.

Usage
-----
    python3 scripts/fetch_images.py
    python3 scripts/fetch_images.py --limit 20 --per-product 1
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import load_json, short_gid, work  # noqa: E402


def extension(url):
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif") else ".jpg"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--products", default=work("products.json"))
    parser.add_argument("--out-dir", default=work("images"))
    parser.add_argument("--per-product", type=int, default=1,
                        help="images per product (default: 1)")
    parser.add_argument("--limit", type=int, help="stop after N products")
    args = parser.parse_args()

    catalog = load_json(args.products)
    os.makedirs(args.out_dir, exist_ok=True)

    saved, skipped = 0, []
    products = catalog["products"][:args.limit] if args.limit else catalog["products"]
    for product in products:
        images = product.get("images") or []
        if not images:
            skipped.append(product["title"])
            continue
        for index, image in enumerate(images[:args.per_product]):
            name = "%s%s%s" % (short_gid(product["gid"]),
                               "" if index == 0 else "_%d" % index,
                               extension(image["url"]))
            path = os.path.join(args.out_dir, name)
            if os.path.exists(path):
                saved += 1
                continue
            try:
                with urllib.request.urlopen(image["url"]) as response, \
                        open(path, "wb") as handle:
                    handle.write(response.read())
                saved += 1
            except Exception as error:                      # noqa: BLE001
                skipped.append("%s (%s)" % (product["title"], error))

    print("saved %d image(s) to %s" % (saved, args.out_dir))
    if skipped:
        print("  no image for %d product(s):" % len(skipped))
        for title in skipped[:10]:
            print("      %s" % title)
    print("\nNow LOOK at them before proposing any visual attribute.")
    print("Each file is named by product id, so work/images/<id>.png is that")
    print("product's photo. Record what the image actually shows, and only")
    print("that -- a photo is evidence for pattern and colour, never for")
    print("fabric, care instructions or stretch.")


if __name__ == "__main__":
    main()
