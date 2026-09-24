# Going public — checklist

The repository ships private. Everything below is what has to happen when it is
made public, in order. Nothing here is automatic.

## 1. Secrets and variables

| Name | Kind | Value | Used by |
|---|---|---|---|
| `SLACK_WEBHOOK_URL` | secret | the Slack incoming-webhook URL | both notification workflows |
| `NOTIFICATIONS_ENABLED` | variable | `true` | gates both notification jobs |

Both notification workflows are gated on `vars.NOTIFICATIONS_ENABLED == 'true'`
as well as their triggers, so setting the secret alone does not switch them on.
That is deliberate: it means the secret can be added and tested before anything
starts posting.

## 2. Re-enable the notification workflows

Both are currently `workflow_dispatch:` only. Restore their real triggers:

`.github/workflows/star-fork-notify.yml`

```yaml
on:
  watch:
    types: [started]
  fork:
```

`.github/workflows/download-tracker.yml`

```yaml
on:
  schedule:
    - cron: '0 */6 * * *'
  workflow_dispatch:
```

Remove the "DISABLED while the repository is private" comment from each while
you are there, so it does not outlive the situation it describes.

`check-generated.yml` is already live and stays as it is.

## 3. Create the `download-stats` branch

The download tracker checks out a branch that holds nothing but its own state
file, and it will fail on the first run if that branch does not exist:

```
git switch --orphan download-stats
git rm -rf . --quiet 2>/dev/null || true
echo '{}' > previous.json
git add previous.json
git commit -m "chore: initialise download counter state"
git push -u origin download-stats
git switch main
```

## 4. Cut the first release

The tracker counts release-asset downloads, so it reports nothing until there is
a release with the bundle attached.

```
python3 scripts/build_key_map.py --check          # artifacts current
python3 scripts/build_taxonomy_index.py --version 2026-08   # only if re-pinning

gh release create v0.1.0 shopify-category-metafields.skill \
  --title "v0.1.0" \
  --notes "First release. Assigns Shopify Standard Product Taxonomy categories and fills category metafields. Does not touch tags."
```

Rebuild the bundle first if any of `SKILL.md`, `scripts/`, `taxonomy/`,
`templates/` or `config.json` changed since the last one — the committed
`.skill` is a build artifact and goes stale silently.

## 5. Before flipping visibility

- `docs/design.md` names the test store, `pancakeclothing.com`, and quotes real
  product titles and metaobject ids from it. Confirm that is acceptable in
  public, or scrub it.
- `work/` is gitignored and has never been committed — verify with
  `git log --all --name-only -- work/ | head`, which should print nothing.
- The README's Known limits section describes real connector behaviour. Keep it:
  a user who hits the `metafieldsDelete` refusal without warning will assume the
  skill is broken.

## 6. Taxonomy version

The pinned release is recorded in `taxonomy/index.json.gz` under `_version` and
`_source`. Shopify cuts a stable taxonomy release at most quarterly. To move:

```
python3 scripts/build_taxonomy_index.py --version <new>
python3 scripts/build_key_map.py
```

Then re-read `taxonomy/key_exceptions.json` — the collapsed and renamed keys were
verified against one release and are not guaranteed to survive another.
