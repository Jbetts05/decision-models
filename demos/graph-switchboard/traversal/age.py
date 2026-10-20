"""Apache AGE storage. Model-authored queries have no SQL execution surface."""

import json
import os
import re
import time

import psycopg
from psycopg import sql

from traversal.synthetic import ENTITY_TYPES, RELATION_TYPES, canonical_hash


def literal(value):
    if isinstance(value, dict):
        if any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", key) for key in value):
            raise ValueError("Invalid property name.")
        return "{" + ", ".join(f"{key}: {literal(item)}" for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(literal(item) for item in value) + "]"
    return json.dumps(value, allow_nan=False)


def validate_read_query(query):
    if not isinstance(query, str) or not 1 <= len(query) <= 8000:
        raise ValueError("Cypher must contain 1-8000 characters.")
    # This is a deliberately bounded query dialect, not a general Cypher parser.
    # Role privileges and READ ONLY transactions are the enforcement boundary.
    without_strings = re.sub(r"""'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*" """.strip(), "''", query)
    if any(token in without_strings for token in (";", "//", "/*", "--", "$", "`")):
        raise ValueError("Comments, parameters, backticks and multiple statements are not supported.")
    if not re.match(r"\s*MATCH\b", without_strings, re.I) or not re.search(r"\bRETURN\b", without_strings, re.I):
        raise ValueError("Use one MATCH query with one returned map/list column.")
    if re.search(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL|LOAD|COPY|UNION)\b", without_strings, re.I):
        raise ValueError("Only read-only MATCH queries are permitted.")
    functions = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", without_strings)
    allowed = {
        "MATCH", "WHERE", "AND", "OR", "NOT", "IN",
        "properties", "labels", "type", "id", "nodes", "relationships",
        "collect", "count", "size", "length", "head", "last",
        "coalesce", "toString", "toLower", "toUpper", "exists",
    }
    if any(name.lower() not in {item.lower() for item in allowed} for name in functions):
        raise ValueError("Query uses a function outside the permitted graph-read dialect.")
    return query


def connect(dsn, *, initialize=False):
    connection = psycopg.connect(dsn, autocommit=True, connect_timeout=10)
    try:
        if initialize:
            connection.execute("CREATE EXTENSION IF NOT EXISTS age")
        if os.environ.get("AGE_PRELOADED") != "1":
            connection.execute("LOAD 'age'")
        connection.execute('SET search_path = ag_catalog, "$user", public')
    except Exception:
        connection.close()
        raise
    return connection


def cypher_sql(graph_name, query, columns="result ag_catalog.agtype"):
    return sql.SQL("SELECT * FROM ag_catalog.cypher({}, {}) AS ({})").format(
        sql.Literal(graph_name), dollar_quote(query), sql.SQL(columns)
    )


def dollar_quote(query):
    tag = "$cypher$"
    while tag in query:
        tag = tag[:-1] + "_$"
    return sql.SQL(tag + query + tag)


def bound_cypher(query, parameters):
    """Display values without changing the parameterised query sent to AGE."""
    if parameters is None:
        return query
    return re.sub(r"""'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|\$([a-zA-Z_][a-zA-Z0-9_]*)""",
                  lambda match: literal(parameters[match[1]])
                  if match[1] in parameters else match[0], query)


def stored_properties(value):
    """AGE omits null-valued map properties; missing reads back as null."""
    if isinstance(value, dict):
        return {key: stored_properties(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [stored_properties(item) for item in value]
    return value


def graph_projection(rows, *, encoded=False):
    """Project only complete graph property maps actually present in AGE rows."""
    nodes, edges = {}, {}

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            identifier, kind = value.get("id"), value.get("type")
            if isinstance(identifier, str):
                if kind in ENTITY_TYPES:
                    nodes[identifier] = value
                elif kind in RELATION_TYPES and all(isinstance(value.get(k), str) for k in ("source", "target")):
                    edges[identifier] = value
            for item in value.values():
                visit(item)

    for row in rows:
        if encoded and isinstance(row, str):
            # Preserve quoted content, stripping only AGE's external type tags.
            row = re.sub(r'"(?:\\.|[^"\\])*"|::(?:vertex|edge|path)\b',
                         lambda match: match[0] if match[0].startswith('"') else "", row)
            row = json.loads(row)
        visit(row)
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def load_graph(dsn, graph):
    name = "traversal_" + canonical_hash(graph)[:12]
    with connect(dsn, initialize=True) as connection:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (name,))
            exists = connection.execute(
                "SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s", (name,)
            ).fetchone()
            if not exists:
                connection.execute("SELECT ag_catalog.create_graph(%s)", (name,))
                for node in graph["nodes"]:
                    if node["type"] not in ENTITY_TYPES:
                        raise ValueError("Unexpected entity type.")
                    query = f"CREATE (n:{node['type']} {literal(node)}) RETURN n.id"
                    connection.execute(cypher_sql(name, query)).fetchall()
                for edge in graph["edges"]:
                    if edge["type"] not in RELATION_TYPES:
                        raise ValueError("Unexpected relationship type.")
                    query = (
                        f"MATCH (a {{id: {literal(edge['source'])}}}), "
                        f"(b {{id: {literal(edge['target'])}}}) "
                        f"CREATE (a)-[r:{edge['type']} {literal(edge)}]->(b) RETURN r.id"
                    )
                    connection.execute(cypher_sql(name, query)).fetchall()
            role = connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = 'traversal_reader'"
            ).fetchone()
            if not role:
                connection.execute("CREATE ROLE traversal_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
            connection.execute("GRANT USAGE ON SCHEMA ag_catalog TO traversal_reader")
            connection.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO traversal_reader").format(sql.Identifier(name)))
            connection.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO traversal_reader").format(sql.Identifier(name)))
    return name


class AgeGraph:
    def __init__(self, dsn, graph_name, *, emit=None):
        if not re.fullmatch(r"traversal_[0-9a-f]{12}", graph_name):
            raise ValueError("Unexpected graph name.")
        self.name = graph_name
        self.connection = connect(dsn)
        try:
            self.connection.execute("SET ROLE traversal_reader")
            self.connection.execute("SET statement_timeout = '3000ms'")
        except Exception:
            self.connection.close()
            raise
        self.prepared = {}
        self.query_count = 0
        self.query_ms = 0.0
        self.emit = emit

    def close(self):
        self.connection.close()

    def read(self, query, parameters=None, *, model_authored=False):
        if model_authored:
            validate_read_query(query)
        trace = self.emit if not model_authored else None
        details = {"query_id": self.query_count + 1, "cypher": query,
                   "parameters": dict(parameters) if parameters is not None else None,
                   "resolved_cypher": bound_cypher(query, parameters)}
        if trace:
            trace({"event": "graph_query", **details})
        start = time.perf_counter()
        self.query_count += 1
        try:
            with self.connection.transaction():
                self.connection.execute("SET TRANSACTION READ ONLY")
                if parameters is not None:
                    if query not in self.prepared:
                        statement = f"q{len(self.prepared)}"
                        prepared = sql.SQL(
                            "PREPARE {}(ag_catalog.agtype) AS "
                            "SELECT * FROM ag_catalog.cypher({}, {}, $1) AS (result ag_catalog.agtype)"
                        ).format(sql.Identifier(statement), sql.Literal(self.name), dollar_quote(query))
                        self.connection.execute(prepared)
                        self.prepared[query] = statement
                    command = sql.SQL("EXECUTE {}({}::ag_catalog.agtype)").format(
                        sql.Identifier(self.prepared[query]), sql.Literal(json.dumps(parameters))
                    )
                else:
                    command = cypher_sql(self.name, query)
                with self.connection.cursor() as cursor:
                    cursor.execute(command)
                    rows = cursor.fetchmany(201)
                if len(rows) > 200:
                    raise ValueError("Graph query exceeded the 200-row limit; narrow the query.")
                # Raw agtype is retained for model-authored reads, including typed nodes.
                if model_authored:
                    result = [str(row[0]) for row in rows]
                else:
                    result = [json.loads(row[0]) for row in rows]
        except Exception as exc:
            if trace:
                trace({"event": "graph_rows", **details, "error": str(exc)[:1500],
                       "duration_ms": round((time.perf_counter() - start) * 1000, 3)})
            raise
        finally:
            duration = (time.perf_counter() - start) * 1000
            self.query_ms += duration
        if trace:
            trace({"event": "graph_rows", **details, "rows": result, "query_ms": round(duration, 2),
                   "duration_ms": round(duration, 3)})
        if self.emit:
            self.emit({"event": "graph_data", "query_id": self.query_count,
                       "model_authored": model_authored, **graph_projection(result, encoded=model_authored)})
        return result

    def node(self, identifier):
        rows = self.read("MATCH (n) WHERE n.id = $id RETURN properties(n)", {"id": identifier})
        if len(rows) != 1:
            raise ValueError("Current graph node is absent or not unique.")
        return rows[0]

    def neighbors(self, identifier):
        return self.read(
            "MATCH (n)-[r]->(m) WHERE n.id = $id "
            "RETURN {edge: properties(r), node: properties(m)}",
            {"id": identifier},
        )

    def entries(self, vehicle):
        return self.read(
            "MATCH (p:Procedure)-[a:APPLIES_TO]->(v:VehicleModel) "
            "WHERE p.status = 'published' AND toLower(v.make) = toLower($make) "
            "AND toLower(v.model) = toLower($model) AND v.model_year = $year "
            "AND toLower(v.configuration) = toLower($configuration) "
            "MATCH (p)-[e:ENTRY_POINT]->(c:Condition) "
            "RETURN {procedure: properties(p), vehicle: properties(v), "
            "applicability_edge: properties(a), entry_edge: properties(e), "
            "entry_condition: properties(c)}",
            {key: vehicle[key] for key in ("make", "model", "year", "configuration")},
        )

    def eligible(self, node, vehicle):
        rows = self.read(
            "MATCH (p:Procedure)-[:APPLIES_TO]->(v:VehicleModel) "
            "WHERE p.id = $procedure AND v.id = $vehicle AND p.status = 'published' "
            "RETURN p.id",
            {"procedure": node["procedure_id"], "vehicle": vehicle},
        )
        return bool(rows)

    def is_entry(self, node):
        return bool(self.read(
            "MATCH (p:Procedure)-[:ENTRY_POINT]->(c:Condition) "
            "WHERE p.id = $procedure AND c.id = $id RETURN c.id",
            {"procedure": node["procedure_id"], "id": node["id"]},
        ))

    def verify(self, graph):
        actual_nodes = self.read("MATCH (n) RETURN collect(properties(n))")[0]
        actual_edges = self.read("MATCH ()-[r]->() RETURN collect(properties(r))")[0]
        expected_nodes = sorted(stored_properties(graph["nodes"]), key=lambda n: n["id"])
        expected_edges = sorted(stored_properties(graph["edges"]), key=lambda e: e["id"])
        if sorted(actual_nodes, key=lambda n: n["id"]) != expected_nodes:
            raise ValueError("AGE node contents differ from the versioned dataset.")
        if sorted(actual_edges, key=lambda e: e["id"]) != expected_edges:
            raise ValueError("AGE relationships differ from the versioned dataset.")
