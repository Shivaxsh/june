import type { VoiceOption } from "./types";
// Web Speech exposes no gender field. These known female identities are deliberately
// conservative; unknown names never become an arbitrary default voice.
const FEMALE = /\b(?:Samantha|Veena|Neerja|Heera|Swara|Aria|Jenny|Zira|Susan|Hazel|Sonia|Libby|Natasha|Clara|Karen|Moira|Tessa|Kathy|Victoria|Allison|Ava|Nicky|Serena|Shelley|Sandy|Flo)\b|Google UK English Female/i;
export const VOICE_KEY = "june-voice-v1";
export const AUTO_KEY = "june-speak-replies-v1";
export const LANGUAGE_KEY = "june-recognition-language-v1";
export const voiceId = (voice: SpeechSynthesisVoice) => `${voice.voiceURI}|${voice.name}|${voice.lang}`;
export const accent = (lang: string) => ({ "en-in": "Indian English", "en-us": "American English", "en-gb": "British English", "en-au": "Australian English", "en-ie": "Irish English", "en-za": "South African English", "en-ca": "Canadian English" }[lang.toLowerCase().replaceAll("_", "-")] || lang);
export function femaleVoices(voices: SpeechSynthesisVoice[]) {
  return voices.filter(v => v.localService === true && /^en(?:[-_]|$)/i.test(v.lang) && FEMALE.test(v.name))
    .sort((a, b) => Number(/^en[-_]IN$/i.test(b.lang)) - Number(/^en[-_]IN$/i.test(a.lang))
      || Number(/Samantha/i.test(b.name)) - Number(/Samantha/i.test(a.name)) || a.name.localeCompare(b.name));
}
export function saved(storage: Pick<Storage, "getItem"> | undefined, key: string, fallback: string) {
  try { return storage?.getItem(key) ?? fallback; } catch { return fallback; }
}
export function save(storage: Pick<Storage, "setItem"> | undefined, key: string, value: string) {
  try { storage?.setItem(key, value); } catch { /* Settings are optional; chat still works. */ }
}
export type VoiceState = { options: VoiceOption[]; selected: string; message: string };
export class VoiceRegistry {
  private synth: SpeechSynthesis;
  private storage: Storage | undefined;
  private notify: (state: VoiceState) => void;
  private choices: SpeechSynthesisVoice[] = [];
  private preference: string;
  private selected = "";
  private loaded = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  constructor(synth: SpeechSynthesis, storage: Storage | undefined, notify: (state: VoiceState) => void) {
    this.synth = synth; this.storage = storage; this.notify = notify;
    this.preference = saved(storage, VOICE_KEY, "");
    synth.addEventListener("voiceschanged", this.refresh);
    this.timer = setTimeout(() => { this.loaded = true; this.refresh(); }, 4000);
    this.refresh();
  }
  refresh = () => {
    let all: SpeechSynthesisVoice[] = [];
    try { all = this.synth.getVoices(); } catch { /* Show a missing voice instead. */ }
    if (all.length) this.loaded = true;
    this.choices = femaleVoices(all);
    const remembered = this.choices.find(v => voiceId(v) === this.preference);
    const current = this.choices.find(v => voiceId(v) === this.selected);
    this.selected = (remembered || current || this.choices[0]) ? voiceId((remembered || current || this.choices[0])) : "";
    const choice = this.get(this.selected);
    const hasIndian = this.choices.some(v => /^en[-_]IN$/i.test(v.lang));
    this.notify({ options: this.choices.map(v => ({ id: voiceId(v), name: v.name, accent: accent(v.lang), lang: v.lang })), selected: this.selected,
      message: choice ? `${choice.name} · ${accent(choice.lang)} · local female voice${/^en[-_]IN$/i.test(choice.lang) ? "" : hasIndian ? " · Indian English is available in the selector" : " · no recognised female Indian English voice is available"}`
        : this.loaded ? "No recognised local female English voice was found. Install one in system settings, then refresh voices."
        : "Loading browser voices…" });
  };
  get(id: string) { return this.choices.find(v => voiceId(v) === id); }
  choose(id: string) {
    if (!this.get(id)) return;
    this.preference = id; this.selected = id; save(this.storage, VOICE_KEY, id); this.refresh();
  }
  dispose() { clearTimeout(this.timer); this.synth.removeEventListener("voiceschanged", this.refresh); }
}
