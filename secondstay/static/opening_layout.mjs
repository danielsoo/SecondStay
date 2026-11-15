// Partition each wall around its recorded openings. No solid panel crosses a hole.
export function wallSections(wall, defaultHeight = 2.8) {
  const [a,b,c,d] = wall.segment, length = Math.hypot(c-a,d-b);
  const openings = (wall.openings || []).map(o => {
    const bottom = o.sill_m ?? (o.kind === 'window' ? 0.85 : 0);
    return {...o, start: Math.max(0,o.start), end: Math.min(length,o.end),
      bottom, top: bottom + (o.height_m ?? (o.kind === 'window' ? 1.3 : 2.1))};
  }).filter(o => o.end > o.start && o.top > o.bottom);
  const height = wall.height_m || Math.max(defaultHeight, ...openings.map(o => o.top + 0.12));
  const cuts = (values, max) => [...new Set(values.map(v => Math.max(0,Math.min(max,v))))].sort((x,y)=>x-y);
  const xs = cuts([0,length,...openings.flatMap(o=>[o.start,o.end])],length);
  const ys = cuts([0,height,...openings.flatMap(o=>[o.bottom,o.top])],height);
  const panels = [];
  for(let i=1;i<xs.length;i++) for(let j=1;j<ys.length;j++) {
    const x=(xs[i-1]+xs[i])/2,y=(ys[j-1]+ys[j])/2;
    if(!openings.some(o=>x>o.start&&x<o.end&&y>o.bottom&&y<o.top))
      panels.push({start:xs[i-1],end:xs[i],bottom:ys[j-1],top:ys[j]});
  }
  return {height,length,panels,openings};
}
