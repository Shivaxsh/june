# Open a saved project in VS Code

In **Systems → Hands → Open a project**, save a short name and an existing absolute folder path. Saving only registers the folder; it does not open it or approve it. Up to ten folders can be saved. June stores the canonical path, so a symlink is saved as its resolved destination.

Choose **Review opening…**, or ask **“Open the June project in VS Code.”** The approval card shows the exact saved folder. Approve once; leave **Remember approval for this exact project folder** checked to open it next time without another card. Each folder has its own approval, separate from opening VS Code alone. **Forget approval** restores review; **Remove project** revokes its approval and cancels pending proposals. An action already handed to macOS cannot be cancelled by removing its project.

Chat can select saved names only. It cannot add folders, supply a path, run a command or approve a proposal. Unknown names ask you to add the project in Hands. The service revalidates the canonical path and filesystem identity at proposal, approval and execution; a moved, missing or replaced directory must be removed and added again. The native helper checks the same identity before passing the folder URL to VS Code through NSWorkspace. VS Code may show its own Workspace Trust dialog.

A successful result means macOS accepted the folder request and VS Code was observed running or active. June does not inspect its editor or claim to have verified the folder contents. Uncertain outcomes are never automatically retried. Explicit direct requests reuse their request id on network retry; one id cannot execute twice. Approval remains bound to the stored fingerprint and expires after five minutes.

Project paths and action snapshots stay in the private local actions SQLite database. Removed projects disappear from the registry; their action history retains the approved path for the existing 30-day history period.

## API

- `GET /api/actions` adds `projects: [{id, name, folderPath, remembered}]`.
- `POST /api/actions/projects` takes `{name, path}` for manual registration.
- `POST /api/actions/projects/{id}/{remove|forget}` takes `{}`.
- `POST /api/actions/propose` takes `{action: "open-project", projectId}`.
- `POST /api/actions/run` takes `{action: "open-project", projectId, requestId}` and requires that folder's remembered approval.
- Existing approve/cancel routes bind the same action fingerprint. Existing app-only approval is unchanged.
