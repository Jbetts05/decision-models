"""Keep the catalogue and colleague-facing entry points portable."""

import json
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


DEMO = Path(__file__).resolve().parents[1]
ROOT = DEMO.parents[1]


class RepositoryTests(unittest.TestCase):
    def test_current_guides_have_resolvable_local_links(self):
        guides = [
            ROOT / "README.md",
            ROOT / "docs" / "proposals" / "live-vision.md",
            DEMO / "README.md",
            DEMO / "docs" / "development.md",
            DEMO / "docs" / "deployment.md",
            DEMO / "docs" / "graph-switchboard-history.md",
        ]
        for guide in guides:
            for link in re.findall(r"\]\(([^)\s]+)\)", guide.read_text(encoding="utf-8")):
                if "://" in link or link.startswith("#"):
                    continue
                with self.subTest(guide=guide.name, link=link):
                    self.assertTrue((guide.parent / link.split("#", 1)[0]).exists())

    def test_svg_is_self_contained_accessible_and_reduced_motion_safe(self):
        source = (DEMO / "docs" / "images" / "overview.svg").read_text(encoding="utf-8")
        svg = ET.fromstring(source)
        namespace = "{http://www.w3.org/2000/svg}"
        self.assertEqual(svg.tag, namespace + "svg")
        self.assertEqual(svg.attrib["role"], "img")
        ids = {element.get("id") for element in svg.iter()}
        for label in svg.attrib["aria-labelledby"].split():
            self.assertIn(label, ids)
        self.assertIsNotNone(svg.find(namespace + "title"))
        self.assertIsNotNone(svg.find(namespace + "desc"))
        self.assertIn("prefers-reduced-motion: reduce", source)
        self.assertIn("animation: none", source)
        self.assertNotRegex(source, r"<(?:script|foreignObject|image)\b")
        for element in svg.iter():
            for attribute, value in element.attrib.items():
                if attribute.endswith("href"):
                    self.assertTrue(value.startswith("#"), value)

    def test_editable_artwork_keeps_visible_text_dimensions(self):
        diagram = json.loads((DEMO / "docs" / "images" / "overview.excalidraw").read_text())
        self.assertEqual(diagram["type"], "excalidraw")
        ids = [element["id"] for element in diagram["elements"]]
        self.assertEqual(len(ids), len(set(ids)))
        for element in diagram["elements"]:
            if element["type"] == "text":
                self.assertGreater(element["width"], 0)
                self.assertGreater(element["height"], 0)
                self.assertEqual(element["strokeColor"], "#000000")

    def test_local_database_project_keeps_existing_volume_identity(self):
        compose = (DEMO / "compose.yaml").read_text()
        self.assertTrue(compose.startswith("name: decision-models\n"))
        self.assertIn("traversal-age:/var/lib/postgresql/data", compose)

    def test_git_preserves_frozen_source_and_authoring_pack_bytes(self):
        attributes = (ROOT / ".gitattributes").read_text()
        self.assertIn("demos/graph-switchboard/data/traversal/** -text", attributes)
        self.assertIn("demos/graph-switchboard/docs/case-journeys-v4.md -text", attributes)

    def test_deployment_requires_the_owners_azure_target(self):
        script = (DEMO / "infra" / "deploy.ps1").read_text()
        for name in ("SubscriptionId", "FoundryResourceGroup", "FoundryAccount"):
            self.assertIn(f"[Parameter(Mandatory)][string]${name}", script)
        template = (DEMO / "infra" / "application.bicep").read_text()
        self.assertRegex(template, r"(?m)^param foundryEndpoint string$")


if __name__ == "__main__":
    unittest.main()
