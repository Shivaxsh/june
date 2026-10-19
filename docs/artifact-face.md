# June’s artifact face

The app uses the Canvas network from `docs/roadmap/building-june.html`: the same seed 7, 510 nodes in six clusters, nearest-neighbour edges and bridges, 24 hubs, wireframe icosahedron and three orbit paths. The reference artifact is unchanged.

## Components and behaviour

- `lib/orb/renderer.ts` owns reference geometry, projection, mood interpolation, drawing and the render lifecycle. Connections are precomputed once. All per-instance animation state stays inside its controller.
- `components/orb/Orb.tsx` adapts the existing mood, label, measured level and speech-activity references. The public props and backend contracts are unchanged. Phase 2/3 studios use this same component.
- Near-black charcoal surfaces retain the network’s coloured activity accents throughout the surrounding app. The canvas itself is transparent: no card, border, radius or shadow surrounds June, following the requested seamless presentation.
- The projected artwork is uniformly fitted to leave room for the outermost orbit and marker; the reference’s relative geometry and colours are retained. This responsive framing differs from the reference’s fixed `.36 × canvas width` radius, which can clip a moving marker.
- Microphone and file/sample audio use measured levels. Speech activity is a labelled approximation from existing playback events. Only labelled mood previews use the artifact’s synthetic listening/speaking envelope. Cluster names illustrate modules, not enabled features.
- The renderer targets 30 FPS, caps backing resolution at 2×, and suspends scheduling while hidden or offscreen. Still view uses frozen geometry with a 10 Hz measured-level readout. Observer, frame, timer and font-completion callbacks are cleaned up or guarded on unmount.

## Font

The unchanged Bricolage Grotesque variable TTF is hosted locally at `public/fonts/bricolage-grotesque/`. Source: the Google Fonts repository, `ofl/bricolagegrotesque/BricolageGrotesque[opsz,wdth,wght].ttf`. Its SIL Open Font License and attribution are included alongside it in `OFL.txt`. No external font request is required. The reference’s system-font fallback remains usable if font loading fails.

## Verification

`tests/orb-renderer.test.mjs` compares all generated geometry directly with the reference artifact, checks all moods, finite/normalised input, resolution cap, hidden/offscreen scheduling, disposal, static drawing and a full orbit’s marker bounds. Existing voice, audio, context and cancellation regressions remain in their existing suites.

Run:

```sh
npm test
npm run typecheck
npm run backend:test
npm run build
```

Manual checks and screenshots are recorded under the private, ignored `.june-work/artifact-face/` directory. No microphone or voice preference is changed by the renderer. Actual human microphone interruption and acoustic echo are not established by renderer tests.

### Results — 19 October 2026

- All **76 JavaScript tests**, **69 Python backend tests**, TypeScript and the production build passed. The backend retains its existing Starlette/httpx deprecation warning; it did not fail tests.
- Browser checks covered all four labelled previews, keyboard activation, desktop (1280 px) and mobile (390 px), Phase 2/3 mounting and navigation, zero horizontal overflow, and no console errors in the checked pages.
- Still view produced byte-identical consecutive canvas screenshots. A local Nicky preview/replayed reply entered the actual speaking state; Stop voice returned idle. A real Qwen request entered generation, Stop left a labelled partial reply, and New chat restored idle. A second request returned “Hello, I am June.” in 1.3 seconds total, first text at 0.6 seconds in that observed run; these are not performance guarantees.
- The original audio sample produced a measured meter value of approximately 0.16 in the browser. Pause returned idle, Resume restored Audio playback, and Stop returned idle. The level never uses the synthetic preview envelope.
- The final stage’s computed background is transparent, with zero border/radius and no shadow. Screenshots and raw check logs remain private under `.june-work/artifact-face/`.
- Physical microphone interruption/echo was not retested for this visual change. Reduced-motion drawing was verified through the shared Still-view renderer and focused tests; changing the OS preference itself was not automated.


### Charcoal palette — 19 October 2026

The page uses flat `#0B0C0E`, panels `#141518`, raised surfaces `#1B1D21` and subtle borders `#303238`. Inputs, code examples and speech captions use the same neutral surface tokens. The page and hands-free panel no longer add navy gradients. Particle colours, coloured activity states, typography and transparent canvas styling are unchanged.

A focused contrast regression checks normal text and activity colours against each main surface. Desktop keyboard previews retained a visible 2px teal focus ring. Proof screenshots are stored in `.june-work/charcoal-theme/`.
