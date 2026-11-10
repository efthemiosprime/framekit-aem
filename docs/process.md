# Process: Figma page → AEM page

The steps below are the ones used to build and verify the first production
pages built with this tool (see `examples/sample-site` for the file layout).
Each step lists what it produces and **the check that proves it worked**. Do not skip the checks: most real problems found on
that project were invisible until something was measured.

```
 1 Analyse Figma ─┐
 2 Analyse AEM  ──┼─▶ 3 Map components ─▶ 4 Style policies ─▶ 5 Component styles (LESS)
                  │                                              │
                  └────────────────────────▶ 6 Page structure ◀──┘
                                              7 Assets
                                              8 Package + rollback ─▶ 9 Install ─▶ 10 Verify parity
```

---

## 1. Analyse the Figma page

```bash
python3 -m figma2aem map --project <dir> --node <page frame id>
```

Produces a table of every top-level component instance with the variant it
uses, and `build/figma-inventory.json`.

Look for:
- **Variants that exist but are unused**, e.g. mobile/tablet variants that only
  appear in separate "Tablet test" / "Mobile test" frames. Find those frames
  and add them to `page.json verify.viewports`.
- **Component descriptions** in Figma (they often say which AEM component the
  designer intended, e.g. "AEM: core/wcm/components/teaser/v2/teaser").
- **Responsive variable modes** (Desktop / Tablet / Mobile). They give exact
  tablet and mobile values for spacing and type. Put them in your tokens file,
  scoped (see step 5).
- **Hidden or duplicate layers**: a hidden old section or a detached copy of a
  component. Leave them out.

✔ Check: every component in the table has a row in `figma.componentMap`.

## 2. Analyse the AEM site

```bash
python3 -m figma2aem inventory     --project <dir>   # placeable components, every style + page usage
python3 -m figma2aem aem-inventory --project <dir>   # one page's component tree
```

Map before you make: for every Figma component, pick the first option that can
render it: reuse an existing component + style, extend a style with a
modifier, add a new style, and only as a last resort a new component. Record
the decision (keep it in the site repo, e.g. `docs/component-map.md`).

Prints the current page tree with resource types and **resolved** style
classes. Pages store Style System choices as IDs (`cq:styleIds`), not class
names, so you need the policies to read them.

Also export the current page as a package (Package Manager, or
`figma2aem backup --yes`) and point `page.json basePackage` at it.

✔ Checks that matter:
- **Child pages.** If the target page has children, a package filter on the page
  itself would delete them. The tool only ever filters `<page>/jcr:content`.
- **Policies in the repo can be stale.** On the first production site, the repo's policies file was
  missing IDs that pages already used. Always read policies **from AEM**: the
  tool does, and checks new IDs against them.
- **Header/footer** usually come from page properties (`headerXf`, `footerXf`).
  They are kept from the base package, not rebuilt.

## 3. Map Figma components → AEM components

Decide, per Figma component, which existing AEM component renders it. Prefer
existing components plus a style over new components. Record:
- component types in `project.json components` (resource type, policy, defaults);
- the mapping in `figma.componentMap` (documentation and the `map` report).

Get the **real rendered markup** for each component before writing CSS: view
source on an existing page that uses it, or the live site. Examples that
differed from what you would assume:
- a link button renders `a.cmp-button > span.cmp-button__text`;
- the custom teaser renders `div.cmp-teaser__title > a.cmp-teaser__title-link > p`;
- a rich-text hero title renders `<h2 class="cmp-teaser__title"><h1>…</h1></h2>`.
  Browsers split that into an empty `h2` (containing whitespace) and a sibling
  `h1`, so `:empty` does not match it;
- container background images are inline `style="background-image:…"` on
  `.cmp-container`, so overriding them needs `!important`.

`scaffold-less` writes these markup hints into each LESS file header.

## 4. Style System policies

Edit `styles.json`: one entry per style, grouped by component type.

```bash
python3 -m figma2aem styles --project <dir>
```

- New IDs are checked against every style ID in AEM and saved to
  `style-ids.lock.json`. **Commit the lock file.** Later builds reuse the same
  IDs, so pages that already reference them keep working.
- Each component policy gets **one new group** (`groupNode`), so existing groups
  are never touched. The package filters only those group nodes.
- Composite styles (e.g. `"ds-section ds-bg--dark ds-footnotes"`) give
  authors one click per section, matching existing site conventions.

✔ Check: the command reports how many existing AEM IDs it checked against. If
that number is 0, it did not read the right policies root.

## 5. Component styles (LESS)

```bash
python3 -m figma2aem scaffold-less --project <dir> --all --out <clientlib>/styles/style_system
```

Then write the CSS by hand from the Figma design context. Rules learned on the first production build:

- **Scope responsive tokens.** Legacy rules may read the same tokens (e.g.
  `@gutter-x: … var(--grid-margin)`; heading rules reading the type sizes).
  Put tablet/mobile overrides under a section class (`.ds-section`), not
  `:root`, or you change pages that were not rebuilt.
- **Re-declare aliases inside the scope.** `--card-gap: var(--grid-gutter)` on
  `:root` is computed once at the root; overriding `--grid-gutter` inside
  `.ds-section` does not update it, so re-declare the alias there too.
- **AEM's LESS compiler is old.** Escape `calc()`, `max()`, `min()`, `mask`
  shorthands with `~"…"`, as the existing clientlibs do. Compile with LESS 1.7.5
  *and* a current LESS before deploying:
  `npx -p less@1.7.5 lessc styles/index.less out.css`.
- **Copy Figma exactly, including what looks odd**: `line-height: normal` on
  buttons (41/43px tall buttons), `content-start` / `items-start` on wrapping
  rows (stops cards and images stretching), clipping (`overflow-clip`) on the
  quote row.
- **Text that just fits.** If a Figma text box is only a fraction of a pixel
  wider than its text (632.6px of text in a 633px box), browsers may wrap one
  line earlier. Give the column a few pixels of slack and note why in a
  comment.

## 6. Page structure

Describe the page as a component tree in `page.json body` (see
[config-reference](config-reference.md)). Use `dam:<file>` for image
references and style **keys** (not IDs) in `styles`.

```bash
python3 -m figma2aem page --project <dir>     # writes build/page.content.xml to review
```

The page's own properties (template, XFs, analytics IDs, login requirement)
come from the base package unchanged; only the body is replaced.

## 7. Assets

```bash
python3 -m figma2aem export-assets --project <dir>
```

- `figmaNode` renders a layer **with its children** at `scale` (default 2x).
  Use it for card media and illustrations.
- `figmaFill` downloads the **original** image of a layer's image fill, without
  children or crop. Use it for photos that are a frame's background.
- The MCP/screenshot route only gives 1x; prefer this command for retina images.
- Write a real `title` (alt text) per asset.

## 8. Package + rollback

```bash
python3 -m figma2aem package --project <dir> [--rollback-all]
```

Produces in `build/`:
- `<name>-<version>.zip`: filters `<page>/jcr:content`, the DAM folder, and one
  filter per style group. Nothing else on the instance is in scope.
- `<name>-rollback-<version>.zip`: restores the page body from the base
  package. With `--rollback-all` it also deletes the generated style groups and
  the DAM folder. Only use that if no other page uses them.

✔ Check: the printed filter list. Every filter must be either the page's
`jcr:content`, the DAM folder, or a `cq:styleGroups/<groupNode>` node.

## 8b. Checks and preflight

`package` runs `check` first and refuses to write the zip on errors:
- every DAM path a page references is in the package (this caught a missing
  SVG on the first production build);
- every author class in `lessDir` is registered in a policy, and selectable on
  its own, not only inside a combined style;
- styles reused with `class:` resolve to exactly one existing style.

Before installing on another server, run `preflight --target <url>`. It reads
the target (read-only) and fails if a policy, a reused style, a parent page,
a header/footer fragment or the DAM parent is missing, or if a new style ID is
already taken there. Build a backup package on the target with the same
filters before you install.

## 9. Install

1. Deploy the CSS (your clientlib build, e.g. `mvn clean install -PautoInstallPackage`).
2. Install the package in Package Manager.
3. Open the page with `?wcmmode=disabled`, then in the editor confirm the new
   group appears in each component's Styles dropdown.

Order matters: a page installed before its CSS renders unstyled.

## 10. Verify parity with Figma

```bash
python3 -m figma2aem verify-spec --project <dir>
node verify/probe.mjs <dir>/build/verify-spec.json --shots <dir>/build/shots
```

Each component node with a `verify` block is measured at every viewport and
compared with the matching Figma layer (by name, relative to the frame).
Non-zero exit when anything is off by more than `tolerance`.

- **Test CSS before deploying it:**
  `--css out.css --css-match "clientlib-mysite\.lc-.*\.css"` serves your
  compiled file in place of the deployed one. Nothing is written to AEM.
- **Fonts.** The probe prints which font families loaded and which failed. Never
  send AEM credentials as a global header: Typekit's font requests then fail
  their CORS preflight and the page silently renders in the fallback font (the
  probe scopes the login to the AEM origin). If a font still fails, text-driven
  heights are not comparable; compare boxes, images and spacing only.
- **Header offsets.** Figma frames include the nav. If the live header height
  differs (70 vs 72px), set `headerOffset` on that viewport so the shift is not
  reported as a component difference.

Report deltas faithfully: say which differences remain and why (for example
"+32px: the heading wraps because Chrome renders it 1px wider than its 296px
column"), rather than tuning numbers until the table is green.
