"""Project configuration: project.json, styles.json, page.json.

All paths inside the JSON files are resolved relative to the file that
declares them, so a project folder can be moved as a unit.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


def load_json(path):
    path = Path(path).expanduser()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc


def require(mapping, key, where):
    if key not in mapping:
        raise ConfigError(f"{where}: missing required key '{key}'")
    return mapping[key]


@dataclass(frozen=True)
class Project:
    root: Path
    data: dict

    @classmethod
    def load(cls, project_dir):
        root = Path(project_dir).expanduser().resolve()
        data = load_json(root / "project.json")
        for key in ("aem", "components", "package"):
            require(data, key, "project.json")
        for name, comp in data["components"].items():
            require(comp, "resourceType", f"project.json components.{name}")
        return cls(root, data)

    # -- paths ---------------------------------------------------------------
    def path(self, relative):
        return (self.root / Path(relative).expanduser()).resolve()

    @property
    def build_dir(self):
        return self.path(self.data.get("buildDir", "build"))

    @property
    def assets_dir(self):
        return self.path(self.data.get("assetsDir", "assets"))

    # -- sections ------------------------------------------------------------
    @property
    def aem(self):
        return self.data["aem"]

    @property
    def figma(self):
        return self.data.get("figma", {})

    @property
    def components(self):
        return self.data["components"]

    @property
    def package(self):
        return self.data["package"]

    @property
    def dam_root(self):
        return require(self.data, "damRoot", "project.json")

    def component(self, kind):
        try:
            return self.components[kind]
        except KeyError as exc:
            raise ConfigError(f"Unknown component type '{kind}' (define it in project.json components)") from exc

    def styles(self):
        return load_json(self.path(self.data.get("styles", "styles.json")))

    def page(self):
        return load_json(self.path(self.data.get("page", "page.json")))

    def pages(self):
        """All page specs of the project: "pages": [files] or the single "page"."""
        files = self.data.get("pages") or [self.data.get("page", "page.json")]
        specs = []
        for rel in files:
            spec = load_json(self.path(rel))
            spec.setdefault("_file", str(rel))
            specs.append(spec)
        paths = [s.get("path") for s in specs]
        if len(set(paths)) != len(paths):
            raise ConfigError(f"Two page files target the same AEM path: {paths}")
        return specs

    @property
    def clientlib(self):
        return self.data.get("clientlib", {})

    @property
    def clientlibs_dir(self):
        """Folder that receives clientlib-<theme>/ (e.g. ui.apps/…/apps/<app>/clientlibs)."""
        rel = self.clientlib.get("dir")
        return self.path(rel) if rel else self.build_dir / "clientlibs"

    @property
    def less_dir(self):
        rel = self.data.get("lessDir")
        if rel:
            return self.path(rel)
        theme = self.clientlib.get("theme")
        # Without lessDir, check the generated clientlib's component styles once it exists.
        if theme:
            generated = self.clientlibs_dir / f"clientlib-{theme}" / "styles" / "style_system"
            return generated if generated.is_dir() else None
        return None

    @property
    def class_prefix(self):
        return self.data.get("classPrefix", "ds-")

    def style_lock_path(self):
        return self.path(self.data.get("styleLock", "style-ids.lock.json"))


def credentials(prefix):
    """Read <PREFIX>_USER / <PREFIX>_PASSWORD from the environment."""
    user = os.environ.get(f"{prefix}_USER")
    password = os.environ.get(f"{prefix}_PASSWORD")
    if not user or not password:
        raise ConfigError(f"Set {prefix}_USER and {prefix}_PASSWORD in the environment")
    return user, password


def figma_token():
    token = os.environ.get("FIGMA_TOKEN")
    if not token:
        raise ConfigError("Set FIGMA_TOKEN (Figma personal access token) in the environment")
    return token
