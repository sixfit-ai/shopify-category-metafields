# Settings

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
