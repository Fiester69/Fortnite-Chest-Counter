"""CI-проверка: встроенный Tesseract (папка tess) читает русскую подсказку 'Открыть сундук'."""
import os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

root = os.path.dirname(os.path.abspath(__file__))
tess = os.path.join(root, "tess")
font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 42)
img = Image.new("L", (520, 110), 255)
ImageDraw.Draw(img).text((20, 25), "Открыть сундук", font=font, fill=0)
img.save("ocr_check.png")

env = dict(os.environ, TESSDATA_PREFIX=os.path.join(tess, "tessdata"))
out = subprocess.run([os.path.join(tess, "tesseract.exe"), "ocr_check.png", "stdout", "-l", "rus+eng", "--psm", "11"],
                     capture_output=True, text=True, encoding="utf-8", env=env)
text = out.stdout.lower()
print("OCR вывод:", repr(text), "| stderr:", out.stderr.strip())
if "сундук" not in text:
    sys.exit("OCR не распознал слово 'сундук'")
print("OCR OK")
