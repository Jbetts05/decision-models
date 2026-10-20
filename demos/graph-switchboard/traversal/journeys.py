"""Source-grounded v4 authoring. Reviewer outcomes never enter public input."""

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from traversal.synthetic import (
    ENTITY_TYPES, RELATION_TYPES, NOTICE, VEHICLE_ID, canonical_hash, dump, write_lines,
)
from traversal.vehicles import expand_vehicles
from traversal.examples import extend_examples

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "traversal" / "source-material"
PACK = ROOT / "docs" / "case-journeys-v4.md"
PROBLEMS = ROOT / "data" / "traversal" / "problem-journeys.json"
VERSION = "4.2.0"


def source_sections(path):
    text = path.read_text(encoding="utf-8")
    return {match[1]: match[0].strip() for match in re.findall(
        r"(^## (G\d+\.\d+)\b.*?)(?=^## |\Z)", text, re.M | re.S
    )}


def released_turns(text):
    """Extract only visible quotes and their document labels before reviewer text."""
    turns = []
    for section in re.split(r"^### Turn \d+:.*$", text, flags=re.M)[1:]:
        visible = section.split("**Reviewer only:**", 1)[0]
        records, questions = [], []
        for match in re.finditer(r"(?:^>.*(?:\n|$))+", visible, re.M):
            label = visible[:match.start()].strip().split("\n\n")[-1].strip()
            quote = " ".join(line.removeprefix("> ").strip()
                             for line in match[0].strip().splitlines())
            if label == "Customer:":
                questions.append(quote)
            else:
                records.append({"check": label.rstrip(":"), "observation": quote})
        if len(questions) != 1:
            raise ValueError("Each journey turn requires one customer question.")
        turns.append((questions[0], records))
    if len(turns) != 4:
        raise ValueError("Each approved journey requires exactly four releases.")
    return turns


def generate():
    nodes, edges, queries, oracle = [], [], [], []
    nodes.append({"id": VEHICLE_ID, "type": "VehicleModel", "make": "Brand X",
                  "model": "Model A", "model_year": 2021, "configuration": "petrol",
                  "fictional": True, "description": NOTICE,
                  "source_reference": "approved-fictional-source-pack-v4:applicability"})
    files = sorted(SOURCES.glob("SG-*.md"))
    if {path.name for path in files} != {
        "SG-01-cylinder-misfire.md", "SG-02-lean-idle.md",
        "SG-03-cabin-airflow.md", "SG-04-vehicle-applicability.md",
        "SG-05-slow-cranking.md", "SG-06-intermittent-charging.md",
        "SG-07-idle-cooling.md", "SG-08-warm-cooling-air.md", "SG-09-power-window.md",
        "SG-10-weak-washer-flow.md", "SG-11-patchy-demister.md",
    }:
        raise ValueError("Expected ten problem guides and the vehicle-applicability supplement.")
    sections = {}
    source_hashes = {}
    for path in files:
        sections.update(source_sections(path))
        source_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()

    def node(identifier, kind, pid, section, description, **props):
        nodes.append({"id": identifier, "type": kind, "procedure_id": pid,
                      "description": description, "source_reference": f"SG-0{section[1]}:1.0:{section}",
                      **props})
        return identifier

    def edge(kind, start, end, pid, section, **props):
        identifier = f"j{len(edges):04d}"
        edges.append({"id": identifier, "type": kind, "source": start, "target": end,
                      "procedure_id": pid, "source_reference": f"SG-0{section[1]}:1.0:{section}",
                      **props})
        return identifier

    definitions = [
        ("misfire", "Rough running with a current cylinder-one misfire finding", "G1", [
            ("coil", "Review the recorded coil comparison", "2", False),
            ("plug", "Review the recorded plug comparison", "3", False),
            ("referral", "Request workshop review of unresolved misfire", "5", True),
        ], {"coil": ("Cylinder-one ignition-coil fault", "4"),
            "plug": ("Cylinder-one spark-plug fault", "4")}),
        ("lean", "Rough idle with a current lean-mixture finding", "G2", [
            ("pressure", "Review the current RP-IDLE pressure record", "2", False),
            ("localisation", "Review the complete joint J localisation record", "3", False),
            ("pressure-referral", "Request workshop review of out-of-band pressure", "5", True),
            ("referral", "Request workshop review of non-localising evidence", "5", True),
        ], {"joint": ("Unmetered-air leak at intake joint J", "4")}),
        ("airflow", "Missing cabin airflow or missing fan speeds", "G3", [
            ("pattern", "Review the current workshop fan-stage record", "2", False),
            ("comparison", "Review the completed CP-FAN control-unit comparison", "3", False),
            ("none-referral", "Request workshop review of complete airflow loss", "2", True),
            ("temperature-referral", "Refer the temperature-only complaint outside this guide", "2", True),
            ("pattern-referral", "Request workshop review of an unhandled fan-stage pattern", "2", True),
            ("referral", "Request workshop review of unresolved low-speed airflow loss", "3", True),
        ], {"controller": ("Original low-speed fan control-unit fault", "4")}),
    ]
    catalog = {}
    findings = {
        ("misfire", "plug"): "The completed coil-only comparison leaves the misfire on cylinder one.",
        ("misfire", "referral"): "Neither completed ignition-component comparison localises the misfire.",
        ("lean", "localisation"): "The current RP-IDLE pressure record is within the source reference band.",
        ("lean", "pressure-referral"): "The current RP-IDLE pressure record is outside the source reference band.",
        ("lean", "referral"): "The complete joint J comparison fails the required repeatable pattern.",
        ("airflow", "comparison"): "Current workshop record: stages 1-3 have no airflow; stage 4 has airflow.",
        ("airflow", "none-referral"): "The current workshop record shows no airflow at any fan stage.",
        ("airflow", "temperature-referral"): "Airflow is present at every stage; the remaining complaint is temperature.",
        ("airflow", "pattern-referral"): "The complete fan-stage pattern is outside this guide's supported comparison.",
        ("airflow", "referral"): "The complete CP-FAN comparison does not localise the low-speed airflow fault.",
    }
    for key, title, prefix, actions, roots in definitions:
        pid = "procedure-v4-" + key
        node(pid, "Procedure", pid, prefix + ".1", title,
             title=title, version=4, status="published", origin_type="source_authored",
             entry_criteria=sections[prefix + ".1"],
             publication_date="2026-10-20", synthetic=True, expert_validation=False,
             source_document=f"SG-0{prefix[1]}", source_version="1.0",
             applicability="Fictional 2021 Brand X Model A petrol only.", safety_metadata=NOTICE)
        edge("APPLIES_TO", pid, VEHICLE_ID, pid, prefix + ".0")
        info = {"pid": pid, "actions": {}, "conditions": {}, "next": {}, "roots": {}, "results": {}}
        for index, (name, description, section, handoff) in enumerate(actions):
            ref = prefix + "." + section
            condition = node(f"{pid}-c-{name}", "Condition", pid, ref,
                             title if index == 0 else findings[key, name],
                             entry=index == 0,
                             entry_criteria=sections[prefix + ".1"] if index == 0 else None)
            action = node(f"{pid}-a-{name}", "Action", pid, ref, description,
                          instruction=sections[ref], result_type="observation" if handoff else "categorical",
                          expected_unit=None, handoff=handoff, safety_metadata=NOTICE)
            info["conditions"][name], info["actions"][name] = condition, action
            info["next"][name] = edge("NEXT_ACTION", condition, action, pid, ref, weight=None)
            if index == 0:
                info["entry"] = condition
                edge("ENTRY_POINT", pid, condition, pid, prefix + ".1")
        for name, (description, section) in roots.items():
            info["roots"][name] = node(
                hashlib.sha256(f"v4:{pid}:{name}".encode()).hexdigest()[:14],
                "RootCause", pid, prefix + "." + section, description, confirmation_required=True)
        catalog[key] = info

    def result(key, action, label, target, section, criteria):
        info = catalog[key]
        root = target.startswith("@")
        identifier = edge(
            "RESULT", info["actions"][action],
            info["roots"][target[1:]] if root else info["conditions"][target],
            info["pid"], section, result_type="categorical", description=label,
            selection_criteria=criteria, rule={"operator": "eq", "value": label},
            establishes_finding=root, confirmation_basis=sections[section] if root else None)
        info["results"][action, label] = (identifier, target)

    result("misfire", "coil", "misfire follows coil", "@coil", "G1.2",
           "Complete current-job coil-only comparison: P0301 baseline; misfire follows the coil to the donor; return check reproduces P0301. All controls in G1.2 required.")
    result("misfire", "coil", "misfire remains on cylinder one", "plug", "G1.2",
           "Valid current-job coil-only comparison: P0301 persists with coils exchanged and after return; plugs unchanged. A plug check need not have been done yet.")
    result("misfire", "plug", "misfire follows plug", "@plug", "G1.3",
           "Complete plug-only comparison after the valid coil check: P0301 baseline; misfire follows the original plug to donor cylinder; returning plugs reproduces P0301; coils original throughout.")
    result("misfire", "plug", "misfire remains on cylinder one", "referral", "G1.3",
           "Completed valid plug comparison leaves the misfire on cylinder one. Missing or incomplete comparisons are NOT this result.")
    result("lean", "pressure", "applicable pressure inside reference band", "localisation", "G2.2",
           "Current job RP-IDLE record, declared unit, 250-400 kPa inclusive. Explicitly permitted conversion: 1 bar = 100 kPa. Old/key-on records are not applicable.")
    result("lean", "pressure", "applicable pressure outside reference band", "pressure-referral", "G2.2",
           "Complete current-job RP-IDLE record outside 250-400 kPa inclusive, with declared kPa or bar. A missing unit is clarification, not this result.")
    result("lean", "localisation", "repeatable localisation at joint J", "@joint", "G2.3",
           "All complete same-job RP-IDLE records: A >+15%, B in [-5,+5]%, A2 >+15%, control C >+15%, no other diagnostic changes, pressure within band throughout.")
    result("lean", "localisation", "complete comparison does not localise", "referral", "G2.3",
           "All required current-job comparison observations and prerequisites supplied, but required pattern fails. In particular A2 of +4% fails recurrence. Missing A2 or C instead requires clarification.")
    for label, target, criteria in [
        ("low-speed stages absent", "comparison", "Current WORKSHOP record: no airflow at 1,2,3; airflow present at 4. A customer complaint alone is not the workshop record."),
        ("all stages absent", "none-referral", "Complete current workshop record: no airflow at any of 1,2,3,4."),
        ("temperature complaint only", "temperature-referral", "Current workshop record: airflow at all stages; remaining complaint concerns air temperature."),
        ("other complete stage pattern", "pattern-referral", "Complete current workshop record with another speed pattern, not incomplete or contradictory."),
    ]:
        result("airflow", "pattern", label, target, "G3.2", criteria)
    result("airflow", "comparison", "controlled fault follows original unit", "@controller", "G3.3",
           "Complete CP-FAN comparison: supply/ground/connection prerequisites pass throughout; only low-speed control unit changes; A original 1-3 absent/4 present, B reference all present, A2 original pattern recurs.")
    result("airflow", "comparison", "complete comparison is non-localising", "referral", "G3.3",
           "Completed otherwise valid CP-FAN comparison fails the required A-B-A2 pattern. Missing return or prerequisite record instead requires clarification.")

    pack = PACK.read_text(encoding="utf-8")
    blocks = re.split(r'^## Journey \d+:', pack, flags=re.M)[1:]
    routes = {
        "misfire": [
            ([], "clarify", None), ([], "next_action", "coil"),
            ([("coil", "misfire remains on cylinder one")], "next_action", "plug"),
            ([("coil", "misfire remains on cylinder one"), ("plug", "misfire follows plug")], "root_cause", "@plug"),
        ],
        "lean": [
            ([], "clarify", "pressure"),
            ([("pressure", "applicable pressure inside reference band")], "next_action", "localisation"),
            ([("pressure", "applicable pressure inside reference band")], "clarify", "localisation"),
            ([("pressure", "applicable pressure inside reference band"), ("localisation", "complete comparison does not localise")], "next_action", "referral"),
        ],
        "airflow": [
            ([], "next_action", "pattern"),
            ([("pattern", "low-speed stages absent")], "next_action", "comparison"),
            ([("pattern", "low-speed stages absent")], "clarify", "comparison"),
            ([("pattern", "low-speed stages absent"), ("comparison", "controlled fault follows original unit")], "root_cause", "@controller"),
        ],
    }

    def answer_for(identifier, key, route, status, stop):
        info, path = catalog[key], []
        for action, label in route:
            path.extend([info["next"][action], info["results"][action, label][0]])
        target = None
        if stop:
            target = info["roots"][stop[1:]] if stop.startswith("@") else info["actions"][stop]
            if not stop.startswith("@"):
                path.append(info["next"][stop])
        return {"id": identifier, "procedure_id": info["pid"], "status": status,
                "target": target, "path": path}

    for (key, _, _, _, _), block in zip(definitions, blocks, strict=True):
        title = block.split("\n", 1)[0].strip().strip('"')
        job = block.split("### Visible job-card context\n", 1)[1].split("### Turn", 1)[0].strip()
        turns = released_turns(block.split("### Contrast:", 1)[0])
        evidence = [{"check": "Job card", "observation": job}]
        questions = []
        for index, (question, records) in enumerate(turns):
            evidence.extend(records)
            questions.append(question)
            identifier = f"{key}-turn-{index}"
            query = {
                "id": identifier, "title": title, "journey_id": key, "turn": index, "turn_count": 4,
                "next_case": f"{key}-turn-{index + 1}" if index < 3 else None,
                "vehicle_id": VEHICLE_ID, "vehicle": {"make": "Brand X", "model": "Model A",
                    "year": 2021, "configuration": "petrol"},
                "question": "\n\n".join(questions), "evidence": copy.deepcopy(evidence),
                "start_node": catalog[key]["entry"], "demo": True, "category": "staged_journey",
                "intent": "customer_and_workshop_records", "split": "demonstration",
            }
            queries.append(query)
            route, status, stop = routes[key][index]
            oracle.append(answer_for(identifier, key, route, status, stop))

    contrast = copy.deepcopy(next(q for q in queries if q["id"] == "misfire-turn-1"))
    contrast.update(id="misfire-both-codes", demo=False, next_case=None, turn_count=1, turn=0)
    record = contrast["evidence"][-1]
    record["observation"] = "Complaint reproduced at idle. Active fault list: P0301 and P0171. No procedure priority recorded."
    queries.append(contrast)
    oracle.append(answer_for(contrast["id"], "misfire", [], "clarify", None))
    contrast = copy.deepcopy(next(q for q in queries if q["id"] == "lean-turn-3"))
    contrast.update(id="lean-recurrence", demo=False, next_case=None, turn_count=1, turn=0)
    contrast["evidence"][-1]["observation"] = contrast["evidence"][-1]["observation"].replace("+4%", "+23%")
    queries.append(contrast)
    oracle.append(answer_for(contrast["id"], "lean", [
        ("pressure", "applicable pressure inside reference band"),
        ("localisation", "repeatable localisation at joint J")], "root_cause", "@joint"))
    contrast = copy.deepcopy(next(q for q in queries if q["id"] == "airflow-turn-0"))
    contrast.update(id="airflow-temperature-only", demo=False, next_case=None, turn_count=1, turn=0,
                    question="Air comes out strongly on every setting. It just stays warm when I ask for cooling. Is the old resistor advice relevant?")
    queries.append(contrast)
    oracle.append(answer_for(contrast["id"], "airflow", [], "unsupported", None))
    graph = {"schema_version": 1, "dataset_version": VERSION, "synthetic": True,
             "nodes": nodes, "edges": edges}
    profiles = expand_vehicles(
        graph, queries, oracle, sections,
        (SOURCES / "SG-04-vehicle-applicability.md").read_text(encoding="utf-8"),
    )
    for query in queries:
        if query["category"] == "vehicle_applicability":
            query["demo"] = False
    problems = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    extend_examples(graph, queries, oracle, profiles, sections, problems)
    manifest = {
        "dataset_version": VERSION, "generator": "traversal.journeys.generate",
        "graph_sha256": canonical_hash(graph), "queries_sha256": canonical_hash(queries),
        "oracle_sha256": canonical_hash(oracle), "nodes": dict(Counter(n["type"] for n in nodes)),
        "relationships": dict(Counter(e["type"] for e in edges)), "queries": len(queries),
        "demonstrations": sum(q.get("demo", False) and q.get("turn", 0) == 0 for q in queries),
        "journey_turns": sum(q.get("demo", False) for q in queries),
        "adversarial_evaluation": sum(not q.get("demo", False) for q in queries),
        "problem_families": 10,
        "applicability_evaluation": {
            "cases": sum(q["category"] == "vehicle_applicability" for q in queries),
            "vehicles": len(profiles), "published_procedures": 30,
            "matched_pressure_groups": 2, "independent_test_set": False,
            "matched_order_pattern_cases": 6, "variant_negative_paths": 6,
            "model_entry_selection": "Entry selection is evaluated separately from corpus construction; the application records its workflow per run.",
        },
        "sources": source_hashes, "journey_pack_sha256": hashlib.sha256(PACK.read_bytes()).hexdigest(),
        "problem_pack_sha256": hashlib.sha256(PROBLEMS.read_bytes()).hexdigest(),
        "provenance": {"graph": "Derived from ten fictional diagnostic guides and an explicit vehicle-variant source schedule.",
                       "expert_validation": False, "external_vehicle_data": False,
                       "oracle": "Reviewer-authored source-linked paths, not model-scored ground truth."},
        "review": {
            "model": "claude-opus-5.5", "verdict": "Historical v4.1.1 only: conditionally fit after four blocking findings were corrected. Not a review of the expanded corpus.",
            "scope": "Historical v4.1.1 review only: three original families and vehicle variants. The seven new v4.2.0 families have not received this model review.",
            "change_policy": "Freeze sources and artifact hashes. Model failures alone do not justify changing evidence or expected outcomes.",
        },
        "prior_versions": [
            {"version": "4.2.0-preflight", "published": False,
             "graph_sha256": "05a2ad4a165f5eab961b14b4790811e3200f04458d15f4264d93521be570611f",
             "queries_sha256": "e13bc0b6b287664b914773617ef055b031fd65c918a521b85dd6b7f0fa537546",
             "oracle_sha256": "bd2bead6c79ad3e87696cfb713358787c4d57ebbe370f86fc4abaa54c45a41ff",
             "correction": "New procedures inherited a Model A safety notice. The final notice names each actual applicable vehicle; no diagnostic source, public input, branch rule or expected path changed."},
            {"version": "4.1.2", "published": True,
             "graph_sha256": "190d0dd03193a3d3e264d80a8b2bfe82c6d57d54468aab20d263ed34fec33a41",
             "queries_sha256": "e603d5946b06add90d89f5aa3a804b993b9d6f17be32824b7bd4ca9cd047b85b",
             "oracle_sha256": "e8004df1eef40bc031da106100dc766ce0c5967057c68c453183222f29889f79"},
            {"version": "4.1.1", "published": True,
             "graph_sha256": "640b47bb0c2ffb92c416f5ec665af4b8fb4489400d88b715240e44103e4f7a36",
             "queries_sha256": "53bdc88a87e3d43c6f5d7d0541f7f24be1514150b0fe37bf9e3ae743c53bcd1b",
             "oracle_sha256": "e8004df1eef40bc031da106100dc766ce0c5967057c68c453183222f29889f79"},
            {"version": "4.0.0", "published": True,
             "graph_sha256": "7d733d6a09bb4c95944ad8e80622105e69f5f5ada19a6cb4ce3953e04e6cb311",
             "queries_sha256": "d2fd7f5a9e31b74f982d8f3f8499654c59acaf0064d6cc0568f75a44c1dc7390",
             "oracle_sha256": "896ebcbd68bb25f7b3f9f3a8bca454e6213c2217a6d2db7419c379923b306397"},
            {"version": "4.1.0", "published": False,
             "graph_sha256": "dcaf146a80416064770b76191bc182d37f4c8bb431b6737dc239af62ce45a423",
             "queries_sha256": "3856a110e30f0753697c7b00fc3675deadffcd0c6edb0b8318c0f003bc2b700e",
             "oracle_sha256": "6c84329b8de6e02d99541be33f3a5a75660cf7b8998deff0717bddf38b6e02fd"},
        ],
        "input_revision": {
            "reason": "User-requested diagnostic variety, not a response to model accuracy.",
            "changes": "Seven independently authored fictional problem families; repeated applicability cases move into the evaluation picker.",
            "unchanged": "All 87 historical public inputs, source rules, graph nodes/edges and expected paths; only their demo presentation flag changes.",
        },
        "comparison_compatibility": "v4.2.0 adds entry candidates and new authored families. Historical accuracy/timing results are not comparable and do not establish performance on this expanded graph.",
        "limitations": ["All Brand X vehicles, procedures and reference values in this dataset are fictional; review supplied records only, not real vehicle work.",
                       "Ten fictional vehicles and thirty-seven procedures; not manufacturer or expert-validated guidance.",
                       "Thirty procedures are correlated variants of three families; seven additional families each have one explicitly applicable vehicle. There are ten diagnostic families, not thirty-seven independent ones.",
                       "Matched vehicle cases are authored counterfactuals, not independent real workshop jobs or a held-out accuracy benchmark.",
                       "Numeric limits and controlled comparison criteria are invented.",
                       "INDICATES is supported by the schema but not invented where the sources do not need it."],
    }
    validate(graph, queries, oracle)
    return graph, queries, oracle, manifest


def validate(graph, queries, oracle):
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {e["id"]: e for e in graph["edges"]}
    if len(nodes) != len(graph["nodes"]) or len(edges) != len(graph["edges"]):
        raise ValueError("Duplicate source-derived graph IDs.")
    if set(n["type"] for n in nodes.values()) != ENTITY_TYPES:
        raise ValueError("Unexpected source-derived entity types.")
    for edge in edges.values():
        if (edge["type"] not in RELATION_TYPES
                or edge["source"] not in nodes or edge["target"] not in nodes):
            raise ValueError("Unknown relationship type or endpoint.")
        if (nodes[edge["source"]]["type"], nodes[edge["target"]]["type"]) not in RELATION_TYPES[edge["type"]]:
            raise ValueError("Invalid source-derived relationship.")
        if not edge.get("source_reference"):
            raise ValueError("Missing source provenance.")
        if (edge["procedure_id"] != nodes[edge["source"]].get("procedure_id")
                or (edge["type"] != "APPLIES_TO"
                    and nodes[edge["target"]].get("procedure_id") != edge["procedure_id"])):
            raise ValueError("Cross-procedure relationship.")
        if edge["type"] == "NEXT_ACTION" and edge.get("weight") is not None:
            raise ValueError("Source pack supplies no empirical weights.")
    if (len({q["id"] for q in queries}) != len(queries)
            or len({a["id"] for a in oracle}) != len(oracle)
            or {q["id"] for q in queries} != {a["id"] for a in oracle}):
        raise ValueError("Journey and oracle identifiers disagree.")
    outgoing = {identifier: [e for e in edges.values() if e["source"] == identifier]
                for identifier in nodes}
    vehicles = {node["id"]: node for node in nodes.values() if node["type"] == "VehicleModel"}
    identities = [(node["make"], node["model"], node["model_year"], node["configuration"])
                  for node in vehicles.values()]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate vehicle applicability identity.")
    for node in nodes.values():
        if not node.get("source_reference"):
            raise ValueError("Missing source provenance.")
        if node["type"] != "VehicleModel":
            owner = nodes.get(node.get("procedure_id"))
            if (not owner or owner["type"] != "Procedure"
                    or (node["type"] == "Procedure" and node["procedure_id"] != node["id"])):
                raise ValueError("Invalid owning procedure.")
        links = outgoing[node["id"]]
        if node["type"] == "Condition" and (len(links) != 1 or links[0]["type"] != "NEXT_ACTION"):
            raise ValueError("Condition requires its published mandatory continuation.")
        if node["type"] == "Action":
            if node.get("handoff") and links:
                raise ValueError("Referral cannot invent a subsequent cause.")
            if not node.get("handoff") and (len(links) < 2 or any(e["type"] != "RESULT" for e in links)):
                raise ValueError("Action requires published result choices.")
        if node["type"] == "RootCause":
            incoming = [e for e in edges.values() if e["target"] == node["id"]]
            if (links or not incoming or not node.get("confirmation_required")
                    or any(not e.get("establishes_finding") or not e.get("confirmation_basis") for e in incoming)):
                raise ValueError("RootCause requires affirmative source confirmation.")
    visited, active = set(), set()

    def visit(identifier):
        if identifier in active:
            raise ValueError("Source-derived graph contains a cycle.")
        if identifier in visited:
            return
        active.add(identifier)
        for edge in outgoing[identifier]:
            visit(edge["target"])
        active.remove(identifier)
        visited.add(identifier)

    for node in nodes.values():
        if node["type"] == "Procedure":
            links = outgoing[node["id"]]
            if (node.get("status") != "published" or not node.get("version")
                    or sum(e["type"] == "ENTRY_POINT" for e in links) != 1
                    or sum(e["type"] == "APPLIES_TO" for e in links) != 1):
                raise ValueError("Procedure lacks publication or applicability.")
            visit(node["id"])
    if visited != set(nodes):
        raise ValueError("Unreachable source-derived node.")
    for q, a in zip(queries, oracle, strict=True):
        if q["id"] != a["id"]:
            raise ValueError("Journey and oracle ordering disagree.")
        current = q["start_node"]
        if a["target"] is not None:
            vehicle = vehicles.get(q["vehicle_id"])
            if (vehicle is None or q["vehicle"] != {
                    "make": vehicle["make"], "model": vehicle["model"],
                    "year": vehicle["model_year"], "configuration": vehicle["configuration"]}):
                raise ValueError("Resolved fixture has inconsistent visible vehicle context.")
            entries = [edge for edge in edges.values() if edge["type"] == "ENTRY_POINT"
                       and edge["target"] == current]
            if (len(entries) != 1 or entries[0]["source"] != a["procedure_id"]
                    or not any(edge["type"] == "APPLIES_TO"
                               and edge["source"] == a["procedure_id"]
                               and edge["target"] == q["vehicle_id"] for edge in edges.values())):
                raise ValueError("Expected entry violates vehicle applicability.")
        for identifier in a["path"]:
            edge = edges[identifier]
            if edge["source"] != current or edge["procedure_id"] != a["procedure_id"]:
                raise ValueError("Non-contiguous source-derived path.")
            current = edge["target"]
        if a["target"] is not None and a["target"] != current:
            raise ValueError("Incorrect source-derived target.")
        if a["target"] and nodes[current]["type"] != ("RootCause" if a["status"] == "root_cause" else "Action"):
            raise ValueError("Incorrect terminal semantics.")
        if a["status"] in {"clarify", "unsupported"} and a["target"] is None and a["path"]:
            raise ValueError("Unresolved entry cannot have a path.")


def save(directory):
    graph, queries, oracle, manifest = generate()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    dump(directory / "graph.json", graph)
    write_lines(directory / "queries.jsonl", queries)
    write_lines(directory / "oracle.jsonl", oracle)
    dump(directory / "manifest.json", manifest)
    return manifest
