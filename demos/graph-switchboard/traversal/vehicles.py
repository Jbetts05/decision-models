"""Source-scheduled vehicle variants and paired applicability evaluation cases."""

import copy
import re

from traversal.synthetic import VEHICLE_ID


def vehicle_profiles(text):
    rows = []
    for line in text.splitlines():
        if not re.match(r"\| [a-j]\d\d \|", line):
            continue
        values = [value.strip() for value in line.strip("|").split("|")]
        if len(values) != 12:
            raise ValueError("Vehicle schedule requires twelve columns.")
        key, model, year, configuration, cylinder, donor, order, low, high, joint, missing, working = values
        profile = {
            "key": key, "model": model, "year": int(year), "configuration": configuration,
            "cylinder": int(cylinder), "donor": int(donor), "order": order,
            "low": int(low), "high": int(high), "joint": joint,
            "missing_stages": missing, "working_stages": working,
        }
        if (order not in {"coil-first", "plug-first"} or not 0 < profile["low"] < profile["high"]
                or profile["cylinder"] not in range(1, 5) or profile["donor"] not in range(1, 5)
                or profile["cylinder"] == profile["donor"]
                or (missing, working) not in {("1-3", "4"), ("1-2", "3-4")}):
            raise ValueError("Invalid vehicle-specific diagnostic schedule.")
        rows.append(profile)
    if len(rows) != 10 or len({row["key"] for row in rows}) != 10:
        raise ValueError("Expected ten uniquely keyed vehicle configurations.")
    identities = {(row["model"], row["year"], row["configuration"]) for row in rows}
    if len(identities) != 10:
        raise ValueError("Duplicate vehicle applicability.")
    if rows[0] != {
        "key": "a21", "model": "Model A", "year": 2021, "configuration": "petrol",
        "cylinder": 1, "donor": 2, "order": "coil-first", "low": 250, "high": 400,
        "joint": "J", "missing_stages": "1-3", "working_stages": "4",
    }:
        raise ValueError("The original staged journeys require the unchanged a21 schedule.")
    return rows


def expand_vehicles(graph, queries, oracle, sections, source_text):
    profiles = vehicle_profiles(source_text)
    base_nodes, base_edges = copy.deepcopy(graph["nodes"]), copy.deepcopy(graph["edges"])
    words = {1: "one", 2: "two", 3: "three", 4: "four"}
    for profile in profiles:
        key = profile["key"]
        profile["vehicle_id"] = (VEHICLE_ID if key == "a21"
                                 else f"vehicle-brandx-{profile['model'].lower().replace(' ', '')}-{profile['year']}")
        profile["vehicle"] = {
            "make": "Brand X", "model": profile["model"], "year": profile["year"],
            "configuration": profile["configuration"],
        }
        if key == "a21":
            continue
        ids = {node["id"]: node["id"] + "-" + key for node in base_nodes}
        ids[VEHICLE_ID] = profile["vehicle_id"]
        ids.update({edge["id"]: edge["id"] + "-" + key for edge in base_edges})
        midpoint = (profile["low"] + profile["high"]) / 2
        substitutions = {
            "2021 Brand X Model A": f"{profile['year']} Brand X {profile['model']}",
            "Model A": profile["model"], "petrol": profile["configuration"],
            "P03010": f"P030{profile['cylinder']}0",
            "P0301": f"P030{profile['cylinder']}", "P0302": f"P030{profile['donor']}",
            "Cylinder-one": "Cylinder-" + words[profile["cylinder"]],
            "cylinder-one": "cylinder-" + words[profile["cylinder"]],
            "cylinder one": "cylinder " + words[profile["cylinder"]],
            "250": str(profile["low"]), "400": str(profile["high"]),
            "3.1 bar": f"{midpoint / 100:g} bar", "310 kPa": f"{midpoint:g} kPa",
            "joint J": "joint " + profile["joint"],
            "Joint J": "Joint " + profile["joint"],
            "J isolated": profile["joint"] + " isolated",
            "J in its": profile["joint"] + " in its",
            "to J.": "to " + profile["joint"] + ".",
            '"3.1"': f'"{midpoint / 100:g}"',
        }
        pattern = re.compile("|".join(re.escape(value) for value in sorted(substitutions, key=len, reverse=True)))

        def clone(value):
            if isinstance(value, str):
                return ids[value] if value in ids else pattern.sub(lambda match: substitutions[match[0]], value)
            if isinstance(value, list):
                return [clone(item) for item in value]
            if isinstance(value, dict):
                return {name: clone(item) for name, item in value.items()}
            return value

        nodes, edges = clone(base_nodes), clone(base_edges)
        for item in nodes + edges:
            item["source_reference"] += f"; SG-04:1.0:G4.1:{key}"
        vehicle = next(node for node in nodes if node["type"] == "VehicleModel")
        vehicle.update(model_year=profile["year"], **{
            name: value for name, value in profile["vehicle"].items() if name != "year"
        })
        template = {
            **profile, "baseline_code": f"P030{profile['cylinder']}",
            "donor_code": f"P030{profile['donor']}",
        }
        for node in nodes:
            if node["type"] == "Procedure":
                node["version"] = "4.1"
                node["applicability_source"] = f"SG-04:1.0:G4.1:{key}"
                node["entry_criteria"] += (
                    "\n\n" + sections["G4.0"] + "\n\n"
                    + (sections["G4.2"] if "-misfire" in node["id"] else
                       sections["G4.5"] if "-lean" in node["id"] else "")
                )
        by_id = {node["id"]: node for node in nodes}
        if profile["order"] == "plug-first":
            pid = ids["procedure-v4-misfire"]
            coil, plug = ids["procedure-v4-misfire-c-coil"], ids["procedure-v4-misfire-c-plug"]
            by_id[coil].update(entry=False, entry_criteria=None,
                               description="The complete plug-only comparison leaves the misfire on the original cylinder.")
            by_id[plug].update(entry=True, description=by_id[pid]["description"],
                               entry_criteria=by_id[pid]["entry_criteria"])
            by_id[ids["procedure-v4-misfire-a-plug"]]["instruction"] = sections["G4.3"].format(**template)
            by_id[ids["procedure-v4-misfire-a-coil"]]["instruction"] = sections["G4.4"].format(**template)
            referral = ids["procedure-v4-misfire-c-referral"]
            for edge in edges:
                if edge["procedure_id"] != pid:
                    continue
                if edge["type"] == "ENTRY_POINT":
                    edge["target"] = plug
                elif edge["type"] == "RESULT":
                    action = by_id[edge["source"]]
                    edge["selection_criteria"] = (
                        f"Take only the '{edge['description']}' outcome under this complete review:\n"
                        + action["instruction"]
                    )
                    if edge["target"] == plug:
                        edge["target"] = referral
                    elif edge["target"] == referral:
                        edge["target"] = coil
                    if edge.get("establishes_finding"):
                        edge["confirmation_basis"] = action["instruction"]
                    edge["source_reference"] += "; SG-04:1.0:G4.2-G4.4"
        for node in nodes:
            if node["type"] == "Condition" and node.get("entry"):
                node["entry_criteria"] = by_id[node["procedure_id"]]["entry_criteria"]
            if node["id"] == ids["procedure-v4-airflow-a-pattern"]:
                node["instruction"] = sections["G4.6"].format(**template)
            elif node["id"] == ids["procedure-v4-airflow-a-comparison"]:
                node["instruction"] = sections["G4.7"].format(**template)
            elif node["type"] == "Action" and node["procedure_id"] == ids["procedure-v4-airflow"]:
                node["instruction"] = (
                    "Request qualified workshop review of this unresolved finding. "
                    "No component cause is established and no further diagnostic transition "
                    "is published from this referral. " + (
                        sections["G4.7"] if node["id"] == ids["procedure-v4-airflow-a-referral"]
                        else sections["G4.6"]
                    ).format(**template)
                )
            elif node["id"] == ids["procedure-v4-airflow-c-comparison"]:
                node["description"] = (
                    f"Current workshop record: no airflow at {profile['missing_stages']}; "
                    f"airflow at {profile['working_stages']}."
                )
        for edge in edges:
            if edge["type"] == "RESULT" and edge["procedure_id"] == ids["procedure-v4-airflow"]:
                edge["selection_criteria"] = (
                    f"Take only the '{edge['description']}' outcome under this complete review:\n"
                    + by_id[edge["source"]]["instruction"]
                )
                if edge.get("establishes_finding"):
                    edge["confirmation_basis"] = by_id[edge["source"]]["instruction"]
        graph["nodes"].extend(nodes)
        graph["edges"].extend(edges)

    for node in graph["nodes"]:
        if node["type"] == "Procedure" and node["id"] in {item["id"] for item in base_nodes}:
            node["entry_criteria"] += "\n\n" + sections["G4.0"]
            node["source_reference"] += "; SG-04:1.0:G4.0"
        elif node["type"] == "Condition" and node.get("entry"):
            owner = next(item for item in graph["nodes"] if item["id"] == node["procedure_id"])
            node["entry_criteria"] = owner["entry_criteria"]
        if node["type"] == "Action":
            node["instruction"] += (
                "\n\nUse only records for the declared vehicle, current job and requested profile. "
                "A supplied wrong-vehicle record requires clarification, not a result."
            )
            node["source_reference"] += "; SG-04:1.0:G4.0"
    add_vehicle_cases(graph, queries, oracle, profiles)
    return profiles


def add_vehicle_cases(graph, queries, oracle, profiles):
    nodes = {node["id"]: node for node in graph["nodes"]}
    outgoing = {}
    for edge in graph["edges"]:
        outgoing.setdefault(edge["source"], []).append(edge)

    def procedure(profile, family):
        return "procedure-v4-" + family + ("" if profile["key"] == "a21" else "-" + profile["key"])

    def expected(profile, family, outcomes, status, stop=True):
        pid = procedure(profile, family)
        current = next(edge["target"] for edge in outgoing[pid] if edge["type"] == "ENTRY_POINT")
        path = []
        for outcome in outcomes:
            continuation, = outgoing[current]
            path.append(continuation["id"])
            current = continuation["target"]
            result, = [edge for edge in outgoing[current] if edge["description"] == outcome]
            path.append(result["id"])
            current = result["target"]
        if stop and nodes[current]["type"] == "Condition":
            continuation, = outgoing[current]
            path.append(continuation["id"])
            current = continuation["target"]
        return {"procedure_id": pid, "status": status, "target": current if stop else None, "path": path}

    def case(identifier, profile, family, question, evidence, answer, *, group, demo=False):
        pid = procedure(profile, family)
        entry = next(edge["target"] for edge in outgoing[pid] if edge["type"] == "ENTRY_POINT")
        queries.append({
            "id": identifier, "title": f"{profile['model']} {profile['year']}: {question}",
            "vehicle_id": profile["vehicle_id"], "vehicle": copy.deepcopy(profile["vehicle"]),
            "question": question, "evidence": evidence, "start_node": entry,
            "demo": demo, "category": "vehicle_applicability", "intent": group,
            "split": "authored_applicability", "pair_group": group,
        })
        oracle.append({"id": identifier, **answer})
        return queries[-1]

    for profile in profiles:
        key = profile["key"]
        for pressure in (310, 500):
            inside = profile["low"] <= pressure <= profile["high"]
            answer = expected(profile, "lean", [
                "applicable pressure inside reference band" if inside else "applicable pressure outside reference band"
            ], "next_action")
            case(f"vehicle-{key}-pressure-{pressure}", profile, "lean",
                 "The engine light is on and it shakes at idle. What should the workshop review next?",
                 [{"check": "Current workshop attachment, APP-01",
                   "observation": f"Current job APP-01: P0171 present; no P0301, P0302, P0303 or P0304. "
                                  f"RP-IDLE pressure {pressure} kPa, unit verified. Localisation not done."}],
                 answer, group=f"matched-pressure-{pressure}", demo=pressure == 310)

        first = "coil" if profile["order"] == "coil-first" else "plug"
        second = "plug" if first == "coil" else "coil"
        original, donor = f"P030{profile['cylinder']}", f"P030{profile['donor']}"
        label = "misfire remains on cylinder " + {1: "one", 2: "two", 3: "three", 4: "four"}[profile["cylinder"]]
        unchanged = "plugs" if first == "coil" else "coils"
        case(f"vehicle-{key}-misfire-return", profile, "misfire",
             "The light stayed on after the first comparison, then moved cylinders during the second. What does that establish?",
             [{"check": "Current workshop scan, IGN-01",
               "observation": f"Current job IGN-01, rough idle reproduced: {original}, no P0171."},
              {"check": "First component comparison, IGN-01",
               "observation": f"Baseline {original}. Only {first}s exchanged between cylinders "
                              f"{profile['cylinder']} and {profile['donor']}; {unchanged} untouched. "
                              f"Result {original}; original positions restored: {original}. "
                              "No other changes during this comparison."},
              {"check": "Second component comparison, IGN-01",
               "observation": f"First comparison restored before this separate record. Baseline {original}. "
                              f"Only {second}s exchanged between cylinders {profile['cylinder']} and "
                              f"{profile['donor']}; {first}s original and unchanged. "
                              f"Result {donor}, no {original}; original positions restored: "
                              f"{original}, no {donor}. No other changes during this comparison."}],
             expected(profile, "misfire", [label, f"misfire follows {second}"], "root_cause"),
             group="controlled-ignition-order")

        midpoint = (profile["low"] + profile["high"]) / 2
        case(f"vehicle-{key}-lean-return", profile, "lean",
             "It improved during the workshop comparison and came back afterwards. What do the records establish?",
             [{"check": "Current workshop pressure record, LEAN-01",
               "observation": f"Current job LEAN-01, rough idle and P0171; no P0301, P0302, P0303 or P0304. "
                              f"RP-IDLE pressure {midpoint:g} kPa."},
              {"check": "Controlled comparison, LEAN-01",
               "observation": f"Same job LEAN-01, RP-IDLE throughout. Correction: original A +24%; "
                              f"joint {profile['joint']} isolated B +2%; original restored A2 +23%; "
                              f"control joint K, {profile['joint']} original, C +22%. "
                              f"No other diagnostic changes. Signed pressure stability: "
                              f"{midpoint:g} kPa throughout."}],
             expected(profile, "lean", ["applicable pressure inside reference band",
                                      "repeatable localisation at joint " + profile["joint"]], "root_cause"),
             group="controlled-localisation")

        case(f"vehicle-{key}-airflow-return", profile, "airflow",
             "Air only comes out on some fan settings. What does the comparison show?",
             [{"check": "Current workshop stage record, FAN-01",
               "observation": f"Current job FAN-01: no airflow at {profile['missing_stages']}; "
                              f"airflow at {profile['working_stages']}."},
              {"check": "Current CP-FAN record, FAN-01",
               "observation": f"Same job FAN-01. Signed CP-FAN supply, ground and connection prerequisites "
                              "passed throughout. Only the low-speed control unit changed. "
                              f"A original: {profile['missing_stages']} absent, {profile['working_stages']} present. "
                              f"B reference: all four present. A2 original restored: "
                              f"{profile['missing_stages']} absent, {profile['working_stages']} present."}],
             expected(profile, "airflow", ["low-speed stages absent",
                                          "controlled fault follows original unit"], "root_cause"),
             group="controlled-fan-pattern")

    base = profiles[0]
    for identifier, vehicle, vehicle_id, question, status in [
        ("vehicle-missing", {}, "", "The engine light is on. Today's scan says P0171, no P0301. I do not know which model or year this is.", "clarify"),
        ("vehicle-model-missing", {"make": "Brand X", "year": 2021, "configuration": "petrol"}, "",
         "It idles roughly and today's scan says P0171, no P0301. I do not know the model.", "clarify"),
        ("vehicle-year-missing", {"make": "Brand X", "model": "Model A", "configuration": "petrol"}, "",
         "My Model A has P0171 and rough idle. I have not checked the model year.", "clarify"),
        ("vehicle-context-conflict", base["vehicle"], base["vehicle_id"],
         "The selected Model A is wrong: this job is for a 2021 Brand X Model B petrol. Current P0171 and rough idle.", "clarify"),
        ("vehicle-unsupported-model", {**base["vehicle"], "model": "Model Z"}, "vehicle-brandx-modelz-2021",
         "My Model Z idles roughly. Today's scan has P0171 and no P0301.", "unsupported"),
        ("vehicle-unsupported-year", {**base["vehicle"], "year": 2018}, "vehicle-brandx-modela-2018",
         "My 2018 Model A idles roughly. Today's scan has P0171 and no P0301.", "unsupported"),
        ("vehicle-unsupported-configuration", {**base["vehicle"], "configuration": "electric"}, "vehicle-brandx-modela-2021-electric",
         "My electric Model A has weak airflow at the lower fan settings.", "unsupported"),
    ]:
        item = case(identifier, base, "lean", question, [],
                    {"procedure_id": None, "status": status, "target": None, "path": []},
                    group="vehicle-context-boundaries")
        item.update(vehicle=copy.deepcopy(vehicle), vehicle_id=vehicle_id, start_node=None)
    for identifier, observation in [
        ("vehicle-wrong-record", "Current job APP-01, but the attached RP-IDLE record explicitly identifies "
         "2021 Brand X Model B petrol, not this Model A: 310 kPa. No pressure record for the selected vehicle."),
        ("vehicle-unit-missing", "Current job APP-01, RP-IDLE pressure 3.1; unit cropped from photograph."),
    ]:
        case(identifier, base, "lean",
             "My car idles roughly. Today's scan shows P0171 and no P0301. Is this pressure record enough?",
             [{"check": "Workshop attachment", "observation": observation}],
             expected(base, "lean", [], "clarify"), group="pressure-evidence-boundaries")
    case("vehicle-competing-current-codes", profiles[2], "misfire",
         "It idles roughly. Today's scan shows P0302 and P0171. Which procedure should we use?",
         [], {"procedure_id": None, "status": "clarify", "target": None, "path": []},
         group="competing-entry-conditions")["start_node"] = None

    for profile in profiles[:2]:
        key = profile["key"]
        case(f"vehicle-{key}-coil-only", profile, "misfire",
             "The engine light is on. Does this workshop record establish a component fault?",
             [{"check": "Current scan and coil comparison, ORDER-01",
               "observation": "Current job ORDER-01: rough idle, P0301, no P0171. "
                              "Baseline P0301; only coils 1 and 2 exchanged, plugs unchanged. "
                              "Result P0302, no P0301. Coils restored: P0301, no P0302. "
                              "No other changes during this comparison. Plug comparison not done."}],
             expected(profile, "misfire", ["misfire follows coil"] if key == "a21" else [],
                      "root_cause" if key == "a21" else "next_action"),
             group="matched-ignition-order")
        for missing, working in (("1-3", "4"), ("1-2", "3-4")):
            supported = profile["missing_stages"] == missing
            case(f"vehicle-{key}-fan-{missing}", profile, "airflow",
                 "Air only comes out on some settings. What should the workshop review next?",
                 [{"check": "Current workshop record, PATTERN-01",
                   "observation": f"Current job PATTERN-01: no airflow at {missing}; airflow at {working}. "
                                  "No control-unit comparison has been performed."}],
                 expected(profile, "airflow", [
                     "low-speed stages absent" if supported else "other complete stage pattern"
                 ], "next_action"),
                 group=f"matched-fan-{missing}")

    b = profiles[1]
    for identifier, status, observation, outcomes in [
        ("vehicle-b21-coil-not-done", "next_action",
         "Current ORDER-02 scan P0301, no P0171. Baseline P0301; only plugs 1 and 2 exchanged, "
         "coils untouched: still P0301. Plugs restored: P0301. No other changes. Coil comparison not done.",
         ["misfire remains on cylinder one"]),
        ("vehicle-b21-coil-partial", "clarify",
         "Current ORDER-02 scan P0301, no P0171. Baseline P0301; only plugs 1 and 2 exchanged, "
         "coils untouched: P0301. Plugs restored: P0301. No other changes during plug comparison. "
         "Separate coil-only comparison: baseline P0301, plugs original and unchanged, "
         "coils 1 and 2 exchanged: P0302. Return observation missing.",
         ["misfire remains on cylinder one"]),
        ("vehicle-b21-misfire-unresolved", "next_action",
         "Current ORDER-02 scan P0301, no P0171. Baseline P0301; only plugs 1 and 2 exchanged, "
         "coils untouched: P0301. Plugs restored: P0301. No other changes during plug comparison. "
         "Separate coil-only comparison: baseline P0301, plugs original and unchanged, "
         "coils 1 and 2 exchanged: P0301. Coils restored: P0301. No other changes during coil comparison.",
         ["misfire remains on cylinder one", "misfire remains on cylinder one"]),
    ]:
        case(identifier, b, "misfire", "The engine still runs roughly. What do these current records support?",
             [{"check": "Current workshop records, ORDER-02", "observation": observation}],
             expected(b, "misfire", outcomes, status), group="variant-negative-paths")
    lean_case = copy.deepcopy(next(query for query in queries if query["id"] == "vehicle-b21-lean-return"))
    case("vehicle-b21-lean-nonlocalising", b, "lean", lean_case["question"],
         [{**item, "observation": item["observation"].replace("A2 +23%", "A2 +4%")}
          for item in lean_case["evidence"]],
         expected(b, "lean", ["applicable pressure inside reference band",
                             "complete comparison does not localise"], "next_action"),
         group="variant-negative-paths")
    fan_case = next(query for query in queries if query["id"] == "vehicle-b21-airflow-return")
    for identifier, result, status in [
        ("vehicle-b21-fan-nonlocalising", "A2 original restored: all four stages present.", "next_action"),
        ("vehicle-b21-fan-partial", "A2 original restored, but return observations missing.", "clarify"),
    ]:
        evidence = copy.deepcopy(fan_case["evidence"])
        evidence[-1]["observation"] = evidence[-1]["observation"].split("A2 original restored:")[0] + result
        case(identifier, b, "airflow", fan_case["question"], evidence,
             expected(b, "airflow", ["low-speed stages absent"] + (
                 ["complete comparison is non-localising"] if status == "next_action" else []
             ), status), group="variant-negative-paths")
