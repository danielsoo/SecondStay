import * as THREE from "three";
import { CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { CSS3DObject } from "three/addons/renderers/CSS3DRenderer.js";
import { floorPose, validFloor, sameScope, chooseFloorAsset, floorCoverage } from "./floor_motion.mjs";
import { wallSections } from "./opening_layout.mjs";
import { traceCandidates } from "./plan_trace.mjs";
import { floorAccounting, gridSegments, GRID_FT } from "./floor_accounting.mjs";

export function floorExplorer(host, data, makeStage, initial, onFloor, onTour = () => {}) {
  const stage = makeStage(host, { bloom: false }), { scene, camera, controls, ticks } = stage;
  controls.autoRotate = false;
  scene.fog = null;
  scene.background = new THREE.Color(0xf2f1ec);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x9a968a, 0.95));
  const sun = new THREE.DirectionalLight(0xffead3, 1.0); sun.position.set(-30,60,35); scene.add(sun);
  const b = data.building, o = data.outside, count = Math.max(1, b.stories || 1);
  let selected = validFloor(initial, count) || 1, mode = "isolated", alive = true, request = 0;
  const basis = o.bbox, lat = (basis[1] + basis[3]) / 2, lon = (basis[0] + basis[2]) / 2;
  const rings = o.footprint.map(ring => ring.map(([x, y]) => [(x - lon) * 111320 * Math.cos(lat * Math.PI / 180), (y - lat) * 110540]));
  const pts = rings.flat(), xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 10);
  const height = (o.height_ft || count * 12) * 0.3048, storyH = height / count;
  const context = new THREE.Group(); scene.add(context);
  const kx = 111320 * Math.cos(lat * Math.PI / 180), ky = 110540;
  for (const [bounds, suffix, elevation] of [[o.bbox, "", -0.5], [o.context_bbox, "?context=1", -0.6]]) {
    if (!bounds?.length) continue;
    const [w,s,e,n] = bounds;
    const mat = new THREE.MeshBasicMaterial({color:0xffffff});
    const ground = new THREE.Mesh(new THREE.PlaneGeometry((e-w)*kx,(n-s)*ky).rotateX(-Math.PI/2),mat);
    ground.position.set(((w+e)/2-lon)*kx-cx,elevation,-(((s+n)/2-lat)*ky-cy));
    ground.visible=false; context.add(ground);
    new THREE.TextureLoader().load(`/api/spaces/${b.property_id}/aerial.jpg${suffix}`,texture=>{
      if(!alive) {texture.dispose(); return;}
      texture.colorSpace=THREE.SRGBColorSpace; texture.anisotropy=8;
      mat.map=texture; mat.needsUpdate=true; ground.visible=true;
    });
  }
  const levels = [], picks = [], vectorRoot = new THREE.Group(), planSlab = new THREE.Group();
  // Room floors of listed suites: hovering names the suite, clicking walks into its 3D tour.
  const roomPicks = []; let hovered = null, touring = false;
  // Hover focus: the rest of the floor fades to a dark, see-through model and the pointed room rises as a tile.
  let focusNow = 0, focusTarget = 0, liftTile = null, wallTop = 2.4;
  const DIM_COLOR = new THREE.Color(0xe9e7e1); // fade toward the paper, not into the dark
  const scanOf = (model) => model.scan_id || (b.spaces || []).find(s => String(s.id) === String(model.space_id))?.scans?.[0] || "";
  const marketFloors = new Set((b.spaces || []).map(s => s.floor).filter(Boolean));
  const label = document.createElement("span"); label.className = "tag3d cyan";
  const marker = new CSS2DObject(label);
  const slabGeometry = rings.map(r => new THREE.ExtrudeGeometry(new THREE.Shape(r.map(([x, y]) => new THREE.Vector2(x - cx, y - cy))), { depth: 0.45, bevelEnabled: false }).rotateX(-Math.PI / 2));
  for (let n = 1; n <= count; n++) {
    const group = new THREE.Group();
    const material = new THREE.MeshStandardMaterial({ color: 0xb8b4a8, transparent: true, opacity: 0.7, roughness: 0.8, side: THREE.DoubleSide });
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x8c8a82, transparent: true, opacity: 0.35 });
    slabGeometry.forEach(geometry => {
      const mesh = new THREE.Mesh(geometry, material); mesh.userData.floor = n; group.add(mesh); picks.push(mesh);
      group.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry), edgeMaterial));
    });
    scene.add(group); levels.push({ group, material, edgeMaterial, number: n });
  }
  let scope = {}, geometry = null, geometrySpan = span, flight = null;
  // While a floor's sources are being read, show nothing in their place: no reference plan, grid or "not placed" list.
  let loading = false;
  const legend = document.createElement("div");
  legend.style.cssText = "display:flex;flex-wrap:wrap;gap:16px;margin:12px 0;color:var(--muted);font-size:13px";
  document.getElementById("floor-source").before(legend);
  const coverage = document.createElement("section");
  coverage.className = "panel floor-coverage";
  coverage.style.cssText = "padding:12px 16px;margin:0 0 12px;border-color:var(--line)";
  coverage.setAttribute("aria-label","Interior model coverage");
  coverage.hidden = true;
  host.before(coverage);
  // What every part of the selected floor is, and why it is or is not drawn.
  const ledger = document.createElement("section");
  ledger.className = "panel floor-ledger";
  ledger.setAttribute("aria-label", "What is on record for this floor");
  host.before(ledger);
  const gridRoot = new THREE.Group();
  const gridMaterial = new THREE.LineBasicMaterial({ color: 0x1c7a98, transparent: true, opacity: 0.35 });
  const gridTag = document.createElement("span"); gridTag.className = "tag3d";
  const gridLabel = new CSS2DObject(gridTag);
  // A short card on the floor itself: what is on record here.
  const cardEl = document.createElement("div"); cardEl.className = "floor-card";
  const card = new CSS2DObject(cardEl);
  // The building's whole-floor plan, laid on a floor that has no record of its own (reference only).
  let refImage = null;
  const reference = data.reference_plan;
  if (reference?.url) {
    const img = document.createElement("img"); img.alt = "Whole-floor plan on record (reference)"; img.style.opacity = "0";
    img.onload = () => {
      const fx = Math.max(...xs) - Math.min(...xs), fy = Math.max(...ys) - Math.min(...ys);
      refImage.scale.setScalar(Math.min(fx / img.naturalWidth, fy / img.naturalHeight) * 0.98); refImage.userData.ready = true;
    };
    img.src = reference.url;
    refImage = new CSS3DObject(img); refImage.rotation.x = -Math.PI / 2; refImage.position.set(0, 0.55, 0);
    refImage.scale.setScalar(0.0001);
  }
  const geometryCache = new Map(), scopeKey = s => `${s.floor}:${s.asset_key || ""}`;
  let asset = null;
  const planView = document.getElementById("floor-plan-view");
  const detail = document.getElementById("floor-detail"), note = document.getElementById("floor-note");
  const title = document.getElementById("floor-title");
  const source = document.getElementById("floor-source");
  const link = (container, text, url) => {
    const a=document.createElement("a"); a.textContent=text; a.href=url; a.target="_blank"; a.rel="noopener"; container.appendChild(a); return a;
  };
  const tourUrl = id => `https://my.matterport.com/show/?m=${encodeURIComponent(id)}`;
  const unassigned = document.getElementById("floor-unassigned");
  unassigned.hidden = !data.floor_sources?.unassigned?.length;
  const unassignedList = unassigned.querySelector("div"); unassignedList.replaceChildren();
  for(const item of data.floor_sources?.unassigned || []) link(unassignedList, item.label, item.plan_url || tourUrl(item.scan_id));
  function showSource() {
    source.replaceChildren(); planView.replaceChildren();
    const onlyPlan = mode === "isolated" && !geometry?.available && !!asset && (!asset.geometry_available || !!geometry);
    planView.hidden = !onlyPlan; host.classList.toggle("plan-only",onlyPlan);
    if(asset?.plan_url) {
      link(source, `Open original 2D plan · ${asset.label}`, asset.plan_url);
      if(onlyPlan) {
        const img=document.createElement("img"); img.src=asset.plan_url; img.alt=`Original 2D plan · Floor ${selected} · ${asset.label}`;
        const caption=document.createElement("p"); caption.textContent="Original 2D plan · image only; no 3D interior vectors linked to this source.";
        img.onerror=()=>{ if(alive && img.isConnected) {img.hidden=true; caption.textContent="The plan preview could not load. Open the original plan below.";} };
        planView.append(img,caption);
      }
    }
    if(asset?.model_source_url) link(source, "Placement / reconstruction source", asset.model_source_url);
    if(asset?.scan_id) {
      link(source, `Open original scan · ${asset.label}`, tourUrl(asset.scan_id));
      if(onlyPlan && !asset.plan_url) {
        const p=document.createElement("p"); p.textContent="A scan is linked to this floor, but usable interior vectors are not available in the local cache.";
        planView.appendChild(p); link(planView,"Open original 3D tour",tourUrl(asset.scan_id));
      }
    }
    if(asset?.space_id && String(data.space?.id || "") !== asset.space_id) {
      const review=document.createElement("a"); review.textContent=`Review ${asset.label}`;
      review.href=`#/space/${b.property_id}?${new URLSearchParams({floor:selected,view:mode,space:asset.space_id,interior:asset.key})}`;
      source.appendChild(review);
    }
  }
  const clearVectors = () => {
    roomPicks.length = 0; hovered = null; liftTile = null; focusNow = focusTarget = 0;
    for (const child of [...vectorRoot.children]) {
      child.geometry?.dispose();
      if (child.material) [].concat(child.material).forEach(m => m.dispose());
      vectorRoot.remove(child);
    }
  };
  const SQFT = n => n == null ? "area not recorded" : `${Math.round(n).toLocaleString("en-US")} sq ft`;
  const COLORS = { drawn: "#2F6B45", listed_unplaced: "#C08A2E", listed_plan: "#D9B370", listed_tour: "#1C7A98",
    listed_none: "#A9A69C", leased: "#7FA9B8", unrecorded: "#C9C6BD" };
  function showLedger(models) {
    const a = floorAccounting({ building: b, catalog: data.floor_sources, floor: selected, shownModels: models,
      footprintSqft: o.footprint_sqft || null });
    ledger.replaceChildren();
    const head = document.createElement("strong");
    const marketCount = (b.spaces || []).filter(s => s.floor === selected).length;
    head.textContent = `Floor ${selected} · ${marketCount ? `${marketCount} space${marketCount === 1 ? "" : "s"} on the market` : "no space on the market"}` + (a.floorSqft ? ` · floor ${SQFT(a.floorSqft)} (${a.basis})` : "");
    const bar = document.createElement("div"); bar.className = "ledger-bar";
    const total = Math.max(a.floorSqft || 0, a.parts.reduce((t, x) => t + (x.sqft || 0), 0)) || 1; // the empty end of the bar is the rest of the floor
    for (const part of a.parts) {
      if (!part.sqft) continue;
      const seg = document.createElement("span"); seg.style.width = `${(part.sqft / total * 100).toFixed(2)}%`;
      seg.style.background = COLORS[part.kind]; seg.className = part.kind === "unrecorded" ? "hatched" : "";
      seg.title = `${part.label} · ${SQFT(part.sqft)}`; bar.append(seg);
    }
    const list = document.createElement("ul"); list.className = "ledger-list";
    for (const part of a.parts) {
      const li = document.createElement("li");
      const dot = document.createElement("i"); dot.style.background = COLORS[part.kind];
      const name = document.createElement("b"); name.textContent = part.label;
      const size = document.createElement("span"); size.className = "num"; size.textContent = SQFT(part.sqft);
      const why = document.createElement("span"); why.className = "sub"; why.textContent = part.reason;
      li.append(dot, name, size, why);
      if (part.asset) {
        const btn = document.createElement("button"); btn.className = "btn"; btn.textContent = "Open model";
        btn.onclick = () => { data.interiorAsset = part.asset; selectFloor(selected, "isolated"); }; li.append(btn);
      } else if (part.url) link(li, "Open plan", part.url);
      else if (part.scan) {
        const btn = document.createElement("button"); btn.className = "btn"; btn.textContent = "Walk inside";
        btn.onclick = () => onTour({ suite: part.label.replace(/^Suite /, ""), space_id: String(part.space_id || ""), scan: part.scan, name: part.label });
        li.append(btn);
      }
      list.append(li);
    }
    const foot = document.createElement("p"); foot.className = "sub"; foot.style.margin = "6px 0 0";
    foot.textContent = a.note + ` Where a space has no plan, the floor shows a ${GRID_FT} ft reference grid, not invented rooms.`;
    ledger.append(head, bar, list, foot);
    const lines = a.parts.filter(p => p.kind !== "unrecorded").slice(0, 5).map(p =>
      `<div><b>${p.label}</b> · ${SQFT(p.sqft)} <span class="why">· ${p.placed ? "placed model, not shown" : ({drawn:"drawn", listed_unplaced:"model not placed", listed_plan:"plan image only",
        listed_tour:"tour only", listed_none:"no plan or scan", leased:"tenant plans not public"})[p.kind] || ""}</span></div>`);
    cardEl.innerHTML = `<div><b>Floor ${selected}</b> · ${a.floorSqft ? SQFT(a.floorSqft) : "size not recorded"}</div>` +
      (lines.join("") || '<div class="why">No space on the market on this floor.</div>');

  }
  function showGrid(value) {
    for (const child of [...gridRoot.children]) { child.geometry?.dispose(); gridRoot.remove(child); }
    let outlines = null, lift = 0.5;
    if (value?.available && value.registered && value.floor_outline && value.units !== "plan_relative") {
      outlines = [value.floor_outline]; lift = 0.3;
    } else if (!value?.available) {
      outlines = rings.map(r => r.map(([x, y]) => [x - cx, y - cy]));
    }
    if (!outlines) { card.position.set(-span * 0.6, 3, -span * 0.4); return; } // a suite model with no floor frame: no grid
    const segs = gridSegments(outlines, GRID_FT * 0.3048);
    const points = segs.flatMap(([x1, y1, x2, y2]) => [new THREE.Vector3(x1, lift, -y1), new THREE.Vector3(x2, lift, -y2)]);
    // On a bare slab the grid is dark so it reads against the light surface; around drawn rooms it is light.
    gridMaterial.color.set(value?.available ? 0x1c7a98 : 0x5e5c55); gridMaterial.opacity = value?.available ? 0.35 : 0.55;
    if (points.length) gridRoot.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(points), gridMaterial));
    gridTag.textContent = value?.available ? `${GRID_FT} ft reference grid · blank areas are not on the market or have no plan` : `No plan on record for the spaces here · ${GRID_FT} ft reference grid`;
    const ox = outlines.flat().map(p => p[0]), oy = outlines.flat().map(p => p[1]);
    gridLabel.position.set((Math.min(...ox) + Math.max(...ox)) / 2, lift + 1.2, -Math.max(...oy)); // far edge, clear of the floor label
    card.position.set(Math.min(...ox) - 1, lift + 2.5, -Math.max(...oy)); // the far left corner, off the drawing
    gridRoot.add(gridLabel);
  }
  function showPending() {
    loading = true;
    ledger.replaceChildren();
    const head = document.createElement("strong"); head.textContent = `Floor ${selected} · reading interior sources…`;
    ledger.append(head);
    cardEl.innerHTML = `<div><b>Floor ${selected}</b> · <span class="why">reading…</span></div>`;
  }
  function showGeometry(value) {
    loading = false;
    showLedger(value?.available ? (value.assembly || [value]) : []);
    showGrid(value);
    geometry = value; clearVectors(); geometrySpan = span; legend.replaceChildren();
    coverage.replaceChildren(); coverage.hidden = true;
    for(const child of [...planSlab.children]) { child.geometry?.dispose(); child.material?.dispose(); planSlab.remove(child); }
    if (!value?.available) return;
    if(value.registered && value.floor_outline) {
      if(value.floor_scope === "whole_floor") {
        const shape = new THREE.Shape(value.floor_outline.map(([x,y])=>new THREE.Vector2(x,y)));
        const mesh = new THREE.Mesh(new THREE.ExtrudeGeometry(shape,{depth:.22,bevelEnabled:false}).rotateX(-Math.PI/2),new THREE.MeshStandardMaterial({color:0xb2bec1,transparent:true,opacity:.26,side:THREE.DoubleSide}));
        planSlab.add(mesh);
      } else {
        // A source perimeter is context, not evidence of an empty floor surface.
        const outline = new THREE.BufferGeometry().setFromPoints(value.floor_outline.map(([x,y])=>new THREE.Vector3(x,.25,-y)));
        const boundary = new THREE.LineLoop(outline,new THREE.LineDashedMaterial({color:0x1c7a98,dashSize:1,gapSize:.6,transparent:true,opacity:.65}));
        boundary.computeLineDistances(); planSlab.add(boundary);
        coverage.hidden = false;
        const models = value.assembly || [value];
        const heading = document.createElement("strong");
        heading.textContent = `Partial floor model · shown: ${models.map(m=>m.space_id ? `Suite ${m.suite || "on record"}` : m.suite || "Linked geometry").join(" + ")}`;
        const explanation = document.createElement("p"); explanation.style.margin="6px 0";
        explanation.textContent = "The dashed boundary marks the source floor perimeter. Remaining interiors are not represented; their occupancy is not inferred.";
        coverage.append(heading,explanation);
        const missing = floorCoverage(data.floor_sources,b.spaces,selected,models.map(m=>m.space_id).filter(Boolean));
        if(missing.otherModels.length) {
          const line = document.createElement("div"); line.style.cssText="display:flex;align-items:center;flex-wrap:wrap;gap:8px";
          const caption = document.createElement("span"); caption.textContent="Other suite models, not placed in this floor frame:"; line.append(caption);
          for(const item of missing.otherModels) {
            const button=document.createElement("button"); button.className="btn"; button.textContent=`Open ${item.label}`;
            button.onclick=()=>{ data.interiorAsset=item.key; selectFloor(selected,"isolated"); }; line.append(button);
          }
          coverage.append(line);
        }
        if(missing.withoutGeometry.length) {
          const line=document.createElement("p"); line.className="sub"; line.style.margin="8px 0 0";
          line.textContent="Listed spaces without a linked interior model: "+missing.withoutGeometry.map(s=>s.suite ? `Suite ${s.suite}` : "Listed space").join(", ");
          coverage.append(line);
        }
      }
    }
    for(const model of value.assembly || [value]) renderGeometry(model);
    if(value.floor_outline) {
      const xs=value.floor_outline.map(p=>p[0]), ys=value.floor_outline.map(p=>p[1]);
      geometrySpan=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
    }
    const hint=document.createElement('span');
    hint.textContent=value.registered ? "Source floor plan · geographic orientation not registered" : "Suite model · position within the floor not yet linked";
    if(value.units === "plan_relative") hint.textContent += " · drawing proportions only; no physical scale";
    if(value.reconstructed) hint.textContent = "Plan reconstruction draft · " + hint.textContent;
    legend.prepend(hint);
  }
  function renderGeometry(value) {
    const points = value.walls.flatMap(s => [[s[0], s[1]], [s[2], s[3]]]);
    const px = points.map(p => p[0]), py = points.map(p => p[1]);
    const mx = value.registered ? 0 : (Math.min(...px) + Math.max(...px)) / 2, my = value.registered ? 0 : (Math.min(...py) + Math.max(...py)) / 2;
    geometrySpan = Math.max(12, Math.max(...px) - Math.min(...px), Math.max(...py) - Math.min(...py));
    const wallH = Math.min(2.8, storyH * 0.85); wallTop = 0.46 + wallH;
    const material = (color, transparent = false) => new THREE.MeshStandardMaterial({ color, roughness: transparent ? 0.18 : 0.8, metalness: transparent ? 0.2 : 0, transparent, opacity: transparent ? 0.38 : 1, side: THREE.DoubleSide });
    const roomColors = [0xc9ac83, 0x9fb7aa, 0xaaaec8, 0xc9b896, 0x9fb9c4, 0xc5a89a];
    for (const [i,room] of (value.rooms || []).entries()) {
      const shape = new THREE.Shape(room.polygon.map(([x,y])=>new THREE.Vector2(x-mx,y-my)));
      for(const ring of room.holes || []) shape.holes.push(new THREE.Path(ring.map(([x,y])=>new THREE.Vector2(x-mx,y-my))));
      const floor = new THREE.Mesh(new THREE.ShapeGeometry(shape).rotateX(-Math.PI/2), material(roomColors[i % roomColors.length]));
      floor.position.y = 0.48; vectorRoot.add(floor);
      if (value.space_id) {
        floor.userData.room = { suite: value.suite || "", space_id: String(value.space_id), scan: scanOf(value),
          label: room.label && room.label !== "Unlabelled area" ? room.label : "" };
        floor.userData.shape = shape;
        roomPicks.push(floor);
      }
    }
    const wallData = value.wall_segments || value.walls.map(segment=>({segment,openings:[]}));
    for (const wall of wallData) {
      const [x1,y1,x2,y2] = wall.segment, layout = wallSections(wall,wallH);
      if(layout.length < 0.03) continue;
      const box = (start,end,bottom,top,thickness,color,glass=false) => {
        if(end-start < 0.001 || top-bottom < 0.001) return;
        const fraction=(start+end)/2/layout.length;
        const mesh = new THREE.Mesh(new THREE.BoxGeometry(end-start,top-bottom,thickness),material(color,glass));
        mesh.position.set(x1+(x2-x1)*fraction-mx,0.46+(bottom+top)/2,-(y1+(y2-y1)*fraction-my));
        mesh.rotation.y=Math.atan2(y2-y1,x2-x1); vectorRoot.add(mesh);
      };
      layout.panels.forEach(p=>box(p.start,p.end,p.bottom,p.top,0.13,0xe6ded0));
      for(const o of layout.openings) {
        const color=o.kind==='window'?0x398f9e:0xc28a47, trim=0.045;
        // Frames surround the opening; doorway voids stay empty. Swing/entrance type is not recorded.
        box(o.start,o.start+trim,o.bottom,o.top,0.17,color);
        box(o.end-trim,o.end,o.bottom,o.top,0.17,color);
        box(o.start,o.end,o.top-trim,o.top,0.17,color);
        if(o.kind==='window') {
          box(o.start,o.end,o.bottom,o.bottom+trim,0.17,color);
          box(o.start+trim,o.end-trim,o.bottom+trim,o.top-trim,0.025,0x74cad7,true);
        } else box(o.start,o.end,o.bottom,o.bottom+0.025,0.24,0xc28a47);
      }
    }
    const counts=value.counts;
    if(counts) for(const [color,text] of [['#1c7a98',`${counts.windows} window openings`],['#c08a2e',`${counts.doors} doorways`],['#8c8a82',`${counts.rooms} room boundaries`]]) {
      const item=document.createElement('span'); item.style.color=color; item.textContent=(value.suite ? value.suite+' · ' : '')+'● '+text; legend.appendChild(item);
    }
  }

  function frame() {
    marker.position.z = (mode === "isolated" ? geometrySpan : span) * 0.52;
    const p = floorPose(selected, count, storyH, span, mode, selected);
    const end = floorPose(count, count, storyH, span, mode, selected);
    const target = mode === "exploded" ? new THREE.Vector3(span * 0.08, end.y * 0.48, 0) : new THREE.Vector3(p.x, p.y, p.z);
    const wide = Math.max(1, 1.2 / camera.aspect);
    const range = (mode === "isolated" ? geometrySpan * 1.18 : Math.max(span * 1.5, end.y * 1.25)) * wide;
    const position = target.clone().add(new THREE.Vector3(range * 0.55, range * (mode === "isolated" ? 0.95 : 0.65), range));
    flight = { at: performance.now(), from: camera.position.clone(), look: controls.target.clone(), position, target };
    controls.autoRotate = false;
  }
  function arrange() {
    context.visible = false; // Floor-plan coordinates have no geographic registration.
    const floor = levels[selected - 1];
    floor.group.add(vectorRoot, marker, planSlab, gridRoot, card);
    if (refImage) floor.group.add(refImage);
    marker.position.set(0, 3.5, span * 0.52);
    label.textContent = `Floor ${selected}${asset ? " · " + asset.label : ""}`;
    title.textContent = label.textContent;
    document.getElementById("floor-scope-note").textContent = data.space && String(data.space.id) !== scope.space_id
      ? `Viewing Floor ${selected}${asset ? " · " + asset.label : ""}. The checklist below still reviews Suite ${data.space.suite || "on record"} on Floor ${data.space.floor}. Use the review link below to change the checklist scope.`
      : !data.space ? "The interior view focuses on this source. The checklist below reviews the building." : "The interior view and checklist refer to the selected suite.";
    showSource();
    detail.hidden = false;
    host.classList.add("floor-mode");
    document.querySelectorAll("[data-scene-mode]").forEach(el => el.setAttribute("aria-pressed", String(el.dataset.sceneMode === mode)));
    document.getElementById("floor-picker").value = String(selected);
    frame();
  }
  async function selectFloor(number, nextMode = mode) {
    const checked = validFloor(number, count);
    if (checked === null) return;
    const nextAsset = chooseFloorAsset(data.floor_sources, checked, data.interiorAsset, data.space?.floor === checked ? data.space.id : "");
    const nextScope = {floor:checked,space_id:nextAsset?.space_id || "",scan_id:nextAsset?.scan_id || "",asset_key:nextAsset?.key || ""};
    const changed = !sameScope(scope,nextScope) || !geometry;
    selected = checked; mode = nextMode; asset = nextAsset; scope = nextScope;
    data.interiorAsset = asset?.key || "";
    if (changed) { showGeometry(null); showPending(); note.textContent = "Reading interior sources for this floor…"; }
    arrange(); onFloor?.(selected, mode, asset?.key);
    if (!changed) return;
    const mine = ++request, requested = { ...scope };
    const cached = geometryCache.get(scopeKey(scope));
    if (cached) { showGeometry(cached); note.textContent = cached.note; showSource(); frame(); return; }
    if(!asset?.geometry_available && !asset?.scan_id) {
      const borrowed = asset?.plan_url ? null : await repeatedCore(selected);
      if (!alive || mine !== request) return;
      if (borrowed) { geometryCache.set(scopeKey(scope), borrowed); showGeometry(borrowed); note.textContent = borrowed.note; showSource(); frame(); return; }
      const result={available:false,note:asset?.plan_url ? "CoStar plan linked to this floor. The original image is shown without inferring walls, orientation or dimensions." : "No floor-linked plan or scan is recorded for this selection. The outline repeats the building footprint." + (reference?.url ? " The building's whole-floor plan on record is laid on the floor as a reference; it is not this floor's own layout." : "")};
      geometryCache.set(scopeKey(scope),result); showGeometry(result); note.textContent=result.note; showSource(); return;
    }
    try {
      const params = new URLSearchParams({ floor: selected, space: scope.space_id, scan: scope.scan_id });
      const response = await fetch(`/api/spaces/${b.property_id}/floor-geometry?${params}`);
      const result = await response.json();
      if (!alive || mine !== request || !sameScope(requested, scope)) return;
      if (!response.ok) throw new Error(result.error || "Interior geometry is unavailable.");
      geometryCache.set(scopeKey(scope), result);
      showGeometry(result); note.textContent = result.note;
      showSource(); frame();
    } catch (error) {
      if (alive && mine === request) { showGeometry(null); note.textContent = error.message; showSource(); }
    }
  }
  // The core (stairs, elevators, restrooms) of an office tower usually repeats floor to floor.
  async function repeatedCore(floor) {
    const donors = (data.floor_sources?.floors || []).flatMap(f => (f.assets || [])
      .filter(a => a.registered && a.geometry_available && a.units !== "plan_relative").map(a => ({ floor: f.floor, asset: a })))
      .sort((p, q) => Math.abs(p.floor - floor) - Math.abs(q.floor - floor));
    for (const { floor: from, asset: donor } of donors) {
      if (from === floor) continue;
      try {
        const params = new URLSearchParams({ floor: from, space: donor.space_id || "", scan: donor.scan_id || "" });
        const response = await fetch(`/api/spaces/${b.property_id}/floor-geometry?${params}`);
        const result = await response.json();
        if (!response.ok || !result.floor_outline) continue;
        const core = (result.assembly || []).filter(m => !m.space_id && (m.walls || []).length);
        return { available: true, registered: true, units: result.units, floor_scope: "partial", floor_outline: result.floor_outline,
          assembly: core.length ? core.map(m => ({ ...m, suite: `Core repeated from floor ${from}` })) : [],
          walls: core[0]?.walls || [], repeated_from: from,
          note: core.length
            ? `No plan or scan is on record for floor ${floor}. The shared core and floor outline are repeated from floor ${from}, assuming the core is the same on every floor; that assumption is to be confirmed.`
            : `No plan or scan is on record for floor ${floor}. The floor outline is repeated from floor ${from}.` };
      } catch { continue; }
    }
    return null;
  }
  let last = performance.now();
  ticks.push(() => {
    const now = performance.now(), blend = 1 - Math.exp(-Math.min(100, now - last) / 180); last = now;
    // Ease the hover focus in and out, and float the pointed room just above the wall tops.
    const ease = Math.min(1, blend * 1.6);
    if (Math.abs(focusTarget - focusNow) > 0.002) { focusNow += (focusTarget - focusNow) * ease; applyFocus(focusNow); }
    else if (focusNow !== focusTarget) { focusNow = focusTarget; applyFocus(focusNow); }
    if (liftTile) {
      const y = liftTile.position.y + (wallTop + 0.35 - liftTile.position.y) * ease;
      liftTile.position.y = liftTile.userData.edge.position.y = y;
    }
    levels.forEach(level => {
      const p = floorPose(level.number, count, storyH, span, mode, selected);
      level.group.position.x += (p.x - level.group.position.x) * blend;
      level.group.position.y += (p.y - level.group.position.y) * blend;
      level.group.position.z += (p.z - level.group.position.z) * blend;
      const dim = marketFloors.has(level.number) || level.number === selected ? 1 : 0.5; // not on the market: kept only for the building's shape
      level.material.opacity += (p.opacity * dim * (level.number === selected ? (geometry?.available && mode === "isolated" ? 0.08 : 0.95) : 0.9) - level.material.opacity) * blend;
      const onMarket = marketFloors.has(level.number);
      level.material.color.set(level.number === selected ? 0xa9c3cb : onMarket ? 0xc3cbc8 : 0xdedbd3);
      level.edgeMaterial.opacity = level.number === selected ? 0.45 : 0.18;
      const physicalFrame = geometry?.registered && geometry.units !== "plan_relative";
      const showingInterior = geometry?.available && (mode === "isolated" || physicalFrame);
      for(const child of level.group.children) if(child !== vectorRoot && child !== marker && child !== planSlab && child !== gridRoot && child !== card && child !== refImage) child.visible = !(showingInterior && level.number === selected);
      card.visible = mode === "isolated";
      if (refImage) {
        // Shown only on a floor with nothing drawn: a repeated core sits in a different, plan-based frame.
        refImage.visible = mode === "isolated" && !loading && !geometry?.available && !!refImage.userData.ready;
        refImage.element.style.opacity = refImage.visible ? "0.82" : "0";
      }
      gridRoot.visible = mode === "isolated" && !loading;
      gridTag.style.display = mode === "isolated" && !loading ? "" : "none";
      level.group.visible = level.material.opacity > 0.005;
      vectorRoot.visible = !!showingInterior;
      planSlab.visible = !!geometry?.registered && !!showingInterior;
      marker.element.style.display = "";
    });
    if (flight) {
      const t = Math.min(1, (now - flight.at) / (matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : 900));
      const e = t * t * (3 - 2 * t);
      camera.position.lerpVectors(flight.from, flight.position, e); controls.target.lerpVectors(flight.look, flight.target, e);
      if (flight.then && e >= flight.thenAt) { const then = flight.then; flight.then = null; then(); }
      if (t === 1) flight = null;
    }
  });
  const ray = new THREE.Raycaster(), pointer = new THREE.Vector2(); let down;
  stage.renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; flight = null; });
  stage.renderer.domElement.addEventListener("wheel", () => { flight = null; }, { passive: true });
  const roomAt = (e) => {
    const r = stage.renderer.domElement.getBoundingClientRect();
    pointer.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    ray.setFromCamera(pointer, camera);
    return mode === "isolated" && vectorRoot.visible ? ray.intersectObjects(roomPicks)[0] : null;
  };
  const roomTag = document.createElement("span"); roomTag.className = "tag3d room-tag"; roomTag.style.display = "none";
  const roomLabel = new CSS2DObject(roomTag); scene.add(roomLabel);
  const roomName = (room) => (room.suite ? `Suite ${room.suite}` : "Listed space") + (room.label ? ` · ${room.label}` : "");
  // Every drawn mesh keeps its own colour and opacity, so focus can fade it and restore it exactly.
  function applyFocus(t) {
    for (const child of vectorRoot.children) {
      const m = child.material;
      if (!m || child === liftTile || child.userData.isTileEdge) continue;
      const base = child.userData.base || (child.userData.base = { color: m.color.clone(), opacity: m.opacity, transparent: m.transparent });
      m.color.copy(base.color).lerp(DIM_COLOR, 0.6 * t);
      m.opacity = base.opacity * (1 - 0.62 * t);
      m.transparent = base.transparent || t > 0.001;
      m.depthWrite = t < 0.5 || !m.transparent ? true : false;
    }
  }
  function dropTile() {
    if (!liftTile) return;
    for (const part of [liftTile, liftTile.userData.edge]) {
      if (!part) continue;
      part.geometry.dispose(); part.material.dispose(); vectorRoot.remove(part);
    }
    liftTile = null;
  }
  function raiseTile(mesh) {
    dropTile();
    const room = mesh.userData.room, accent = room.scan ? 0x1c7a98 : 0xc08a2e;
    const geometry = new THREE.ExtrudeGeometry(mesh.userData.shape, { depth: 0.22, bevelEnabled: false }).rotateX(-Math.PI / 2);
    // A copy of the room's own colour: the original is darkened by the focus fade.
    liftTile = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: (mesh.userData.base?.color || mesh.material.color).clone(),
      emissive: accent, emissiveIntensity: 0.28, roughness: 0.55 }));
    const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30), new THREE.LineBasicMaterial({ color: accent }));
    edge.userData.isTileEdge = true; liftTile.userData.edge = edge;
    liftTile.position.y = edge.position.y = 0.48;
    vectorRoot.add(liftTile, edge);
  }
  function highlight(hit) {
    const mesh = hit?.object || null;
    const above = (point) => new THREE.Vector3(point.x, vectorRoot.getWorldPosition(new THREE.Vector3()).y + wallTop + 1.6, point.z);
    if (mesh === hovered) { if (hit) roomLabel.position.copy(above(hit.point)); return; }
    hovered = mesh;
    stage.renderer.domElement.style.cursor = mesh ? "pointer" : "";
    roomTag.style.display = mesh ? "" : "none";
    focusTarget = mesh ? 1 : 0;
    if (!mesh) { dropTile(); return; }
    const room = mesh.userData.room;
    raiseTile(mesh);
    roomTag.textContent = roomName(room) + (room.scan ? " · click to walk inside" : " · plan only");
    roomLabel.position.copy(above(hit.point));
  }
  let moveQueued = false;
  stage.renderer.domElement.addEventListener("pointermove", e => {
    if (moveQueued || touring) return; moveQueued = true;
    requestAnimationFrame(() => { moveQueued = false; if (!down) highlight(roomAt(e)); });
  });
  stage.renderer.domElement.addEventListener("pointerleave", () => highlight(null));
  // Dive into the room, then hand over to the tour while the camera is still moving.
  function enterRoom(hit) {
    const room = hit.object.userData.room;
    if (!room.scan) { onTour({ ...room, name: roomName(room) }); return; }
    touring = true; roomTag.style.display = "none"; // keep the lifted room in view during the dive
    const target = hit.point.clone();
    controls.minDistance = 0.5;
    flight = { at: performance.now(), from: camera.position.clone(), look: controls.target.clone(),
      position: target.clone().add(new THREE.Vector3(0.6, 1.6, 1.2)), target,
      thenAt: 0.6, then: () => onTour({ ...room, name: roomName(room) }) };
  }
  stage.renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) { down = null; return; }
    down = null;
    const roomHit = roomAt(e); // also aims the ray for the floor pick below
    if (roomHit && !touring) { enterRoom(roomHit); return; }
    if (mode !== "exploded") return;
    const hit = ray.intersectObjects(picks.filter(m => m.parent.visible))[0];
    if (hit) selectFloor(hit.object.userData.floor, "isolated");
  });
  controls.minDistance = 5; controls.maxDistance = Math.max(height * 5, span * 6);
  camera.position.set(span * 1.5, height + span, span * 2);

  // A local, reviewed image draft stays attached to the selected floor/suite only.
  const file = document.getElementById("plan-file"), preview = document.getElementById("plan-preview");
  const apply = document.getElementById("plan-apply"), draftNote = document.getElementById("plan-draft-note");
  let bitmap = null, segments = [], crop = null, fileScope = null, start = null;
  const ctx = preview.getContext("2d", { willReadFrequently: true });
  const drawDraft = () => {
    ctx.drawImage(bitmap, 0, 0, preview.width, preview.height);
    const area = crop || { x: 0, y: 0, w: preview.width, h: preview.height };
    const pixels = ctx.getImageData(area.x, area.y, area.w, area.h);
    segments = traceCandidates(pixels.data, area.w, area.h, 110, Math.max(12, Math.round(Math.min(area.w, area.h) * 0.045))).map(([a,b,c,d]) => [a + area.x,b + area.y,c + area.x,d + area.y]);
    ctx.strokeStyle = "#00a6e8"; ctx.lineWidth = 2;
    segments.forEach(([a,b,c,d]) => { ctx.beginPath(); ctx.moveTo(a,b); ctx.lineTo(c,d); ctx.stroke(); });
    ctx.strokeStyle = "#ff9f1a"; ctx.strokeRect(area.x, area.y, area.w, area.h);
    draftNote.textContent = `${segments.length} horizontal/vertical line candidates. Drag to crop out titles and legends. Diagonals, curves and openings are not reconstructed. Review the overlay before using this draft. Observations are read from images, not measured.`;
    apply.disabled = !segments.length;
  };
  file.onchange = async () => {
    const f = file.files[0]; if (!f) return;
    if (!/^image\/(png|jpeg|webp)$/.test(f.type) || f.size > 20 * 1024 * 1024) { draftNote.textContent = "Choose a PNG, JPEG or WebP under 20 MB."; return; }
    const selectedScope = { ...scope };
    let image;
    try { image = await createImageBitmap(f); }
    catch { draftNote.textContent = "This image could not be opened. Choose a PNG, JPEG or WebP."; return; }
    if (!alive || !sameScope(selectedScope, scope)) { image.close(); return; }
    bitmap?.close(); bitmap = image; fileScope = selectedScope;
    const scale = Math.min(1, 1000 / Math.max(image.width, image.height));
    preview.width = Math.round(image.width * scale); preview.height = Math.round(image.height * scale);
    preview.hidden = false; crop = null; drawDraft();
  };
  const local = e => { const r = preview.getBoundingClientRect(); return [Math.max(0, Math.min(preview.width - 1, Math.round((e.clientX - r.left) / r.width * preview.width))), Math.max(0, Math.min(preview.height - 1, Math.round((e.clientY - r.top) / r.height * preview.height)))]; };
  preview.onpointerdown = e => { start = local(e); preview.setPointerCapture(e.pointerId); };
  preview.onpointerup = e => {
    if (!start || !bitmap) return;
    const end = local(e), w = Math.abs(end[0] - start[0]), h = Math.abs(end[1] - start[1]);
    if (w > 20 && h > 20) { crop = { x: Math.min(start[0],end[0]), y: Math.min(start[1],end[1]), w, h }; drawDraft(); }
    start = null;
  };
  apply.onclick = () => {
    if (!sameScope(fileScope || {}, scope) || !segments.length) { draftNote.textContent = "Choose a plan for the currently selected floor and suite."; return; }
    request++;
    const area = crop || { x:0, y:0, w:preview.width, h:preview.height }, scale = 10 / Math.max(area.w, area.h);
    const value = { ...scope, available: true, walls: segments.map(([a,b,c,d]) => [a*scale,-b*scale,c*scale,-d*scale]), windows: [], doors: [], source:"Local image draft",
      note: "Draft line extrusion · read from images, not measured. Scale, orientation, wall height and placement are illustrative. This local preview is cleared when leaving the scene." };
    geometryCache.set(scopeKey(scope), value);
    showGeometry(value); mode = "isolated"; arrange();
    note.textContent = value.note;
  };
  return { selectFloor, setMode() {}, get floor() { return selected; },
    // Back from the tour: rise out of the room to the whole floor again.
    leaveTour() { touring = false; highlight(null); controls.minDistance = 5; frame(); },
    dispose() { planView.hidden=true; planView.replaceChildren(); host.classList.remove("plan-only"); legend.remove(); coverage.remove(); ledger.remove(); gridMaterial.dispose(); scene.remove(roomLabel); roomTag.remove(); alive = false; request++; clearVectors(); bitmap?.close(); file.onchange = null; apply.onclick = null; preview.onpointerdown = preview.onpointerup = null; preview.hidden = true; apply.disabled = true; host.classList.remove("floor-mode"); stage.dispose(); } };
}
