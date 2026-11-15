"""Read private, cached floor vectors without assigning one suite's interior to another."""

import json
import math
import re
from pathlib import Path

from . import matterport

ROOT = Path(__file__).resolve().parent.parent
PLAN_CACHE = ROOT / "data/raw/floorplans"
SCAN_CACHE = ROOT / "data/raw/matterport"


def finite(value, low=0, high=10000):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high


def room_rings(edges):
    """Recover closed boundaries; dangling scan edges do not erase valid loops.

    Remove graph bridges before tracing degree-two components. This introduces
    no edges across gaps. Ambiguous intersecting cycles remain unfilled.
    """
    points, adjacent, buckets = [], {}, {}
    def vertex(p):
        cell = tuple(math.floor(v / .005) for v in p)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for i in buckets.get((cell[0]+dx,cell[1]+dy),[]):
                    if math.dist(p,points[i]) < .005: return i
        i = len(points); points.append(p); adjacent[i] = set()
        buckets.setdefault(cell,[]).append(i)
        return i
    for edge in edges:
        ps = [v.get("position") or {} for v in edge.get("vertices") or []]
        if len(ps) == 2 and all(finite(p.get(k), -10000) for p in ps for k in ("x", "y")):
            a,b = [vertex([p['x'],p['y']]) for p in ps]
            if a != b: adjacent[a].add(b); adjacent[b].add(a)
    seen, low, parent, bridges = {}, {}, {}, []
    for start in adjacent:
        if start in seen: continue
        seen[start] = low[start] = len(seen)
        stack = [(start,iter(sorted(adjacent[start])))]
        while stack:
            v,neighbors = stack[-1]
            n = next(neighbors,None)
            if n is None:
                stack.pop()
                if v in parent:
                    p = parent[v]; low[p] = min(low[p],low[v])
                    if low[v] > seen[p]: bridges.append((p,v))
            elif n != parent.get(v):
                if n not in seen:
                    parent[n] = v; seen[n] = low[n] = len(seen)
                    stack.append((n,iter(sorted(adjacent[n]))))
                else: low[v] = min(low[v],seen[n])
    for a,b in bridges: adjacent[a].remove(b); adjacent[b].remove(a)
    rings, visited = [], set()
    for start in adjacent:
        if start in visited or not adjacent[start]: continue
        component, todo = set(), [start]
        while todo:
            v = todo.pop()
            if v in component: continue
            component.add(v); todo.extend(adjacent[v]-component)
        visited.update(component)
        if any(len(adjacent[v]) != 2 for v in component): continue
        ring, previous, current = [points[start]], start, min(adjacent[start])
        while current != start:
            ring.append(points[current])
            previous,current = current,next(n for n in adjacent[current] if n != previous)
        if len(ring) >= 3: rings.append(ring)
    return rings


def ring_area(ring):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(ring,ring[1:]+ring[:1])))/2


def room_ring(edges):
    rings = room_rings(edges)
    return rings[0] if len(rings) == 1 else []


def interior_details(model, floor_label):
    """Preserve openings and room boundaries that the flat line renderer omitted."""
    walls, rooms = {}, []
    for room in model.get("rooms") or []:
        if ((room.get("floor") or {}).get("label") or "") != floor_label:
            continue
        edges = (room.get("boundary") or {}).get("edges") or []
        classes = [c.get("label") for c in room.get("classifications") or []]
        kind = next((k for k in classes if k not in (None, "Void", "Other")), "Unlabelled area")
        rings = sorted(room_rings(edges), key=ring_area, reverse=True)
        def inside(p, ring):
            contained = False
            for a,b in zip(ring,ring[1:]+ring[:1]):
                if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
                    contained = not contained
            return contained
        if "Void" not in classes:
            area = (room.get("dimensionEstimates") or {}).get("area")
            while rings:
                polygon = rings.pop(0)
                holes = [ring for ring in rings if inside(ring[0],polygon)]
                rings = [ring for ring in rings if ring not in holes]
                rooms.append({"label":kind,"polygon":polygon,"holes":holes,
                              "area_sqft":area if finite(area,0.01) else None})
        height = (room.get("dimensionEstimates") or {}).get("height")
        height_m = height * 0.3048 if finite(height, 1, 60) else None  # room query uses imperial units
        for edge in edges:
            points = [v.get("position") or {} for v in edge.get("vertices") or []]
            if edge.get("type") != "wall" or len(points) != 2 or not all(finite(p.get(k), -10000) for p in points for k in ("x", "y")):
                continue
            segment = [points[0]["x"], points[0]["y"], points[1]["x"], points[1]["y"]]
            length = math.dist(segment[:2], segment[2:])
            if length < 0.03:
                continue
            key = edge.get("id") or tuple(sorted((tuple(segment[:2]), tuple(segment[2:]))))
            wall = walls.setdefault(key, {"segment": segment, "height_m": height_m, "openings": []})
            if height_m:
                wall["height_m"] = max(wall["height_m"] or 0, height_m)
            base = wall["segment"]
            dx, dy = base[2] - base[0], base[3] - base[1]
            for opening in edge.get("openings") or []:
                kind = {"window": "window", "doorway": "door"}.get(opening.get("type"))
                center, width = opening.get("relativeCenter"), opening.get("width")
                if not kind or not finite(center, 0, 1) or not finite(width, 0.03, 100):
                    continue
                x = segment[0] + (segment[2] - segment[0]) * center
                y = segment[1] + (segment[3] - segment[1]) * center
                along = ((x - base[0]) * dx + (y - base[1]) * dy) / length
                start, end = max(0, along - width / 2), min(length, along + width / 2)
                if end <= start:
                    continue
                if any(o["kind"] == kind and abs(o["start"] - start) < 0.01 and abs(o["end"] - end) < 0.01 for o in wall["openings"]):
                    continue
                h, sill = opening.get("height"), opening.get("lowerElevation")
                wall["openings"].append({"kind": kind, "start": start, "end": end,
                    "height_m": h if finite(h, 0.03, 30) else None,
                    "sill_m": sill if finite(sill, 0, 30) else None})
    values = list(walls.values())
    openings = [o for w in values for o in w["openings"]]
    return {"wall_segments": values, "rooms": rooms, "counts": {
        "windows": sum(o["kind"] == "window" for o in openings),
        "doors": sum(o["kind"] == "door" for o in openings), "rooms": len(rooms)}}


def dxf_lines(text: str) -> list:
    """Matterport ASCII DXF LINE entities in metres; retain no assumed wall semantics."""
    rows = text.splitlines()
    if len(rows) % 2 or len(rows) > 500000:
        return []
    pairs = [(a.strip(), b.strip()) for a, b in zip(rows[::2], rows[1::2])]
    units = next((pairs[i + 1][1] for i, p in enumerate(pairs[:-1]) if p == ("9", "$INSUNITS")), "")
    scale = {"6": 1, "4": 0.001, "5": 0.01, "2": 0.3048, "1": 0.0254}.get(units)
    if scale is None:
        return []
    entities, current, kind, in_entities = [], {}, "", False

    def append():
        if kind != "LINE" or not in_entities:
            return
        try:
            segment = [float(current[k]) * scale for k in ("10", "20", "11", "21")]
        except (KeyError, ValueError):
            return
        if all(math.isfinite(n) and abs(n) < 10000 for n in segment) and math.hypot(segment[2] - segment[0], segment[3] - segment[1]) > 0.03:
            entities.append(segment)

    for code, value in pairs:
        if code == "0":
            append()
            kind, current = value, {}
            if value == "ENDSEC":
                in_entities = False
        elif code == "2" and kind == "SECTION":
            in_entities = value == "ENTITIES"
        else:
            current[code] = value
    append()
    return entities[:5000]


def _scan_geometry_for(b, floor: int, space_id: str = "", scan_id: str = "") -> dict:
    if not 1 <= floor <= (b.stories or 1):
        raise ValueError("Choose a floor on record.")
    space = next((s for s in b.spaces if str(s["id"]) == str(space_id)), None) if space_id else None
    if space_id and (space is None or space["floor"] != floor):
        raise ValueError("Choose a suite on this floor.")
    candidates = [s for s in b.scans if s.floor == floor and s.floor_basis != "read from the suite number"]
    if space:
        candidates = [s for s in candidates if s.model_id in space["scans"]]
    if scan_id:
        candidates = [s for s in candidates if s.model_id == scan_id]
    result = {"floor": floor, "space_id": str(space_id), "available": False, "walls": [], "windows": [], "doors": [],
              "source": "", "note": "No interior vectors are linked to this floor and selection. The floor outline uses the building footprint; individual floor outlines are not recorded."}
    for scan in candidates:
        if not re.fullmatch(r"[A-Za-z0-9]{6,20}", scan.model_id):
            continue
        try:
            model = json.loads((SCAN_CACHE / f"{scan.model_id}.json").read_text())
        except (OSError, ValueError):
            continue
        # A scan's local 'Floor 1' need not be the building's first floor. Only map
        # a single-floor scan via its listing/caption. Multi-floor assets need a manifest.
        floors = model.get("floors") or []
        if len(floors) != 1:
            continue
        lines = matterport.plan_lines(model)
        label = floors[0].get("label") or ""
        geometry = lines.get(label, {})
        source = "Matterport wall geometry"
        if geometry.get("walls"):
            geometry.update(interior_details(model, label))
        if not geometry.get("walls"):
            assets = sorted(PLAN_CACHE.glob(f"{scan.model_id}_*.dxf"))
            if len(assets) != 1:
                continue
            try:
                geometry = {"walls": dxf_lines(assets[0].read_text()), "windows": [], "doors": []}
            except (OSError, UnicodeError):
                continue
            source = "Matterport DXF linework"
        if geometry.get("walls"):
            return {**result, **geometry, "available": True, "source": source, "scan_id": scan.model_id,
                    "suite": scan.suite, "floor_basis": scan.floor_basis,
                    "note": f"{source}{' · Suite ' + scan.suite if scan.suite else ''} · floor linked by {scan.floor_basis}. Opening dimensions are used where recorded; missing vertical dimensions use display assumptions. This scan may cover only part of the floor. Interior placement and orientation within the building are unverified. Doorways are not identified as building entrances."}
    return result


def geometry_for(b, floor: int, space_id: str = "", scan_id: str = "") -> dict:
    from .interior_models import load_models, transform_geometry
    # This also validates suite/floor scope before private models are considered.
    result = _scan_geometry_for(b, floor, space_id, scan_id)
    private = load_models(b)
    models = [m for m in private['models'] if m['floor'] == floor]
    selected = next((m for m in models if str(m['space_id']) == str(space_id)
                     and (not scan_id or m.get('scan_id') == scan_id)), None)
    if selected is None and not space_id and not scan_id:
        selected = next((m for m in models if m.get('registration')), None)
    if selected is None:
        # A full-floor listing plus its own scan supplies an intrinsic floor frame.
        full = next((s for s in b.spaces if s.get('floor') == floor and s.get('full_floor')
                     and result.get('scan_id') in s.get('scans',[]) and (not space_id or str(s['id']) == str(space_id))),None)
        rooms = result.get('rooms',[])
        if full and rooms:
            outline = max((r['polygon'] for r in rooms),key=ring_area)
            recorded = full.get('sqft') or 0
            # A small room cannot define the whole-floor perimeter.
            if recorded and ring_area(outline)*10.7639 > recorded*.65:
                return {**result,'registered':True,'floor_outline':outline,'floor_scope':'whole_floor',
                        'floor_frame':{'basis':'Full-floor scan coordinate frame; geographic orientation is not registered.'},
                        'note':'Full-floor listing and its own Matterport boundary. All rooms retain their original relative coordinates and metre scale. Internal shafts are retained as holes. Geographic orientation is not registered.'}
        return {**result, 'registered': False}

    def model_geometry(model):
        raw = model.get('geometry') or _scan_geometry_for(b, floor, str(model['space_id']), model.get('scan_id',''))
        if not raw.get('walls'): return None
        raw = {**raw, 'available':True, 'space_id':str(model['space_id']),
               'suite':model.get('suite',''), 'source_url':model['source_url'],
               'basis':model['basis'], 'reconstructed':bool(model.get('geometry')),
               'source':raw.get('source') or 'Source plan reconstruction'}
        if model.get('registration'):
            raw = transform_geometry(raw,model['registration'])
            raw['registered'] = True
            raw['registration'] = model['registration']
        else:
            raw['registered'] = False
        return raw

    value = model_geometry(selected)
    if not value: return result
    outline = private['floors'].get(str(floor))
    if value['registered'] and outline:
        selected_space = next(s for s in b.spaces if str(s['id']) == str(selected['space_id']))
        value['floor_scope'] = 'whole_floor' if selected_space.get('full_floor') else 'partial'
        value['floor_outline'] = outline['outline']
        value['floor_frame'] = outline
        value['assembly'] = [g for m in models if m.get('registration') for g in [model_geometry(m)] if g]
        if outline.get('geometry'):
            value['assembly'].append({**outline['geometry'], 'registered': True, 'available': True, 'suite': 'Shared core'})
        value['note'] = ('Placement follows the linked source floor plan: read from images, not measured. '
                         'Geographic orientation and the present-day layout need confirmation. ' + selected['basis'])
    else:
        value['note'] = ('Walls, rooms and visible openings reconstructed from the linked sheet: read from images, not measured. '
                         'This sheet does not locate the suite within the floor; the model is shown separately. ' + selected['basis'])
    if value.get('units') == 'plan_relative':
        value['note'] = 'Drawing proportions only; physical scale is not established. Vertical extrusion is illustrative. ' + value['note']
    return {**result, **value}


def source_catalog(b):
    """Index every floor-linked source, without fetching images or guessing placement."""
    from .costar import scan_place, suite_key, floor_number
    floors = {n: {"floor": n, "assets": []} for n in range(1, (b.stories or 1) + 1)}
    linked_plans, linked_scans = set(), set()
    for space in b.spaces:
        floor = space.get("floor")
        if floor not in floors:
            continue
        scans = [s for s in b.scans if s.model_id in space.get("scans", []) and s.floor == floor
                 and s.floor_basis != "read from the suite number"]
        for scan in scans or [None]:
            plan = space.get("plan_url") or ""
            if not scan and not plan:
                continue
            sid = str(space["id"])
            model = scan.model_id if scan else ""
            geometry = geometry_for(b, floor, sid, model)
            floors[floor]["assets"].append({"key": f"space:{sid}:{model}", "space_id": sid,
                "scan_id": model, "suite": space.get("suite") or "", "label": f"Suite {space['suite']}" if space.get("suite") else "Listed space",
                "plan_url": plan, "geometry_available": geometry['available'],
                "registered": bool(geometry.get('registered')), "units": geometry.get('units','metres')})
            if model:
                linked_scans.add(model)
            if plan:
                linked_plans.add(plan)
    for scan in b.scans:
        if scan.model_id in linked_scans or scan.floor not in floors or scan.floor_basis == "read from the suite number":
            continue
        floors[scan.floor]["assets"].append({"key": f"scan:{scan.model_id}", "space_id": "", "scan_id": scan.model_id,
            "suite": scan.suite, "label": f"Suite {scan.suite}" if scan.suite else scan.caption or "Floor scan",
            "plan_url": "", "geometry_available": geometry_for(b, scan.floor, scan_id=scan.model_id)["available"]})
        linked_scans.add(scan.model_id)
    unassigned = []
    for i, plan in enumerate(b.floor_plans):
        url = plan.get("url") or ""
        if not url or url in linked_plans:
            continue
        suite, floor, basis = scan_place(plan.get("caption") or "", b.stories)
        # A suite caption can be linked only through its listing, never its digits.
        matches = {s.get("floor") for s in b.spaces if suite and suite_key(s.get("suite")) == suite_key(suite)}
        encoded = re.search(r"\bfloor\s+(\d+)\b", plan.get("caption") or "", re.I) if plan.get("source") == "space" else None
        if encoded:
            # _add_spaces writes CoStar's floor enum into this generated caption.
            floor = floor_number(int(encoded.group(1)))
        elif basis != "named in the scan's caption":
            floor = next(iter(matches)) if len(matches) == 1 else None
        asset = {"key": f"plan:{i}", "space_id": "", "scan_id": "", "suite": suite,
                 "label": plan.get("caption") or "Building plan", "plan_url": url, "geometry_available": False}
        if floor in floors:
            floors[floor]["assets"].append(asset)
        else:
            unassigned.append(asset)
        linked_plans.add(url)
    for scan in b.scans:
        if scan.model_id not in linked_scans:
            unassigned.append({"key": f"scan:{scan.model_id}", "space_id": "", "scan_id": scan.model_id,
                "suite": scan.suite, "label": scan.caption or "Scan", "plan_url": "", "geometry_available": False})
    from .interior_models import load_models
    private = load_models(b)
    for f in floors.values():
        f['plan_frame'] = private['floors'].get(str(f['floor']))
        for asset in f['assets']:
            model = next((m for m in private['models'] if m['floor'] == f['floor'] and str(m['space_id']) == asset['space_id'] and (not asset['scan_id'] or m.get('scan_id') == asset['scan_id'])),None)
            if model:
                asset['registered'] = bool(model.get('registration'))
                asset['reconstructed'] = bool(model.get('geometry'))
                asset['model_source_url'] = model['source_url']
                asset['geometry_available'] = bool(model.get('geometry')) or asset['geometry_available']
    return {"floors": list(floors.values()), "unassigned": unassigned}
