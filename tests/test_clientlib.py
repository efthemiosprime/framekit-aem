"""Offline tests for clientlib-<theme> generation: python3 -m unittest discover -s tests"""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.dom import minidom

from figma2aem import cli, clientlib
from figma2aem.config import ConfigError, Project

STYLES = {
    "groupLabel": "New", "groupNode": "new2026", "idBase": 100,
    "styles": {
        "container": [{"key": "section", "classes": "x-section", "label": "Section"},
                      {"key": "dark", "classes": "x-section--dark", "label": "Dark"}],
        "text": [{"key": "lead", "classes": "x-lead", "label": "Lead"}],
    },
}
PAGE = {"path": "/content/site/en", "body": {"name": "root", "type": "container", "children": [
    {"name": "intro", "type": "container", "styles": ["section"]}]}}


def make_project(tmp, clientlib_config):
    root = Path(tmp).resolve()  # Project resolves symlinks (/var → /private/var on macOS)
    (root / "project.json").write_text(json.dumps({
        "aem": {"baseUrl": "http://aem", "policiesRoot": "/conf/site/settings/wcm/policies"},
        "package": {"name": "site-home", "group": "site", "version": "2.0"},
        "classPrefix": "x-",
        "clientlib": clientlib_config,
        "components": {"container": {"resourceType": "site/components/container", "policy": "p/1"},
                       "text": {"resourceType": "site/components/text", "policy": "p/2"}},
    }))
    (root / "styles.json").write_text(json.dumps(STYLES))
    (root / "page.json").write_text(json.dumps(PAGE))
    return root


class SpecTest(unittest.TestCase):
    def test_defaults_follow_theme(self):
        spec = clientlib.load_spec({"theme": "acme"})
        self.assertEqual(spec.name, "clientlib-acme")
        self.assertEqual(spec.categories, ("acme.site",))
        self.assertEqual(spec.css_processor, ("default:none", "min:gcc"))
        self.assertEqual(spec.resources_url, "")

    def test_cli_theme_overrides_config(self):
        self.assertEqual(clientlib.load_spec({"theme": "a"}, "b").name, "clientlib-b")

    def test_invalid_input(self):
        for config in ({}, {"theme": "Bad Name"}, {"theme": "1x"}, {"theme": "a", "appsPath": "/content/x"},
                       {"theme": "a", "dependencies": [1]}):
            with self.subTest(config=config), self.assertRaises(ConfigError):
                clientlib.load_spec(config)

    def test_jcr_path_requires_apps_path(self):
        with self.assertRaises(ConfigError):
            clientlib.load_spec({"theme": "a"}).jcr_path

    def test_resources_url_is_proxy_path(self):
        spec = clientlib.load_spec({"theme": "acme", "appsPath": "/apps/acme/clientlibs/"})
        self.assertEqual(spec.jcr_path, "/apps/acme/clientlibs/clientlib-acme")
        self.assertEqual(spec.resources_url, "/etc.clientlibs/acme/clientlibs/clientlib-acme/resources/")

    def test_content_xml(self):
        spec = clientlib.load_spec({"theme": "acme", "dependencies": ["acme.global"],
                                    "jsProcessor": ["default:none", "min:gcc;languageIn=ECMASCRIPT_2015"]})
        root = minidom.parseString(clientlib.content_xml(spec)).documentElement
        self.assertEqual(root.getAttribute("jcr:primaryType"), "cq:ClientLibraryFolder")
        self.assertEqual(root.getAttribute("allowProxy"), "{Boolean}true")
        self.assertEqual(root.getAttribute("categories"), "[acme.site]")
        self.assertEqual(root.getAttribute("dependencies"), "[acme.global]")
        self.assertEqual(root.getAttribute("jsProcessor"), "[default:none,min:gcc;languageIn=ECMASCRIPT_2015]")


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_project(self.tmp.name, {"theme": "acme", "appsPath": "/apps/acme/clientlibs"})
        self.folder = self.root / "build" / "clientlibs" / "clientlib-acme"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra):
        self.assertEqual(cli.main(["clientlib", "--project", str(self.root), *extra]), 0)

    def test_layout_matches_reference(self):
        self.run_cli()
        files = {p.relative_to(self.folder).as_posix() for p in self.folder.rglob("*") if p.is_file()}
        self.assertEqual(files, {
            ".content.xml", "css.txt", "js.txt", "scripts/site.js",
            "styles/index.less", "styles/variables.less", "styles/base.less",
            *(f"styles/design-system/{n}.less" for n in
              ("index", "tokens", "spacing", "grid", "fonts", "typography", "variants")),
            "styles/style_system/index.less", "styles/style_system/x-foundation.less",
            "styles/style_system/x-section.less", "styles/style_system/x-lead.less"})
        self.assertIn("#base=styles\nindex.less", (self.folder / "css.txt").read_text())
        self.assertIn("/etc.clientlibs/acme/clientlibs/clientlib-acme/resources/",
                      (self.folder / "styles/variables.less").read_text())
        index = (self.folder / "styles/style_system/index.less").read_text().splitlines()
        self.assertEqual(index[1:], ['@import "x-foundation.less";', '@import "x-section.less";', '@import "x-lead.less";'])

    def test_rerun_keeps_developer_files_and_picks_up_new_ones(self):
        self.run_cli()
        section = self.folder / "styles/style_system/x-section.less"
        section.write_text(".x-section { color: red; }\n")
        (self.folder / "styles/style_system/x-extra.less").write_text("")
        self.run_cli()
        self.assertEqual(section.read_text(), ".x-section { color: red; }\n")
        self.assertIn('@import "x-extra.less";', (self.folder / "styles/style_system/index.less").read_text())

    def test_less_dir_falls_back_to_generated_clientlib(self):
        project = Project.load(self.root)
        self.assertIsNone(project.less_dir)
        self.run_cli()
        self.assertEqual(Project.load(self.root).less_dir, self.folder / "styles" / "style_system")

    def test_package(self):
        self.run_cli("--package")
        zip_path = self.root / "build" / "site-home-clientlib-acme-2.0.zip"
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            self.assertIn('<filter root="/apps/acme/clientlibs/clientlib-acme"/>',
                          zf.read("META-INF/vault/filter.xml").decode())
        self.assertIn("jcr_root/apps/acme/clientlibs/clientlib-acme/.content.xml", names)
        self.assertIn("jcr_root/apps/acme/clientlibs/clientlib-acme/styles/style_system/x-lead.less", names)


if __name__ == "__main__":
    unittest.main()
