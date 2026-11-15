"""Tiger Data (TimescaleDB on PostgreSQL) as the private store behind data/raw/.

Two jobs:

1. Backup and restore. data/raw/ is git-ignored: CoStar records, Matterport scans, Vexcel imagery,
   hand-traced interior models and model readings cannot go into the public repository. Each file is
   kept as one row (path, sha256, bytes). ``restore`` writes back what a fresh checkout lacks and never
   overwrites a local file that differs unless asked to.
2. Permit history as time series. LADBS permits matched to each building (data/raw/permits/) and the
   city-wide cost permits (data/raw/la_costs/raw_*.json) go into hypertables, compressed in columnar
   form, with continuous aggregates of permits and declared valuation per year. Declared valuation is
   what the applicant wrote on the permit, not what the work cost.

Connection: TIGER_DATABASE_URL in .env (never committed).

Run:  python -m secondstay.tiger push        # data/raw -> database
      python -m secondstay.tiger restore     # database -> data/raw (missing files only; --force to overwrite)
      python -m secondstay.tiger permits     # load permit hypertables, compress, refresh aggregates
      python -m secondstay.tiger runs        # store finished evidence-agent runs from data/raw/agent_runs
      python -m secondstay.tiger status
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from . import permits as permit_records

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
ENV_KEY = "TIGER_DATABASE_URL"
SKIP_NAMES = {".DS_Store"}

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS raw_files (
        path text PRIMARY KEY,
        sha256 text NOT NULL,
        size bigint NOT NULL,
        body bytea NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS building_permits (
        issued timestamptz NOT NULL,
        property_id bigint NOT NULL,
        number text NOT NULL,
        kind text NOT NULL,
        type text,
        subtype text,
        status text,
        work text,
        valuation double precision,
        topics text[] NOT NULL DEFAULT '{}',
        PRIMARY KEY (property_id, kind, number, issued))""",
    "SELECT create_hypertable('building_permits', by_range('issued', INTERVAL '5 years'), if_not_exists => TRUE)",
    """ALTER TABLE building_permits SET (timescaledb.compress,
        timescaledb.compress_segmentby = 'property_id', timescaledb.compress_orderby = 'issued DESC')""",
    """CREATE TABLE IF NOT EXISTS city_cost_permits (
        issued timestamptz NOT NULL,
        search text NOT NULL,
        number text NOT NULL,
        subtype text,
        work text,
        valuation double precision,
        PRIMARY KEY (search, number, issued))""",
    "SELECT create_hypertable('city_cost_permits', by_range('issued', INTERVAL '5 years'), if_not_exists => TRUE)",
    """ALTER TABLE city_cost_permits SET (timescaledb.compress,
        timescaledb.compress_segmentby = 'search', timescaledb.compress_orderby = 'issued DESC')""",
]

AGGREGATES = [
    ("building_permits_yearly", """CREATE MATERIALIZED VIEW IF NOT EXISTS building_permits_yearly
        WITH (timescaledb.continuous) AS
        SELECT property_id, time_bucket(INTERVAL '1 year', issued) AS year,
               count(*) AS permits, count(valuation) AS valued, sum(valuation) AS declared_valuation
        FROM building_permits GROUP BY property_id, year WITH NO DATA"""),
    ("city_cost_permits_yearly", """CREATE MATERIALIZED VIEW IF NOT EXISTS city_cost_permits_yearly
        WITH (timescaledb.continuous) AS
        SELECT search, time_bucket(INTERVAL '1 year', issued) AS year,
               count(*) AS permits, count(valuation) AS valued, avg(valuation) AS mean_valuation,
               max(valuation) AS max_valuation
        FROM city_cost_permits GROUP BY search, year WITH NO DATA"""),
]


class NotConfigured(RuntimeError):
    pass


# --- pure parts (tested without a database) ---------------------------------------------------

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_files(root: Path = RAW_DIR) -> dict:
    """Relative path -> sha256 for every file under root."""
    out = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in SKIP_NAMES:
            out[path.relative_to(root).as_posix()] = sha256(path.read_bytes())
    return out


def plan_push(local: dict, remote: dict) -> list:
    """Paths to upload: new or changed locally."""
    return [p for p, digest in local.items() if remote.get(p) != digest]


def plan_restore(remote: dict, local: dict, force: bool = False) -> tuple:
    """(paths to write, paths that differ locally and are kept)."""
    write, kept = [], []
    for p, digest in remote.items():
        if p not in local:
            write.append(p)
        elif local[p] != digest:
            (write if force else kept).append(p)
    return write, kept


def safe_target(root: Path, rel: str) -> Path:
    """Resolve a stored path inside root; a stored path that escapes root is refused."""
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        raise ValueError(f"Refusing to write outside {root}: {rel}")
    return target


def _number(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _issued(value) -> Optional[datetime]:
    text = (value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def permit_rows(property_id, records: Iterable[dict]) -> list:
    """Rows for building_permits from one building's cached permits; records without an issue date are left out."""
    rows, seen = [], set()
    for r in records:
        issued = _issued(r.get("issued"))
        if issued is None or not r.get("number"):
            continue
        key = (r.get("kind") or "", r["number"], issued)
        if key in seen:
            continue
        seen.add(key)
        rows.append((issued, int(property_id), r["number"], r.get("kind") or "", r.get("type") or None,
                     r.get("subtype") or None, r.get("status") or None, (r.get("work") or "").strip() or None,
                     _number(r.get("valuation")), sorted(permit_records.topics_of(r))))
    return rows


def cost_rows(search: str, records: Iterable[dict]) -> list:
    """Rows for city_cost_permits from one cached city-wide search (data/raw/la_costs/raw_<search>.json)."""
    rows, seen = [], set()
    for r in records:
        issued = _issued(r.get("issue_date"))
        number = r.get("permit_nbr")
        if issued is None or not number or (number, issued) in seen:
            continue
        seen.add((number, issued))
        rows.append((issued, search, number, r.get("permit_sub_type") or None,
                     (r.get("work_desc") or "").strip() or None, _number(r.get("valuation"))))
    return rows


# --- database ---------------------------------------------------------------------------------

def database_url() -> str:
    url = os.getenv(ENV_KEY)
    env = REPO_ROOT / ".env"
    if not url and env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == ENV_KEY and value.strip():
                url = value.strip().strip("'\"")
    if not url:
        raise NotConfigured(f"Set {ENV_KEY} in .env to the Tiger Data service URL.")
    return url


def connect(autocommit: bool = False):
    import psycopg
    return psycopg.connect(database_url(), autocommit=autocommit, connect_timeout=20)


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        for statement in SCHEMA:
            try:
                cur.execute(statement)
            except Exception as error:  # compression already enabled on a table with compressed chunks
                if "compress" not in statement or "already" not in str(error).lower():
                    raise
        for _, statement in AGGREGATES:
            cur.execute(statement)


def remote_files(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT path, sha256 FROM raw_files")
        return dict(cur.fetchall())


def push(root: Path = RAW_DIR, out=sys.stdout) -> dict:
    local = local_files(root)
    with connect(autocommit=True) as conn:
        ensure_schema(conn)
        todo = plan_push(local, remote_files(conn))
        sent = 0
        with conn.cursor() as cur:
            for i, rel in enumerate(todo, 1):
                body = (root / rel).read_bytes()
                cur.execute("""INSERT INTO raw_files (path, sha256, size, body, updated_at) VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (path) DO UPDATE SET sha256 = EXCLUDED.sha256, size = EXCLUDED.size,
                    body = EXCLUDED.body, updated_at = now()""", (rel, local[rel], len(body), body))
                sent += len(body)
                if i % 100 == 0:
                    print(f"  {i}/{len(todo)} files", file=out)
    result = {"local": len(local), "uploaded": len(todo), "bytes": sent}
    print(f"Pushed {len(todo)} of {len(local)} files ({sent / 1e6:.1f} MB); the rest were already stored.", file=out)
    return result


def restore(root: Path = RAW_DIR, force: bool = False, out=sys.stdout) -> dict:
    local = local_files(root)
    with connect() as conn:
        write, kept = plan_restore(remote_files(conn), local, force)
        with conn.cursor() as cur:
            for rel in write:
                target = safe_target(root, rel)
                cur.execute("SELECT body FROM raw_files WHERE path = %s", (rel,))
                body = bytes(cur.fetchone()[0])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
    print(f"Restored {len(write)} files into {root}.", file=out)
    if kept:
        print(f"Kept {len(kept)} local files that differ from the stored copy (use --force to overwrite).", file=out)
    return {"written": len(write), "kept": kept}


def load_permits(root: Path = RAW_DIR, out=sys.stdout) -> dict:
    """Reload both permit hypertables from the cached files, compress them, refresh the yearly aggregates."""
    building = []
    for path in sorted((root / "permits").glob("*.json")):
        if path.stem.isdigit():
            building += permit_rows(path.stem, json.loads(path.read_text()))
    city = []
    for path in sorted((root / "la_costs").glob("raw_*.json")):
        city += cost_rows(path.stem[len("raw_"):], json.loads(path.read_text()))
    with connect(autocommit=True) as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE building_permits, city_cost_permits")
            with cur.copy("COPY building_permits (issued, property_id, number, kind, type, subtype, status, work, valuation, topics) FROM STDIN") as copy:
                copy.set_types(["timestamptz", "int8", "text", "text", "text", "text", "text", "text", "float8", "text[]"])
                for row in building:
                    copy.write_row(row)
            with cur.copy("COPY city_cost_permits (issued, search, number, subtype, work, valuation) FROM STDIN") as copy:
                copy.set_types(["timestamptz", "text", "text", "text", "text", "float8"])
                for row in city:
                    copy.write_row(row)
            for table in ("building_permits", "city_cost_permits"):
                cur.execute(f"SELECT compress_chunk(c, if_not_compressed => TRUE) FROM show_chunks('{table}') c")
            for name, _ in AGGREGATES:
                cur.execute(f"CALL refresh_continuous_aggregate('{name}', NULL, NULL)")
    print(f"Loaded {len(building)} building permits and {len(city)} city-wide cost permits; "
          "chunks compressed and yearly aggregates refreshed.", file=out)
    return {"building_permits": len(building), "city_cost_permits": len(city)}


def compression(conn) -> list:
    """(table, bytes before, bytes after) for each permit hypertable."""
    rows = []
    with conn.cursor() as cur:
        for table in ("building_permits", "city_cost_permits"):
            cur.execute("SELECT before_compression_total_bytes, after_compression_total_bytes "
                        "FROM hypertable_compression_stats(%s)", (table,))
            before, after = cur.fetchone() or (None, None)
            rows.append((table, before, after))
    return rows


def status(root: Path = RAW_DIR, out=sys.stdout) -> dict:
    local = local_files(root)
    with connect() as conn:
        remote = remote_files(conn)
        missing, differ = plan_restore(remote, local)
        with conn.cursor() as cur:
            cur.execute("SELECT (SELECT count(*) FROM building_permits), (SELECT count(*) FROM city_cost_permits)")
            counts = cur.fetchone()
        stats = compression(conn)
    print(f"Files: {len(local)} local, {len(remote)} stored; {len(missing)} stored files missing locally, "
          f"{len(differ)} differ, {len(plan_push(local, remote))} local files not yet pushed.", file=out)
    print(f"Permits: {counts[0]} building, {counts[1]} city-wide.", file=out)
    for table, before, after in stats:
        if before and after:
            print(f"  {table}: {before / 1e6:.2f} MB -> {after / 1e6:.2f} MB compressed "
                  f"({100 * (1 - after / before):.0f}% smaller)", file=out)
    return {"local": len(local), "stored": len(remote), "permits": counts}


# --- evidence agent runs ----------------------------------------------------------------------

RUN_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS agent_runs (
        id text PRIMARY KEY,
        building_id bigint NOT NULL,
        space_id text NOT NULL DEFAULT '',
        scan_id text NOT NULL DEFAULT '',
        status text NOT NULL,
        mode text NOT NULL,
        started_at timestamptz NOT NULL,
        data jsonb NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS agent_runs_scope ON agent_runs (building_id, space_id, started_at DESC)",
]
_runs_ready = False


def _run_table(conn) -> None:
    global _runs_ready
    if not _runs_ready:
        with conn.cursor() as cur:
            for statement in RUN_SCHEMA:
                cur.execute(statement)
        _runs_ready = True


def save_run(data: dict) -> None:
    """Keep one evidence-agent run (its events, checklist and report) so every screen can show it."""
    from psycopg.types.json import Jsonb
    with connect(autocommit=True) as conn:
        _run_table(conn)
        conn.execute("""INSERT INTO agent_runs (id, building_id, space_id, scan_id, status, mode, started_at, data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, data = EXCLUDED.data""",
            (data["id"], int(data["building_id"]), str(data.get("space_id") or ""), str(data.get("scan_id") or ""),
             data["status"], data.get("mode") or "live", data["started_at"], Jsonb(data)))


def get_run(run_id: str) -> Optional[dict]:
    with connect(autocommit=True) as conn:
        _run_table(conn)
        row = conn.execute("SELECT data FROM agent_runs WHERE id = %s", (run_id,)).fetchone()
    return row[0] if row else None


def list_runs(building_id, space_id: str = "") -> list:
    """Summaries of stored runs for one building and space, newest first."""
    with connect(autocommit=True) as conn:
        _run_table(conn)
        rows = conn.execute("""SELECT id, status, mode, started_at, scan_id FROM agent_runs
            WHERE building_id = %s AND space_id = %s ORDER BY started_at DESC LIMIT 20""",
            (int(building_id), str(space_id or ""))).fetchall()
    return [{"id": i, "status": st, "mode": m, "started_at": t.isoformat(), "scan_id": sc} for i, st, m, t, sc in rows]


def push_runs(directory: Path = RAW_DIR / "agent_runs", out=sys.stdout) -> int:
    """Store every finished run saved on disk."""
    count = 0
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        if data.get("status") != "running":
            save_run(data)
            count += 1
    print(f"Stored {count} evidence-agent runs.", file=out)
    return count


# --- reads for the app ------------------------------------------------------------------------

def permit_years(property_id) -> list:
    """Permits and declared valuation per year for one building, from the continuous aggregate."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT extract(year FROM year)::int, permits, valued, declared_valuation
            FROM building_permits_yearly WHERE property_id = %s ORDER BY year""", (int(property_id),))
        return [{"year": y, "permits": n, "valued": v, "declared_valuation": s} for y, n, v, s in cur.fetchall()]


def city_cost_years(search: str) -> list:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT extract(year FROM year)::int, permits, valued, mean_valuation, max_valuation
            FROM city_cost_permits_yearly WHERE search = %s ORDER BY year""", (search,))
        return [{"year": y, "permits": n, "valued": v, "mean_valuation": m, "max_valuation": x}
                for y, n, v, m, x in cur.fetchall()]


def main(argv: list) -> int:
    command = argv[0] if argv else "status"
    try:
        if command == "push":
            push()
        elif command == "restore":
            restore(force="--force" in argv)
        elif command == "permits":
            load_permits()
        elif command == "runs":
            push_runs()
        elif command == "status":
            status()
        else:
            print(__doc__)
            return 2
    except NotConfigured as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
