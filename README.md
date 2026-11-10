# figma2aem

Turn a Figma page design into an installable AEM content package: Style
System policies, page structure, DAM images, and a rollback, plus a browser
check that the result matches Figma to the pixel.

It is config-driven. You describe the site once (`project.json`), the styles
(`styles.json`) and the page tree (`page.json`); the tool generates the
FileVault package. The CSS stays hand-written in your clientlib; the tool
scaffolds a starter LESS file per style and measures the result.

Worked example: [`examples/sample-site`](examples/sample-site), a synthetic
two-page project (an existing **Home** whose body is replaced, and a new
**Landing** page) showing every config file and the folder layout. The tool was
first used on a production AEM site, where it reproduced a hand-built,
Figma-verified two-page package file for file; that client project is not
part of this repository.

## Requirements

| What | Why |
|---|---|
| Python 3.9+ (stdlib only) | the pipeline (`python3 -m figma2aem`) |
| `FIGMA_TOKEN` | Figma personal access token for `map`, `export-assets`, `verify-spec` |
| `AEM_USER` / `AEM_PASSWORD` | read policies and the page from AEM (`styles`, `package`, `aem-inventory`) |
| An exported package of the current page | `page.json basePackage`: keeps page properties exactly (template, XFs, GTM…) |
| Node 18+ and `npm install` in `verify/` | only for the browser parity check |

Credentials are read from the environment only; nothing is stored.

## Quick start

```bash
export AEM_USER=admin AEM_PASSWORD=admin FIGMA_TOKEN=figd_…
P=examples/sample-site

python3 -m figma2aem inventory     --project $P   # what already exists: placeable components, styles + usage
python3 -m figma2aem map           --project $P   # Figma components + variants used on the page
python3 -m figma2aem aem-inventory --project $P   # current AEM page tree with resolved styles
python3 -m figma2aem export-assets --project $P   # images from Figma (2x renders / original fills)
python3 -m figma2aem styles        --project $P   # assign + lock Style System IDs
python3 -m figma2aem scaffold-less --project $P --all --out <clientlib>/styles/style_system
python3 -m figma2aem check         --project $P   # assets, style references, LESS coverage
python3 -m figma2aem package       --project $P   # build/<name>-<version>.zip + rollback zip (runs check)
TARGET_AEM_USER=… TARGET_AEM_PASSWORD=… \
python3 -m figma2aem preflight     --project $P --target https://author.example.com   # before a server install

# after installing the CSS and the package:
python3 -m figma2aem verify-spec   --project $P
(cd verify && npm install)
node verify/probe.mjs $P/build/verify-content_mysite_us_en_landing.json --shots $P/build/shots
```

## What each command touches

| Command | Reads | Writes |
|---|---|---|
| `inventory` | AEM template policies, policies, QueryBuilder | `build/aem-styles-inventory.json` |
| `map` | Figma | `build/figma-inventory.json` |
| `aem-inventory` | AEM page + policies | `build/aem-inventory.json` |
| `export-assets` | Figma | `assets/` (skips existing files unless `--force`) |
| `styles` | AEM policies | `style-ids.lock.json` |
| `scaffold-less` | styles.json, page.json | new `.less` files only, never overwrites |
| `check` | pages, assets, styles, LESS | nothing (report; non-zero exit on errors) |
| `page` | base package / parent page, AEM policies | `build/pages/*.content.xml` (preview) |
| `package` | all of the above | `build/*.zip`, `style-ids.lock.json` |
| `preflight` | the **target** AEM (read-only) | nothing (report; non-zero exit on errors) |
| `verify-spec` | Figma | `build/verify-<page>.json` per page |
| `backup --yes` | AEM | **creates a package in AEM `/etc/packages`** + downloads it |

Only `backup` writes to AEM, and only with `--yes`. Installing a package is
always done by you (Package Manager or your Maven build).

## Documentation

- [docs/process.md](docs/process.md): the end-to-end process, step by step, with the checks that matter
- [docs/config-reference.md](docs/config-reference.md): every key in project.json, styles.json, page.json
- [docs/roadmap.md](docs/roadmap.md): where this is heading, mapped from the FrameKit (Figma → WordPress) architecture

## Tests

```bash
python3 -m unittest discover -s tests
```
Offline tests (no network): docview escaping, stable style IDs, page
rendering, new pages, class references, checks, crops, preflight,
policy entries, LESS scaffolding, Figma inventory and geometry.
