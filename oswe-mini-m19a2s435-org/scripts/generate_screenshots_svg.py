import os
os.makedirs('docs/screenshots', exist_ok=True)

cases = [
    ('success.svg', 'Success', '#2ECC71'),
    ('failure.svg', 'Failure', '#EF4444'),
    ('in_progress.svg', 'In Progress', '#6366F1'),
    ('idempotent_blocked.svg', 'Idempotent: Blocked', '#3B82F6'),
    ('compensation_triggered.svg', 'Compensated', '#F97316'),
]

for fn, text, color in cases:
    svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='600'>
  <rect width='100%' height='100%' fill='#F8FAFC'/>
  <rect x='60' y='60' width='1080' height='480' rx='20' fill='white' stroke='#E6EEF8' />
  <text x='120' y='280' font-family='Arial' font-size='48' fill='{color}'>{text}</text>
  <text x='120' y='340' font-family='Arial' font-size='20' fill='#6B7280'>Placeholder screenshot for {text}</text>
</svg>
"""
    path = os.path.join('docs', 'screenshots', fn)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(svg)
    print('Saved', path)
