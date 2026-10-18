# Building June — personal assistant roadmap

Open `building-june.html` for the roadmap, voice demo, checklist and personality workshop. `June Build Workbook.md` contains the same phases with practice exercises and project acceptance checks.

## Main route

Phases 0–8 → Phase 11 → Phase 12. Phases 9–10 are optional model-learning tracks. Testing, permissions, privacy, cancellation and result verification start with each feature; Phase 11 consolidates them. Existing models can power useful automation; fine-tuning is optional and cannot guarantee frontier-model reasoning.

Phase 8 projects explicitly cover Mac/home control, accounts/email, truthful job applications, editable websites/designs, PDF/PPTX outputs, groceries/movie tickets and a separate payment milestone. Each requires its own integrations and verification. These documents do not implement those future capabilities or mark any build complete.

## Edit and regenerate

- Edit `source/building-june.source.html` for phase data, milestones and presentation.
- Edit `source/workbook.py` for matching practice exercises.
- Run `python3 docs/roadmap/source/build.py` from the June repository.
- Phase headings, project versions, topic/resource order and capability acceptance checks are generated from the artifact, avoiding competing curricula.
- `phases.json` and `self-build.html` are generated data/overview, not separate courses.

The source is a snapshot of the latest local roadmap, including the local Whisper and Python phase updates. Its embedded orb, female voice controller and workshop are preserved. All 97 checkbox IDs, phase numbers and storage keys retain their identities; optional status changes no checkbox meaning. No checked items or personality answers are changed by this update.

## Preview and saved progress

Serve this folder on the existing local roadmap origin:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory /Users/apple/Documents/June/docs/roadmap
```

Open http://127.0.0.1:8765/building-june.html . Progress belongs to the browser and origin; retain that address to reuse it. Export/Import transfers progress and personality answers across copies. Keep backups private. No private progress data belongs in this repository.

This is the local artifact. The original hosted Claude artifact has not been republished. The public GitHub Pages v0.0 site and June's app implementation are unchanged.
