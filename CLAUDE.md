@AGENTS.md

# Working on June with Claude Code

## Every session

1. Start the local model, then the app, with the Browser pane launch configs in `.claude/launch.json`:
   `june-model` (Ollama on 127.0.0.1:11434), then `june` (`npm run dev`: Python backend on 8001 + Next.js on 127.0.0.1:3001).
   Microphone permission belongs to **June Audio** itself (`local.june.audio`): the helper re-execs as its own responsible process (`native/JuneAudio.swift`, `becomeResponsibleForSelf`), so it works however June is started. Rebuilding it with `npm run audio:setup` changes its ad-hoc signature, and macOS may ask once more after a rebuild.
2. Keep two tabs open in the built-in browser:
   - June app: http://127.0.0.1:3001
   - Building June artifact: https://claude.ai/artifact/FyMvoJizXCaVFcU5Kd5tTF
     (published from `docs/roadmap/building-june.html`; the roadmap source is `docs/roadmap/phases.json` + `docs/roadmap/source/`)
3. Check `git status` and preserve uncommitted work. Branch per version (`codex/june-v0.x`); never commit to `main`.

## Checks before calling work done

```sh
npm run typecheck
npm test
npm run backend:test
npm run build
```

Opt-in real-model checks (`scripts/check-reliability.py`, `scripts/check-knowledge.py --run`) write ignored reports under `.june-work/` that contain private reply text — never publish them.

## Ground rules

- Port 3001 is intentional (Mad Realm uses 3000). Everything binds to loopback; no paid APIs or cloud inference.
- Keep `.env.local`, models, `.june-work/`, private documents and personality notes out of Git.
- Human acceptance gates (spoken conversation, room audio) are recorded as pending until the user performs them; never mark them passed from automated runs.
- Learning progress and workbook checkboxes belong to the user; regenerate the roadmap with `docs/roadmap/source/workbook.py` without changing their state.
