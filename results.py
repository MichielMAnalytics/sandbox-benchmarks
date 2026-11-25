"""Print the table of results in results/, one JSON file per provider, written by the benchmarks with --save.

uv run results.py            # the medians, as a markdown table
uv run results.py --ranges   # minimum to maximum, in place of the medians
uv run results.py --write    # replace the table in README.md
uv run results.py --check    # fail if the table in README.md is out of date
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
START, END = '<!-- results: written by results.py -->', '<!-- /results -->'


def table(ranges: bool = False) -> str:
    """The results as markdown: a row per provider, fastest at `1 + 1` first, and any notes below it."""
    results = [json.loads(path.read_text()) for path in sorted((ROOT / 'results').glob('*.json'))]
    cases = list(results[0]['cases'])
    results.sort(key=lambda r: r['cases'][cases[0]]['median'])
    rows = [['Provider', *(f'`{case}`' if case == '1 + 1' else case for case in cases)]]
    fastest = {case: min(r['cases'][case]['median'] for r in results) for case in cases}
    for r in results:
        row = [r['provider']]
        for case in cases:
            c = r['cases'][case]
            if ranges:
                row.append(f'{c["min"]}–{c["max"]}')
            elif c['median'] == fastest[case]:
                row.append(str(c['median']))
            else:
                # how many times slower than the fastest provider at this case
                slower = c['median'] / fastest[case]
                row.append(f'{c["median"]} ({slower:.1f}x)' if slower < 10 else f'{c["median"]} ({slower:.0f}x)')
        rows.append(row)
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    rows.insert(1, ['-' * w for w in widths])
    lines = ['| ' + ' | '.join(cell.ljust(w) for cell, w in zip(row, widths)) + ' |' for row in rows]

    # results are only comparable from the same place, so say where, and point out any from somewhere else
    location = Counter(r['location'] for r in results).most_common(1)[0][0]
    dates = sorted({r['date'] for r in results})
    when = dates[0] if len(dates) == 1 else f'{dates[0]} to {dates[-1]}'
    kind = 'Minimum to maximum' if ranges else 'Median'
    intro = f'{kind} milliseconds from {location}, {when}, from checking out a new session to that session ending:'
    notes = []
    for r in results:
        elsewhere = f'Run from {r["location"]}. ' if r['location'] != location else ''
        if elsewhere or r.get('note'):
            notes.append(f'- {r["provider"]}: {elsewhere}{r.get("note", "")}'.rstrip())
    return '\n'.join([intro, '', *lines, '', *notes])


def main() -> None:
    if '--write' not in sys.argv and '--check' not in sys.argv:
        print(table(ranges='--ranges' in sys.argv))
        return
    readme = ROOT / 'README.md'
    old = readme.read_text()
    before, rest = old.split(START)
    new = f'{before}{START}\n\n{table()}\n\n{END}{rest.split(END)[1]}'
    if '--write' in sys.argv:
        readme.write_text(new)
    elif new != old:
        sys.exit('the table in README.md is out of date, run `uv run results.py --write`')


if __name__ == '__main__':
    main()
