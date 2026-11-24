"""Choose a fixed house style for June's documents, or let her choose a design each time.

Usage: backend/.venv/bin/python scripts/make-templates.py <preset|none> [Templates folder]
Presets: clay midnight forest citrus mono ocean plum blueprint sunset newsprint neon botanical.
Writes house-style.txt (default folder: ~/Documents/June Documents/Templates); "none" removes it.
Words in a request ("make it dark") still win. Your own template.docx / template.pptx always win.
"""
import sys
from pathlib import Path

PRESETS = {'clay', 'midnight', 'forest', 'citrus', 'mono', 'ocean', 'plum', 'blueprint', 'sunset', 'newsprint', 'neon', 'botanical'}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in PRESETS | {'none'}:
        sys.exit(__doc__)
    folder = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / 'Documents' / 'June Documents' / 'Templates'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'house-style.txt'
    if sys.argv[1] == 'none':
        target.unlink(missing_ok=True); print('June chooses a design for each document.')
    else:
        target.write_text(sys.argv[1] + '\n'); print('House style:', sys.argv[1])


if __name__ == '__main__':
    main()
