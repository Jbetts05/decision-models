"""Load scenario manifests, policy documents and approved question files."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "scenarios"
CHECK_ID = re.compile(r"^[a-z0-9_]{1,48}$")
VERDICTS = ("pass", "fail", "cannot_assess")


class CatalogError(ValueError):
    pass


def scenario_ids():
    return sorted(p.name for p in SCENARIOS.iterdir() if (p / "visits.json").is_file())


def _within(folder, relative):
    path = (folder / relative).resolve()
    if folder.resolve() not in path.parents:
        raise CatalogError(f"Path escapes the scenario folder: {relative}")
    return path


def validate_questions(data, photo_types, campaign):
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list) or not data["checks"]:
        raise CatalogError(f"Campaign {campaign} questions need a non-empty checks list.")
    seen = set()
    for check in data["checks"]:
        if not isinstance(check, dict):
            raise CatalogError(f"Campaign {campaign}: each check must be an object.")
        cid = check.get("id")
        if not isinstance(cid, str) or not CHECK_ID.match(cid) or cid in seen:
            raise CatalogError(f"Campaign {campaign}: invalid or duplicate check id {cid!r}.")
        seen.add(cid)
        for key in ("rule", "requirement", "question", "compliant", "not_compliant"):
            if not isinstance(check.get(key), str) or not check[key].strip():
                raise CatalogError(f"Campaign {campaign} check {cid}: missing {key}.")
        photos = check.get("photos")
        if not isinstance(photos, list) or not photos or len(set(photos)) != len(photos) \
                or any(p not in photo_types for p in photos):
            raise CatalogError(f"Campaign {campaign} check {cid}: photos must be known photo types.")
        if not isinstance(check.get("uses_reference"), bool):
            raise CatalogError(f"Campaign {campaign} check {cid}: uses_reference must be true or false.")
    if not isinstance(data.get("not_checkable", []), list):
        raise CatalogError(f"Campaign {campaign}: not_checkable must be a list.")
    return data


def validate_demo(demo, campaigns, visit_ids):
    if not isinstance(demo, dict) or not all(isinstance(demo.get(k), str) for k in ("store", "audit")):
        raise CatalogError("The demo block needs a store and an audit description.")
    live = demo.get("campaigns")
    if not isinstance(live, list) or not live or len(set(live)) != len(live) or any(c not in campaigns for c in live):
        raise CatalogError("Demo campaigns must be known, distinct campaign ids.")
    cases = demo.get("cases")
    if not isinstance(cases, list) or not cases or len({c.get("visit") for c in cases}) != len(cases):
        raise CatalogError("Demo cases must name distinct visits.")
    for case in cases:
        if case.get("visit") not in visit_ids or not all(isinstance(case.get(k), str) for k in ("title", "summary")):
            raise CatalogError(f"Demo case {case.get('visit')!r} needs a known visit, a title and a summary.")


def demo_view(scenario):
    """The scenario as the web demo shows it: only the live campaigns and the chosen cases, in order."""
    demo = scenario["demo"]
    by_id = {v["id"]: v for v in scenario["visits"]}
    visits = [dict(by_id[c["visit"]], title=c["title"], summary=c["summary"],
                   expected={k: by_id[c["visit"]]["expected"][k] for k in demo["campaigns"]})
              for c in demo["cases"]]
    return dict(scenario, campaigns={k: scenario["campaigns"][k] for k in demo["campaigns"]}, visits=visits)


def load_scenario(scenario_id, demo=False):
    """Load a scenario: the full evaluation set, or with demo=True the curated web demo view."""
    if scenario_id not in scenario_ids():
        raise CatalogError(f"Unknown scenario: {scenario_id}")
    folder = SCENARIOS / scenario_id
    manifest = json.loads((folder / "visits.json").read_text(encoding="utf-8"))
    photo_types = manifest["photo_types"]
    campaigns = {}
    for key, campaign in manifest["campaigns"].items():
        entry = dict(campaign, id=key)
        entry["brief_text"] = _within(folder, campaign["brief"]).read_text(encoding="utf-8")
        if campaign.get("standards"):
            entry["standards_text"] = _within(folder, campaign["standards"]).read_text(encoding="utf-8")
        if campaign.get("reference"):
            entry["reference_path"] = _within(folder, campaign["reference"])
        question_file = folder / "questions" / f"{key}.json"
        if question_file.is_file():
            entry["questions"] = validate_questions(
                json.loads(question_file.read_text(encoding="utf-8")), photo_types, key)
            if any(c["uses_reference"] for c in entry["questions"]["checks"]) and "reference_path" not in entry:
                raise CatalogError(f"Campaign {key} uses a reference image but has none.")
        campaigns[key] = entry
    visits = []
    for visit in manifest["visits"]:
        photos = {p["type"]: _within(folder, f"images/visits/{visit['id']}/{p['type']}.jpg")
                  for p in visit["photos"]}
        if any(p not in photo_types for p in photos):
            raise CatalogError(f"Visit {visit['id']} uses an unknown photo type.")
        if set(visit["expected"]) != set(campaigns) or any(v not in VERDICTS for v in visit["expected"].values()):
            raise CatalogError(f"Visit {visit['id']} needs an expected verdict for every campaign.")
        visits.append(dict(visit, photo_paths=photos))
    validate_demo(manifest.get("demo"), campaigns, {v["id"] for v in visits})
    scenario = {"id": scenario_id, "name": manifest["scenario"], "folder": folder, "note": manifest["note"],
                "photo_types": photo_types, "campaigns": campaigns, "visits": visits, "demo": manifest["demo"]}
    return demo_view(scenario) if demo else scenario


def find_visit(scenario, visit_id):
    for visit in scenario["visits"]:
        if visit["id"] == visit_id:
            return visit
    raise CatalogError(f"Unknown visit: {visit_id}")
