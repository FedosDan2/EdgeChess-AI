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
