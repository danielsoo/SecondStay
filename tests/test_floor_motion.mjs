import { test } from 'node:test';
import assert from 'node:assert/strict';
import { floorPose, validFloor, sameScope, chooseFloorAsset } from '../secondstay/static/floor_motion.mjs';
import { traceCandidates } from '../secondstay/static/plan_trace.mjs';
import { wallSections } from '../secondstay/static/opening_layout.mjs';

test('isolating a floor retains its number and hides all other floors', () => {
  for (const selected of [1, 7, 19]) {
    const poses = Array.from({length:19}, (_,i)=>floorPose(i+1,19,3.5,40,'isolated',selected));
    assert.equal(poses.filter(p=>p.opacity===1).length,1);
    assert.equal(poses[selected-1].y,0);
  }
  assert.equal(validFloor(20,19),null);
  assert.equal(validFloor(null,19),null);
});
test('exploded floor sequence stays ordered and selected floor stays highlighted', () => {
  const poses = Array.from({length:19},(_,i)=>floorPose(i+1,19,3.5,40,'exploded',7));
  for(let i=1;i<poses.length;i++){assert.ok(poses[i].y>poses[i-1].y);assert.equal(poses[i].z,0);}
  assert.ok(poses.at(-1).y < 19*3.5+12);
  assert.equal(poses.filter(p=>p.x!==0).length,1);
  assert.equal(poses[6].opacity,1);
  assert.equal(sameScope({floor:3,space_id:11},{floor:3,space_id:'11'}),true);
  assert.equal(sameScope({floor:3,space_id:11},{floor:3,space_id:12}),false);
});
test('doorways cut to the floor and windows retain sill and lintel panels', () => {
  const result=wallSections({segment:[0,0,8,0],height_m:3,openings:[
    {kind:'door',start:1,end:2,height_m:2.1,sill_m:0},
    {kind:'window',start:4,end:6,height_m:1.5,sill_m:0.8}]});
  const solid=(x,y)=>result.panels.some(p=>x>p.start&&x<p.end&&y>p.bottom&&y<p.top);
  assert.equal(solid(1.5,0.1),false);
  assert.equal(solid(1.5,2.6),true);
  assert.equal(solid(5,0.4),true);
  assert.equal(solid(5,1.2),false);
  assert.equal(solid(5,2.6),true);
  assert.equal(solid(3,1),true);
});
test('missing vertical dimensions use explicit display defaults without filling holes',()=>{
  const result=wallSections({segment:[0,0,4,0],openings:[{kind:'window',start:1,end:3,height_m:3,sill_m:1}]},2.8);
  assert.ok(result.height>4);
  assert.equal(result.panels.some(p=>2>p.start&&2<p.end&&2>p.bottom&&2<p.top),false);
});
test('raster drafts detect long runs while excluding short text-like marks', () => {
  const w=80,h=80,p=new Uint8ClampedArray(w*h*4).fill(255);
  const black=(x,y)=>{const i=(y*w+x)*4;p[i]=p[i+1]=p[i+2]=0;};
  for(let x=10;x<70;x++)for(let y=20;y<23;y++)black(x,y);
  for(let y=30;y<70;y++)black(30,y);
  for(let x=5;x<9;x++)black(x,5);
  const segments=traceCandidates(p,w,h,100,20);
  assert.equal(segments.length,2);
  assert.ok(segments.some(s=>s[0]===10&&s[2]===70));
  assert.ok(segments.some(s=>s[1]===30&&s[3]===70));
});

test('floor navigation selects its own sources and retains explicit plan or scan choices',()=>{
  const first={key:'first',space_id:'10',scan_id:'a',geometry_available:true};
  const plan={key:'plan',space_id:'20',plan_url:'https://example.com/plan.png'};
  const scan={key:'scan',space_id:'21',scan_id:'b',geometry_available:true};
  const catalog={floors:[{floor:1,assets:[first]},{floor:2,assets:[plan,scan]},{floor:3,assets:[]}]};
  assert.equal(chooseFloorAsset(catalog,2,'first','10'),scan);
  assert.equal(chooseFloorAsset(catalog,2,'plan','10'),plan);
  assert.equal(chooseFloorAsset(catalog,2,'','20'),plan);
  assert.equal(chooseFloorAsset(catalog,3,'scan','21'),null);
  assert.equal(sameScope({floor:2,space_id:'21',scan_id:'b'},{floor:2,space_id:'21',scan_id:'c'}),false);
  assert.equal(sameScope({floor:2,asset_key:'plan1'},{floor:2,asset_key:'plan2'}),false);
});
