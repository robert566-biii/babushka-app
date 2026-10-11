"""
═══════════════════════════════════════════════════════════════
  БАБУШКИН ПОМОЩНИК — приложение-напоминалка о лекарствах
═══════════════════════════════════════════════════════════════

  Что делает:
    • Напоминает бабушке про таблетки в нужное время
    • Говорит голосом (Android TTS)
    • Если не выпила за 15 минут — шлёт push сыну через ntfy
    • Хранит все данные локально

  Один файл. Python + Kivy.

  Для сборки APK: buildozer android debug
═══════════════════════════════════════════════════════════════
"""

import json
import os
import threading
from datetime import datetime, timedelta

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex

import requests


# ═══════════════════════════════════════════════════════════════
#  ПРОВЕРКА ПЛАТФОРМЫ
# ═══════════════════════════════════════════════════════════════

try:
    from jnius import autoclass
    from android import mActivity
    from android.permissions import request_permissions, Permission
    IS_ANDROID = True
except ImportError:
    IS_ANDROID = False


# ═══════════════════════════════════════════════════════════════
#  НАСТРОЙКИ И ЦВЕТА
# ═══════════════════════════════════════════════════════════════

DATA_FILE = "babushka_data.json"

BG      = get_color_from_hex("#FFF8E7")   # тёплый бежевый
CARD    = get_color_from_hex("#FFFFFF")   # белый
GREEN   = get_color_from_hex("#27AE60")   # зелёный
ORANGE  = get_color_from_hex("#F39C12")   # оранжевый
RED     = get_color_from_hex("#E74C3C")   # красный
BLUE    = get_color_from_hex("#3498DB")   # синий
DARK    = get_color_from_hex("#2C3E50")   # тёмный текст
GRAY    = get_color_from_hex("#95A5A6")   # серый
YELLOW  = get_color_from_hex("#F1C40F")   # жёлтый


# ═══════════════════════════════════════════════════════════════
#  ГОЛОС — TTS на Android
# ═══════════════════════════════════════════════════════════════

_tts = None


def init_tts():
    """Инициализируем TTS один раз."""
    global _tts
    if not IS_ANDROID:
        return
    try:
        TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
        Locale = autoclass("java.util.Locale")
        _tts = TextToSpeech(mActivity, None)
        _tts.setLanguage(Locale("ru", "RU"))
        _tts.setSpeechRate(0.85)   # медленнее — бабушке понятнее
        _tts.setPitch(1.0)          # обычный тон
    except Exception as e:
        print(f"TTS init error: {e}")


def say(text):
    """Произносит текст. На Android — голосом. На компе — в консоль."""
    print(f"🔊 {text}")
    if IS_ANDROID and _tts:
        try:
            _tts.speak(text, 0, None, "id")
        except Exception as e:
            print(f"TTS speak error: {e}")


def say_async(text):
    """Говорит в отдельном потоке — чтобы не тормозить интерфейс."""
    threading.Thread(target=say, args=(text,), daemon=True).start()


# ═══════════════════════════════════════════════════════════════
#  ХРАНИЛИЩЕ
# ═══════════════════════════════════════════════════════════════

DEFAULT_DATA = {
    "name": "",
    "ntfy_topic": "",
    "medicines": [],
    "last_taken": {},
    "postponed": {},
    "setup_done": False,
}


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                for k, v in DEFAULT_DATA.items():
                    d.setdefault(k, v)
                return d
        except Exception:
            pass
    return dict(DEFAULT_DATA)


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"save error: {e}")


# ═══════════════════════════════════════════════════════════════
#  NTFLY — отправка push сыну
# ═══════════════════════════════════════════════════════════════

def notify_son(topic, med_name, time_str, mom_name):
    """Шлём push сыну через ntfy. Бесплатно, без регистрации."""
    if not topic:
        print("⚠️ Нет темы ntfy — уведомление не отправлено")
        return
    try:
        url = f"https://ntfy.sh/{topic}"
        text = (
            f"⚠️ {mom_name} не выпила {med_name} в {time_str}.\n"
            f"Позвони ей, пожалуйста."
        )
        r = requests.post(
            url,
            data=text.encode("utf-8"),
            headers={
                "Title": "Бабушка пропустила таблетки",
                "Priority": "high",
                "Tags": "warning,pill",
            },
            timeout=15,
        )
        print(f"✅ ntfy: {r.status_code}")
    except Exception as e:
        print(f"❌ ntfy ошибка: {e}")


def notify_son_async(topic, med_name, time_str, mom_name):
    threading.Thread(
        target=notify_son,
        args=(topic, med_name, time_str, mom_name),
        daemon=True,
    ).start()


# ═══════════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════

def make_button(text, color, height=dp(70), font=dp(24)):
    """Создать большую кнопку."""
    btn = Button(
        text=text,
        font_size=font,
        background_color=color,
        background_normal="",
        color=(1, 1, 1, 1),
        size_hint_y=None,
        height=height,
        bold=True,
    )
    return btn


def make_label(text, size=dp(22), color=DARK, height=dp(50), halign="center"):
    """Создать подпись."""
    lbl = Label(
        text=text,
        font_size=size,
        color=color,
        size_hint_y=None,
        height=height,
        halign=halign,
        valign="middle",
    )
    lbl.bind(size=lambda *a: setattr(lbl, "text_size", lbl.size))
    return lbl


def show_popup(title, text, size=(0.8, 0.4)):
    Popup(
        title=title,
        content=Label(text=text, font_size=dp(22), halign="center"),
        size_hint=size,
    ).open()


# ═══════════════════════════════════════════════════════════════
#  ЭКРАН 1: НАСТРОЙКА
# ═══════════════════════════════════════════════════════════════

class SetupScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = load_data()

        root = BoxLayout(orientation="vertical", padding=dp(25), spacing=dp(15))

        root.add_widget(make_label("💊", size=dp(60), height=dp(80)))
        root.add_widget(make_label("Бабушкин Помощник",
                                   size=dp(30), height=dp(50)))
        root.add_widget(make_label("Настроим один раз — работает всегда",
                                   size=dp(16), color=GRAY, height=dp(40)))

        root.add_widget(make_label("Как вас зовут?",
                                   size=dp(20), height=dp(35), halign="left"))

        self.name_input = TextInput(
            text=self.data.get("name", ""),
            font_size=dp(26),
            multiline=False,
            size_hint_y=None,
            height=dp(60),
            background_color=(1, 1, 1, 1),
            foreground_color=DARK,
            padding=[dp(15), dp(15)],
        )
        root.add_widget(self.name_input)

        root.add_widget(make_label("Код для сына (придумайте слово):",
                                   size=dp(18), height=dp(35), halign="left"))

        self.topic_input = TextInput(
            text=self.data.get("ntfy_topic", ""),
            font_size=dp(22),
            multiline=False,
            size_hint_y=None,
            height=dp(60),
            background_color=(1, 1, 1, 1),
            foreground_color=DARK,
            padding=[dp(15), dp(15)],
        )
        root.add_widget(self.topic_input)

        root.add_widget(make_label(
            "(Сын введёт этот код\nв приложении ntfy)",
            size=dp(15), color=GRAY, height=dp(60)
        ))

        save_btn = make_button("✅ СОХРАНИТЬ", GREEN, height=dp(80), font=dp(26))
        save_btn.bind(on_press=self.save)
        root.add_widget(save_btn)

        self.add_widget(root)

    def save(self, *args):
        name = self.name_input.text.strip()
        topic = self.topic_input.text.strip().replace(" ", "-")

        if not name:
            show_popup("Ошибка", "Напишите ваше имя")
            return
        if not topic:
            show_popup("Ошибка", "Придумайте код для сына")
            return

        self.data["name"] = name
        self.data["ntfy_topic"] = topic
        self.data["setup_done"] = True
        save_data(self.data)

        say_async(f"Здравствуйте, {name}! Я буду напоминать вам о лекарствах.")

        self.manager.current = "main"
        self.manager.get_screen("main").refresh()


# ═══════════════════════════════════════════════════════════════
#  ЭКРАН 2: ГЛАВНЫЙ
# ═══════════════════════════════════════════════════════════════

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data = load_data()

        root = BoxLayout(orientation="vertical", padding=dp(15), spacing=dp(10))

        # Заголовок
        self.title_label = make_label("💊 Мои лекарства",
                                      size=dp(26), height=dp(60))
        root.add_widget(self.title_label)

        self.subtitle = make_label("", size=dp(16), color=GRAY, height=dp(30))
        root.add_widget(self.subtitle)

        # Прокрутка
        scroll = ScrollView()
        self.meds_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
            padding=[0, dp(10)],
        )
        self.meds_box.bind(minimum_height=self.meds_box.setter("height"))
        scroll.add_widget(self.meds_box)
        root.add_widget(scroll)

        # Кнопки
        add_btn = make_button("➕ ДОБАВИТЬ ЛЕКАРСТВО", GREEN,
                              height=dp(75), font=dp(22))
        add_btn.bind(on_press=self.go_add)
        root.add_widget(add_btn)

        settings_btn = make_button("⚙️ НАСТРОЙКИ", BLUE,
                                   height=dp(55), font=dp(18))
        settings_btn.bind(on_press=self.go_setup)
        root.add_widget(settings_btn)

        self.add_widget(root)

    def refresh(self):
        self.data = load_data()
        name = self.data.get("name", "")
        self.title_label.text = f"💊 {name}, ваши лекарства:"
        self.subtitle.text = f"Код для сына: {self.data['ntfy_topic']}"

        self.meds_box.clear_widgets()

        if not self.data["medicines"]:
            self.meds_box.add_widget(make_label(
                "Пока ничего нет.\nНажмите «Добавить» 👇",
                size=dp(20), color=GRAY, height=dp(150)
            ))
            return

        for med in self.data["medicines"]:
            self.meds_box.add_widget(self.make_card(med))

    def make_card(self, med):
        card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(140),
            padding=dp(15),
            spacing=dp(8),
        )

        card.add_widget(make_label(
            f"💊 {med['name']}",
            size=dp(24), height=dp(40), halign="left"
        ))
        card.add_widget(make_label(
            f"{med['dose']}  •  ⏰ {med['time']}",
            size=dp(18), color=GRAY, height=dp(30), halign="left"
        ))

        del_btn = make_button("🗑 Удалить", RED, height=dp(45), font=dp(16))
        del_btn.bind(on_press=lambda *a, m=med: self.delete_med(m))
        card.add_widget(del_btn)

        return card

    def go_add(self, *args):
        self.manager.current = "add"

    def go_setup(self, *args):
        self.manager.current = "setup"

    def delete_med(self, med):
        self.data["medicines"] = [
            m for m in self.data["medicines"] if m != med
        ]
        save_data(self.data)
        self.refresh()
        say_async("Лекарство удалено.")


# ═══════════════════════════════════════════════════════════════
#  ЭКРАН 3: ДОБАВЛЕНИЕ
# ═══════════════════════════════════════════════════════════════

class AddScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))

        root.add_widget(make_label("➕ Новое лекарство",
                                   size=dp(26), height=dp(60)))

        # Название
        root.add_widget(make_label("Название:", size=dp(18), height=dp(30),
                                   halign="left"))
        self.name_input = TextInput(
            font_size=dp(24), multiline=False,
            size_hint_y=None, height=dp(60),
            background_color=(1, 1, 1, 1), foreground_color=DARK,
            padding=[dp(15), dp(15)],
        )
        root.add_widget(self.name_input)

        # Доза — быстрые кнопки
        root.add_widget(make_label("Сколько:", size=dp(18), height=dp(30),
                                   halign="left"))

        dose_row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        for txt in ["1 таблетка", "2 таблетки", "5 мл"]:
            b = make_button(txt, BLUE, height=dp(60), font=dp(16))
            b.bind(on_press=lambda *a, t=txt: self.set_dose(t))
            dose_row.add_widget(b)
        root.add_widget(dose_row)

        self.dose_input = TextInput(
            text="1 таблетка", font_size=dp(22), multiline=False,
            size_hint_y=None, height=dp(55),
            background_color=(1, 1, 1, 1), foreground_color=DARK,
            padding=[dp(15), dp(15)],
        )
        root.add_widget(self.dose_input)

        # Время — быстрые кнопки
        root.add_widget(make_label("Когда:", size=dp(18), height=dp(30),
                                   halign="left"))

        time_row1 = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        for txt, tm in [("🌅 Утро 8:00", "08:00"),
                        ("☀️ День 14:00", "14:00")]:
            b = make_button(txt, ORANGE, height=dp(60), font=dp(16))
            b.bind(on_press=lambda *a, t=tm: self.set_time(t))
            time_row1.add_widget(b)
        root.add_widget(time_row1)

        time_row2 = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        for txt, tm in [("🌙 Вечер 20:00", "20:00"),
                        ("🌃 Ночь 22:00", "22:00")]:
            b = make_button(txt, ORANGE, height=dp(60), font=dp(16))
            b.bind(on_press=lambda *a, t=tm: self.set_time(t))
            time_row2.add_widget(b)
        root.add_widget(time_row2)

        self.time_input = TextInput(
            text="08:00", font_size=dp(22), multiline=False,
            size_hint_y=None, height=dp(55),
            background_color=(1, 1, 1, 1), foreground_color=DARK,
            padding=[dp(15), dp(15)],
        )
        root.add_widget(self.time_input)

        # Кнопки
        save_btn = make_button("✅ ДОБАВИТЬ", GREEN, height=dp(75), font=dp(24))
        save_btn.bind(on_press=self.save)
        root.add_widget(save_btn)

        back_btn = make_button("◀ НАЗАД", GRAY, height=dp(55), font=dp(18))
        back_btn.bind(on_press=self.go_back)
        root.add_widget(back_btn)

        self.add_widget(root)

    def set_dose(self, txt):
        self.dose_input.text = txt

    def set_time(self, tm):
        self.time_input.text = tm

    def save(self, *args):
        name = self.name_input.text.strip()
        dose = self.dose_input.text.strip()
        time_str = self.time_input.text.strip()

        if not name:
            show_popup("Ошибка", "Напишите название лекарства")
            return

        try:
            h, m = time_str.split(":")
            h, m = int(h), int(m)
            assert 0 <= h < 24 and 0 <= m < 60
            time_str = f"{h:02d}:{m:02d}"
        except Exception:
            show_popup("Ошибка", "Время в формате ЧЧ:ММ\nНапример: 08:00")
            return

        data = load_data()
        data["medicines"].append({
            "name": name,
            "dose": dose or "1 таблетка",
            "time": time_str,
        })
        save_data(data)

        say_async(f"Добавлено: {name} в {time_str}")

        self.name_input.text = ""
        self.dose_input.text = "1 таблетка"
        self.time_input.text = "08:00"

        self.manager.current = "main"
        self.manager.get_screen("main").refresh()

    def go_back(self, *args):
        self.manager.current = "main"


# ═══════════════════════════════════════════════════════════════
#  ЭКРАН 4: НАПОМИНАНИЕ
# ═══════════════════════════════════════════════════════════════

class ReminderScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_med = None
        self.current_time = None

        root = BoxLayout(orientation="vertical", padding=dp(25), spacing=dp(20))

        root.add_widget(make_label("🔔", size=dp(70), height=dp(90)))
        root.add_widget(make_label("ПОРА ПИТЬ!", size=dp(34),
                                   color=RED, height=dp(60)))

        self.name_label = make_label("", size=dp(42), height=dp(90))
        root.add_widget(self.name_label)

        self.dose_label = make_label("", size=dp(28), height=dp(60))
        root.add_widget(self.dose_label)

        root.add_widget(make_label("", height=dp(20)))

        taken_btn = make_button("✅ ВЫПИЛА", GREEN,
                                height=dp(110), font=dp(30))
        taken_btn.bind(on_press=self.taken)
        root.add_widget(taken_btn)

        later_btn = make_button("⏰ ПОЗЖЕ (15 мин)", ORANGE,
                                height=dp(80), font=dp(22))
        later_btn.bind(on_press=self.later)
        root.add_widget(later_btn)

        repeat_btn = make_button("🔊 ПОВТОРИТЬ", BLUE,
                                 height=dp(60), font=dp(18))
        repeat_btn.bind(on_press=self.repeat)
        root.add_widget(repeat_btn)

        self.add_widget(root)

    def set_med(self, med, time_str):
        self.current_med = med
        self.current_time = time_str
        self.name_label.text = med["name"]
        self.dose_label.text = med["dose"]

        data = load_data()
        text = (
            f"{data['name']}, пора пить {med['name']}. "
            f"{med['dose']}. Пожалуйста, не забудьте."
        )
        say_async(text)

    def repeat(self, *args):
        if self.current_med:
            self.set_med(self.current_med, self.current_time)

    def taken(self, *args):
        data = load_data()
        key = f"{self.current_med['name']}_{self.current_time}"
        data["last_taken"][key] = datetime.now().isoformat()
        # Убираем из отложенных, если было
        data.get("postponed", {}).pop(key, None)
        save_data(data)

        say_async(f"Молодец, {data['name']}! Всё выпили. Спасибо вам.")

        show_popup("Молодец! 💚",
                   f"{data['name']}, вы молодец!\nВсё выпили.")

        Clock.schedule_once(lambda dt: self.go_back(), 2)

    def later(self, *args):
        data = load_data()
        key = f"{self.current_med['name']}_{self.current_time}"
        postpone_until = (datetime.now() + timedelta(minutes=15)).isoformat()
        data.setdefault("postponed", {})[key] = postpone_until
        save_data(data)

        say_async("Хорошо. Я напомню через пятнадцать минут.")
        self.go_back()

    def go_back(self, *args):
        self.manager.current = "main"


# ═══════════════════════════════════════════════════════════════
#  ПРОВЕРКА ВРЕМЕНИ — сердце приложения
# ═══════════════════════════════════════════════════════════════

def check_time(app):
    """Каждые 30 секунд проверяем: не пора ли напомнить?
    И не пропустила ли бабушка?"""
    data = load_data()
    if not data.get("setup_done"):
        return

    now = datetime.now()
    now_str = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")

    # 1. Проверяем отложенные напоминания
    postponed = data.get("postponed", {})
    for key in list(postponed.keys()):
        try:
            until = datetime.fromisoformat(postponed[key])
            if datetime.now() >= until:
                # Пора напомнить снова
                med_name, med_time = key.rsplit("_", 1)
                med = next(
                    (m for m in data["medicines"]
                     if m["name"] == med_name and m["time"] == med_time),
                    None
                )
                if med:
                    show_reminder(app, med, med_time)
                del postponed[key]
                save_data(data)
        except Exception:
            pass

    # 2. Проверяем обычные напоминания
    for med in data["medicines"]:
        if med["time"] != now_str:
            continue

        key = f"{med['name']}_{med['time']}"
        last = data["last_taken"].get(key, "")

        # Уже принимала сегодня?
        if last.startswith(today):
            continue

        # Отложено?
        if key in postponed:
            continue

        show_reminder(app, med, med["time"])
        break


def show_reminder(app, med, time_str):
    """Показываем экран напоминания."""
    screen = app.root.get_screen("reminder")
    screen.set_med(med, time_str)
    app.root.current = "reminder"

    # Через 15 минут проверяем — не пропустила ли
    Clock.schedule_once(
        lambda dt: check_ignored(app, med, time_str),
        15 * 60,   # 15 минут
    )


def check_ignored(app, med, time_str):
    """Если бабушка не нажала «Выпила» — шлём push сыну."""
    data = load_data()
    key = f"{med['name']}_{time_str}"
    today = datetime.now().strftime("%Y-%m-%d")
    last = data["last_taken"].get(key, "")

    if last.startswith(today):
        return  # выпила — всё ок

    # Не выпила — уведомляем сына
    print(f"⚠️ {data['name']} не выпила {med['name']} в {time_str}")
    notify_son_async(
        data["ntfy_topic"],
        med["name"],
        time_str,
        data["name"],
    )


# ═══════════════════════════════════════════════════════════════
#  ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ═══════════════════════════════════════════════════════════════

class BabushkaApp(App):
    def build(self):
        self.title = "Бабушкин Помощник"
        Window.clearcolor = BG

        # TTS
        init_tts()

        # Экран-менеджер
        sm = ScreenManager()
        sm.add_widget(SetupScreen(name="setup"))
        sm.add_widget(MainScreen(name="main"))
        sm.add_widget(AddScreen(name="add"))
        sm.add_widget(ReminderScreen(name="reminder"))

        # Стартовый экран
        data = load_data()
        if data.get("setup_done") and data.get("name"):
            sm.current = "main"
            sm.get_screen("main").refresh()
        else:
            sm.current = "setup"

        # Проверка каждые 30 секунд
        Clock.schedule_interval(lambda dt: check_time(self), 30)

        # Первое приветствие
        if data.get("name"):
            Clock.schedule_once(
                lambda dt: say_async(f"Здравствуйте, {data['name']}!"),
                2
            )

        return sm


# ═══════════════════════════════════════════════════════════════
#  ЗАПУСК
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if IS_ANDROID:
        try:
            request_permissions([Permission.INTERNET])
        except Exception:
            pass
    BabushkaApp().run()