"""Starter LESS file per style ("component styles").

The scaffold records where the style is used in page.json (expected AEM
markup outline), the Figma source node, and an empty rule per class. It never
overwrites an existing file: once written, the file belongs to the developer.
"""
from pathlib import Path

from .config import ConfigError
from .page import walk_spec

MARKUP_HINTS = {
    "container": "div.container.responsivegrid.<styles> > div.cmp-container > children",
    "text": "div.text.<styles> > div.cmp-text > (rich text)",
    "image": "div.image.<styles> > div.cmp-image > img.cmp-image__image",
    "button": "div.button.<styles> > a.cmp-button > span.cmp-button__text",
    "teaser": ("div.teaser.<styles> > div.cmp-teaser > div.cmp-teaser__image > div.cmp-image > img | "
               "div.cmp-teaser__content > div.cmp-teaser__title > a.cmp-teaser__title-link"),
    "hero": ("div.teaser.<styles> > div.cmp-teaser > div.teaser-bg-img|teaser-bg-tab-img|teaser-bg-mob-img "
             "+ div.cmp-teaser__content > h2.cmp-teaser__title(+h1) + div.cmp-teaser__description"),
}


def find_style(styles_spec, key):
    for kind, entries in styles_spec["styles"].items():
        for entry in entries:
            if entry["key"] == key:
                return kind, entry
    raise ConfigError(f"Style key '{key}' not found in styles.json")


def usages(page_spec, key):
    return [n for n in walk_spec(page_spec["body"]) if key in n.get("styles", [])]


def outline(node, depth=0, max_depth=3):
    if depth > max_depth:
        return []
    styles = ",".join(node.get("styles", []))
    lines = [f"//   {'  ' * depth}{node['name']} [{node['type']}]" + (f" styles={styles}" if styles else "")]
    for child in node.get("children", []):
        lines += outline(child, depth + 1, max_depth)
    return lines


def scaffold(styles_spec, page_spec, key, file_prefix="ds-"):
    kind, entry = find_style(styles_spec, key)
    classes = entry["classes"].split()
    own_class = classes[-1]  # composite styles list shared classes first
    nodes = usages(page_spec, key)
    figma = set()
    for node in nodes:
        names = node.get("verify", {}).get("figma") or []
        figma.update([names] if isinstance(names, str) else names)
    figma = sorted(figma)

    lines = [
        "// " + "=" * 77,
        f"// {entry['label']}  (style key: {key}, classes: {entry['classes']})",
        "//",
        f"// Figma source: {', '.join(figma) if figma else 'add verify.figma in page.json'}",
        f"// AEM markup:   {MARKUP_HINTS.get(kind, kind)}",
        "//",
        "// Used in page.json:",
    ]
    for node in nodes:
        lines += outline(node)
    lines += ["// " + "=" * 77, "",
              f".{own_class} {{",
              "    // Use tokens from tokens.less (var(--…)) and the @ds-mq-* breakpoints",
              "    // from ds-foundation.less; escape calc()/max() as ~\"…\" for AEM's LESS.",
              "}", ""]
    file_name = f"{file_prefix}{own_class.removeprefix(file_prefix).split('--')[0].split('__')[0]}.less"
    return file_name, "\n".join(lines)


def write_scaffold(target_dir, file_name, text):
    path = Path(target_dir).expanduser() / file_name
    if path.exists():
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path, True
