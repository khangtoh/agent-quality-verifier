#!/usr/bin/env python3
"""D5/D6 adapter for SQLite: print what a database really contains, as one line of JSON.

    sqlite_schema.py path/to/app.db

For each table and view: its columns (type, nullable), primary key and foreign keys. For each
view, also the columns its definition reads, taken from SQLite's authorizer while the view is
compiled, so the answer comes from the database engine and not from parsing SQL.
Uses only the standard library.
"""
import json
import sqlite3
import sys

READ = 20


def kind_of(declared):
    t = (declared or "").upper()
    if not t:
        return ""
    if "BOOL" in t:
        return "boolean"
    if "INT" in t:
        return "integer"
    if "CHAR" in t or "CLOB" in t or "TEXT" in t:
        return "text"
    if "BLOB" in t:
        return "blob"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "real"
    if "NUM" in t or "DEC" in t:
        return "numeric"
    return t.lower()


def main(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, cached_statements=0)
    objects = conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    datasets = {}
    for name, kind in objects:
        quoted = '"' + name.replace('"', '""') + '"'
        try:
            info = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
        except sqlite3.Error as err:  # a view over a column or table that no longer exists
            datasets[name] = {"kind": kind, "columns": {}, "error": str(err)}
            continue
        pk = [row[1] for row in sorted((r for r in info if r[5]), key=lambda r: r[5])]
        # INTEGER PRIMARY KEY is the rowid: SQLite reports it as nullable, but it never is.
        rowid = [r[1] for r in info if r[5] and len(pk) == 1 and kind_of(r[2]) == "integer"]
        columns = {r[1]: {"type": kind_of(r[2]), "nullable": not r[3] and r[1] not in rowid} for r in info}
        entry = {"kind": kind, "columns": columns, "primary_key": pk}
        if kind == "table":
            keys = {}
            for row in conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall():
                keys.setdefault(row[0], []).append(row)
            fks = []
            for rows in keys.values():
                rows.sort(key=lambda r: r[1])
                target = rows[0][2]
                to = [r[4] for r in rows]
                if None in to:  # REFERENCES t with no column means t's primary key
                    tq = '"' + target.replace('"', '""') + '"'
                    tinfo = conn.execute(f"PRAGMA table_info({tq})").fetchall()
                    to = [r[1] for r in sorted((r for r in tinfo if r[5]), key=lambda r: r[5])]
                fks.append({"columns": [r[3] for r in rows], "references": f"{target}.{','.join(to)}"})
            entry["foreign_keys"] = sorted(fks, key=lambda f: f["columns"])
        else:
            reads = set()

            def authorize(action, arg1, arg2, _db, source, view=name):
                if action == READ and source == view and not arg1.startswith("sqlite_"):
                    reads.add(f"{arg1}.{arg2 or '*'}")
                return sqlite3.SQLITE_OK

            conn.set_authorizer(authorize)
            conn.execute(f"SELECT * FROM {quoted} LIMIT 0")
            conn.set_authorizer(None)
            entry["reads"] = sorted(reads)
        datasets[name] = entry
    print(json.dumps({"datasets": datasets}, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: sqlite_schema.py DATABASE")
    main(sys.argv[1])
