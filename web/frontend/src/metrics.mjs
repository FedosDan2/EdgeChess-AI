// Pure helpers also used by the Node tests; only measured samples go here.
export function percentile(values, percent) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const position = ((sorted.length - 1) * percent) / 100;
  const lo = Math.floor(position),
    hi = Math.ceil(position);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (position - lo);
}
export function scaleBox(box, sourceWidth, sourceHeight, width, height) {
  return [
    (box[0] * width) / sourceWidth,
    (box[1] * height) / sourceHeight,
    ((box[2] - box[0]) * width) / sourceWidth,
    ((box[3] - box[1]) * height) / sourceHeight,
  ];
}

export function comparePlacements(actual, expected) {
  const expand = placement => {
    if (typeof placement !== "string") return null;
    const ranks = placement.split("/");
    if (ranks.length !== 8) return null;
    const cells = [];
    for (const rank of ranks) {
      const row = [];
      for (const symbol of rank) {
        if (/^[1-8]$/.test(symbol)) row.push(...Array(Number(symbol)).fill(""));
        else if (/^[prnbqkPRNBQK]$/.test(symbol)) row.push(symbol);
        else return null;
      }
      if (row.length !== 8) return null;
      cells.push(...row);
    }
    return cells;
  };
  const observed = expand(actual), reference = expand(expected);
  if (!observed || !reference) return null;
  return { correct: observed.filter((piece, i) => piece === reference[i]).length, total: 64 };
}
