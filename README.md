# June v0.0

Hello, I'm June — a personal AI assistant, built one phase at a time.

This is the Phase 0 foundation: a static greeting page written in HTML and CSS. Conversation, voice and memory are later projects in the Building June roadmap.

## Files

- `index.html` contains the page text and structure.
- `styles.css` contains the colours, layout and decorative orb.

There are no external assets, dependencies or build steps.

## Edit and preview

Open this folder in your editor. Change the greeting in `index.html`, or the colour variables at the top of `styles.css`.

To preview with Python installed:

```sh
cd /Users/apple/Documents/June
python3 -m http.server 8080 --bind 127.0.0.1
```

Open `http://127.0.0.1:8080` in your browser. Refresh after editing. Press Control+C in the terminal to stop the server.

## Save a change with Git

Inspect your changes before committing:

```sh
git diff
git add index.html styles.css README.md
git commit -m "Update June's greeting page"
git push origin main
```

## Publish with GitHub Pages

The source repository is [Shivaxsh/june](https://github.com/Shivaxsh/june).

In the repository's **Settings → Pages**, choose **Deploy from a branch**, select **main** and **/(root)**, and save. Once GitHub reports a successful deployment, open [June](https://shivaxsh.github.io/june/).

The stylesheet uses a relative path, so it works under the repository's `/june/` address. Updates pushed to the publishing branch deploy again. Check the published page after an update; a local preview alone does not confirm publication.

The repository and published page are public. Keep private notes and credentials out of this folder.
