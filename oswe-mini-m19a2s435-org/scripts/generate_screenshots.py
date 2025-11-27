from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs('docs/screenshots', exist_ok=True)

cases = [
    ('success.png', 'Success', (46, 204, 113)),
    ('failure.png', 'Failure', (239, 68, 68)),
    ('in_progress.png', 'In Progress', (99, 102, 241)),
    ('idempotent_blocked.png', 'Idempotent: Blocked', (59, 130, 246)),
    ('compensation_triggered.png', 'Compensated', (249, 115, 22)),
]

for fn, text, color in cases:
    img = Image.new('RGB', (1200, 600), (250, 250, 250))
    d = ImageDraw.Draw(img)
    # Try to load default font
    try:
        font = ImageFont.truetype('arial.ttf', 48)
    except Exception:
        font = ImageFont.load_default()
    # Draw headline
    d.rectangle([60, 60, 1140, 540], fill=(255, 255, 255))
    d.text((80, 200), text, fill=color, font=font)
    path = os.path.join('docs','screenshots', fn)
    img.save(path)
    print('Saved', path)
