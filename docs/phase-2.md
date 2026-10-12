# Phase 2: June gets a face

June v0.2 uses the existing local Qwen chat and adds browser graphics and audio visualisation. Run it at http://127.0.0.1:3001; the learning studio is /learn/phase-2. Start/stop commands are in the README.

## Read the code in this order

1. `components/orb/CanvasLesson.tsx`: a circle, dot array, nearby connections and a moving network. Coordinates begin at the top-left. The Canvas context draws each shape.
2. `components/orb/Orb.tsx`: the integrated face. Points rotate mathematically in 3D, then project onto a 2D Canvas. Five angular groups produce coloured clusters; connections only join nearby points at similar depths. Signals travel along selected edges.
3. `components/orb/GraphicsDemo.tsx`: ordinary Three.js with a real scene, perspective camera and GPU renderer. The GLSL example computes each pixel's glow using distance from the centre. A CSS fallback remains readable when WebGL is unavailable.
4. `lib/orb/audio-controller.ts`: one audio source, one context and one analyser. RMS is the square root of the average squared sample value. A gain factor and smoothing map this to a stable 0–1 level.
5. `lib/orb/state.ts`: real generation first, then deliberate preview, then actual audio activity, then idle. Preview labels and audio status prevent visual animation from implying speech understanding.
6. `components/Chat.tsx`: wires the state to the orb. It exits preview on Send and stops media on New chat. Chat HTTP contracts are unchanged.

## Ownership and cleanup

The audio hook creates its controller after mounting. A generation counter invalidates old asynchronous work: Stop, replacement and disposal all increment it. If microphone access resolves afterwards, its tracks stop immediately. A 30-second timer ends unanswered requests without reopening capture later.

Files use local blob URLs and HTMLAudioElement playback. Stopping playback removes media event handlers, pauses the element, disconnects nodes, closes the context and revokes the URL. The chosen File is only an in-memory reference until the page closes; nothing is uploaded or recorded.

Microphone input connects to the analyser only, never the output device. File/sample playback connects through the analyser to the speakers. The level is shared through a mutable ref, so React updates on state changes rather than every animation frame.

Leaving or hiding the page stops capture and playback. Canvas animation pauses while hidden; the learning page unmounts the previous demonstration when changing topics. WebGL geometry, material, context and renderer are released.

## Motion and performance

The main network uses 110 points and a target of 30 drawing frames per second; device-pixel ratio is capped at 1.75. This is a rendering target, not a measured frame-rate guarantee. The GPU demo caps its ratio at 1.5 and runs only on the learning page.

Still view and the system reduced-motion preference draw a static network with labels; a low-frequency meter still displays sound level. The main orb works without WebGL. Three.js is dynamically loaded by the learning page only. React Three Fiber is optional reading and is not installed.

## Try it yourself

- Change a point colour, radius, or connection threshold and explain the result.
- Switch to each mood preview and compare the label, accent and movement.
- Play June tones, pause/resume, then stop. Watch measured level return to zero.
- Choose a local audio file and try switching to the microphone deliberately.
- Use Still view and confirm the state and sound meter remain understandable.
- Send a real chat message during playback; the face says Generating reply while the separate audio status remains visible.
- Use New chat to stop both tasks.

## Free references

- [Canvas tutorial](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial)
- [Three.js manual](https://threejs.org/manual/)
- [Web Audio visualisation](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Visualizations_with_Web_Audio_API)
- [Microphone access](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [The Book of Shaders](https://thebookofshaders.com/)
- [React Three Fiber introduction](https://r3f.docs.pmnd.rs/getting-started/introduction)

## Original sample

`public/audio/june-tones.wav` is an original 18-second mono PCM arpeggio generated for June at 22,050 Hz. The six-note sequence uses C4, E4, G4, C5, G4, E4, with soft envelopes and changing volume so the analyser's response is easy to see. It is not a recording of a person or a downloaded song.
