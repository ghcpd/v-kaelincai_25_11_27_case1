import os
from html import escape

LABELS = {
    "success.svg": "Status: SUCCESS\nSlot: slot-123\nRequest: req-success-1",
    "failure.svg": "Status: FAILURE\nSlot: slot-456\nRequest: req-timeout-1\nError: CALENDAR_TIMEOUT",
    "in_progress.svg": "Status: IN-PROGRESS\nAwaiting calendar...",
    "idempotent_retry.svg": "Status: SUCCESS\nIdempotent retry\nSame appointment_id",
    "compensation.svg": "Status: FAILURE\nCompensation executed\nSlot released"
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TEMPLATE = """
<svg width='640' height='360' xmlns='http://www.w3.org/2000/svg'>
  <rect width='640' height='360' fill='#f5f5f5' />
  <text x='40' y='60' font-family='Arial, sans-serif' font-size='20' fill='#000'>%s</text>
</svg>
"""

for filename, text in LABELS.items():
    # Replace newlines with tspan for multi-line
    lines = text.split("\n")
    tspans = []
    y = 0
    for i, line in enumerate(lines):
        tspans.append(f"<tspan x='40' dy='{30 if i>0 else 0}'>{escape(line)}</tspan>")
    svg_content = TEMPLATE % "".join(tspans)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"wrote {path}")
