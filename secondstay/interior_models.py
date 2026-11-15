"""Private plan models and source-backed registration in a shared floor frame.

Coordinates are metres unless explicitly marked plan_relative. A plan frame is not a geographic frame: north and site
placement need separate control points. No fitting to a rentable area or footprint.
"""
import copy
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

MODEL_DIR = Path(__file__).resolve().parent.parent / 'data/raw/interior_models'


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) < 100000


def point(p):
    return isinstance(p, list) and len(p) == 2 and all(number(v) for v in p)


def rigid_registration(anchors, units='metres'):
    """Least-squares rotation + translation; never stretch a measured scan."""
    if not isinstance(anchors, list) or len(anchors) < 3:
        raise ValueError('At least three matching control points are required.')
    a, b = [], []
    for pair in anchors:
        if not isinstance(pair, dict) or not point(pair.get('source')) or not point(pair.get('target')):
            raise ValueError('Control points must contain finite source and target coordinates.')
        a.append(pair['source']); b.append(pair['target'])
    # Collinear controls cannot establish the handedness of a floor plan.
    cross = lambda p, q, r: (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if max(abs(cross(a[0], a[i], a[j])) for i in range(1,len(a)) for j in range(1,len(a))) < .01:
        raise ValueError('Use non-collinear control points.')
    mean = lambda ps: [sum(p[k] for p in ps)/len(ps) for k in (0,1)]
    ma, mb = mean(a), mean(b)
    dot = sum((p[0]-ma[0])*(q[0]-mb[0])+(p[1]-ma[1])*(q[1]-mb[1]) for p,q in zip(a,b))
    det = sum((p[0]-ma[0])*(q[1]-mb[1])-(p[1]-ma[1])*(q[0]-mb[0]) for p,q in zip(a,b))
    angle = math.atan2(det,dot); c,s = math.cos(angle),math.sin(angle)
    t = [mb[0]-c*ma[0]+s*ma[1], mb[1]-s*ma[0]-c*ma[1]]
    result = {'rotation':angle,'translation':t}
    errors = [math.dist(transform_point(p,result),q) for p,q in zip(a,b)]
    result['residual_m' if units == 'metres' else 'residual_plan_units'] = math.sqrt(sum(e*e for e in errors)/len(errors))
    if max(errors) > (.5 if units == 'metres' else .01):
        raise ValueError('Control points disagree; do not place this model.')
    return result


def transform_point(p, transform):
    c,s = math.cos(transform['rotation']),math.sin(transform['rotation'])
    tx,ty = transform['translation']
    return [c*p[0]-s*p[1]+tx,s*p[0]+c*p[1]+ty]


def transform_geometry(geometry, transform):
    result = copy.deepcopy(geometry)
    segment = lambda w: transform_point(w[:2],transform)+transform_point(w[2:],transform)
    for key in ('walls','windows','doors'):
        result[key] = [segment(w) for w in result.get(key,[])]
    for wall in result.get('wall_segments',[]):
        wall['segment'] = segment(wall['segment'])
    for room in result.get('rooms',[]):
        room['polygon'] = [transform_point(p,transform) for p in room['polygon']]
        room['holes'] = [[transform_point(p,transform) for p in ring] for ring in room.get('holes',[])]
    return result


def valid_geometry(g):
    if not isinstance(g,dict) or not isinstance(g.get('walls'),list) or not 1 <= len(g['walls']) <= 10000:
        return False
    if g.get('units','metres') not in ('metres','plan_relative'):
        return False
    segment = lambda w: isinstance(w,list) and len(w)==4 and all(number(n) for n in w)
    ring = lambda r: isinstance(r,list) and 3 <= len(r) <= 10000 and all(point(p) for p in r)
    for key in ('walls','windows','doors'):
        values = g.get(key,[])
        if not isinstance(values,list) or len(values)>10000 or not all(segment(w) for w in values):
            return False
    rooms = g.get('rooms',[])
    if not isinstance(rooms,list) or len(rooms)>10000:
        return False
    for room in rooms:
        if not isinstance(room,dict) or not ring(room.get('polygon')):
            return False
        holes = room.get('holes',[])
        if not isinstance(holes,list) or not all(ring(h) for h in holes):
            return False
    walls = g.get('wall_segments',[])
    if not isinstance(walls,list) or len(walls)>10000:
        return False
    dimension = lambda v: v is None or (number(v) and 0 <= v <= 100)
    for wall in walls:
        if not isinstance(wall,dict) or not segment(wall.get('segment')) or not dimension(wall.get('height_m')):
            return False
        openings = wall.get('openings',[])
        if not isinstance(openings,list): return False
        length = math.dist(wall['segment'][:2],wall['segment'][2:])
        for opening in openings:
            if not isinstance(opening,dict) or opening.get('kind') not in ('window','door'):
                return False
            start,end = opening.get('start'),opening.get('end')
            if not number(start) or not number(end) or not 0 <= start < end <= length + .01:
                return False
            if not all(dimension(opening.get(k)) for k in ('height_m','sill_m')):
                return False
    return True


def valid_source(value):
    if not isinstance(value,dict) or not isinstance(value.get('basis'),str) or not value['basis'].strip():
        return False
    url = value.get('source_url')
    if not isinstance(url,str): return False
    try:
        parsed = urlsplit(url)
        return parsed.scheme in ('http','https') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def load_models(building):
    try:
        data = json.loads((MODEL_DIR / f'{int(building.property_id)}.json').read_text())
    except (OSError, ValueError):
        return {'floors':{},'models':[]}
    if not isinstance(data,dict) or data.get('version') != 1:
        return {'floors':{},'models':[]}
    floor_data, model_data = data.get('floors',{}), data.get('models',[])
    if not isinstance(floor_data,dict) or not isinstance(model_data,list):
        return {'floors':{},'models':[]}
    floors = {}
    for key,value in floor_data.items():
        if not key.isdigit() or not 1 <= int(key) <= (building.stories or 1) or not isinstance(value,dict):
            continue
        outline = value.get('outline',[])
        if isinstance(outline,list) and 3 <= len(outline) <= 1000 and all(point(p) for p in outline) and valid_source(value) and value.get('units','metres') in ('metres','plan_relative'):
            if value.get('geometry') and not valid_geometry(value['geometry']):
                value = {k:v for k,v in value.items() if k != 'geometry'}
            floors[key] = value
    models = []
    spaces = {str(s['id']):s for s in building.spaces}
    for model in model_data:
        if not isinstance(model,dict): continue
        space = spaces.get(str(model.get('space_id')))
        if not space or not isinstance(model.get('floor'),int) or isinstance(model['floor'],bool) or not 1 <= model['floor'] <= (building.stories or 1) or model['floor'] != space.get('floor') or not valid_source(model):
            continue
        if model.get('geometry') and not valid_geometry(model['geometry']): continue
        if model.get('scan_id') and model['scan_id'] not in space.get('scans',[]): continue
        model = copy.deepcopy(model)
        # Registration is derived only from controls, never trusted from the file.
        model.pop('registration',None)
        model.pop('registration_error',None)
        if model.get('anchors') and str(model['floor']) in floors:
            try:
                units = (model.get('geometry') or {}).get('units','metres')
                if units != floors[str(model['floor'])].get('units','metres') or (model.get('scan_id') and units != 'metres'):
                    raise ValueError('The model and floor must use the same coordinate units.')
                model['registration'] = rigid_registration(model['anchors'],units)
            except ValueError: model['registration_error'] = 'Control points need reconciliation.'
        models.append(model)
    return {'floors':floors,'models':models}
