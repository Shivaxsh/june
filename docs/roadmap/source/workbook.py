"""Derive workbook headings, topics, builds and navigation from artifact phases."""
from html import escape
import json
import subprocess


# Each exercise supplements the corresponding learn item; it does not define order.
PRACTICE = {
    'p0': [
        'Navigate to a practice folder, list its files and create a text file. Explain the working directory and the difference between a relative and an absolute path.',
        'Create a repository, commit the Hello June page, change one line and inspect its diff. Push to GitHub yourself and explain how to return to a previous version.',
        'Open your project folder, edit a file and use the integrated terminal. Learn how to find the file and line reported by an error.',
        'Install a supported Node.js version yourself from its official source when needed. Confirm Node and npm work; initialise a practice package and explain package.json and a package script.',
    ],
    'p1': [
        'Fetch a small JSON response and handle success, waiting and failure. Write the response function with async/await; avoid duplicate sends while it is pending.',
        'Represent messages as role/text objects. Convert an object to JSON and back, then handle malformed or unexpected data instead of trusting it.',
        'Define message and response types. Introduce an intentional type mismatch, explain the reported error and fix it.',
        'Learn React components, props, state and form events, then Next.js routing and server routes. Build the conversation view and a server route for model requests. Keep browser code and server code separate.',
        'Read server configuration from environment variables. Keep local configuration out of Git and out of browser bundles; do not add an API key just to finish this exercise.',
        'Explain API, tokens, context window, temperature, streaming and system prompt using one June request. Separate a system instruction from the user message and retrieved text.',
        'Create a replaceable model adapter. Begin with explicitly labelled simulated replies; later connect a small local model through your server route and display the real model name. Handle a missing or stopped runtime and then add streaming.',
    ],
    'p2': [
        'Draw a small animated network on Canvas. Resize it with its container, and pause or reduce animation when the user requests reduced motion.',
        'Recreate a small part of the network in Three.js to learn a scene, camera and renderer. Compare its complexity with your Canvas version before choosing the final approach.',
        'Use a short audio sample to measure volume and drive a visual change. Ask for microphone permission only if you choose to add microphone input.',
        'Make one simple glow or colour effect and explain which work happens in the shader. Keep an ordinary rendering fallback.',
        'Give idle, listening, thinking and speaking distinct states. Manual mood buttons are a visual exercise; label them so they do not imply June is actually listening or thinking.',
        'Optional: recreate one scene as React Three Fiber components. Skip this exercise if you keep the plain Canvas or Three.js version.',
    ],
    'p3': [
        'Learn browser recognition versus synthesis. June uses direct microphone recording and local Whisper base.en because browser recognition services can fail. Keep typing available and show words for editable review.',
        'Capture a short microphone clip with AudioWorklet, resample to mono 16 kHz PCM WAV, and transcribe on this Mac through the local server. Release starts transcription; do not claim live words while recording. Check silence, cancellation and microphone denial.',
        'Speak a short June reply with an available female system voice. Compare the role of a speech engine with that of the language model; a provider subscription is optional.',
        'Queue complete reply sentences in order as model text arrives. Check cancellation and buffering so late audio does not play after Stop.',
        'Connect playback events and available audio measurements to the orb. Mark a timed visual approximation as such; do not claim it measures sound if it does not.',
        'Wait for voices and voiceschanged, offer recognised female English voices, prefer Indian English when available and label the actual accent. Add preview, a saved selection and Stop; never use pitch as a substitute for selecting a female voice.',
    ],
    'p4': [
        'Write small functions using variables, lists, loops and classes. Express a simple message record in Python and explain its equivalent in JavaScript.',
        'Create an isolated environment for this project, install one required library and record its dependency. Explain which interpreter and environment your editor uses.',
        'Use a notebook to inspect a small dataset you own. Restart the kernel and run cells in order so the result does not depend on hidden earlier state.',
        'Implement an asynchronous request with an error and timeout path. Explain what concurrent work means and why it differs from running everything in sequence.',
        'Build a FastAPI endpoint and a WebSocket connection. Move the existing model and speech adapters behind this Python service, keeping the working browser interface and contracts. Bind the development service locally.',
    ],
    'p5': [
        'Try one voice pipeline framework with your chosen speech and model components. Measure the delay at each stage rather than assuming the framework makes it instant.',
        'Add deliberate wake-word activation and a visible listening indicator. Check false activations and provide a way to disable the microphone.',
        'Detect the beginning and end of speech. Try background noise and pauses, recording what the detector gets wrong.',
        'Interrupt June while she speaks. Cancel queued speech and stale generated output so old replies do not resume after you start speaking.',
        'Distinguish a thinking pause from the end of a turn. Adjust the behaviour with real examples of your own speaking style.',
        'Explain how audio moves between endpoints. Handle disconnect/reconnect and avoid leaving June appearing to listen when the connection has failed.',
        'Compare separate speech/model components with a speech-to-speech design on paper first. Use the modular route for this free-first build; trying a paid service is not a requirement.',
    ],
    'p6': [
        'Write a short June system prompt and compare its responses on fixed examples. Track failures instead of assuming a prompt always works.',
        'Complete the artifact personality workshop in your own words. Turn your approved values and boundaries into the prompt used by the actual model.',
        'Rewrite a few answers as short, natural spoken replies. Read them aloud; remove formatting that is awkward to speak.',
        'Save conversation history with explicit identifiers and a retention choice. Learn the database concepts in the listed topic; start locally if a hosted database is unnecessary.',
        'Let June propose a useful fact for review, then use only an approved fact in a new conversation. Do not automatically promote every chat message to lasting memory.',
        'Adjust voice pace and orb mood for a chosen conversational state. Keep the voice understandable and label limitations of your current speech engine.',
        'Build Save, Review, Edit, Delete and Export. Decline one proposed fact, save another, recall it after reload, edit it and finally delete it. Confirm deletion also removes it from the next model context.',
    ],
    'p7': [
        'Embed a few notes you own and compare similarity for related and unrelated questions. Explain why an embedding is not the original text.',
        'Store vectors with source IDs and metadata, then retrieve candidates. Choose a local store first if it meets your experiment; learn the alternatives named in the artifact.',
        'Split notes into passages while retaining source and location. Compare a few chunk sizes on the same questions.',
        'Inspect retrieved candidates before generating an answer. Reorder or rerank them and compare whether the useful passage rises to the top.',
        'Show the source passage and location with each supported answer. Ask a question absent from the notes and have June say the evidence is missing.',
    ],
    'p8': [
        'Package your existing web interface in one desktop approach. Keep the local bridge narrow and understand which operations run in the browser and which run on the Mac.',
        'Implement propose → approve → execute → observe for one tool. Limit iterations and handle failures rather than letting a generated plan run indefinitely.',
        'Connect one narrowly scoped MCP tool. Explain discovery, validated arguments, results and authorisation; the protocol itself does not grant access to your accounts.',
        'Choose one app or inspect one Shortcut. Add a fixed allowlist, show the exact action for approval, execute it at most once and observe its visible result. Never run model-written shell strings.',
        'Start with a clearly labelled simulator. Connect a real Home Assistant device only when you have compatible hardware and authorised access; read its resulting state.',
        'Capture only a screen or window you deliberately choose. Explain what will be sent to the model and avoid collecting screens in the background.',
        'Build one opt-in routine with a stop control. Use available authorised data; do not fabricate a calendar or weather response when disconnected.',
        'Start with one authorised read connection, such as a calendar. Restrict its scope, keep tokens server-side and confirm revoking access stops the connection.',
        'Prepare a practice checkout or booking review without paying. Show merchant, exact item/itinerary, total, fees and terms. Require new approval if the price changes; never retry a purchase blindly.',
        'Reject unsupported actions, invalid arguments and duplicate confirmations. Read back actual results and distinguish real devices/accounts from simulations.',
    ],
    'p9': [
        'Work through vectors, matrix multiplication, probability and a gradient on small examples. Explain which quantities the learning algorithm changes.',
        'Train a deliberately tiny network on a simple task. Record training and validation loss, and compare with a baseline.',
        'Build the same learning loop using tensors, automatic differentiation and an optimiser. Save and reload weights.',
        'Study a small attention calculation and construct a tiny transformer. Keep its size suited to a learning experiment on the available hardware.',
        'Encode and decode text with a tokenizer. Split data before training and explain how next-token prediction produces generated text.',
    ],
    'p10': [
        'Expand the Phase 6 character document into explicit values, tone and action boundaries, with examples you can evaluate. A principles file alone does not reproduce a frontier training process.',
        'Prepare conversations you have rights to use, remove secrets and duplicates, and reserve complete unseen scenarios for validation and final evaluation.',
        'Record an open-model baseline, train a small adapter and compare it on the held-out tasks. Use an appropriate GPU notebook if available; do not assume this Intel Mac can run a useful large fine-tune.',
        'Learn preference pairs and DPO. Try it only if a specific style issue remains and suitable compute is available; do not treat it as a mandatory paid step.',
        'Evaluate a licensed female voice independently of the language-model adapter. An original voice or a commercial service is an optional later choice; use a voice only with appropriate rights.',
        'Check each component offline separately: recognition, model, retrieval and speech. Measure memory and response time, and label any component still using an online service.',
        'Explain quantised base weights versus trainable adapters. Choose sequence length and batch size to fit the actual training environment; keep near-duplicates out of separate data splits.',
        'Prepare the data and evaluation locally first. Check a concrete configuration before using free notebook compute; do not buy or rent hardware to complete the planning exercise.',
    ],
    'p11': [
        'Create a fixed set of representative questions with expected properties, then rerun it after changes. Include facts, retrieval, refusal and tool proposals.',
        'Use a written rubric to compare personality and clarity. Start with manual scoring; a paid model judge is optional and its judgement is not ground truth.',
        'Check approval boundaries implemented from the start: cancelling does nothing, changed details require review and spending/sending/deletion never happen silently.',
        'Put hostile instructions in a practice retrieved document and confirm that June treats them as source text, not permission to act.',
        'Verify the listening indicator, microphone stop, retention controls and deletion. Avoid recording private content merely to produce a log.',
        'Record useful timing, errors and action outcomes, redacting secrets. Learn the named observability tool, but keep the initial evidence local if that is enough.',
        'Exercise disconnected devices, revoked access, duplicate requests, cancelled actions, timeouts and changed prices. Check that failures are accurately reported.',
    ],
    'p12': [
        'Make a desktop package, document installation and updates, and offer an explicit startup preference. Verify the packaged app rather than just the development server.',
        'Build a small React Native/Expo client for the same backend. Preserve memory and approval semantics on the phone.',
        'Use a simulated endpoint first. If suitable hardware becomes available, connect its microphone, speaker and wake word; verify a real conversation before calling the speaker complete.',
        'Plan authentication and hosting for your actual model and clients. Keep a local personal deployment until remote access is useful; choose hosting only after measuring requirements.',
        'Track inference and speech usage and cache only appropriate repeatable content. Record actual local resource use or service charges; do not assume every provider bills the same way.',
        'Package the service reproducibly and create an automated build/check workflow. Practise rollback and do not automatically publish private data.',
        'Keep the always-on home controller separate from training experiments. Confirm loss of the model or network produces a clear unavailable state rather than a false successful action.',
    ],
}

BUILD = {
    'p0': ('Create a minimal Hello June page in your own repository. Commit it and publish it through GitHub Pages yourself; inspect what will be public before publishing.', 'The live page shows Hello June, the committed source is available to you, and you can explain terminal, editor, Git and Node/npm roles.'),
    'p1': ('Optional refresher within this phase: if form events or DOM rendering are rusty, make a tiny `index.html`/`styles.css`/`app.js` screen first. Skip this refresher if comfortable. Then build the phase project in React/Next.js with typed messages, an asynchronous adapter, a June prompt, server configuration and streaming real replies from a small local model when ready.', 'Blank input sends nothing; Enter submits once; long text wraps; text such as `<script>` is rendered safely; failures leave controls usable. A simulated adapter is labelled demo. The final phase build produces real model replies and streams them. Explain the browser → server → model flow.'),
    'p2': ('Add your own orb to the Phase 1 app. Connect the real request state to its visual state, then connect the available audio signal.', 'The orb resizes without overflow and distinguishes all four moods. An animation does not imply a connected microphone or a real thinking model. Reduced motion remains usable.'),
    'p3': ('Add push-to-talk using local Whisper base.en, editable transcript review, the selected female voice, Preview and Stop. Keep recordings temporary and connect the orb to actual recording and playback events.', 'Speak a short request, review it, send it to the model, hear its reply and stop playback. Saved voice selection survives reload. Unsupported recognition or missing female voices are clearly shown; typing remains usable.'),
    'p4': ('Keep the working interface, move provider/speech calls behind your Python service, and retain the same message and error contracts.', 'The browser talks to the Python backend; requests, streaming and failures work. Restarting the service does not leave the UI stuck or expose configuration.'),
    'p5': ('Extend Phase 3 push-to-talk into the hands-free loop, using the Python foundation from Phase 4. Add wake-word, turn detection, interruption and measured timing.', 'June wakes deliberately, handles a turn and stops when interrupted. Timings are recorded on your actual Mac. A one-second target is not a promise or a completion claim.'),
    'p6': ('Use the personality workshop to personalise June and add approved persistent memory separately from chat history.', 'A saved preference is recalled in a new conversation; a declined fact is not saved; edited/deleted facts are reflected in subsequent context. Use a fixed set of examples to check personality instead of claiming it never fails.'),
    'p7': ('Connect your own small note collection to retrieval, generation and citations, then ask about it through the voice flow.', 'You can inspect the passage supporting an answer. Absent information is reported honestly. Deleted or unauthorised sources are not retrieved.'),
    'p8': ('Begin with one approved Mac action, then add email, job applications, editable websites/designs, PDF/PPTX outputs, home control and transaction review one connection at a time. Use the capability project checks below before live writes or payments. A focus playlist or briefing requires the corresponding real authorised service. Use simulations until devices/accounts are available, and record those dependencies.', 'One real Mac action is approved and visibly completes; cancelling and unsupported commands have no effect. Connected services/devices report actual outcomes and revoked access fails. Booking/order review shows exact details without making an unapproved purchase. Simulated integrations are not marked as completed real integrations.'),
    'p9': ('Train a tiny model on licensed or self-owned text using the learning loop you wrote. Keep a validation split, a simple baseline and saved weights.', 'Weights can be reloaded, samples and losses are recorded, and you can explain tokenisation, attention and optimisation. This learning model is not claimed to be a capable June assistant.'),
    'p10': ('Adapt a chosen open model to the behaviours you can measure, export/version the adapter and select a speech voice separately. Investigate DPO only if useful; benchmark offline operation on appropriate hardware.', 'Held-out results compare baseline and adapter without leakage; factual/tool behaviour is checked as well as style. An export runs in the actual app; the base version is retained for rollback. Offline claims match the components and hardware actually verified.'),
    'p11': ('Grow the earlier completion checks into the artifact\'s 100-question suite and a score-history page. Cover personality, accuracy, speed and tool safety.', 'The suite contains 100 recorded cases, results are inspectable across versions, and failure handling is checked. Approval and privacy protections already implemented in earlier phases are verified here, not postponed until this phase.'),
    'p12': ('Package the Mac app first, then the phone and speaker endpoints when their dependencies are available. Connect them to a consistent memory store and permission model.', 'Each claimed endpoint works in its packaged form, uses the approved memory and honours revocation/approval controls. Update/rollback and failure states are documented. Unavailable hardware or unconnected accounts remain pending.'),
}


def phase_data(html):
    script = """const fs=require('fs'), vm=require('vm');
const html=fs.readFileSync(0,'utf8');
const start=html.indexOf('const PHASES ='), end=html.indexOf('const EXTRAS =',start);
if(start<0 || end<0) throw Error('Phase data not found');
const context={};vm.createContext(context);
vm.runInContext(html.slice(start,end)+';globalThis.output=JSON.stringify(PHASES)',context);
process.stdout.write(context.output);
"""
    result = subprocess.run(['node', '-e', script], input=html, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def capability_checks(html):
    """Reuse artifact project text so the workbook cannot develop another task order."""
    import re
    from html import unescape
    section = html.split('<ol class="milestones">', 1)[1].split('</ol>', 1)[0]
    clean = lambda text: unescape(re.sub(r'<[^>]+>', '', text)).strip()
    result = []
    for title, body in re.findall(r'<h3>(.*?)</h3>(.*?)</div></li>', section, re.S):
        result += ['### ' + clean(title), '']
        result += [clean(text) for text in re.findall(r'<p[^>]*>(.*?)</p>', body, re.S)]
        result += ['']
    return result


def generate(html, output_dir):
    phases = phase_data(html)
    # Fail before writing if exercises no longer match the authoritative phase topics.
    if [p['n'] for p in phases] != list(range(13)):
        raise ValueError('Expected artifact phases 0–12 in sequence')
    for p in phases:
        if len(PRACTICE[p['id']]) != len(p['learn']):
            raise ValueError(f"Exercise/topic mismatch in {p['id']}")
    md = [
        '# Building June — phase-by-phase workbook',
        '',
        '**Main assistant route: Phases 0–8 → Phase 11 → Phase 12. Optional model-learning tracks: Phases 9–10.** This workbook follows the Building June artifact. Phase numbers, names, learning topics, project versions and resource order are generated from the artifact\'s phase data. The artifact is the overview; this workbook adds practice and completion checks inside each matching phase.',
        '',
        'The former Session 1–8 shortcut is retired. Do not use it as a second course. The optional HTML/CSS refresher is inside Phase 1; toolkit setup is Phase 0, the orb is Phase 2, Python is Phase 4, memory is Phase 6 and Mac actions are Phase 8.',
        '',
        'You write June yourself. Start on your current Intel Mac with free resources. A named commercial provider is a topic/example, not a required subscription. Use simulated replies only while learning the flow, label them, then connect a real model. Install tools and choose connections yourself when their phase requires them; no hardware purchase is required to begin.',
        '',
        '## How to use both documents',
        '',
        '1. Open the same phase in the artifact and this workbook.',
        '2. Read **Learn** in the listed order and do each matching **Practice** exercise.',
        '3. Write the **Build** project, complete its checks and explain its flow in your own words.',
        '4. Tick the corresponding artifact items only when you understand or have completed them. Keep short notes on failures and fixes.',
        '5. Follow Phases 0–8, then Phase 11 and Phase 12. Study Phases 9–10 optionally when useful; training does not gate automation. Apply safety and completion checks as each feature is introduced.',
        '',
        '## Phase index',
        '',
        '| Phase | Same phase in the artifact | Build | Route |',
        '|---|---|---|---|',
    ]
    for p in phases:
        md.append(f"| {p['n']} | [{p['title']}](#phase-{p['n']}) | {p['build'][0]} | {'Optional model study' if p.get('optional') else 'Main assistant route'} |")
    for p in phases:
        md += ['', f'<a id="phase-{p["n"]}"></a>', '', f'## Phase {p["n"]} — {p["title"]}', '', p['why'], '', '### Learn and practise — same order as the artifact', '']
        for i, ((topic, explanation), exercise) in enumerate(zip(p['learn'], PRACTICE[p['id']]), 1):
            md += [f'#### {p["n"]}.{i} {topic}', '', f'**Learn:** {explanation}.', '', f'**Practice:** {exercise}', '']
        task, check = BUILD[p['id']]
        md += [f'### Build — {p["build"][0]}', '', '**Artifact project:** ' + p['build'][1], '', '**Your exercise:** ' + task, '', '**Completion checks:** ' + check, '', '### Resources — same order as the artifact', '']
        for resource in p['res']:
            md.append(f'- [{resource[0]}]({resource[1]})' + (' — paid; optional.' if len(resource) > 2 and resource[2] else ''))
    md += [
        '', '## Capability milestones within this same course', '',
        '| Milestone | When to check it |', '|---|---|',
        '| Voice conversation | Phase 3 adds push-to-talk; Phase 5 adds hands-free turn-taking and interruption. |',
        '| Approved saved memory | Phase 6. Recall a saved fact in a new conversation and verify editing/deletion. |',
        '| One authorised Mac action | Phase 8. Observe a real result and confirm cancellation prevents it. |',
        '| First combined milestone | During Phase 8: voice conversation + approved memory + one authorised Mac action. |',
        '| Home, accounts and transaction review | Phase 8 introduces them; advance each only as hardware and authorised connections become available. |',
        '| Tiny model from scratch | Optional Phase 9 learning project; not needed for automation or fine-tuning. |',
        '| Adapted open model and separate voice | Optional Phase 10; evaluate against the original model, retain rollback. |',
        '| Production endpoints | Phase 12, after the Phase 11 regression/safety review. |',
        '', 'These are checkpoints in the main route and optional study tracks. Basic error handling, privacy and action approval are required when features are introduced; Phase 11 consolidates their evaluation.',
        '', '## Phase 8 project acceptance checks', '', 'Before each live integration: compare model candidates on your tasks; test tools in a simulator; validate arguments on the server; treat retrieved content as untrusted; restrict permissions; bind approval to exact action details; verify results; retain cancellation, a log without secrets and rollback. No verified success means no completion claim.', '', *capability_checks(html), '', '## Hardware and model-training notes', '',
        'Your current Mac is the development machine. Measure a small local model before making offline-performance claims. A home hub serves a different purpose from training compute; use a labelled simulator until compatible hardware is available.',
        '',
        'Optional Phase 9 teaches a deliberately tiny model from scratch. Optional Phase 10 teaches adapting an existing open model with LoRA/QLoRA, reviewed examples and separate validation/test conversations. Fine-tuning text behaviour does not train a female speaking voice and does not automatically connect accounts or devices.',
        '',
        'Prepare data locally first. For early 3–8B QLoRA experiments, the artifact uses 16–24 GB GPU memory as a planning target, subject to model/configuration; it is not a fit guarantee. Free GPU notebook availability varies. Defer purchases and rentals until a concrete experiment requires them.',
        '',
        'Use the artifact\'s hardware guide and training guide at their corresponding phases: [training requirements](https://unsloth.ai/docs/get-started/fine-tuning-for-beginners/unsloth-requirements), [Colab limits](https://research.google.com/colaboratory/faq.html).',
        '', '## Start here', '',
        'If you have not started the course, begin with **Phase 0 — Set up your toolkit**. If a topic is already familiar, demonstrate its exercise and tick it off; do not start a new numbering scheme. Share your own work or a specific error when you want a hint or review.',
        '', 'The local roadmap and this workbook now share one sequence. The original hosted Claude artifact has not been republished from this session.', '',
    ]
    (output_dir / 'June Build Workbook.md').write_text('\n'.join(md))
    (output_dir / 'phases.json').write_text(json.dumps(phases, ensure_ascii=False, indent=2) + '\n')
    links = ''.join(f'<li><a href="#{p["id"]}"><strong>Phase {p["n"]} · {escape(p["title"])}</strong></a><br><span>{escape(p["build"][0])}{" · Optional model study" if p.get("optional") else ""}</span></li>' for p in phases)
    section = f'''      <section id="self-build">
        <div class="eyebrow">One roadmap · practical assistant first</div>
        <h2>Follow the same phases in both documents</h2>
        <p class="intro">Start with Phase 0. The artifact shows what to learn and build; the workbook provides practice and completion checks inside those same phases. Both use the same phase numbers, names, topics and project versions.</p>
        <div class="goal-banner"><div class="label">One course, two views</div><h3>Build useful capabilities. Study model training optionally.</h3><p>The separate eight-session shortcut is retired. HTML and CSS are an optional refresher within Phase 1, since you already know them. Node.js setup belongs in Phase 0, the orb in Phase 2, voice in Phase 3, Python in Phase 4, memory in Phase 6 and Mac actions in Phase 8.</p></div>
        <p class="intro">Main assistant route: Phases 0–8 → Phase 11 → Phase 12. Phases 9–10 are optional model-learning tracks; they do not gate useful automation. Testing, privacy and action approvals begin with each feature, before real account or device actions.</p><ul class="training-flow">{links}</ul>
        <p class="pace">The first combined milestone is checked during Phase 8: voice conversation, approved saved memory and one authorised Mac action. Main assistant route: Phases 0–8 → Phase 11 → Phase 12. Phases 9–10 are optional model-learning tracks; they do not gate useful automation. Testing, privacy and action approvals begin with each feature, before real account or device actions.</p>
        <div class="section-links"><a href="June%20Build%20Workbook.md" download>Download the matching workbook</a><a href="#p0">Begin Phase 0</a><a href="#roadmap">Phase checklist</a><a href="#build-goal">Capability milestones</a></div>
      </section>'''
    (output_dir / 'self-build.html').write_text(section + '\n')
    return section
