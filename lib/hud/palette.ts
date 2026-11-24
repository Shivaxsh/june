/* One source for HUD colours drawn in canvas or inline styles. Cluster colours
 * come from the orb network itself, so the swatches, constellation and orb
 * can never drift apart. CSS colours live as tokens in app/globals.css. */
import { createNetwork } from "@/lib/orb/renderer";

export type RGB = readonly [number, number, number];
const clusters = createNetwork().clusters.map(c => [c.col[0], c.col[1], c.col[2]] as const);

/** Memory, Voice, Personality, Knowledge, Hands, Ears — in orb cluster order. */
export const CLUSTER_RGB: readonly RGB[] = clusters;
export const GRAPH_RGB = { doc: clusters[3], mem: clusters[0], chat: clusters[4], cite: clusters[5] } as const;
export const LABEL_RGB: RGB = [201, 219, 215];
export const LINE_RGB: RGB = [112, 224, 207];

export const rgb = (c: RGB) => `rgb(${c[0]},${c[1]},${c[2]})`;
export const rgba = (c: RGB, alpha: number) => `rgba(${c[0]},${c[1]},${c[2]},${alpha})`;
