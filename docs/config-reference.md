# Configuration reference

A project is a folder with three JSON files, plus `assets/` and generated
`build/` and `style-ids.lock.json`. Relative paths resolve against the
project folder; `~` is expanded.

## project.json

```jsonc
{
  "aem": {
    "baseUrl": "http://localhost:4502",
    "policiesRoot": "/conf/<site>/settings/wcm/policies",      // read live for ID checks
    "requiredPageProps": ["cq:template=", "headerXf="],         // page build refuses if missing
    "template": "/conf/<site>/settings/wcm/templates/content-page", // for `inventory`
    "contentRoot": "/content/<site>"                             // for `inventory` usage counts
  },
  "figma": {
    "fileKey": "AbCdEfGhIjKlMnOpQrStUv",                       // from the Figma URL
    "pageNode": "1:2",                                   // default for `map`
    "componentMap": { "1.1 Content Teaser": "teaser" }         // Figma component(set) → component type
  },
  "damRoot": "/content/dam/<site>/<folder>",                  // where assets are installed; "dam:" prefix
  "assetsDir": "assets",
  "buildDir": "build",
  "styles": "styles.json",
  "pages": ["pages/home.json", "pages/overview.json"],   // or "page": "page.json" for one page
  "lessDir": "/path/to/clientlib/styles/style_system",   // enables the LESS coverage check
  "classPrefix": "ds-",                                 // which classes the coverage check looks at
  "jsClasses": ["ds-tabs__dots"],                   // classes created by JS (no policy needed)
  "clientlib": {                                       // for `clientlib` (all optional except theme)
    "theme": "mysite",                                 // → clientlib-mysite; --theme overrides
    "dir": "../ui.apps/src/main/content/jcr_root/apps/mysite/clientlibs",  // default build/clientlibs
    "appsPath": "/apps/mysite/clientlibs",            // JCR parent: resources URL + --package filter
    "categories": ["mysite.site"],                     // default ["<theme>.site"]
    "dependencies": ["mysite.global"], "embed": [],
    "cssProcessor": ["default:none", "min:gcc"],       // default shown
    "jsProcessor": ["default:none", "min:gcc;languageIn=ECMASCRIPT_2015;compilationLevel=whitespace"],
    "figmaFrames": ["12:3", "40:1"],                   // extra frames for `--figma`: Foundations, Components…
    "breakpoints": {"tablet": 1023, "mobile": 767},    // max-width per mode, widest first (default shown)
    "tokenScope": ":root"                              // where Tablet/Mobile overrides go, e.g. ".ds-section"
  },
  "damFolders": {"landing": "Landing"},      // titles for DAM subfolders
  "styleLock": "style-ids.lock.json",
  "package": {
    "name": "site-home", "group": "site", "version": "1.0",
    "description": "…", "damFolderTitle": "…"
  },
  "components": {
    "<type>": {
      "resourceType": "mysite/components/content/container",
      "policy": "mysite/components/content/container/policy_123",  // relative to policiesRoot
      "defaults": { "layout": "simple" }                                        // merged under node props
    }
  }
}
```

Find a component's `policy` in the template's policy mappings:
`/conf/<site>/settings/wcm/templates/<template>/policies.infinity.json`
(`cq:policy` values under `root/container/<resourceType>`).

Without `lessDir`, the LESS coverage check reads
`<clientlib.dir>/clientlib-<theme>/styles/style_system` once `clientlib` has
created it.

### Generated clientlib

`clientlib` writes `clientlib-<theme>/` in the layout of a hand-built site
clientlib:

| File | Owner |
|---|---|
| `.content.xml` (`cq:ClientLibraryFolder`, `allowProxy`, categories, processors, dependencies, embed) | tool: rewritten from `clientlib` config |
| `styles/style_system/index.less` (`<prefix>foundation.less`, then one file per style in styles.json order, then other `.less` files in the folder) | tool: rewritten |
| `styles/design-system/*.less` (from the Figma snapshot, see below) | tool: rewritten |
| `css.txt`, `js.txt`, `styles/index.less`, `variables.less`, `base.less`, `style_system/<prefix>foundation.less`, `style_system/<prefix>*.less`, `scripts/site.js` | you: created once, never overwritten |

### Design system layer (`clientlib --figma`)

`--figma` fetches the breakpoint frames (every page's `verify.viewports`), the
`clientlib.figmaFrames`, and the file's local variables, and saves them to
`build/figma-design-system.json`. Later runs reuse that snapshot offline
(`--snapshot <file>` picks another). Frames are assigned to a mode by width
against `breakpoints`; variable modes by name ("Desktop", "Tablet", "Mobile").

| File | From Figma |
|---|---|
| `tokens.less` | variables → `--<name>` (`codeSyntax.WEB` wins, else the slugged name); default mode on `:root`, Tablet/Mobile modes as `@media` overrides in `tokenScope` (each compared with the next wider mode, because max-width queries nest), other modes (Light/Dark…) under `[data-<collection>="<mode>"]`; aliases stay `var()`; fill and effect styles → `--color-*`, `--shadow-*` |
| `spacing.less` | gaps, paddings and radii **not** bound to a variable → `--space-<n>`, `--radius-<n>` |
| `grid.less` | `@<prefix>mq-desktop/tablet/mobile`; each breakpoint frame's COLUMNS layout grid → `--grid-columns/gutter/margin/max-width`; `.<prefix>grid()` |
| `fonts.less` | `@font-face` per family / weight / style used, `src` = `resources/fonts/<PostScriptName>.woff2` (+ `.woff` if present); needs `appsPath` |
| `typography.less` | text styles → `--type-<style>-<property>` + `.<prefix>type--<style>()` |
| `variants.less` | component variants (definition in a component set, else first top-level instance) → `.<prefix>variant--<set>--<variant>()` (box: background, border, radius, flex, gap, padding, shadow) and `…--text()` (text style + color) |

All of it is mixins and custom properties, so no new author classes appear and
the coverage check is unaffected. Call the mixins from `style_system/` files:
`.ds-button .cmp-button { .ds-variant--button--primary(); }`.

The generated media queries are literal (`screen and (max-width: 767px)`):
LESS 1.7.5, AEM's compiler, cannot parse `@media @{var}`, and current LESS
deprecates `@media @var`.

The Variables API is Enterprise-only. On other plans the 403 is recorded
in the snapshot, and tokens come from styles and the values in the frames.
`build/design-system-report.md` lists what is not tokenised: unbound colors,
spacing, radii, font sizes without a text style, and missing font files.

`--package` zips the folder as it is on disk (including your edits) under
`appsPath`. Use that zip for a local or AEM 6.5 install. On AEM as a Cloud
Service `/apps` is immutable, so deploy the folder through ui.apps.

## styles.json

```jsonc
{
  "groupLabel": "Design System",          // shown in the editor's Styles dropdown
  "groupNode": "designsystem",            // node under each policy's cq:styleGroups (filtered by the package)
  "idBase": 1794500000000,           // first ID tried for new styles
  "styles": {
    "<component type>": [
      { "key": "section", "classes": "ds-section", "label": "DS Section" }
    ]
  }
}
```
- `key` must be unique across all types; `page.json` refers to styles by key.
- `classes` may list several classes (composite style).
- The group is multi-select (`cq:styleGroupMultiple`), so styles combine.

## page.json (one file per page)

```jsonc
{
  "path": "/content/<site>/us/en",
  "mode": "replace",                           // "replace": swap <path>/jcr:content (needs basePackage)
                                               // "create":  new page; rollback deletes it
  "basePackage": "~/Downloads/export.zip",     // replace: contains jcr_root<path>/.content.xml
  "inheritProps": ["cq:template", "headerXf"], // create: copied from the parent's jcr:content (default list in page.py)
  "pageProps": {"jcr:title": "…", "navTitle": "…"},   // create: set on the new page
  "parentProps": { },                          // create, offline: parent props instead of reading AEM
  "assets": [
    { "file": "hero.png", "title": "Alt text", "figmaFill": "10:20" },
    { "file": "card.png", "title": "Alt text", "figmaNode": "I10:21;30:40", "scale": 2 },
    { "file": "sub/hero-mobile.jpg", "title": "…", "figmaFill": "I6044:4871;…", "crop": true, "width": 1440 }
  ],                                            // "crop": apply the layer's Figma crop to the original fill
                                                // files may sit in DAM subfolders ("sub/…")
  "verify": {
    "url": "http://localhost:4502/content/<site>/us/en.html?wcmmode=disabled",
    "tolerance": 2,
    "viewports": [ { "width": 1440, "figmaFrame": "1:2" },
                   { "width": 768, "figmaFrame": "1:3", "headerOffset": -2 },  // live header 70 vs Figma nav 72
                   { "width": 360, "figmaFrame": "1:4" } ]
  },
  "body": { /* component node */ }
}
```

### Component node

```jsonc
{
  "name": "card_feature",              // JCR node name, unique among siblings
  "type": "teaser",                     // project.json components key
  "styles": ["teaser_card", "class:text--hanging-asterisk"],
                                        // styles.json keys → new IDs; "class:<classes>" reuses an
                                        // existing AEM style on this component's policy
  "props": {                            // written as-is (strings stay strings)
    "jcr:title": "<p>Feature title</p>",
    "fileReference": "dam:card-1.png",
    "textIsRich": ["true", "true"]      // arrays → multi-value
  },
  "actions": [ { "link": "/content/…", "text": "Read more" } ],   // teaser CTAs → actions/itemN
  "children": [ /* component nodes */ ],
  "verify": {
    "figma": ["Hero_Desktop", "Hero_Mobile"],   // layer name(s); first present in the frame wins
    "figmaIndex": 0,                            // nth layer with that name (default 0)
    "selector": ".ds-card .cmp-teaser", // CSS selector on the rendered page
    "index": 0                                  // nth DOM match of the selector (default 0)
  }
}
```

Property values: JSON strings are JCR Strings (AEM stores most component
flags as the strings `"true"`/`"false"`). JSON booleans become `{Boolean}`.
Multi-value strings use arrays. `dam:<file>` expands to `damRoot/<file>`.

## style-ids.lock.json (generated, commit it)

`{ "<style key>": "<cq:styleId>" }`. Delete an entry only if that style was
never installed anywhere. Otherwise pages lose their style.
