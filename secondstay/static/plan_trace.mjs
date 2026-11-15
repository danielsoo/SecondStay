// Local raster line candidates. This does not classify rooms, openings or wall heights.
// Operates only on a user-selected file, never on cross-origin CoStar images.
export function traceCandidates(pixels, width, height, threshold = 100, minimum = 25) {
  const ink = (x, y) => {
    const i = (y * width + x) * 4;
    return pixels[i + 3] > 100 && (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3 < threshold;
  };
  const lines = [];
  for (const vertical of [false, true]) {
    const across = vertical ? width : height, along = vertical ? height : width;
    const previous = [];
    for (let a = 0; a < across; a++) {
      let start = -1;
      for (let b = 0; b <= along; b++) {
        const dark = b < along && ink(vertical ? a : b, vertical ? b : a);
        if (dark && start < 0) start = b;
        if (!dark && start >= 0) {
          if (b - start >= minimum) {
            const neighbor = previous.find(s => a - s.at <= 4 && a - s.at >= 0 && Math.abs(start - s.start) < 5 && Math.abs(b - s.end) < 5);
            if (neighbor) neighbor.at = a;
            else {
              previous.push({ at: a, start, end: b });
              lines.push(vertical ? [a, start, a, b] : [start, a, b, a]);
            }
          }
          start = -1;
        }
      }
      while (previous.length && a - previous[0].at > 4) previous.shift();
    }
  }
  return lines.slice(0, 2000);
}
