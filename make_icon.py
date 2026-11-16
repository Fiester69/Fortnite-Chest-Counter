"""Рисует иконку приложения (золотой сундук на тёмном фоне) -> app.ico"""
from PIL import Image, ImageDraw


def draw(size):
    S = size * 4
    u = S / 100.0
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=22 * u, fill=(20, 22, 26, 255),
                        outline=(43, 47, 55, 255), width=max(1, int(2 * u)))
    wood, lid, gold, edge = (154, 101, 50), (180, 122, 60), (245, 197, 66), (74, 46, 20)
    d.ellipse((20 * u, 76 * u, 80 * u, 83 * u), fill=(10, 11, 14, 255))
    d.rounded_rectangle((22 * u, 50 * u, 78 * u, 78 * u), radius=4 * u, fill=wood, outline=edge, width=int(1.5 * u))
    d.rounded_rectangle((22 * u, 26 * u, 78 * u, 54 * u), radius=15 * u, fill=lid, outline=edge, width=int(1.5 * u))
    d.rectangle((23 * u, 44 * u, 77 * u, 54 * u), fill=lid)
    for x in (30, 64):
        d.rectangle((x * u, 30 * u, (x + 6) * u, 77 * u), fill=(217, 169, 58, 255))
    d.rectangle((45 * u, 46 * u, 55 * u, 62 * u), fill=gold, outline=(140, 106, 28), width=int(1 * u))
    d.ellipse((48 * u, 51 * u, 52 * u, 55 * u), fill=edge)
    return im.resize((size, size), Image.LANCZOS)


sizes = [16, 24, 32, 48, 64, 128, 256]
big = draw(256)
big.save("app.ico", sizes=[(s, s) for s in sizes])
big.save("app_preview.png")
print("app.ico готов")
