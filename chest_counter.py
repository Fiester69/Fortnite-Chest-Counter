# -*- coding: utf-8 -*-
"""
Fortnite Chest Counter - мини-оверлей со счётчиком открытых сундуков.

Как работает: программа смотрит на кусок экрана, где появляется подсказка
"Открыть сундук" (распознаёт текст через Tesseract OCR) и ловит нажатие клавиши
взаимодействия (E). Подсказка была -> ты нажал E -> подсказка пропала = +1.
В игру ничего не внедряется, читается только картинка экрана.

Горячие клавиши (меняются в config.json):
  F7  +1 вручную        F8  -1            F9  сбросить сессию
  F5 / F6  цель -5 / +5 F10 отладка       F11 спрятать/показать
  F12 выход
Оверлей таскается мышью, правый клик по нему = выход.
"""
import ctypes
import difflib
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

try:
    import keyboard
    import mss
    import pytesseract
    from PIL import Image, ImageOps
except ImportError as e:
    text = "Не хватает библиотеки: %s\nЗапусти install.bat или: pip install -r requirements.txt" % e
    try:
        ctypes.windll.user32.MessageBoxW(0, text, "Chest Counter", 0x10)
    except Exception:
        sys.stderr.write(text + "\n")
    sys.exit(1)

# чёткая картинка на экранах с масштабом 125%/150% и т.д.
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)   # внутри EXE: временная папка распаковки (только чтение)

# настройки, статистика и лог живут в профиле пользователя, а не во временной папке EXE
DATA_DIR = os.path.join(os.environ.get("APPDATA") or APP_DIR, "ChestCounter")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    DATA_DIR = APP_DIR
BASE_DIR = DATA_DIR
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
COUNT_FILE = os.path.join(DATA_DIR, "chest_count.json")
LOG_FILE = os.path.join(DATA_DIR, "chest_counter.log")

try:   # лог не раздувается
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200000:
        os.remove(LOG_FILE)
except OSError:
    pass

# перенос статистики из старой версии (рядом со скриптом), если есть
try:
    _old = os.path.join(APP_DIR, "chest_count.json")
    if DATA_DIR != APP_DIR and not os.path.exists(COUNT_FILE) and os.path.exists(_old):
        shutil.copyfile(_old, COUNT_FILE)
except OSError:
    pass


def log(*args):
    msg = " ".join(str(a) for a in args)
    try:
        if sys.stdout:
            sys.stdout.write(msg + "\n")
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass

DEFAULT_CONFIG = {
    "goal": 20,                 # цель на сессию
    "milestone": 100,           # шаг шкалы "ВСЕГО"
    "scale": 1.0,               # размер оверлея (1.0 = обычный, 1.5 = крупнее)
    "opacity": 0.93,
    "click_through": False,     # true = мышь проходит сквозь оверлей (двигать нельзя)
    "reset_session_on_start": True,
    "monitor": 1,
    "region": [0.30, 0.50, 0.75, 0.90],   # где ищем подсказку (доли экрана: лево, верх, право, низ)
    "interact_key": "e",
    "keywords": ["сундук", "chest"],
    "cooldown_sec": 1.5,
    "scan_interval": 0.12,
    "threshold": 200,           # яркость "белого" текста подсказки
    "min_bright_ratio": 0.0004, # меньше этой доли светлых пикселей = текста нет, OCR пропускаем
    "ocr_lang": "rus+eng",
    "overlay_x": 20,
    "overlay_y": 20,
    "tesseract_path": "",       # пусто = найти автоматически
    "hotkeys": {
        "add": "f7", "sub": "f8", "reset_session": "f9", "debug": "f10",
        "toggle": "f11", "quit": "f12", "goal_down": "f5", "goal_up": "f6",
    },
}

# ---------------------------------------------------------------- конфиг / счёт


def save_config(c):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log("Не смог сохранить config.json:", e)


def load_config():
    c = json.loads(json.dumps(DEFAULT_CONFIG))
    changed = True
    if os.path.exists(CONFIG_FILE):
        changed = False
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                user = json.load(f)
            for k, v in user.items():
                if k == "hotkeys" and isinstance(v, dict):
                    c["hotkeys"].update(v)
                else:
                    c[k] = v
            changed = any(k not in user for k in DEFAULT_CONFIG)
            if isinstance(user.get("hotkeys"), dict):
                changed = changed or any(k not in user["hotkeys"] for k in DEFAULT_CONFIG["hotkeys"])
        except Exception as e:
            log("config.json не прочитался, беру настройки по умолчанию:", e)
    if changed:
        save_config(c)
    c["goal"] = max(1, int(c["goal"]))
    c["milestone"] = max(1, int(c["milestone"]))
    c["scale"] = min(3.0, max(0.6, float(c["scale"])))
    return c


cfg = load_config()


def load_counts():
    try:
        with open(COUNT_FILE, encoding="utf-8") as f:
            d = json.load(f)
        total = int(d.get("total", d.get("count", 0)))   # "count" - формат старой версии
        session = int(d.get("session", 0))
        return session, total
    except Exception:
        return 0, 0


_session, _total = load_counts()
if cfg["reset_session_on_start"]:
    _session = 0

state = {
    "session": _session,
    "total": _total,
    "pulse": 0.0,        # время последнего +1 (для анимации)
    "seen": False,       # сейчас на экране подсказка сундука
    "ocr_ok": True,
    "running": True,
}
lock = threading.Lock()


def _save_counts():
    try:
        with open(COUNT_FILE, "w", encoding="utf-8") as f:
            json.dump({"session": state["session"], "total": state["total"]}, f)
    except Exception:
        pass


def change(delta):
    with lock:
        if delta < 0 and state["session"] == 0:
            return
        state["session"] = max(0, state["session"] + delta)
        state["total"] = max(0, state["total"] + delta)
        if delta > 0:
            state["pulse"] = time.time()
        _save_counts()


def reset_session():
    with lock:
        state["session"] = 0
        _save_counts()


def change_goal(delta):
    cfg["goal"] = max(1, cfg["goal"] + delta)
    save_config(cfg)


# ---------------------------------------------------------------- OCR / детектор

OCR_LANG = "eng"
debug_flag = threading.Event()
key_state = {"last": 0.0}


def setup_ocr():
    """Ищет Tesseract. Возвращает (ok, сообщение)."""
    global OCR_LANG
    os.environ["OMP_THREAD_LIMIT"] = "1"   # Tesseract в один поток: меньше нагрузка на CPU, нет просадок FPS
    bundled = os.path.join(RES_DIR, "tess", "tesseract.exe")   # движок, вшитый в EXE
    if os.path.exists(bundled):
        os.environ["TESSDATA_PREFIX"] = os.path.join(RES_DIR, "tess", "tessdata")
    candidates = [
        bundled,
        cfg["tesseract_path"],
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            break
    try:
        langs = pytesseract.get_languages(config="")
    except Exception as e:
        log("[OCR FAIL] Tesseract не запустился:", e)
        if FROZEN:
            return False, ("Не запустился встроенный движок распознавания (Tesseract).\n"
                           "Чаще всего его блокирует антивирус: добавь папку %TEMP% и ChestCounter.exe в исключения.\n"
                           "Пока счётчик работает вручную (F7/F8). Подробности: " + LOG_FILE)
        return False, ("Не найден Tesseract OCR, автоподсчёт выключен.\n"
                       "Счётчик работает вручную (F7/F8). Установи Tesseract и перезапусти программу.")
    wanted = [l for l in cfg["ocr_lang"].split("+") if l in langs]
    if not wanted:
        wanted = ["eng"] if "eng" in langs else langs[:1]
    OCR_LANG = "+".join(wanted)
    msg = ""
    if "rus" not in wanted and "rus" in cfg["ocr_lang"]:
        msg = "Русский язык для Tesseract не установлен, ищу только английский текст (Chest)."
    return True, msg


def grab_region(sct):
    mons = sct.monitors
    mon = mons[cfg["monitor"]] if 0 < cfg["monitor"] < len(mons) else mons[1]
    l, t, r, b = cfg["region"]
    box = {
        "left": mon["left"] + int(mon["width"] * l),
        "top": mon["top"] + int(mon["height"] * t),
        "width": max(10, int(mon["width"] * (r - l))),
        "height": max(10, int(mon["height"] * (b - t))),
    }
    shot = sct.grab(box)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def bright_ratio(img):
    hist = img.convert("L").histogram()
    return sum(hist[cfg["threshold"]:]) / float(img.width * img.height)


def read_text(img):
    g = ImageOps.grayscale(img)
    if g.width < 1400:
        g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
    th = cfg["threshold"]
    g = g.point(lambda p: 0 if p > th else 255)  # белый текст -> чёрный на белом
    try:
        return pytesseract.image_to_string(g, lang=OCR_LANG, config="--psm 11").lower()
    except Exception as e:
        return "[ocr error: %s]" % e


_LAT2CYR = str.maketrans("aceopxykhbmt", "асеорхукнвмт")


def has_chest_prompt(text):
    """Ищет слово 'сундук'/'chest' в тексте OCR, прощая мелкие ошибки распознавания."""
    for word in re.findall(r"\w+", text):
        if len(word) < 4:
            continue
        forms = (word, word.translate(_LAT2CYR))   # вторая форма: латинские буквы-двойники -> кириллица
        for k in cfg["keywords"]:
            for w in forms:
                if k in w or difflib.SequenceMatcher(None, w, k).ratio() > 0.8:
                    return True
    return False


def detector():
    visible = False
    vis_since = 0.0
    miss = 0
    last_count = 0.0
    try:
        sct = mss.mss()
    except Exception as e:
        log("Не смог начать захват экрана:", e)
        return
    while state["running"]:
        t0 = time.time()
        try:
            img = grab_region(sct)
            ratio = bright_ratio(img)
            dbg = debug_flag.is_set()
            if dbg or ratio >= cfg["min_bright_ratio"]:
                text = read_text(img)
            else:
                text = ""
            seen = has_chest_prompt(text)
            if dbg:
                debug_flag.clear()
                img.save(os.path.join(BASE_DIR, "debug_region.png"))
                log("--- ОТЛАДКА: светлых пикселей %.4f%%, OCR видит: %r, сундук: %s"
                      % (ratio * 100, text.strip(), seen))
        except Exception as e:
            log("Ошибка детектора:", e)
            time.sleep(1)
            continue

        now = time.time()
        state["seen"] = seen
        if seen:
            miss = 0
            if not visible:
                visible = True
                vis_since = now
        else:
            miss += 1
            if visible and miss >= 2:     # 2 пустых кадра подряд - это не мерцание
                visible = False
                kt = key_state["last"]
                if kt >= vis_since - 0.25 and now - kt < 2.0 and now - last_count > cfg["cooldown_sec"]:
                    change(+1)
                    last_count = now
        time.sleep(max(0.0, cfg["scan_interval"] - (time.time() - t0)))


# ---------------------------------------------------------------- оформление

BG = "#14161a"
BORDER = "#2b2f37"
TRACK = "#2a2e36"
TEXT = "#eceef2"
MUTED = "#8a909c"
GOLD = "#f5c542"
GOLD_HI = "#ffd966"
LILAC = "#8fa0ff"
GREEN = "#4ade80"
RED = "#f87171"
IDLE_DOT = "#3a3f49"
KEY = "#010101"   # цвет-"дырка" для скруглённых углов на Windows


def blend(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def lid_amount(t):
    """Насколько открыта крышка через t секунд после +1 (0..1)."""
    if t < 0:
        return 0.0
    if t < 0.18:
        return ease(t / 0.18)
    if t < 0.75:
        return 1.0
    if t < 1.05:
        return 1.0 - ease((t - 0.75) / 0.3)
    return 0.0


class Overlay:
    W = 190
    H = 190

    def __init__(self):
        self.win = sys.platform == "win32"
        r = self.root = tk.Tk()
        r.title("Chest Counter")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        dpi = 1.0
        try:
            dpi = max(1.0, r.winfo_fpixels("1i") / 96.0) if self.win else 1.0
        except Exception:
            pass
        self.S = cfg["scale"] * dpi
        S = self.S
        bgc = BG
        if self.win:
            try:
                r.attributes("-transparentcolor", KEY)
                bgc = KEY
            except tk.TclError:
                pass
        try:
            r.attributes("-alpha", cfg["opacity"])
        except tk.TclError:
            pass
        r.configure(bg=bgc)
        self.w, self.h = int(self.W * S), int(self.H * S)
        r.geometry("%dx%d+%d+%d" % (self.w, self.h, cfg["overlay_x"], cfg["overlay_y"]))
        self.c = tk.Canvas(r, width=self.w, height=self.h, bg=bgc, highlightthickness=0, bd=0)
        self.c.pack()

        fam = "Segoe UI" if self.win else "DejaVu Sans"
        # отрицательный размер = пиксели, не зависит от масштаба Windows
        self.f_big = tkfont.Font(family=fam, size=-int(round(26 * S)), weight="bold")
        self.f_mid = tkfont.Font(family=fam, size=-int(round(13 * S)))
        self.f_plus = tkfont.Font(family=fam, size=-int(round(13 * S)), weight="bold")
        self.f_lbl = tkfont.Font(family=fam, size=-int(round(10 * S)), weight="bold")

        self.cmds = queue.Queue()
        self.b1 = 0.0
        self.b2 = 0.0
        self.last_sig = None
        self.hidden = False
        self.drag = (0, 0)
        self._win_style()

        for w in (r, self.c):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.bind("<ButtonRelease-1>", self._end_drag)
            w.bind("<Button-3>", lambda e: self.cmds.put("quit"))

    # --- окно
    def _win_style(self):
        """Не забирать фокус у игры и не показываться на панели задач."""
        if not self.win:
            return
        try:
            user32 = ctypes.windll.user32
            self.root.update_idletasks()
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            style = user32.GetWindowLongW(hwnd, -20)
            style |= 0x08000000 | 0x00000080          # NOACTIVATE | TOOLWINDOW
            if cfg["click_through"]:
                style |= 0x00080000 | 0x00000020      # LAYERED | TRANSPARENT
            user32.SetWindowLongW(hwnd, -20, style)
        except Exception as e:
            log("Не удалось настроить окно:", e)

    def _start_drag(self, e):
        self.drag = (e.x, e.y)

    def _do_drag(self, e):
        x = self.root.winfo_x() + e.x - self.drag[0]
        y = self.root.winfo_y() + e.y - self.drag[1]
        self.root.geometry("+%d+%d" % (x, y))

    def _end_drag(self, e):
        cfg["overlay_x"], cfg["overlay_y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(cfg)

    # --- рисование
    def rrect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.c.create_polygon(pts, smooth=True, **kw)

    def bar(self, x, y, length, h, frac, color):
        self.rrect(x, y, x + length, y + h, h / 2, fill=TRACK, outline=TRACK)
        if frac > 0.004:
            w = max(h, length * min(1.0, frac))
            self.rrect(x, y, x + w, y + h, h / 2, fill=color, outline=color)

    def chest(self, cx, cy, o):
        c, u = self.c, self.S
        # тень
        c.create_oval(cx - 27 * u, cy + 26 * u, cx + 27 * u, cy + 32 * u, fill="#0e1013", outline="")
        # корпус
        self.rrect(cx - 28 * u, cy, cx + 28 * u, cy + 27 * u, 3 * u, fill="#9a6532", outline="#4a2e14")
        for bx in (-21, 15):
            c.create_rectangle(cx + bx * u, cy + 1 * u, cx + (bx + 6) * u, cy + 26 * u,
                               fill="#d9a93a", outline="#8c6a1c")
        # свет изнутри, когда крышка поднята
        dy = -14 * u * o
        if o > 0.02:
            glow = blend("#3a2410", "#ffe08a", o)
            c.create_polygon(cx - 26 * u, cy, cx + 26 * u, cy, cx + 23 * u, cy + dy, cx - 23 * u, cy + dy,
                             fill=glow, outline="")
        # крышка
        k = 1 - 0.08 * o
        base = [(-28, 0), (-28, -10), (-20, -20), (0, -24), (20, -20), (28, -10), (28, 0)]
        pts = []
        for px, py in base:
            pts += [cx + px * k * u, cy + py * u + dy]
        c.create_polygon(pts, smooth=True, fill="#b47a3c", outline="#4a2e14")
        for bx in (-21, 15):
            c.create_rectangle(cx + bx * k * u, cy - 19 * u + dy, cx + (bx + 6) * k * u, cy - 1 * u + dy,
                               fill="#d9a93a", outline="#8c6a1c")
        # замок
        top = cy - 5 * u * (1 - o)
        c.create_rectangle(cx - 5 * u, top, cx + 5 * u, cy + 9 * u, fill=GOLD, outline="#8c6a1c")
        c.create_oval(cx - 1.6 * u, cy + 1.5 * u, cx + 1.6 * u, cy + 4.5 * u, fill="#4a2e14", outline="")
        # искра
        if o > 0.3:
            s, sx, sy = 5 * u * o, cx, cy - 10 * u + dy
            c.create_polygon(sx, sy - s, sx + s * 0.45, sy, sx, sy + s, sx - s * 0.45, sy,
                             fill=GOLD_HI, outline="")

    def draw(self, sess, total, goal, b1, b2, seen, ocr_ok, o, since_pulse):
        c, u = self.c, self.S
        W, H = self.w, self.h
        c.delete("all")
        self.rrect(1, 1, W - 1, H - 1, 16 * u, fill=BG, outline=BORDER)

        # индикатор: зелёный = вижу подсказку сундука, красный = OCR не работает
        dot = RED if not ocr_ok else (GREEN if seen else IDLE_DOT)
        c.create_oval(W - 17 * u, 11 * u, W - 11 * u, 17 * u, fill=dot, outline="")

        cx = W / 2
        self.chest(cx, 54 * u, o)

        # всплывающий "+1"
        if 0.1 < since_pulse < 1.1:
            f = (since_pulse - 0.1) / 1.0
            c.create_text(cx + 40 * u, 34 * u - f * 18 * u, text="+1", font=self.f_plus,
                          fill=blend(GOLD_HI, BG, f * f))

        # большое число "7 / 20"
        done = sess >= goal
        cs, gs = str(sess), "/ %d" % goal
        w1, w2, gap = self.f_big.measure(cs), self.f_mid.measure(gs), 5 * u
        x0 = W / 2 - (w1 + gap + w2) / 2
        c.create_text(x0, 108 * u, text=cs, anchor="w", font=self.f_big, fill=GOLD if done else TEXT)
        c.create_text(x0 + w1 + gap, 110 * u, text=gs, anchor="w", font=self.f_mid, fill=MUTED)

        # шкалы
        x1, L, bh = 16 * u, W - 32 * u, 6 * u
        pct = "%d%%" % int(min(1.0, float(sess) / goal) * 100)
        if sess > goal:
            pct += "  +%d" % (sess - goal)
        c.create_text(x1, 134 * u, text="ЦЕЛЬ", anchor="w", font=self.f_lbl, fill=MUTED)
        c.create_text(W - x1, 134 * u, text=pct, anchor="e", font=self.f_lbl, fill=GOLD if done else MUTED)
        self.bar(x1, 143 * u, L, bh, b1, GOLD_HI if done else GOLD)

        ms = cfg["milestone"]
        nxt = (total // ms + 1) * ms
        c.create_text(x1, 162 * u, text="ВСЕГО", anchor="w", font=self.f_lbl, fill=MUTED)
        c.create_text(W - x1, 162 * u, text="%d / %d" % (total, nxt), anchor="e", font=self.f_lbl, fill=MUTED)
        self.bar(x1, 171 * u, L, bh, b2, LILAC)

    # --- главный цикл
    def tick(self):
        while True:
            try:
                cmd = self.cmds.get_nowait()
            except queue.Empty:
                break
            if cmd == "quit":
                state["running"] = False
                self.root.destroy()
                return
            if cmd == "toggle":
                self.hidden = not self.hidden
                self.root.withdraw() if self.hidden else self.root.deiconify()

        now = time.time()
        with lock:
            sess, total, pulse = state["session"], state["total"], state["pulse"]
        seen, ocr_ok = state["seen"], state["ocr_ok"]
        goal, ms = cfg["goal"], cfg["milestone"]

        t1 = min(1.0, float(sess) / goal)
        t2 = (total % ms) / float(ms)
        moving = False
        for name, target in (("b1", t1), ("b2", t2)):
            cur = getattr(self, name)
            if abs(target - cur) > 0.002:
                cur += (target - cur) * 0.25
                moving = True
            else:
                cur = target
            setattr(self, name, cur)

        since = now - pulse if pulse else 99.0
        o = lid_amount(since)
        animating = since < 1.2

        sig = (round(self.b1, 3), round(self.b2, 3), sess, total, goal, ms, seen, ocr_ok,
               round(o, 2), int(since * 30) if animating else -1)
        if sig != self.last_sig and not self.hidden:
            self.draw(sess, total, goal, self.b1, self.b2, seen, ocr_ok, o, since)
            self.last_sig = sig

        if self.win and int(now) % 3 == 0:
            self.root.attributes("-topmost", True)   # не даём игре перекрыть оверлей
        self.root.after(33 if (animating or moving) else 120, self.tick)

    def run(self):
        self.tick()
        self.root.mainloop()


# ---------------------------------------------------------------- запуск


def main():
    ocr_ok, msg = setup_ocr()
    state["ocr_ok"] = ocr_ok
    if msg:
        log(msg)
        tmp = tk.Tk()
        tmp.withdraw()
        messagebox.showwarning("Chest Counter", msg)
        tmp.destroy()

    ov = Overlay()

    hk = cfg["hotkeys"]
    binds = [
        ("add", lambda: change(+1)),
        ("sub", lambda: change(-1)),
        ("reset_session", reset_session),
        ("goal_down", lambda: change_goal(-5)),
        ("goal_up", lambda: change_goal(+5)),
        ("debug", debug_flag.set),
        ("toggle", lambda: ov.cmds.put("toggle")),
        ("quit", lambda: ov.cmds.put("quit")),
    ]
    for name, fn in binds:
        try:
            keyboard.add_hotkey(hk[name], fn)
        except Exception as e:
            log("Не получилось повесить клавишу %r (%s): %s" % (hk[name], name, e))

    # ловим именно нажатие (а не опрашиваем), чтобы короткий тап E не терялся
    try:
        keyboard.on_press_key(cfg["interact_key"], lambda e: key_state.__setitem__("last", time.time()))
    except Exception as e:
        log("Не получилось слушать клавишу %r: %s" % (cfg["interact_key"], e))

    if ocr_ok:
        threading.Thread(target=detector, daemon=True).start()

    log("[STARTED] Chest Counter запущен. F7 +1 | F8 -1 | F9 сброс сессии | F5/F6 цель | F10 отладка | F11 спрятать | F12 выход")
    try:
        ov.run()
    finally:
        state["running"] = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass


_mutex = None


def already_running():
    """Второй запуск не нужен: два оверлея считали бы сундуки дважды."""
    global _mutex
    if sys.platform != "win32":
        return False
    try:
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ChestCounterOverlay")
        return ctypes.windll.kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def lower_priority():
    """Низкий приоритет: ни программа, ни Tesseract не отнимают процессор у игры."""
    if sys.platform != "win32":
        return
    try:
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)   # BELOW_NORMAL
    except Exception:
        pass


if __name__ == "__main__":
    if already_running():
        sys.exit(0)
    lower_priority()
    try:
        main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        log(err)
        try:
            tmp = tk.Tk()
            tmp.withdraw()
            messagebox.showerror("Chest Counter",
                                 "Программа остановилась из-за ошибки:\n\n%s\nЛог: %s" % (err[-700:], LOG_FILE))
            tmp.destroy()
        except Exception:
            pass
        sys.exit(1)
