import json
import math
import pytest
from secondstay import interior_models as im
from secondstay import floor_geometry as fg
from secondstay.costar import Building


def test_registration_preserves_dimensions_and_moves_all_features():
    anchors=[{'source':[0,0],'target':[10,20]}, {'source':[4,0],'target':[10,24]}, {'source':[0,3],'target':[7,20]}]
    t=im.rigid_registration(anchors)
    assert t['residual_m'] < 1e-9
    g={'walls':[[0,0,4,0]],'wall_segments':[{'segment':[0,0,4,0],'openings':[{'start':1,'end':2}]}],
       'rooms':[{'polygon':[[0,0],[4,0],[0,3]],'holes':[[[1,1],[2,1],[1,2]]]}]}
    moved=im.transform_geometry(g,t)
    assert moved['walls'][0] == pytest.approx([10,20,10,24])
    assert moved['wall_segments'][0]['openings']==g['wall_segments'][0]['openings']
    assert moved['rooms'][0]['holes'][0][0]==pytest.approx([9,21])
    assert g['walls'][0]==[0,0,4,0]


def test_disagreement_collinearity_and_nonfinite_anchors_are_rejected():
    for anchors in [
        [{'source':[0,0],'target':[0,0]}]*3,
        [{'source':[0,0],'target':[0,0]},{'source':[4,0],'target':[40,0]},{'source':[0,4],'target':[0,40]}],
        [{'source':[0,0],'target':[0,0]},{'source':[4,0],'target':[4,0]},{'source':[0,4],'target':[0,float('nan')]}]]:
        with pytest.raises(ValueError): im.rigid_registration(anchors)


def test_private_models_cannot_cross_floor_or_scan_scope(tmp_path,monkeypatch):
    monkeypatch.setattr(im,'MODEL_DIR',tmp_path)
    b=Building(property_id=1,stories=3,spaces=[{'id':10,'floor':2,'scans':[]}])
    good={'floor':2,'space_id':'10','source_url':'https://example.com/plan.pdf','basis':'Printed room dimensions',
          'geometry':{'walls':[[0,0,4,0]]}}
    (tmp_path/'1.json').write_text(json.dumps({'version':1,'models':[good,{**good,'floor':3},{**good,'scan_id':'OTHER0001'}]}))
    assert len(im.load_models(b)['models'])==1
    g=fg.geometry_for(b,2,'10')
    assert g['available'] and not g['registered']
    assert not fg.geometry_for(b,1)['available']


def test_room_with_core_retains_outer_boundary_and_hole():
    def edges(points):
        return [{'type':'wall','vertices':[{'position':dict(zip(('x','y'),p))} for p in (a,b)]} for a,b in zip(points,points[1:]+points[:1])]
    outer=[[0,0],[20,0],[20,10],[0,10]]
    hole=[[5,4],[8,4],[8,6],[5,6]]
    model={'rooms':[{'floor':{'label':'Local'},'boundary':{'edges':edges(hole)+edges(outer)}}]}
    room=fg.interior_details(model,'Local')['rooms'][0]
    assert room['polygon']==outer
    assert room['holes']==[hole]
    assert fg.room_rings(edges(outer)[:-1])==[]
    # Scan exports can join an outer loop and a shaft with an extra line, and
    # include dangling wall stubs. Retain both loops without closing any gap.
    joined = edges(outer)+edges(hole)+edges([[0,0],[5,4]])[:1]+edges([[8,6],[9,7]])[:1]
    rings = fg.room_rings(joined)
    assert sorted(map(fg.ring_area,rings)) == [6,200]
    assert all(len(r)==4 for r in rings)


def test_registered_floor_assembles_multiple_sources_without_recentering(tmp_path,monkeypatch):
    monkeypatch.setattr(im,'MODEL_DIR',tmp_path)
    b=Building(property_id=1,stories=2,spaces=[{'id':10,'floor':2,'scans':[]},{'id':11,'floor':2,'scans':[]}])
    def model(sid,offset):
        return {'floor':2,'space_id':str(sid),'source_url':'https://example.com/plan.pdf','basis':'Source controls',
                'geometry':{'walls':[[0,0,4,0],[4,0,4,3],[4,3,0,3],[0,3,0,0]]},
                'anchors':[{'source':p,'target':[p[0]+offset,p[1]]} for p in [[0,0],[4,0],[0,3]]]}
    core={'walls':[[5,0,5,3]]}
    (tmp_path/'1.json').write_text(json.dumps({'version':1,
        'floors':{'2':{'outline':[[0,0],[20,0],[20,10],[0,10]],'source_url':'https://example.com/key.pdf','basis':'Key plan','geometry':core}},
        'models':[model(10,1),model(11,10)]}))
    result=fg.geometry_for(b,2,'10')
    assert result['registered']
    assert result['floor_scope']=='partial'
    assert len(result['assembly'])==3
    assert result['assembly'][0]['walls'][0]==pytest.approx([1,0,5,0])
    assert result['assembly'][1]['walls'][0]==pytest.approx([10,0,14,0])
    assert result['assembly'][2]['walls']==core['walls']
    assert result['floor_outline'][1]==[20,0]
    assert not fg.geometry_for(b,1)['available']


def test_private_model_validation_withholds_invalid_geometry_and_forged_placement(tmp_path,monkeypatch):
    monkeypatch.setattr(im,'MODEL_DIR',tmp_path)
    b=Building(property_id=1,stories=2,spaces=[{'id':10,'floor':2,'scans':[]}])
    model={'floor':2,'space_id':'10','source_url':'https://example.com/plan.pdf','basis':'Printed dimensions',
           'geometry':{'walls':[[0,0,4,0]]},'registration':{'rotation':0,'translation':[8,2]}}
    path=tmp_path/'1.json'
    path.write_text(json.dumps({'version':1,'models':[model]}))
    assert 'registration' not in im.load_models(b)['models'][0]
    for geometry in [
        {'walls':[[0,0,4,0]],'rooms':None},
        {'walls':[[0,0,4,0]],'rooms':[{'polygon':[[0,0],[4,0],[0,3]],'holes':[[[float('nan'),0],[1,0],[1,1]]]}]},
        {'walls':[[0,0,4,0]],'wall_segments':[{'segment':[0,0,4,0],'openings':[{'kind':'door','start':1,'end':8}]}]},
        {'walls':[[0,0,4,0]],'wall_segments':[{'segment':[0,0,4,0],'height_m':float('inf')}]},
    ]:
        path.write_text(json.dumps({'version':1,'models':[{**model,'geometry':geometry}]}))
        assert im.load_models(b)['models']==[]
    for extra in [{'models':None},{'floors':[]},{'floors':{'2':{'outline':None}}}]:
        path.write_text(json.dumps({'version':1,**extra}))
        assert im.load_models(b)=={'models':[],'floors':{}}
    path.write_text(json.dumps({'version':1,'models':[{**model,'source_url':'javascript:alert(1)'}]}))
    assert im.load_models(b)['models']==[]


def test_unitless_plan_cannot_be_registered_to_a_measured_floor(tmp_path,monkeypatch):
    monkeypatch.setattr(im,'MODEL_DIR',tmp_path)
    b=Building(property_id=1,stories=2,spaces=[{'id':10,'floor':2,'scans':[]}])
    controls=[{'source':p,'target':p} for p in [[0,0],[4,0],[0,3]]]
    model={'floor':2,'space_id':'10','source_url':'https://example.com/plan.pdf','basis':'No printed scale',
           'geometry':{'units':'plan_relative','walls':[[0,0,4,0]]},'anchors':controls}
    frame={'outline':[[0,0],[4,0],[4,3],[0,3]],'source_url':'https://example.com/key.pdf','basis':'Source perimeter'}
    path=tmp_path/'1.json'
    path.write_text(json.dumps({'version':1,'models':[model],'floors':{'2':frame}}))
    loaded=im.load_models(b)['models'][0]
    assert 'registration' not in loaded and loaded['registration_error']
    frame['units']='plan_relative'
    path.write_text(json.dumps({'version':1,'models':[model],'floors':{'2':frame}}))
    loaded=im.load_models(b)['models'][0]
    assert loaded['registration']['residual_plan_units']==0
    assert 'residual_m' not in loaded['registration']
    geometry=fg.geometry_for(b,2,'10')
    assert geometry['registered'] and 'physical scale is not established' in geometry['note']
