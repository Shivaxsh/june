# Building June — phase-by-phase workbook

**Main assistant route: Phases 0–8 → Phase 11 → Phase 12. Optional model-learning tracks: Phases 9–10.** This workbook follows the Building June artifact. Phase numbers, names, learning topics, project versions and resource order are generated from the artifact's phase data. The artifact is the overview; this workbook adds practice and completion checks inside each matching phase.

The former Session 1–8 shortcut is retired. Do not use it as a second course. The optional HTML/CSS refresher is inside Phase 1; toolkit setup is Phase 0, the orb is Phase 2, Python is Phase 4, memory is Phase 6 and Mac actions are Phase 8.

You write June yourself. Start on your current Intel Mac with free resources. A named commercial provider is a topic/example, not a required subscription. Use simulated replies only while learning the flow, label them, then connect a real model. Install tools and choose connections yourself when their phase requires them; no hardware purchase is required to begin.

## How to use both documents

1. Open the same phase in the artifact and this workbook.
2. Read **Learn** in the listed order and do each matching **Practice** exercise.
3. Write the **Build** project, complete its checks and explain its flow in your own words.
4. Tick the corresponding artifact items only when you understand or have completed them. Keep short notes on failures and fixes.
5. Follow Phases 0–8, then Phase 11 and Phase 12. Study Phases 9–10 optionally when useful; training does not gate automation. Apply safety and completion checks as each feature is introduced.

## Phase index

| Phase | Same phase in the artifact | Build | Route |
|---|---|---|---|
| 0 | [Set up your toolkit](#phase-0) | June v0.0 | Main assistant route |
| 1 | [Modern JavaScript and your first June](#phase-1) | June v0.1 | Main assistant route |
| 2 | [June gets a face](#phase-2) | June v0.2 | Main assistant route |
| 3 | [June gets a voice](#phase-3) | June v0.3.1 | Main assistant route |
| 4 | [Python, the language of AI](#phase-4) | June v0.3.5 | Main assistant route |
| 5 | [Real-time conversation](#phase-5) | June v0.4 | Main assistant route |
| 6 | [Memory and personality](#phase-6) | June v0.5 | Main assistant route |
| 7 | [RAG: giving June knowledge](#phase-7) | June v0.6 | Main assistant route |
| 8 | [June's hands: agents, MCP and your world](#phase-8) | June v0.7 | Main assistant route |
| 9 | [How AI brains actually work](#phase-9) | June-nano | Optional model study |
| 10 | [June's own brain and voice](#phase-10) | June v1.0 | Optional model study |
| 11 | [Testing and safety](#phase-11) | June v1.1 | Main assistant route |
| 12 | [Going live and onto devices](#phase-12) | June v2 | Main assistant route |

<a id="phase-0"></a>

## Phase 0 — Set up your toolkit

The tools every developer uses every day. Once these are set up, everything else plugs into them.

### Learn and practise — same order as the artifact

#### 0.1 The terminal

**Learn:** typing commands instead of clicking.

**Practice:** Navigate to a practice folder, list its files and create a text file. Explain the working directory and the difference between a relative and an absolute path.

#### 0.2 Git and GitHub

**Learn:** saving every version of your code, online.

**Practice:** Create a repository, commit the Hello June page, change one line and inspect its diff. Push to GitHub yourself and explain how to return to a previous version.

#### 0.3 VS Code

**Learn:** the code editor, plus its extensions.

**Practice:** Open your project folder, edit a file and use the integrated terminal. Learn how to find the file and line reported by an error.

#### 0.4 Node.js and npm

**Learn:** running JavaScript outside the browser and installing libraries.

**Practice:** Install a supported Node.js version yourself from its official source when needed. Confirm Node and npm work; initialise a practice package and explain package.json and a package script.

### Build — June v0.0

**Artifact project:** Put a “Hello, I'm June” page online with GitHub Pages.

**Your exercise:** Create a minimal Hello June page in your own repository. Commit it and publish it through GitHub Pages yourself; inspect what will be public before publishing.

**Completion checks:** The live page shows Hello June, the committed source is available to you, and you can explain terminal, editor, Git and Node/npm roles.

### Resources — same order as the artifact

- [The Odin Project: Foundations](https://www.theodinproject.com/paths/foundations/courses/foundations)
- [GitHub Skills](https://skills.github.com/)

<a id="phase-1"></a>

## Phase 1 — Modern JavaScript and your first June

You already know JavaScript. Now learn the parts used to talk to servers and build real apps, and connect June to a brain for the first time.

### Learn and practise — same order as the artifact

#### 1.1 async/await and fetch

**Learn:** how your page asks a server for something and waits for the answer.

**Practice:** Fetch a small JSON response and handle success, waiting and failure. Write the response function with async/await; avoid duplicate sends while it is pending.

#### 1.2 JSON

**Learn:** the text format apps and AIs use to exchange data.

**Practice:** Represent messages as role/text objects. Convert an object to JSON and back, then handle malformed or unexpected data instead of trusting it.

#### 1.3 TypeScript

**Learn:** JavaScript with safety checks that catch mistakes early.

**Practice:** Define message and response types. Introduce an intentional type mismatch, explain the reported error and fix it.

#### 1.4 React and Next.js

**Learn:** the standard way to build web apps today.

**Practice:** Learn React components, props, state and form events, then Next.js routing and server routes. Build the conversation view and a server route for model requests. Keep browser code and server code separate.

#### 1.5 Environment variables

**Learn:** keeping secret API keys out of your code.

**Practice:** Read server configuration from environment variables. Keep local configuration out of Git and out of browser bundles; do not add an API key just to finish this exercise.

#### 1.6 AI basics

**Learn:** API, tokens, context window, temperature, streaming, system prompt.

**Practice:** Explain API, tokens, context window, temperature, streaming and system prompt using one June request. Separate a system instruction from the user message and retrieved text.

#### 1.7 Free first prototype

**Learn:** build a model adapter with simulated responses before connecting a local model or optional paid API.

**Practice:** Create a replaceable model adapter. Begin with explicitly labelled simulated replies; later connect a small local model through your server route and display the real model name. Handle a missing or stopped runtime and then add streaming.

### Build — June v0.1

**Artifact project:** A text chat app with a model adapter and a June system prompt. Begin with simulated replies; connect a small local model or an optional paid API, and stream real responses.

**Your exercise:** Optional refresher within this phase: if form events or DOM rendering are rusty, make a tiny `index.html`/`styles.css`/`app.js` screen first. Skip this refresher if comfortable. Then build the phase project in React/Next.js with typed messages, an asynchronous adapter, a June prompt, server configuration and streaming real replies from a small local model when ready.

**Completion checks:** Blank input sends nothing; Enter submits once; long text wraps; text such as `<script>` is rendered safely; failures leave controls usable. A simulated adapter is labelled demo. The final phase build produces real model replies and streams them. Explain the browser → server → model flow.

### Resources — same order as the artifact

- [javascript.info](https://javascript.info/)
- [React: Learn](https://react.dev/learn)
- [Next.js: Learn course](https://nextjs.org/learn)
- [Claude API docs](https://docs.claude.com/)

<a id="phase-2"></a>

## Phase 2 — June gets a face

The glowing network brain from the videos. This is pure front-end work, so it's the most fun place to use the skills you already have.

### Learn and practise — same order as the artifact

#### 2.1 Canvas 2D

**Learn:** drawing and animating hundreds of connected dots and lines with JavaScript.

**Practice:** Draw a small animated network on Canvas. Resize it with its container, and pause or reduce animation when the user requests reduced motion.

#### 2.2 Three.js

**Learn:** 3D in the browser: particles, lines, glow, orbit rings and camera.

**Practice:** Recreate a small part of the network in Three.js to learn a scene, camera and renderer. Compare its complexity with your Canvas version before choosing the final approach.

#### 2.3 Web Audio API

**Learn:** measuring how loud a sound is, many times a second, so the orb can react to it.

**Practice:** Use a short audio sample to measure volume and drive a visual change. Ask for microphone permission only if you choose to add microphone input.

#### 2.4 Shaders (GLSL) basics

**Learn:** tiny programs that run on the graphics chip for glowing, flowing effects.

**Practice:** Make one simple glow or colour effect and explain which work happens in the shader. Keep an ordinary rendering fallback.

#### 2.5 Mood states

**Learn:** designing how the orb looks when idle, listening, thinking and speaking.

**Practice:** Give idle, listening, thinking and speaking distinct states. Manual mood buttons are a visual exercise; label them so they do not imply June is actually listening or thinking.

#### 2.6 React Three Fiber (optional)

**Learn:** Three.js written as React components.

**Practice:** Optional: recreate one scene as React Three Fiber components. Skip this exercise if you keep the plain Canvas or Three.js version.

### Build — June v0.2

**Artifact project:** June's living brain: coloured clusters of connected dots around a glowing core, with signals firing between them. It reacts to music or your microphone and has four moods.

**Your exercise:** Add your own orb to the Phase 1 app. Connect the real request state to its visual state, then connect the available audio signal.

**Completion checks:** The orb resizes without overflow and distinguishes all four moods. An animation does not imply a connected microphone or a real thinking model. Reduced motion remains usable.

### Resources — same order as the artifact

- [MDN: Canvas tutorial](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial)
- [Three.js manual](https://threejs.org/manual/)
- [MDN: Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)
- [The Book of Shaders](https://thebookofshaders.com/)
- [React Three Fiber docs](https://r3f.docs.pmnd.rs/)
- [Three.js Journey](https://threejs-journey.com/) — paid; optional.

<a id="phase-3"></a>

## Phase 3 — June gets a voice

Use free local Whisper for English voice input and an available local female English voice for replies. Prefer Indian English when available, label the actual accent, and review the transcript before sending.

### Learn and practise — same order as the artifact

#### 3.1 Web Speech API

**Learn:** recognition versus synthesis; June uses local system synthesis because browser recognition services can fail.

**Practice:** Learn browser recognition versus synthesis. June uses direct microphone recording and local Whisper base.en because browser recognition services can fail. Keep typing available and show words for editable review.

#### 3.2 Speech to text

**Learn:** capture a short microphone recording, transcribe it locally with Whisper base.en after release, then review and edit the words.

**Practice:** Capture a short microphone clip with AudioWorklet, resample to mono 16 kHz PCM WAV, and transcribe on this Mac through the local server. Release starts transcription; do not claim live words while recording. Check silence, cancellation and microphone denial.

#### 3.3 Text to speech

**Learn:** read replies with a selected local female system voice; hosted voices are optional later alternatives.

**Practice:** Speak a short June reply with an available female system voice. Compare the role of a speech engine with that of the language model; a provider subscription is optional.

#### 3.4 Streaming audio

**Learn:** queue complete sentences while model text arrives, flush on completion and cancel stale speech.

**Practice:** Queue complete reply sentences in order as model text arrives. Check cancellation and buffering so late audio does not play after Stop.

#### 3.5 Wiring the orb to her voice

**Learn:** measure recording audio; use speech lifecycle events and label synthesis movement as a visual approximation.

**Practice:** Connect playback events and available audio measurements to the orb. Mark a timed visual approximation as such; do not claim it measures sound if it does not.

#### 3.6 Female voice selection

**Learn:** wait for available voices, prefer female Indian English when present, label the actual accent and save your choice.

**Practice:** Wait for voices and voiceschanged, offer recognised female English voices, prefer Indian English when available and label the actual accent. Add preview, a saved selection and Stop; never use pitch as a substitute for selecting a female voice.

### Build — June v0.3.1

**Artifact project:** Record a request, transcribe it on your Mac, review the words, send them to local June and hear her reply in the selected female voice. Stop releases recording, transcription and speech.

**Your exercise:** Add push-to-talk using local Whisper base.en, editable transcript review, the selected female voice, Preview and Stop. Keep recordings temporary and connect the orb to actual recording and playback events.

**Completion checks:** Speak a short request, review it, send it to the model, hear its reply and stop playback. Saved voice selection survives reload. Unsupported recognition or missing female voices are clearly shown; typing remains usable.

### Resources — same order as the artifact

- [MDN: Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [whisper.cpp: local speech](https://github.com/ggml-org/whisper.cpp)
- [MDN: microphone access](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [MDN: AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)
- [MDN: voice loading](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/voiceschanged_event)

<a id="phase-4"></a>

## Phase 4 — Python, the language of AI

The real-time voice tools, AI libraries and training tools you'll use from Phase 5 onwards are mostly written in Python.

### Learn and practise — same order as the artifact

#### 4.1 Python basics

**Learn:** variables, lists, loops, functions, classes.

**Practice:** Write small functions using variables, lists, loops and classes. Express a simple message record in Python and explain its equivalent in JavaScript.

#### 4.2 pip and virtual environments

**Learn:** installing libraries without breaking other projects.

**Practice:** Create an isolated environment for this project, install one required library and record its dependency. Explain which interpreter and environment your editor uses.

#### 4.3 Jupyter notebooks

**Learn:** running code in small pieces and seeing results straight away.

**Practice:** Use a notebook to inspect a small dataset you own. Restart the kernel and run cells in order so the result does not depend on hidden earlier state.

#### 4.4 async in Python

**Learn:** doing several things at once, which live voice needs.

**Practice:** Implement an asynchronous request with an error and timeout path. Explain what concurrent work means and why it differs from running everything in sequence.

#### 4.5 FastAPI and WebSockets

**Learn:** a Python server that streams audio and text back and forth with your app.

**Practice:** Build a FastAPI endpoint and a WebSocket connection. Move the existing model and speech adapters behind this Python service, keeping the working browser interface and contracts. Bind the development service locally.

### Build — June v0.3.5

**Artifact project:** Move June's brain and voice calls into a Python backend that your web app talks to.

**Your exercise:** Keep the working interface, move provider/speech calls behind your Python service, and retain the same message and error contracts.

**Completion checks:** The browser talks to the Python backend; requests, streaming and failures work. Restarting the service does not leave the UI stuck or expose configuration.

### Resources — same order as the artifact

- [CS50's Introduction to Programming with Python](https://cs50.harvard.edu/python/)
- [Automate the Boring Stuff with Python](https://automatetheboringstuff.com/)
- [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/)

<a id="phase-5"></a>

## Phase 5 — Real-time conversation

The step that makes people say “wait, that's real?”. No buttons: you speak from across the room, she answers with a measured response delay, and you can cut her off mid-sentence.

### Learn and practise — same order as the artifact

#### 5.1 Voice frameworks

**Learn:** Pipecat or LiveKit Agents, which connect ears, brain and voice with very little delay.

**Practice:** Try one voice pipeline framework with your chosen speech and model components. Measure the delay at each stage rather than assuming the framework makes it instant.

#### 5.2 Wake word

**Learn:** “Hey June” detected on your own computer with Porcupine or openWakeWord.

**Practice:** Add deliberate wake-word activation and a visible listening indicator. Check false activations and provide a way to disable the microphone.

#### 5.3 Voice activity detection

**Learn:** knowing when you've started and stopped talking (Silero VAD).

**Practice:** Detect the beginning and end of speech. Try background noise and pauses, recording what the detector gets wrong.

#### 5.4 Barge-in

**Learn:** June stops talking the moment you interrupt her.

**Practice:** Interrupt June while she speaks. Cancel queued speech and stale generated output so old replies do not resume after you start speaking.

#### 5.5 Turn-taking

**Learn:** not cutting you off when you pause to think.

**Practice:** Distinguish a thinking pause from the end of a turn. Adjust the behaviour with real examples of your own speaking style.

#### 5.6 WebRTC

**Learn:** the technology video calls use to send live audio quickly.

**Practice:** Explain how audio moves between endpoints. Handle disconnect/reconnect and avoid leaving June appearing to listen when the connection has failed.

#### 5.7 Two ways to build voice

**Learn:** separate pieces vs one speech-to-speech model (see below).

**Practice:** Compare separate speech/model components with a speech-to-speech design on paper first. Use the modular route for this free-first build; trying a paid service is not a requirement.

### Build — June v0.4

**Artifact project:** Say “Hey June”, have a conversation and interrupt her. Measure response time and work toward a one-second first-audio target with suitable hardware.

**Your exercise:** Extend Phase 3 push-to-talk into the hands-free loop, using the Python foundation from Phase 4. Add wake-word, turn detection, interruption and measured timing.

**Completion checks:** June wakes deliberately, handles a turn and stops when interrupted. Timings are recorded on your actual Mac. A one-second target is not a promise or a completion claim.

### Resources — same order as the artifact

- [Pipecat quickstart](https://docs.pipecat.ai/getting-started/quickstart)
- [LiveKit Agents](https://docs.livekit.io/agents/)
- [Picovoice Porcupine (wake word)](https://picovoice.ai/docs/porcupine/)
- [openWakeWord](https://github.com/dscripka/openWakeWord)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime)
- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live)

<a id="phase-6"></a>

## Phase 6 — Memory and personality

Give June a consistent style and user-controlled application memory. Use the workshop as a starting point; this does not train the model.

### Learn and practise — same order as the artifact

#### 6.1 Prompt engineering

**Learn:** writing instructions that get reliable, in-character answers.

**Practice:** Write a short June system prompt and compare its responses on fixed examples. Track failures instead of assuming a prompt always works.

#### 6.2 The character bible

**Learn:** turning your workshop answers into June's system prompt.

**Practice:** Complete the artifact personality workshop in your own words. Turn your approved values and boundaries into the prompt used by the actual model.

#### 6.3 Writing for speech

**Learn:** short spoken sentences, natural fillers like “hmm”, no lists or emoji.

**Practice:** Rewrite a few answers as short, natural spoken replies. Read them aloud; remove formatting that is awkward to speak.

#### 6.4 Conversation memory

**Learn:** private SQLite chats on this Mac for 30 days; hosted Postgres/Supabase is optional later.

**Practice:** Use Python SQLite outside Git with private permissions, versioned migrations and chat/turn identifiers. Reopen and search chats; New chat preserves history. Test expiry 30 days after last activity. Hosted Postgres/Supabase is optional later.

#### 6.5 Long-term memory

**Learn:** June suggests facts with exact supporting quotes; only approved facts inform later chats.

**Practice:** Let the local model suggest up to three facts with exact user quotations; approve, edit or reject them. Reject secrets, fiction and inferences. Recall approved facts after New chat and restart; inspect which memories informed the reply.

#### 6.6 Emotion in voice

**Learn:** adjusting her voice's speed, warmth and emphasis to match her mood.

**Practice:** Compare steady (0.98), calm (0.92) and bright (1.04) speech rates at ordinary pitch, with restrained idle glow/breathing. Actual listening/thinking/speaking takes priority; Still view stays static. Evaluate style on fixed examples.

#### 6.7 Memory controls

**Learn:** ask before saving a fact; let the user review, correct, export and delete it.

**Practice:** Build approval, manual add, deduplication, conflict review, edit/delete and validated JSON import/export. Export chats only by choice. Memory edits/deletions cancel generation and speech across tabs and reset inference context, while source chats remain visible until separately deleted or expired. Handle database failure with an explicit temporary-chat choice.

### Build — June v0.5

**Artifact project:** Review and approve suggested facts, recall them after New chat and restart, and manage a ten-field personality. Chats expire after 30 days; approved memories persist. Voice expression is a preference, not a guarantee of model consistency.

**Your exercise:** Use the personality workshop to personalise June and add approved persistent memory separately from chat history.

**Completion checks:** A saved preference is recalled in a new conversation; a declined fact is not saved; edited/deleted facts are reflected in subsequent context. Use a fixed set of examples to check personality instead of claiming it never fails.

### Resources — same order as the artifact

- [Anthropic: interactive prompt engineering tutorial](https://github.com/anthropics/prompt-eng-interactive-tutorial)
- [Claude API docs](https://docs.claude.com/)
- [Python SQLite documentation](https://docs.python.org/3/library/sqlite3.html)
- [Supabase docs (optional later)](https://supabase.com/docs)
- [DeepLearning.AI short courses](https://www.deeplearning.ai/short-courses/)

<a id="phase-7"></a>

## Phase 7 — RAG: giving June knowledge

RAG means “look it up, then answer”. June searches your notes and documents first, then answers from what she found. You add knowledge without retraining anything.

### Learn and practise — same order as the artifact

#### 7.1 Embeddings

**Learn:** turning text into lists of numbers that capture its meaning.

**Practice:** Embed a few notes you own and compare similarity for related and unrelated questions. Explain why an embedding is not the original text.

#### 7.2 Vector databases

**Learn:** storing embeddings and finding the closest matches (pgvector on Supabase, or Chroma).

**Practice:** Store vectors with source IDs and metadata, then retrieve candidates. Choose a local store first if it meets your experiment; learn the alternatives named in the artifact.

#### 7.3 Chunking

**Learn:** splitting long documents into small pieces.

**Practice:** Split notes into passages while retaining source and location. Compare a few chunk sizes on the same questions.

#### 7.4 Retrieval and reranking

**Learn:** finding candidate pieces, then keeping only the best ones.

**Practice:** Inspect retrieved candidates before generating an answer. Reorder or rerank them and compare whether the useful passage rises to the top.

#### 7.5 Citations

**Learn:** June says where she found the answer.

**Practice:** Show the source passage and location with each supported answer. Ask a question absent from the notes and have June say the evidence is missing.

### Build — June v0.6

**Artifact project:** Ask June out loud about your own notes or PDFs and she answers from them, telling you where the answer came from.

**Your exercise:** Connect your own small note collection to retrieval, generation and citations, then ask about it through the voice flow.

**Completion checks:** You can inspect the passage supporting an answer. Absent information is reported honestly. Deleted or unauthorised sources are not retrieved.

### Resources — same order as the artifact

- [Anthropic: Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [Supabase: AI and vectors](https://supabase.com/docs/guides/ai)
- [DeepLearning.AI short courses (search “RAG”)](https://www.deeplearning.ai/short-courses/)

<a id="phase-8"></a>

## Phase 8 — June's hands: agents, MCP and your world

Connect tools one capability at a time: your Mac, home, email, job applications, editable websites/designs, PDF/PPTX files and transaction preparation. Permissions, review, cancellation and result verification belong in each project before live actions. A desktop wrapper is optional for tools available through the local server.

### Learn and practise — same order as the artifact

#### 8.1 Desktop app

**Learn:** Electron or Tauri, which wrap your web app into a real Mac app with a menu-bar icon and a global shortcut.

**Practice:** Package your existing web interface in one desktop approach. Keep the local bridge narrow and understand which operations run in the browser and which run on the Mac.

#### 8.2 The agent loop

**Learn:** June plans, uses a tool, checks the result, and repeats until the job is done.

**Practice:** Implement propose → approve → execute → observe for one tool. Limit iterations and handle failures rather than letting a generated plan run indefinitely.

#### 8.3 MCP (Model Context Protocol)

**Learn:** a standard plug that connects June to apps like Calendar, GitHub, Spotify and Notion.

**Practice:** Connect one narrowly scoped MCP tool. Explain discovery, validated arguments, results and authorisation; the protocol itself does not grant access to your accounts.

#### 8.4 Controlling your Mac

**Learn:** opening apps and running Apple Shortcuts when you ask.

**Practice:** Choose one app or inspect one Shortcut. Add a fixed allowlist, show the exact action for approval, execute it at most once and observe its visible result. Never run model-written shell strings.

#### 8.5 Smart home

**Learn:** lights, fans and plugs through Home Assistant, which has its own MCP server.

**Practice:** Start with a clearly labelled simulator. Connect a real Home Assistant device only when you have compatible hardware and authorised access; read its resulting state.

#### 8.6 Seeing your screen

**Learn:** sending a screenshot to the brain so June can see what you're looking at.

**Practice:** Capture only a screen or window you deliberately choose. Explain what will be sent to the model and avoid collecting screens in the background.

#### 8.7 Routines

**Learn:** a spoken morning briefing, reminders and check-ins at times you set.

**Practice:** Build one opt-in routine with a stop control. Use available authorised data; do not fabricate a calendar or weather response when disconnected.

#### 8.8 OAuth and permissions

**Learn:** authorise each account separately, restrict scopes and support revoking access.

**Practice:** Start with one authorised read connection, such as a calendar. Restrict its scope, keep tokens server-side and confirm revoking access stops the connection.

#### 8.9 Orders and bookings

**Learn:** prepare an exact transaction for review; confirm changed prices and prevent duplicate purchases.

**Practice:** Prepare a practice checkout or booking review without paying. Show merchant, exact item/itinerary, total, fees and terms. Require new approval if the price changes; never retry a purchase blindly.

#### 8.10 Tool boundaries

**Learn:** allowlist Mac actions and home devices; check the result before saying done.

**Practice:** Reject unsupported actions, invalid arguments and duplicate confirmations. Read back actual results and distinguish real devices/accounts from simulations.

### Build — June v0.7

**Artifact project:** Say “June, open VS Code and play my focus playlist” and it happens. Every morning she greets you with your weather, calendar and goals.

**Your exercise:** Begin with one approved Mac action, then add email, job applications, editable websites/designs, PDF/PPTX outputs, home control and transaction review one connection at a time. Use the capability project checks below before live writes or payments. A focus playlist or briefing requires the corresponding real authorised service. Use simulations until devices/accounts are available, and record those dependencies.

**Completion checks:** One real Mac action is approved and visibly completes; cancelling and unsupported commands have no effect. Connected services/devices report actual outcomes and revoked access fails. Booking/order review shows exact details without making an unapproved purchase. Simulated integrations are not marked as completed real integrations.

### Resources — same order as the artifact

- [Model Context Protocol: official docs](https://modelcontextprotocol.io/)
- [MCP servers you can plug in](https://github.com/modelcontextprotocol/servers)
- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Electron docs](https://www.electronjs.org/docs/latest/)
- [Tauri](https://tauri.app/)
- [Home Assistant](https://www.home-assistant.io/)
- [Home Assistant MCP server](https://www.home-assistant.io/integrations/mcp_server/)
- [Apple Shortcuts for Mac](https://support.apple.com/guide/shortcuts-mac/welcome/mac)

<a id="phase-9"></a>

## Phase 9 — How AI brains actually work

Optional model-learning track. Understand model internals and build a deliberately tiny model as an exercise. You can continue from Phase 8 to Phase 11 and deployment without this track; training from scratch is not required for fine-tuning or a useful assistant.

### Learn and practise — same order as the artifact

#### 9.1 Just enough maths

**Learn:** vectors, matrices, probability and gradients, all taught with pictures.

**Practice:** Work through vectors, matrix multiplication, probability and a gradient on small examples. Explain which quantities the learning algorithm changes.

#### 9.2 Neural networks

**Learn:** how a model learns by adjusting millions of numbers.

**Practice:** Train a deliberately tiny network on a simple task. Record training and validation loss, and compare with a baseline.

#### 9.3 PyTorch

**Learn:** the main library for building and training models.

**Practice:** Build the same learning loop using tensors, automatic differentiation and an optimiser. Save and reload weights.

#### 9.4 Transformers and attention

**Learn:** the design behind Claude, GPT and every modern language model.

**Practice:** Study a small attention calculation and construct a tiny transformer. Keep its size suited to a learning experiment on the available hardware.

#### 9.5 Tokenization

**Learn:** how text is chopped into pieces and turned into numbers.

**Practice:** Encode and decode text with a tokenizer. Split data before training and explain how next-token prediction produces generated text.

### Build — June-nano

**Artifact project:** Train a tiny GPT on text you may use, to understand next-token learning. This is a learning model, not a capable personal assistant.

**Your exercise:** Train a tiny model on licensed or self-owned text using the learning loop you wrote. Keep a validation split, a simple baseline and saved weights.

**Completion checks:** Weights can be reloaded, samples and losses are recorded, and you can explain tokenisation, attention and optimisation. This learning model is not claimed to be a capable June assistant.

### Resources — same order as the artifact

- [3Blue1Brown: Neural networks (videos)](https://www.3blue1brown.com/topics/neural-networks)
- [Andrej Karpathy: Neural Networks, Zero to Hero](https://karpathy.ai/zero-to-hero.html)
- [nanoGPT on GitHub](https://github.com/karpathy/nanoGPT)
- [PyTorch: Learn the basics](https://pytorch.org/tutorials/beginner/basics/intro.html)
- [Hugging Face LLM course](https://huggingface.co/learn/llm-course)

<a id="phase-10"></a>

## Phase 10 — June's own brain and voice

Optional adaptation track. Start only when a measured behaviour gap remains after model selection, prompts, RAG and tools. Compare an adapter with the baseline and choose a voice separately. A GPU may support larger models and experiments; it does not guarantee Claude/Codex-level reliability.

### Learn and practise — same order as the artifact

#### 10.1 Her constitution

**Learn:** your workshop answers grown into a full document of values, tone and rules.

**Practice:** Expand the Phase 6 character document into explicit values, tone and action boundaries, with examples you can evaluate. A principles file alone does not reproduce a frontier training process.

#### 10.2 Training data

**Learn:** reviewed June conversations, cleaned and deduplicated, with separate validation and test sets; see the training guide.

**Practice:** Prepare conversations you have rights to use, remove secrets and duplicates, and reserve complete unseen scenarios for validation and final evaluation.

#### 10.3 LoRA fine-tuning

**Learn:** training a small add-on to a free model (Qwen or Llama) with Unsloth or Hugging Face TRL.

**Practice:** Record an open-model baseline, train a small adapter and compare it on the held-out tasks. Use an appropriate GPU notebook if available; do not assume this Intel Mac can run a useful large fine-tune.

#### 10.4 DPO

**Learn:** teaching June to prefer replies that sound like her.

**Practice:** Learn preference pairs and DPO. Try it only if a specific style issue remains and suitable compute is available; do not treat it as a mandatory paid step.

#### 10.5 Her own voice

**Learn:** an original voice designed in ElevenLabs, or an open voice model like Kokoro or Piper that you run yourself.

**Practice:** Evaluate a licensed female voice independently of the language-model adapter. An original voice or a commercial service is an optional later choice; use a voice only with appropriate rights.

#### 10.6 Offline June

**Learn:** evaluate a small local brain, speech recognition and a licensed female voice on suitable hardware; offline performance must be measured.

**Practice:** Check each component offline separately: recognition, model, retrieval and speech. Measure memory and response time, and label any component still using an online service.

#### 10.7 QLoRA and dataset splits

**Learn:** quantize the base model, train adapters, and hold out entire conversations for evaluation.

**Practice:** Explain quantised base weights versus trainable adapters. Choose sequence length and batch size to fit the actual training environment; keep near-duplicates out of separate data splits.

#### 10.8 Hardware budget

**Learn:** prepare data on your Mac and use a GPU notebook first; see the hardware guide.

**Practice:** Prepare the data and evaluation locally first. Check a concrete configuration before using free notebook compute; do not buy or rent hardware to complete the planning exercise.

### Build — June v1.0

**Artifact project:** June uses an evaluated adapter and a separately chosen voice. Test offline conversation on suitable hardware; online services still need internet.

**Your exercise:** Adapt a chosen open model to the behaviours you can measure, export/version the adapter and select a speech voice separately. Investigate DPO only if useful; benchmark offline operation on appropriate hardware.

**Completion checks:** Held-out results compare baseline and adapter without leakage; factual/tool behaviour is checked as well as style. An export runs in the actual app; the base version is retained for rollback. Offline claims match the components and hardware actually verified.

### Resources — same order as the artifact

- [Unsloth docs and free Colab notebooks](https://docs.unsloth.ai/)
- [Hugging Face TRL](https://huggingface.co/docs/trl)
- [Ollama](https://ollama.com/)
- [Kokoro voice model](https://huggingface.co/hexgrad/Kokoro-82M)
- [Piper voice](https://github.com/OHF-Voice/piper1-gpl)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Paper: Constitutional AI (Anthropic)](https://arxiv.org/abs/2212.08073)
- [Paper: LoRA](https://arxiv.org/abs/2106.09685)
- [Paper: DPO](https://arxiv.org/abs/2305.18290)

<a id="phase-11"></a>

## Phase 11 — Testing and safety

An assistant that can control your computer and hears everything has to be trustworthy. Consolidate checks already introduced alongside every feature. Do not wait until this phase to protect accounts, files or transactions.

### Learn and practise — same order as the artifact

#### 11.1 Evals

**Learn:** a fixed set of test questions you run after every change, so you notice if June gets worse.

**Practice:** Create a fixed set of representative questions with expected properties, then rerun it after changes. Include facts, retrieval, refusal and tool proposals.

#### 11.2 In-character tests

**Learn:** checking that June sounds like June, using a strong model as the judge.

**Practice:** Use a written rubric to compare personality and clarity. Start with manual scoring; a paid model judge is optional and its judgement is not ground truth.

#### 11.3 Confirm before acting

**Learn:** June asks before sending messages, spending money or deleting anything.

**Practice:** Check approval boundaries implemented from the start: cancelling does nothing, changed details require review and spending/sending/deletion never happen silently.

#### 11.4 Prompt injection

**Learn:** ignoring instructions hidden in web pages, emails or screenshots she reads.

**Practice:** Put hostile instructions in a practice retrieved document and confirm that June treats them as source text, not permission to act.

#### 11.5 Privacy

**Learn:** the wake word runs on your device, a visible “listening” light, and recordings you can delete.

**Practice:** Verify the listening indicator, microphone stop, retention controls and deletion. Avoid recording private content merely to produce a log.

#### 11.6 Observability

**Learn:** logging every conversation, delay and cost with Langfuse.

**Practice:** Record useful timing, errors and action outcomes, redacting secrets. Learn the named observability tool, but keep the initial evidence local if that is enough.

#### 11.7 Action regression checks

**Learn:** test disconnected devices, revoked accounts, duplicate requests and price changes before enabling real actions.

**Practice:** Exercise disconnected devices, revoked access, duplicate requests, cancelled actions, timeouts and changed prices. Check that failures are accurately reported.

### Build — June v1.1

**Artifact project:** A 100-question test suite covering personality, accuracy, speed and safety, with a page showing her scores over time.

**Your exercise:** Grow the earlier completion checks into the artifact's 100-question suite and a score-history page. Cover personality, accuracy, speed and tool safety.

**Completion checks:** The suite contains 100 recorded cases, results are inspectable across versions, and failure handling is checked. Approval and privacy protections already implemented in earlier phases are verified here, not postponed until this phase.

### Resources — same order as the artifact

- [OWASP Top 10 for LLM apps](https://genai.owasp.org/llm-top-10/)
- [Langfuse docs](https://langfuse.com/docs)
- [Claude docs: testing and evaluation](https://docs.claude.com/)

<a id="phase-12"></a>

## Phase 12 — Going live and onto devices

June leaves your desk: a polished Mac app, a phone app, and a small speaker that sits in your room.

### Learn and practise — same order as the artifact

#### 12.1 Packaging the desktop app

**Learn:** installers, auto-updates and starting June when your Mac starts.

**Practice:** Make a desktop package, document installation and updates, and offer an explicit startup preference. Verify the packaged app rather than just the development server.

#### 12.2 Phone app

**Learn:** React Native with Expo, using the JavaScript you already know.

**Practice:** Build a small React Native/Expo client for the same backend. Preserve memory and approval semantics on the phone.

#### 12.3 A June speaker

**Learn:** a Raspberry Pi with a microphone and speaker running the wake word and voice.

**Practice:** Use a simulated endpoint first. If suitable hardware becomes available, connect its microphone, speaker and wake word; verify a real conversation before calling the speaker complete.

#### 12.4 Accounts and hosting

**Learn:** Supabase Auth, Vercel for the website, a suitable model host using serving software such as vLLM.

**Practice:** Plan authentication and hosting for your actual model and clients. Keep a local personal deployment until remote access is useful; choose hosting only after measuring requirements.

#### 12.5 Voice costs

**Learn:** voice services charge by the minute, so cache what you can and use cheaper models for easy questions.

**Practice:** Track inference and speech usage and cache only appropriate repeatable content. Record actual local resource use or service charges; do not assume every provider bills the same way.

#### 12.6 Docker and CI/CD

**Learn:** packaging and automatic deployment with GitHub Actions.

**Practice:** Package the service reproducibly and create an automated build/check workflow. Practise rollback and do not automatically publish private data.

#### 12.7 Always-on home hub

**Learn:** keep the home controller and voice endpoint separate from occasional model-training compute.

**Practice:** Keep the always-on home controller separate from training experiments. Confirm loss of the model or network produces a clear unavailable state rather than a false successful action.

### Build — June v2

**Artifact project:** Talk to June from your Mac, your phone, or a speaker in your room. She's the same June, with the same memory, everywhere.

**Your exercise:** Package the Mac app first, then the phone and speaker endpoints when their dependencies are available. Connect them to a consistent memory store and permission model.

**Completion checks:** Each claimed endpoint works in its packaged form, uses the approved memory and honours revocation/approval controls. Update/rollback and failure states are documented. Unavailable hardware or unconnected accounts remain pending.

### Resources — same order as the artifact

- [Expo docs](https://docs.expo.dev/)
- [Raspberry Pi documentation](https://www.raspberrypi.com/documentation/)
- [Supabase Auth](https://supabase.com/docs/guides/auth)
- [Vercel docs](https://vercel.com/docs)
- [vLLM docs](https://docs.vllm.ai/)
- [Docker: Get started](https://docs.docker.com/get-started/)
- [GitHub Actions](https://docs.github.com/en/actions)

## Capability milestones within this same course

| Milestone | When to check it |
|---|---|
| Voice conversation | Phase 3 adds push-to-talk; Phase 5 adds hands-free turn-taking and interruption. |
| Approved saved memory | Phase 6. Recall a saved fact in a new conversation and verify editing/deletion. |
| One authorised Mac action | Phase 8. Observe a real result and confirm cancellation prevents it. |
| First combined milestone | During Phase 8: voice conversation + approved memory + one authorised Mac action. |
| Home, accounts and transaction review | Phase 8 introduces them; advance each only as hardware and authorised connections become available. |
| Tiny model from scratch | Optional Phase 9 learning project; not needed for automation or fine-tuning. |
| Adapted open model and separate voice | Optional Phase 10; evaluate against the original model, retain rollback. |
| Production endpoints | Phase 12, after the Phase 11 regression/safety review. |

These are checkpoints in the main route and optional study tracks. Basic error handling, privacy and action approval are required when features are introduced; Phase 11 consolidates their evaluation.

## Phase 8 project acceptance checks

Before each live integration: compare model candidates on your tasks; test tools in a simulator; validate arguments on the server; treat retrieved content as untrusted; restrict permissions; bind approval to exact action details; verify results; retain cancellation, a log without secrets and rollback. No verified success means no completion claim.

### Voice and memory

Phase 3 → Phase 5 → Phase 6. Begin with push-to-talk and a female voice, then add “Hey June”, interruption and memory you can review. Store useful facts separately from chat history.
Done when: June recalls an approved preference in a new conversation and stops speaking when interrupted.

### Mac control

Phase 8. Wrap the web interface in a desktop app and connect a small allowlist of Apple Shortcuts. Start with “open VS Code”. Add file actions later with previews and clear permissions.
Done when: the app opens, June reports the actual result, and unsupported commands do not run.

### Home control

Phase 8 → Phase 12. Connect Home Assistant through its official MCP server. Expose one compatible light or plug first; use a simulated device until you own suitable hardware.
Done when: June changes the chosen device and reads its updated state. A disconnected device is reported as unavailable.

### Accounts and email

Phase 8. Connect one service with OAuth, limited permissions and revocation. Start with calendar reading, then draft an email showing recipient, subject, body and attachments. Send only after approval of those exact details.
Done when: the provider confirms the send, June records its message ID, revoked access fails clearly, and retrying cannot send a duplicate. Never say “sent” for a draft.

### Job applications

Phase 7 + Phase 8. Use your approved profile and resume to find suitable roles and prepare truthful applications. Show the employer, role, answers and attachments before submitting; hand login or verification steps back to you.
Done when: one authorised application has visible employer confirmation, a saved receipt and no invented qualifications. Unconfirmed, blocked and failed submissions stay labelled that way.

### Websites and designs

Phase 8. Give June scoped project-folder tools and a preview workflow. Produce editable HTML/CSS/JavaScript or design source and assets you may use. Review desktop/mobile output and errors before publishing.
Done when: you can open and edit the source, the preview matches the request, changes are recoverable, and publication has separate approval. Model quality still limits complex coding and design.

### PDFs and presentations

Phase 8. Connect document-generation tools. Start with one short report and five-slide presentation, retaining editable source alongside PDF/PPTX exports. Use approved facts and assets.
Done when: the actual exported files open, rendered pages/slides have no clipped text or missing assets, and their contents match the approved brief.

### Groceries and movie tickets

Phase 8. Compare and prepare a cart or booking with merchant, items, quantities or cinema, film, date, time and seats. Show availability, total including fees and cancellation terms; request approval of the exact transaction.
Done when: a practice checkout reaches review, changed details require new approval, and a confirmed purchase has a receipt. Timeouts never trigger a blind retry. Website restrictions and verification may need your help.

### Payments · separate milestone

Phase 8, with checks before any real payment. Begin in a simulator. June prepares the payee, purpose and exact amount; you review and complete required authentication in the provider’s trusted checkout. Keep PINs, OTPs and card secrets out of chat and logs.
Done when: approval is bound to one transaction, changed amounts require review, cancellation prevents payment, and provider status or a receipt confirms the result. Pending payments are checked before any retry.

### Optional: adapt June’s model

Phase 9 studies tiny models; Phase 10 optionally fine-tunes an existing model. Compare suitable base models first. Use RAG for changing knowledge and tools for actions; fine-tune only for a measured behaviour gap.
Done when: held-out evaluation shows a useful improvement without harming facts or tool use, and rollback works. These tracks are not prerequisites for email, documents, home control or bookings.


## Hardware and model-training notes

Your current Mac is the development machine. Measure a small local model before making offline-performance claims. A home hub serves a different purpose from training compute; use a labelled simulator until compatible hardware is available.

Optional Phase 9 teaches a deliberately tiny model from scratch. Optional Phase 10 teaches adapting an existing open model with LoRA/QLoRA, reviewed examples and separate validation/test conversations. Fine-tuning text behaviour does not train a female speaking voice and does not automatically connect accounts or devices.

Prepare data locally first. For early 3–8B QLoRA experiments, the artifact uses 16–24 GB GPU memory as a planning target, subject to model/configuration; it is not a fit guarantee. Free GPU notebook availability varies. Defer purchases and rentals until a concrete experiment requires them.

Use the artifact's hardware guide and training guide at their corresponding phases: [training requirements](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements), [Colab limits](https://research.google.com/colaboratory/faq.html).

## Start here

If you have not started the course, begin with **Phase 0 — Set up your toolkit**. If a topic is already familiar, demonstrate its exercise and tick it off; do not start a new numbering scheme. Share your own work or a specific error when you want a hint or review.

The local roadmap and this workbook now share one sequence. The original hosted Claude artifact has not been republished from this session.
