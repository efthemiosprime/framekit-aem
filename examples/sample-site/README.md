# sample-site

A synthetic project showing the files figma2aem expects. All names, paths, IDs
and images are placeholders.

```
sample-site/
├─ project.json            AEM paths, component types → resource type + policy, pages list
├─ styles.json             Style System entries (one "Design System" group per policy)
├─ style-ids.lock.json     generated on first build — commit it in real projects
├─ pages/
│  ├─ home.json            mode "replace": swaps the body of an existing page
│  └─ landing.json         mode "create": new page, props from parentProps / parent page
├─ assets/                 images packaged to damRoot (subfolders allowed: landing/…)
├─ styles/ds-sample.less   LESS checked by the coverage check (lessDir)
└─ aem/
   ├─ base-home-export.zip   export of the current Home page (basePackage)
   └─ policies.json          policies export, so the sample runs without an AEM
```

Run it offline from the repository root:

```bash
python3 -m figma2aem check   --project examples/sample-site --policies-json examples/sample-site/aem/policies.json
python3 -m figma2aem package --project examples/sample-site --policies-json examples/sample-site/aem/policies.json
```

`landing.json` reuses an existing style by class (`"class:text--legacy-note"`),
which the check reports so you know it must exist on the target AEM.
