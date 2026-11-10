"""figma2aem — turn a Figma page design into an installable AEM content package.

Pipeline (each step is a CLI subcommand, see ``python3 -m figma2aem --help``):

    map            Figma page → component / variant inventory          (Figma REST, read-only)
    aem-inventory  AEM page   → component tree with resolved styles      (AEM HTTP, read-only)
    styles         styles.json → Style System groups with stable IDs
    scaffold-less  styles.json + page.json → starter LESS file per style
    export-assets  page.json assets → PNG/SVG exports from Figma (2x)
    page           page.json  → en/jcr:content docview XML
    package        everything → install package + rollback package
    verify-spec    Figma geometry + selectors → spec for verify/probe.mjs
    backup         AEM Package Manager backup of the target page        (WRITES to /etc/packages)
"""

__version__ = "0.1.0"
