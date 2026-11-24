/* The profile "address" field is free text for June's character: often an
 * instruction ("Use sir only occasionally…"), not a name. The HUD only shows it
 * when it already reads as a short form of address; otherwise it shows none.
 * The stored profile is never changed. */
const MAX = 24;

export function displayAddress(field: string | null | undefined): string {
  const value = (field ?? "").replace(/\s+/g, " ").trim().replace(/^["“'‘]+|["”'’]+$/g, "");
  if (!value || value.length > MAX) return "";
  if (value.split(" ").length > 3) return "";
  // Sentence punctuation or instruction words mean this is guidance, not an address.
  if (/[.:;!?()\[\]{}<>]/.test(value)) return "";
  if (/\b(use|call|say|only|never|always|sometimes|occasionally|don'?t|do not|avoid|prefer|when|if)\b/i.test(value)) return "";
  return value;
}
