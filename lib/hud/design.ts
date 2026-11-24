/* Which HUD design this build shows (inlined at compile time). "observatory" is June's final design (user-chosen
 * 2026-11-23): darker, frameless, the knowledge constellation as a night sky behind the unchanged orb.
 * NEXT_PUBLIC_JUNE_DESIGN=classic or =specimen at build time selects the earlier designs (rollback / reference). */
export type Design = "classic" | "observatory" | "specimen";
export const designFrom = (value: string | undefined): Design => value === "classic" ? "classic" : value === "specimen" ? "specimen" : "observatory";
export const DESIGN: Design = designFrom(process.env.NEXT_PUBLIC_JUNE_DESIGN);
