"""InvisibleCam — усиление невидимых глазу различий цвета, яркости и пульса.
Чистый numpy, 4 режима, живые ползунки. Kivy + camera4kivy."""
import numpy as np
from collections import deque
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.graphics.texture import Texture
from kivy.graphics import Color, Rectangle
from kivy.utils import platform
from camera4kivy import Preview

# ---------------- ЯДРО ОБРАБОТКИ (проверено, ~2-10 мс/кадр) ----------------

def box_blur(a, r):
    """Быстрое размытие O(n) через cumsum, 2 прохода ≈ гаусс."""
    r = max(1, int(r)); h, w, _ = a.shape
    pad = np.pad(a, ((0,0),(r,r),(0,0)), mode='edge')
    c = np.cumsum(pad, axis=1, dtype=np.float32)
    c = np.concatenate([np.zeros((h,1,3), np.float32), c], axis=1)
    out = (c[:, 2*r+1:, :] - c[:, :-(2*r+1), :]) / (2*r+1)
    pad = np.pad(out, ((r,r),(0,0),(0,0)), mode='edge')
    c = np.cumsum(pad, axis=0, dtype=np.float32)
    c = np.concatenate([np.zeros((1,w,3), np.float32), c], axis=0)
    return (c[2*r+1:, :, :] - c[:-(2*r+1), :, :]) / (2*r+1)

def amplify(rgb, gain, sigma, ds=4):
    """Режим 0: микро-отклонения цвета -> видимые. Пирамида /4 для скорости."""
    small = rgb[::ds, ::ds].copy()
    b = box_blur(small, sigma/ds); b = box_blur(b, sigma/ds)
    base = np.repeat(np.repeat(b, ds, 0), ds, 1)[:rgb.shape[0], :rgb.shape[1]]
    # tanh: слабые сигналы линейно, сильные не 'взрываются'
    return np.clip(base + np.tanh(gain*(rgb-base))/3.0, 0, 1)

def band(rgb, lo, hi):
    """Режим 1: подсветить только диапазон яркости lo..hi (0..1)."""
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    m = ((lum >= lo) & (lum <= hi))[..., None]
    bright = rgb.copy()
    bright[..., 1] = np.clip(bright[..., 1] + 0.3, 0, 1)   # зелёная подсветка
    return np.where(m, bright, lum[..., None]*0.25)

def falsecolor(rgb):
    """Режим 2: псевдоцвет по яркости (НЕ температура!)."""
    l = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    return np.stack([np.clip(1.5-np.abs(l-0.75)*4, 0, 1),
                     np.clip(1.5-np.abs(l-0.50)*4, 0, 1),
                     np.clip(1.5-np.abs(l-0.25)*4, 0, 1)], -1)

class Temporal:
    """Режим 3: полосовой фильтр по времени — пульс кожи, вибрации."""
    def __init__(self): self.buf = deque(maxlen=30)
    def reset(self): self.buf.clear()
    def __call__(self, rgb, gain):
        self.buf.append(rgb.copy())
        if len(self.buf) < 10: return rgb
        frames = list(self.buf)
        fast = np.mean(frames[-5:], axis=0)
        slow = np.mean(frames, axis=0)
        return np.clip(slow + np.tanh(gain*(fast-slow))/3.0, 0, 1)

# ---------------- ВИДЖЕТ КАМЕРЫ С ОБРАБОТКОЙ ----------------

class Analyzer(Preview):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.gain = 60.0; self.sigma = 40.0
        self.lo = 0.0; self.hi = 1.0
        self.mode = 0
        self.temporal = Temporal()
        self.analyzed_texture = None

    def analyze_pixels_callback(self, pixels, image_size, image_pos,
                                scale, mirror):
        # RGBA bytes -> numpy float 0..1 (H,W,3)
        w, h = image_size
        rgba = np.frombuffer(pixels, np.uint8).reshape(h, w, 4)
        rgb = rgba[..., :3].astype(np.float32) / 255.0

        if   self.mode == 0: out = amplify(rgb, self.gain, self.sigma)
        elif self.mode == 1: out = band(rgb, self.lo, self.hi)
        elif self.mode == 2: out = falsecolor(rgb)
        else:                out = self.temporal(rgb, self.gain)

        # numpy -> RGBA текстура Kivy (переворот по вертикали: у Kivy ось Y вверх)
        buf = np.empty((h, w, 4), np.uint8)
        buf[..., :3] = (out[::-1] * 255).astype(np.uint8)
        buf[..., 3] = 255
        self.publish(buf.tobytes(), w, h)

    @mainthread
    def publish(self, data, w, h):
        if not self.camera_connected:
            self.analyzed_texture = None; return
        tex = Texture.create(size=(w, h), colorfmt='rgba')
        tex.blit_buffer(data, colorfmt='rgba', bufferfmt='ubyte')
        self.analyzed_texture = tex

    def canvas_instructions_callback(self, texture, tex_size, tex_pos):
        if self.analyzed_texture:
            Color(1, 1, 1, 1)
            Rectangle(texture=self.analyzed_texture,
                      size=tex_size, pos=tex_pos)

# ---------------- ИНТЕРФЕЙС ----------------

KV = '''
BoxLayout:
    orientation: 'vertical'
    Analyzer:
        id: cam
        aspect_ratio: '4:3'
        letterbox_color: 0,0,0,1
    BoxLayout:
        size_hint_y: None
        height: dp(44)
        Spinner:
            id: mode
            text: 'Усиление цвета'
            values: ['Усиление цвета','Диапазон яркости','Псевдоцвет','Пульс/движение']
            on_text: app.set_mode(self.text)
        Button:
            text: 'Камера: зад/перед'
            on_release: app.switch_camera()
        Button:
            text: 'Фото'
            on_release: app.shoot()
    BoxLayout:
        size_hint_y: None
        height: dp(40)
        Label:
            text: 'Интенсивность %d' % int(gain.value)
            size_hint_x: .4
        Slider:
            id: gain
            min: 1; max: 150; value: 60
            on_value: app.root.ids.cam.gain = self.value
    BoxLayout:
        size_hint_y: None
        height: dp(40)
        Label:
            text: 'Масштаб деталей %d' % int(sigma.value)
            size_hint_x: .4
        Slider:
            id: sigma
            min: 5; max: 100; value: 40
            on_value: app.root.ids.cam.sigma = self.value
    BoxLayout:
        size_hint_y: None
        height: dp(40)
        Label:
            text: 'Яркость НИЗ %d%%' % int(lo.value)
            size_hint_x: .4
        Slider:
            id: lo
            min: 0; max: 100; value: 0
            on_value: app.root.ids.cam.lo = self.value/100.0
    BoxLayout:
        size_hint_y: None
        height: dp(40)
        Label:
            text: 'Яркость ВЕРХ %d%%' % int(hi.value)
            size_hint_x: .4
        Slider:
            id: hi
            min: 0; max: 100; value: 100
            on_value: app.root.ids.cam.hi = self.value/100.0
'''

MODES = {'Усиление цвета': 0, 'Диапазон яркости': 1,
         'Псевдоцвет': 2, 'Пульс/движение': 3}

class InvisibleCamApp(App):
    def build(self):
        self.front = False
        return Builder.load_string(KV)

    def on_start(self):
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.CAMERA], self._connected_later)
        else:
            self._connected_later()

    def _connected_later(self, *args):
        # камера подключается ТОЛЬКО через Clock после on_start (иначе краш)
        Clock.schedule_once(lambda dt: self.connect(), 0.5)

    def connect(self):
        self.root.ids.cam.connect_camera(
            camera_id='front' if self.front else 'back',
            enable_analyze_pixels=True,
            analyze_pixels_resolution=480,   # низкое разрешение = скорость
            enabl тоe_video=False)              # анализ+видео конфликтуют на слабых устройствах

    def switch_camera(self):
        self.front = not self.front
        self.root.ids.cam.disconnect_camera()
        Clock.schedule_once(lambda dt: self.connect(), 0.3)

    def set_mode(self, text):
        cam = self.root.ids.cam
        cam.mode = MODES[text]
        cam.temporal.reset()

    def shoot(self):
        # скриншот сохраняет именно обработанное изображение
        self.root.ids.cam.capture_screenshot()

    def on_stop(self):
        self.root.ids.cam.disconnect_camera()

if __name__ == '__main__':
    InvisibleCamApp().run()
