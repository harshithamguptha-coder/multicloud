from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent


def font(size, bold=False):
    names = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


TITLE = font(34, True)
H1 = font(24, True)
H2 = font(19, True)
BODY = font(17)
SMALL = font(14)


def text_size(draw, text, fnt):
    box = draw.multiline_textbbox((0, 0), text, font=fnt, spacing=5)
    return box[2] - box[0], box[3] - box[1]


def center_text(draw, box, text, fnt, fill="#152238", spacing=5):
    x1, y1, x2, y2 = box
    w, h = text_size(draw, text, fnt)
    draw.multiline_text(
        ((x1 + x2 - w) / 2, (y1 + y2 - h) / 2),
        text,
        font=fnt,
        fill=fill,
        align="center",
        spacing=spacing,
    )


def round_box(draw, box, fill, outline="#2f3a4f", width=3, radius=18):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw, start, end, fill="#2f3a4f", width=4):
    draw.line([start, end], fill=fill, width=width)
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    if abs(dx) > abs(dy):
        sign = 1 if dx > 0 else -1
        pts = [(ex, ey), (ex - 16 * sign, ey - 9), (ex - 16 * sign, ey + 9)]
    else:
        sign = 1 if dy > 0 else -1
        pts = [(ex, ey), (ex - 9, ey - 16 * sign), (ex + 9, ey - 16 * sign)]
    draw.polygon(pts, fill=fill)


def label(draw, xy, text, fill="#263348"):
    draw.multiline_text(xy, text, font=SMALL, fill=fill, align="center", spacing=4)


def architecture_png():
    img = Image.new("RGB", (2200, 1500), "#f6f8fb")
    d = ImageDraw.Draw(img)
    d.text((90, 55), "Secure Multi-Cloud Data Integrity and Self-Healing Storage System", font=TITLE, fill="#111827")
    d.text((92, 102), "System Architecture UML", font=H1, fill="#43506a")

    user = (80, 235, 330, 360)
    browser = (430, 185, 900, 560)
    flask = (1030, 165, 1590, 610)
    services = (1030, 735, 1590, 1045)
    mongo = (1705, 200, 2115, 680)
    b2 = (1705, 805, 2115, 1230)

    round_box(d, user, "#fff7ed", "#c2410c")
    center_text(d, user, "Authenticated\nUser", H2)

    round_box(d, browser, "#eef7ff", "#2563eb")
    d.text((455, 210), "Client Browser", font=H1, fill="#1d4ed8")
    for i, txt in enumerate([
        "Jinja HTML Pages\nlogin, signup, dashboard,\nintegrity, recovery, storage",
        "static/js/app.js\nFetch API + UI rendering",
        "Bootstrap + styles.css",
    ]):
        y = 270 + i * 92
        round_box(d, (470, y, 860, y + 68), "#ffffff", "#93c5fd", width=2, radius=10)
        center_text(d, (470, y, 860, y + 68), txt, BODY)

    round_box(d, flask, "#f0fdf4", "#16a34a")
    d.text((1055, 190), "Flask Application Server", font=H1, fill="#15803d")
    flask_items = [
        "app.py\nRoute/controller layer",
        "Session Auth\nWerkzeug password hashing",
        "MongoState\nDB client manager",
        "Integrity Helpers\nnormalize names\nSHA-256 checks",
    ]
    for i, txt in enumerate(flask_items):
        x = 1068 + (i % 2) * 250
        y = 255 + (i // 2) * 155
        round_box(d, (x, y, x + 220, y + 105), "#ffffff", "#86efac", width=2, radius=10)
        center_text(d, (x, y, x + 220, y + 105), txt, BODY)

    round_box(d, services, "#fefce8", "#ca8a04")
    d.text((1055, 760), "Service Layer", font=H1, fill="#a16207")
    round_box(d, (1070, 825, 1315, 990), "#ffffff", "#fde047", width=2, radius=10)
    center_text(d, (1070, 825, 1315, 990), "services.integrity\nverify_and_heal()\nsha256_bytes()\nutc_now()", BODY)
    round_box(d, (1340, 825, 1560, 990), "#ffffff", "#fde047", width=2, radius=10)
    center_text(d, (1340, 825, 1560, 990), "services.storage\nMultiCloudStorage", BODY)

    round_box(d, mongo, "#f5f3ff", "#7c3aed")
    d.text((1730, 225), "MongoDB Atlas", font=H1, fill="#6d28d9")
    for i, txt in enumerate(["users", "files", "deleted_files", "recovery_logs"]):
        y = 300 + i * 82
        round_box(d, (1750, y, 2070, y + 52), "#ffffff", "#c4b5fd", width=2, radius=8)
        center_text(d, (1750, y, 2070, y + 52), txt, BODY)

    round_box(d, b2, "#ecfeff", "#0891b2")
    d.text((1730, 830), "Backblaze B2 S3-Compatible API", font=H1, fill="#0e7490")
    round_box(d, (1750, 920, 2070, 1005), "#ffffff", "#67e8f9", width=2, radius=10)
    center_text(d, (1750, 920, 2070, 1005), "Primary Bucket", H2)
    round_box(d, (1750, 1070, 2070, 1155), "#ffffff", "#67e8f9", width=2, radius=10)
    center_text(d, (1750, 1070, 2070, 1155), "Backup Bucket", H2)

    arrow(d, (330, 297), (430, 297))
    label(d, (345, 250), "uses\nweb UI")
    arrow(d, (900, 360), (1030, 360))
    label(d, (928, 278), "HTTPS / Fetch API\nupload, list,\nverify, recover")
    arrow(d, (1310, 610), (1310, 735))
    label(d, (1325, 640), "calls")
    arrow(d, (1590, 380), (1705, 380))
    label(d, (1608, 300), "metadata,\nsessions,\nlogs")
    arrow(d, (1590, 900), (1705, 960))
    label(d, (1608, 835), "upload /\ndownload /\ndelete")
    arrow(d, (1590, 950), (1705, 1110))
    label(d, (1605, 1015), "backup copy\n+ recovery source")
    arrow(d, (1210, 825), (1210, 610))
    label(d, (1060, 655), "verify and heal")
    arrow(d, (1450, 825), (1450, 610))
    label(d, (1468, 655), "storage operations")

    note = (
        "Core rule: every new file is stored in both buckets with one shared object_name.\n"
        "MongoDB stores the trusted original_hash. Verification compares bucket hashes against it.\n"
        "If primary is damaged and backup is valid, the app restores primary automatically."
    )
    round_box(d, (360, 1235, 1840, 1390), "#ffffff", "#94a3b8", width=2, radius=14)
    center_text(d, (390, 1265, 1810, 1360), note, BODY)

    img.save(ROOT / "system_architecture.png", "PNG")


def sequence_png():
    img = Image.new("RGB", (2200, 3200), "#fbfcff")
    d = ImageDraw.Draw(img)
    d.text((90, 55), "File Lifecycle Sequence UML", font=TITLE, fill="#111827")
    d.text((92, 103), "Upload, Verify/Self-Heal, Delete, Recover", font=H1, fill="#43506a")

    actors = [
        ("User", 180),
        ("Browser UI\napp.js", 455),
        ("Flask\napp.py", 760),
        ("Storage Service", 1060),
        ("Integrity Service", 1360),
        ("MongoDB Atlas", 1660),
        ("B2 Buckets", 1960),
    ]
    top = 190
    bottom = 3060
    for name, x in actors:
        round_box(d, (x - 105, top, x + 105, top + 75), "#ffffff", "#334155", width=2, radius=12)
        center_text(d, (x - 105, top, x + 105, top + 75), name, BODY)
        d.line([(x, top + 75), (x, bottom)], fill="#94a3b8", width=3)

    def section(y, text):
        d.rounded_rectangle((90, y, 2110, y + 46), radius=8, fill="#e0f2fe", outline="#0284c7", width=2)
        center_text(d, (90, y, 2110, y + 46), text, H2, fill="#075985")

    def msg(y, a, b, text, color="#334155"):
        x1 = dict(actors)[a]
        x2 = dict(actors)[b]
        arrow(d, (x1, y), (x2, y), fill=color, width=3)
        tw, _ = text_size(d, text, SMALL)
        d.rectangle(((x1 + x2 - tw) / 2 - 8, y - 35, (x1 + x2 + tw) / 2 + 8, y - 6), fill="#fbfcff")
        label(d, ((x1 + x2 - tw) / 2, y - 34), text, fill=color)

    y = 320
    section(y, "Upload")
    y += 95
    msg(y, "User", "Browser UI\napp.js", "select file + Upload")
    y += 90
    msg(y, "Browser UI\napp.js", "Flask\napp.py", "POST /api/upload")
    y += 90
    msg(y, "Flask\napp.py", "Flask\napp.py", "validate file, secure filename,\ncalculate SHA-256")
    y += 90
    msg(y, "Flask\napp.py", "MongoDB Atlas", "find matching normalized filename")
    y += 90
    msg(y, "Flask\napp.py", "Storage Service", "upload_to_both()")
    y += 90
    msg(y, "Storage Service", "B2 Buckets", "write same object to\nprimary + backup")
    y += 90
    msg(y, "Flask\napp.py", "MongoDB Atlas", "insert/update metadata\nstatus SAFE or TAMPERED")
    y += 90
    msg(y, "Flask\napp.py", "Browser UI\napp.js", "return JSON result")

    y += 85
    section(y, "Verify and Auto-Heal")
    y += 95
    msg(y, "Browser UI\napp.js", "Flask\napp.py", "GET /api/verify/{file_id}")
    y += 90
    msg(y, "Flask\napp.py", "MongoDB Atlas", "load file metadata")
    y += 90
    msg(y, "Flask\napp.py", "Integrity Service", "verify_and_heal(file_doc)")
    y += 90
    msg(y, "Integrity Service", "Storage Service", "download primary + backup")
    y += 90
    msg(y, "Storage Service", "B2 Buckets", "read objects")
    y += 90
    msg(y, "Integrity Service", "Integrity Service", "compare hashes with\ntrusted original_hash")
    y += 90
    msg(y, "Integrity Service", "Storage Service", "if primary bad and backup good:\noverwrite primary")
    y += 90
    msg(y, "Integrity Service", "MongoDB Atlas", "update SAFE / RECOVERED / TAMPERED\nand insert recovery log")
    y += 90
    msg(y, "Flask\napp.py", "Browser UI\napp.js", "return verification JSON")

    y += 85
    section(y, "Delete")
    y += 95
    msg(y, "Browser UI\napp.js", "Flask\napp.py", "POST /api/delete/{file_id}")
    y += 90
    msg(y, "Flask\napp.py", "Storage Service", "delete primary object")
    y += 90
    msg(y, "Storage Service", "B2 Buckets", "remove from primary bucket")
    y += 90
    msg(y, "Flask\napp.py", "MongoDB Atlas", "move metadata from files\nto deleted_files")

    y += 85
    section(y, "Recover Deleted File")
    y += 95
    msg(y, "Browser UI\napp.js", "Flask\napp.py", "POST /api/recover/{file_id}")
    y += 90
    msg(y, "Flask\napp.py", "Storage Service", "download backup object")
    y += 90
    msg(y, "Flask\napp.py", "Flask\napp.py", "validate backup SHA-256\nagainst original_hash")
    y += 90
    msg(y, "Flask\napp.py", "Storage Service", "restore primary from backup")
    y += 90
    msg(y, "Flask\napp.py", "MongoDB Atlas", "move metadata back to files\nstatus SAFE + log recovery")
    y += 90
    msg(y, "Flask\napp.py", "Browser UI\napp.js", "Recovery successful")

    img.save(ROOT / "file_lifecycle_sequence.png", "PNG")


if __name__ == "__main__":
    architecture_png()
    sequence_png()
    print("Created docs/system_architecture.png")
    print("Created docs/file_lifecycle_sequence.png")
