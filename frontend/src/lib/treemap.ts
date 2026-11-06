export type Rect = { x: number; y: number; w: number; h: number };

/** Squarified treemap (Bruls, Huizing, van Wijk): keeps tiles close to square. Values must be
 * positive; the output is in the same order as the input. */
export function squarify(values: number[], box: Rect): Rect[] {
  const total = values.reduce((a, b) => a + b, 0);
  const out: Rect[] = new Array(values.length);
  if (!total || box.w <= 0 || box.h <= 0) return values.map(() => ({ ...box, w: 0, h: 0 }));
  const order = values.map((v, i) => [v * ((box.w * box.h) / total), i] as const).sort((a, b) => b[0] - a[0]);
  let rest: Rect = { ...box };
  let row: (readonly [number, number])[] = [];

  const worst = (items: typeof row, side: number) => {
    const sum = items.reduce((a, [v]) => a + v, 0);
    const max = Math.max(...items.map(([v]) => v)), min = Math.min(...items.map(([v]) => v));
    return Math.max((side * side * max) / (sum * sum), (sum * sum) / (side * side * min));
  };
  const place = (items: typeof row) => {
    const sum = items.reduce((a, [v]) => a + v, 0);
    const wide = rest.w >= rest.h;
    const thick = wide ? sum / rest.h : sum / rest.w;
    let at = wide ? rest.y : rest.x;
    for (const [v, i] of items) {
      const len = v / thick;
      out[i] = wide ? { x: rest.x, y: at, w: thick, h: len } : { x: at, y: rest.y, w: len, h: thick };
      at += len;
    }
    rest = wide ? { x: rest.x + thick, y: rest.y, w: rest.w - thick, h: rest.h } : { x: rest.x, y: rest.y + thick, w: rest.w, h: rest.h - thick };
  };

  for (const item of order) {
    const side = Math.min(rest.w, rest.h);
    if (!row.length || worst([...row, item], side) <= worst(row, side)) row.push(item);
    else { place(row); row = [item]; }
  }
  if (row.length) place(row);
  return out;
}
