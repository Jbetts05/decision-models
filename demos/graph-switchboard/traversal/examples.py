"""Compile additional published guides and separately authored record journeys."""

import copy
import hashlib
import json
import re

from traversal.synthetic import NOTICE


def extend_examples(graph, queries, oracle, profiles, sections, pack):
    if len({family["id"] for family in pack}) != len(pack) or len({family["guide"] for family in pack}) != len(pack):
        raise ValueError("Additional problem families require unique identifiers and guides.")
    by_vehicle = {profile["key"]: profile for profile in profiles}
    for family in pack:
        prefix = family["guide"]
        document = f"SG-{int(prefix[1:]):02d}"
        pid = "procedure-v42-" + family["id"]
        profile = by_vehicle[family["vehicle"]]
        notice = NOTICE.replace("Model A", profile["model"])
        expected_scope = (f"Fictional {profile['year']} Brand X {profile['model']}, "
                          f"{profile['configuration']} only.")
        if expected_scope not in sections[prefix + ".0"]:
            raise ValueError(f"{document} does not declare the selected vehicle's exact applicability.")
        published = {}

        def add_node(identifier, kind, section, description, **properties):
            graph["nodes"].append({
                "id": identifier, "type": kind, "procedure_id": pid,
                "description": description, "source_reference": f"{document}:1.0:{section}",
                **properties,
            })
            return identifier

        def add_edge(kind, start, end, section, **properties):
            identifier = f"x{prefix[1:]}-{len(graph['edges']):04d}"
            graph["edges"].append({
                "id": identifier, "type": kind, "source": start, "target": end,
                "procedure_id": pid, "source_reference": f"{document}:1.0:{section}",
                **properties,
            })
            return identifier

        entry_section = prefix + ".1"
        entry_text = sections[entry_section]
        first = re.search(r"^Next: (G\d+\.\d+)$", entry_text, re.M)
        if not first:
            raise ValueError(f"{document} entry requires a published next action.")
        add_node(pid, "Procedure", entry_section, family["title"],
                 title=family["title"], version=1, status="published",
                 origin_type="source_authored", entry_criteria=entry_text,
                 publication_date="2026-10-20", synthetic=True, expert_validation=False,
                 source_document=document, source_version="1.0",
                 applicability=sections[prefix + ".0"], safety_metadata=notice,
                 problem_family=family["id"])
        add_edge("APPLIES_TO", pid, profile["vehicle_id"], prefix + ".0")
        for section, body in sections.items():
            if not section.startswith(prefix + "."):
                continue
            header = re.match(r"## G\d+\.\d+ (Action|Handoff|RootCause): (.+)", body)
            if not header:
                continue
            kind, title = header.groups()
            response = re.search(r"^Response: (.+)$", body, re.M)
            if not response:
                raise ValueError(f"{section} requires an authored recipient response.")
            if kind == "RootCause":
                identifier = hashlib.sha256(f"{pid}:{section}".encode()).hexdigest()[:14]
                published[section] = {"target": add_node(
                    identifier, kind, section, title, confirmation_required=True,
                    customer_response=response[1])}
                continue
            state = re.search(r"^State: (.+)$", body, re.M)
            result_type = re.search(r"^Type: (numeric|range|boolean|categorical|observation)$", body, re.M)
            unit = re.search(r"^Unit: (.+)$", body, re.M)
            if not state or not result_type:
                raise ValueError(f"{section} requires its diagnostic state and result type.")
            condition = add_node(
                f"{pid}-{section.lower()}-c", "Condition",
                entry_section if section == first[1] else section,
                state[1], entry=section == first[1],
                entry_criteria=entry_text if section == first[1] else None)
            action = add_node(
                f"{pid}-{section.lower()}-a", "Action", section, title,
                instruction=body, result_type=result_type[1],
                expected_unit=unit[1] if unit else None, handoff=kind == "Handoff",
                safety_metadata=notice, customer_response=response[1])
            published[section] = {
                "target": action, "condition": condition,
                "next": add_edge("NEXT_ACTION", condition, action, section, weight=None),
                "results": {}, "result_type": result_type[1],
            }
        add_edge("ENTRY_POINT", pid, published[first[1]]["condition"], entry_section)
        for section, info in published.items():
            for line in sections[section].splitlines():
                if not line.startswith("| ") or line.startswith("| Outcome |") or line.startswith("| ---"):
                    continue
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if len(cells) != 4:
                    raise ValueError(f"Invalid outcome table in {section}.")
                label, destination, rule, criteria = cells
                target = published[destination]
                root = "condition" not in target
                if label in info["results"] or not criteria:
                    raise ValueError(f"Duplicate or unqualified outcome in {section}.")
                info["results"][label] = add_edge(
                    "RESULT", info["target"], target.get("condition", target["target"]), section,
                    description=label, rule=json.loads(rule),
                    result_type=info["result_type"],
                    selection_criteria=criteria, establishes_finding=root,
                    confirmation_basis=sections[destination] if root else None)

        def add_case(identifier, question, records, expected, **metadata):
            queries.append({
                "id": identifier, "title": family["title"],
                "vehicle_id": profile["vehicle_id"], "vehicle": copy.deepcopy(profile["vehicle"]),
                "question": question, "evidence": copy.deepcopy(records),
                "start_node": published[first[1]]["condition"],
                "category": "problem_journey", "intent": family["id"],
                "split": "authored_problem_examples", **metadata,
            })
            path = []
            for section, outcome in expected["route"]:
                path.extend([published[section]["next"], published[section]["results"][outcome]])
            stop = published[expected["stop"]]
            if "condition" in stop:
                path.append(stop["next"])
            oracle.append({
                "id": identifier, "procedure_id": pid, "status": expected["status"],
                "target": stop["target"], "path": path,
            })

        questions, records, snapshots = [], [], []
        for index, turn in enumerate(family["turns"]):
            questions.append(turn["question"])
            records.extend(turn["records"])
            snapshots.append(("\n\n".join(questions), copy.deepcopy(records)))
            identifier = f"{family['id']}-turn-{index}"
            add_case(
                identifier, "\n\n".join(questions), records, turn["expected"],
                demo=True, journey_id=family["id"], turn=index, turn_count=len(family["turns"]),
                next_case=f"{family['id']}-turn-{index + 1}" if index + 1 < len(family["turns"]) else None)
        for case in family["contrasts"]:
            question, records = copy.deepcopy(snapshots[case["base_turn"]])
            for replacement in case.get("replacements", []):
                matches = [index for index, record in enumerate(records)
                           if record["check"] == replacement["check"]]
                if len(matches) != 1:
                    raise ValueError(f"Contrast replacement must identify one record: {case['id']}")
                records[matches[0]] = replacement
            records.extend(case.get("records", []))
            add_case(f"{family['id']}-{case['id']}", question, records,
                     case["expected"], demo=False)
