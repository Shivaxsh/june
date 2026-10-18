"""Build the roadmap and workbook together; preserve the existing progress contract."""
from pathlib import Path
from workbook import generate, phase_data

root = Path(__file__).resolve().parent.parent
source = root / 'source' / 'building-june.source.html'
html = source.read_text()
phases = phase_data(html)
assert [p['id'] for p in phases] == [f'p{i}' for i in range(13)]
assert sum(len(p['learn']) + 1 for p in phases) == 97
assert 'building-june-progress-v2' in html
assert html.count('<!-- GENERATED_LEARNING_OVERVIEW -->') == 1
html = html.replace('<!-- GENERATED_LEARNING_OVERVIEW -->', generate(html, root))
(root / 'building-june.html').write_text(html)
print('Generated roadmap and workbook together; 13 phases, 97 preserved checkbox IDs.')
