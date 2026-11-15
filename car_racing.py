import math
import os
import random
from array import array

import pygame

# =====================================================================
#  SETUP
# =====================================================================
pygame.mixer.pre_init(22050, -16, 1, 512)
pygame.init()

AUDIO = False
RATE, CH = 22050, 1
try:
    _mi = pygame.mixer.get_init()
    if _mi and abs(_mi[1]) == 16:
        AUDIO = True
        RATE, _, CH = _mi
        pygame.mixer.set_num_channels(12)
        pygame.mixer.set_reserved(2)  # channel 0 = music, channel 1 = engine
except Exception:
    AUDIO = False

info = pygame.display.Info()
W = info.current_w if info.current_w > 0 else 400
H = info.current_h if info.current_h > 0 else 700
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Car Racing")
clock = pygame.time.Clock()

# ---------- colours ----------
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
ROAD_COL = (48, 48, 52)
GRASS = (40, 150, 60)
GRASS_DARK = (34, 132, 52)
RED = (225, 50, 50)
BLUE = (40, 140, 255)
YELLOW = (255, 215, 0)
ORANGE = (255, 140, 0)
GREEN = (0, 200, 120)
PINK = (255, 105, 180)
ENEMY_COLORS = [RED, YELLOW, GREEN, PINK, (160, 90, 255), (235, 235, 235)]

# ---------- layout (scales to any screen) ----------
U = min(W, H * 0.56) / 400.0            # UI unit
ROAD_W = min(int(W * 0.78), int(H * 0.7))
ROAD_X = (W - ROAD_W) // 2
CTRL_H = int(H * 0.16)
PLAY_H = H - CTRL_H
LANES = 3
LANE_W = ROAD_W / LANES
CAR_W = int(LANE_W * 0.48)
CAR_H = int(CAR_W * 1.9)
COIN_R = max(8, int(CAR_W * 0.28))
PY = PLAY_H - CAR_H - int(PLAY_H * 0.06)
PAD = max(8, int(12 * U))
BASE_SPEED = PLAY_H * 0.62
LANE_SPEED = [0.85, 1.0, 1.15]
TREE_R = max(5, min(ROAD_X * 0.36, 30 * U))

LEFT_RECT = pygame.Rect(0, PLAY_H, W // 2, CTRL_H)
RIGHT_RECT = pygame.Rect(W // 2, PLAY_H, W - W // 2, CTRL_H)

def _font(size):
    return pygame.font.SysFont("Arial", max(12, int(size)), bold=True)

F_S, F_M, F_L, F_XL = _font(16 * U), _font(22 * U), _font(38 * U), _font(54 * U)
HUD_H = F_S.get_height() + PAD // 2
MUTE_SZ = max(32, int(40 * U))
MUTE_RECT = pygame.Rect(W - PAD - MUTE_SZ, PAD + HUD_H + PAD // 2, MUTE_SZ, MUTE_SZ)
START_RECT = pygame.Rect(0, 0, int(230 * U), int(66 * U))
START_RECT.center = (W // 2, int(H * 0.5))
RESTART_RECT = pygame.Rect(0, 0, int(230 * U), int(66 * U))
RESTART_RECT.center = (W // 2, int(H * 0.58))

world = pygame.Surface((W, PLAY_H))
DIM = pygame.Surface((W, PLAY_H))
DIM.fill((0, 0, 0))
FLASH = pygame.Surface((W, PLAY_H))
FLASH.fill(WHITE)

HS_FILE = None
try:
    HS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "racing_highscore.txt")
except Exception:
    pass

def load_high():
    try:
        with open(HS_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return 0

def save_high(v):
    try:
        with open(HS_FILE, "w") as f:
            f.write(str(int(v)))
    except Exception:
        pass

# =====================================================================
#  SOUND  (all generated in code, no audio files needed)
# =====================================================================
def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)

def mk(samples, vol=1.0):
    ch = CH
    buf = array("h")
    for s in samples:
        v = int(max(-1.0, min(1.0, s * vol)) * 32767)
        buf.append(v)
        if ch == 2:
            buf.append(v)
    return pygame.mixer.Sound(buffer=buf.tobytes())

def tone(freq, dur, vol=1.0, shape="sine", decay=3.0, attack=0.004):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / RATE
        ph = (t * freq) % 1.0
        if shape == "sine":
            w = math.sin(6.283185 * ph)
        elif shape == "square":
            w = 1.0 if ph < 0.5 else -1.0
        elif shape == "saw":
            w = 2 * ph - 1
        else:
            w = 4 * abs(ph - 0.5) - 1
        env = min(1.0, t / attack) * math.exp(-decay * t / dur)
        out.append(w * env * vol)
    return out

def sweep(f0, f1, dur, vol=1.0):
    n = int(RATE * dur)
    ph, out = 0.0, []
    for i in range(n):
        t = i / n
        ph += (f0 + (f1 - f0) * t) / RATE
        out.append(math.sin(6.283185 * ph) * vol * math.sqrt(math.sin(math.pi * t)))
    return out

def mix(buf, notes, start):
    for k, v in enumerate(notes):
        j = start + k
        if j < len(buf):
            buf[j] += v

def engine_wave(freq):
    n = int(RATE * 0.4)  # freq * 0.4 is a whole number, so it loops cleanly
    out = []
    for i in range(n):
        t = i / RATE
        w = (math.sin(6.283185 * freq * t) + 0.5 * math.sin(12.56637 * freq * t)
             + 0.3 * math.sin(18.84956 * freq * t)) / 1.8
        out.append(w * 0.8)
    return out

def crash_wave():
    n = int(RATE * 0.9)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += (random.uniform(-1, 1) - lp) * 0.35
        w = lp * 1.4 * math.exp(-4 * t) + math.sin(6.283185 * 55 * t) * 0.8 * math.exp(-5 * t)
        w += random.uniform(-1, 1) * math.exp(-25 * t) * 0.8
        out.append(w)
    return out

def whoosh_wave():
    n = int(RATE * 0.35)
    out, lp = [], 0.0
    for i in range(n):
        t = i / n
        lp += (random.uniform(-1, 1) - lp) * (0.1 + 0.5 * t)
        out.append(lp * math.sin(math.pi * t) * 1.6)
    return out

def kick_wave():
    out, ph = [], 0.0
    for i in range(int(RATE * 0.12)):
        t = i / RATE
        ph += (45 + 110 * math.exp(-t * 22)) / RATE
        out.append(math.sin(6.283185 * ph) * math.exp(-t * 20) * 0.9)
    return out

def hat_wave():
    return [random.uniform(-1, 1) * math.exp(-(i / RATE) * 90) for i in range(int(RATE * 0.05))]

def build_music():
    step, per = 0.15, 8
    chords = [(45, [57, 60, 64]), (41, [53, 57, 60]), (48, [60, 64, 67]), (43, [55, 59, 62])]
    buf = [0.0] * int(RATE * step * per * len(chords))
    pat = [0, 1, 2, 1, 2, 1, 0, 1]
    kick, hat = kick_wave(), hat_wave()
    si = 0
    for root, tri in chords:
        for i in range(per):
            start = int(RATE * step * si)
            note = tri[pat[i]] + (12 if i % 4 == 3 else 0)
            mix(buf, tone(midi(note), step * 1.2, 0.16, "square", 4.0), start)
            if i % 2 == 0:
                mix(buf, tone(midi(root), step * 2, 0.28, "triangle", 2.0), start)
                mix(buf, kick, start)
            else:
                mix(buf, hat, start)
            si += 1
    return buf

SND = {}

def build_audio():
    if not AUDIO:
        return
    SND["engine"] = [mk(engine_wave(f)) for f in (70, 90, 115, 145)]
    SND["music"] = mk(build_music())
    SND["crash"] = mk(crash_wave())
    SND["coin"] = mk(tone(988, 0.07, 0.7, "square", 1.5) + tone(1319, 0.3, 0.7, "square", 5.0))
    SND["pass"] = mk(whoosh_wave(), 0.7)
    SND["click"] = mk(tone(660, 0.06, 0.8, "sine", 4.0))
    SND["start"] = mk(sweep(120, 700, 0.6, 0.8))
    lvl = []
    for f in (523, 659, 784, 1047):
        lvl += tone(f, 0.09, 0.5, "square", 2.5)
    SND["level"] = mk(lvl)
    over = []
    for f in (392, 330, 262, 196):
        over += tone(f, 0.2, 0.5, "saw", 2.0)
    SND["over"] = mk(over)

# =====================================================================
#  DRAWING HELPERS
# =====================================================================
def lerp_col(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

def draw_text(surf, s, font, color, pos, anchor="center", shadow=True, alpha=255):
    img = font.render(s, True, color)
    if alpha < 255:
        img.set_alpha(alpha)
    r = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if shadow:
        sh = font.render(s, True, (0, 0, 0))
        sh.set_alpha(min(alpha, 120))
        surf.blit(sh, r.move(2, 2))
    surf.blit(img, r)
    return r

def pill(surf, rect, color=(0, 0, 0, 110)):
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(s, color, s.get_rect(), border_radius=rect.height // 2)
    surf.blit(s, rect.topleft)

def draw_button(surf, rect, label, color, scale=1.0):
    r = rect.copy()
    r.w, r.h = int(rect.w * scale), int(rect.h * scale)
    r.center = rect.center
    rad = r.h // 3
    pygame.draw.rect(surf, tuple(max(0, c - 70) for c in color), r.move(0, 5), border_radius=rad)
    pygame.draw.rect(surf, color, r, border_radius=rad)
    pygame.draw.rect(surf, tuple(min(255, c + 45) for c in color), r, width=3, border_radius=rad)
    draw_text(surf, label, F_M, WHITE, r.center)

def build_car(color):
    w, h = 80, 150
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    dark = tuple(max(0, c - 60) for c in color)
    light = tuple(min(255, c + 55) for c in color)
    for wx, wy in ((2, 24), (62, 24), (2, 92), (62, 92)):
        pygame.draw.rect(s, (15, 15, 15), (wx, wy, 16, 32), border_radius=5)
    pygame.draw.rect(s, color, (8, 6, 64, 138), border_radius=22)
    pygame.draw.rect(s, light, (34, 8, 12, 134), border_radius=5)
    pygame.draw.rect(s, dark, (16, 48, 48, 56), border_radius=10)
    pygame.draw.rect(s, (170, 215, 255), (20, 52, 40, 18), border_radius=5)
    pygame.draw.rect(s, (150, 195, 240), (20, 86, 40, 12), border_radius=4)
    pygame.draw.rect(s, dark, (2, 56, 8, 10), border_radius=3)
    pygame.draw.rect(s, dark, (70, 56, 8, 10), border_radius=3)
    pygame.draw.rect(s, (255, 240, 150), (14, 8, 14, 9), border_radius=3)
    pygame.draw.rect(s, (255, 240, 150), (52, 8, 14, 9), border_radius=3)
    pygame.draw.rect(s, (255, 60, 60), (14, 132, 14, 7), border_radius=3)
    pygame.draw.rect(s, (255, 60, 60), (52, 132, 14, 7), border_radius=3)
    return pygame.transform.smoothscale(s, (CAR_W, CAR_H))

def build_shadow():
    s = pygame.Surface((CAR_W + 10, CAR_H + 10), pygame.SRCALPHA)
    pygame.draw.rect(s, (0, 0, 0, 70), s.get_rect(), border_radius=CAR_W // 3)
    return s

def draw_tree(surf, cx, cy, r):
    sh = int(r * 0.25)
    pygame.draw.circle(surf, (18, 80, 38), (cx + sh, cy + sh), int(r))
    pygame.draw.circle(surf, (24, 110, 50), (cx, cy), int(r))
    pygame.draw.circle(surf, (46, 150, 70), (cx - int(r * 0.2), cy - int(r * 0.2)), int(r * 0.62))
    pygame.draw.circle(surf, (90, 190, 100), (cx - int(r * 0.3), cy - int(r * 0.3)), max(1, int(r * 0.28)))

def draw_coin(surf, cx, cy, R, phase):
    wd = abs(math.cos(phase)) * R
    rect = pygame.Rect(0, 0, max(3, int(wd * 2)), int(R * 2))
    rect.center = (int(cx), int(cy))
    pygame.draw.ellipse(surf, (200, 140, 0), rect.inflate(4, 4))
    pygame.draw.ellipse(surf, YELLOW, rect)
    if rect.w > 8:
        pygame.draw.ellipse(surf, (255, 240, 150), rect.inflate(-int(rect.w * 0.5), -int(rect.h * 0.5)))

# =====================================================================
#  GAME
# =====================================================================
class Game:
    def __init__(self):
        self.high = load_high()
        self.muted = False
        self.t = 0.0
        self.state = "menu"      # menu, play, crash, over
        self.speed = BASE_SPEED * 0.5
        self.scroll = 0.0
        self.engine_idx = -1
        self.left_down = self.right_down = False
        self.player_sprite = build_car(BLUE)
        self.enemy_sprites = {c: build_car(c) for c in ENEMY_COLORS}
        self.shadow = build_shadow()
        self.trees = [[side, i * PLAY_H / 8 + random.uniform(-10, 10), random.uniform(0.8, 1.15),
                       random.uniform(-0.15, 0.15) * ROAD_X] for side in (-1, 1) for i in range(9)]
        self.reset_run()
        if AUDIO:
            self.music_ch = pygame.mixer.Channel(0)
            self.engine_ch = pygame.mixer.Channel(1)
            self.music_ch.play(SND["music"], loops=-1)

    # ---------- state ----------
    def reset_run(self):
        self.px = ROAD_X + ROAD_W / 2 - CAR_W / 2
        self.vx = 0.0
        self.tilt = 0.0
        self.enemies, self.coins, self.parts, self.texts, self.rings = [], [], [], [], []
        self.score = 0.0
        self.level = 1
        self.spawn_t = 0.9
        self.smoke_t = 0.0
        self.shake = 0.0
        self.flash = 0.0
        self.crash_t = 0.0
        self.over_t = 0.0
        self.banner_t = 0.0
        self.banner_text = ""
        self.new_record = False

    def sfx(self, name):
        if AUDIO and not self.muted and name in SND:
            SND[name].play()

    def start(self):
        self.sfx("click")
        self.sfx("start")
        self.reset_run()
        self.state = "play"

    def toggle_mute(self):
        self.muted = not self.muted
        self.sfx("click")

    def crash(self, point):
        self.state = "crash"
        prior = self.high
        self.new_record = prior > 0 and int(self.score) > prior
        if int(self.score) > self.high:
            self.high = int(self.score)
            save_high(self.high)
        self.sfx("crash")
        self.shake, self.flash = 1.0, 0.8
        px, py = point
        self.rings.append([px, py, 0.0])
        cols = [YELLOW, ORANGE, RED, WHITE, (90, 90, 90)]
        for _ in range(70):
            a = random.uniform(0, 6.283)
            sp = random.uniform(80, 420) * U
            life = random.uniform(0.5, 1.0)
            self.parts.append([px, py, math.cos(a) * sp, math.sin(a) * sp, life, life,
                               random.uniform(3, 9) * U, random.choice(cols), "spark"])

    # ---------- input ----------
    def handle(self, ev):
        if ev.type == pygame.QUIT:
            return False
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                return False
            if ev.key == pygame.K_m:
                self.toggle_mute()
            if ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                if self.state == "menu" or (self.state == "over" and self.over_t > 0.4):
                    self.start()
        if ev.type == pygame.MOUSEBUTTONDOWN:
            pos = ev.pos
            if MUTE_RECT.collidepoint(pos):
                self.toggle_mute()
            elif self.state == "menu" and START_RECT.collidepoint(pos):
                self.start()
            elif self.state == "over" and self.over_t > 0.4 and RESTART_RECT.collidepoint(pos):
                self.start()
        return True

    # ---------- update ----------
    def spawn(self):
        near = {e["lane"] for e in self.enemies if e["y"] < CAR_H * 5}
        free = [l for l in range(LANES) if l not in near
                and not any(c["lane"] == l and c["y"] < CAR_H * 1.5 for c in self.coins)]
        if len(near) >= 2 or not free:
            return
        lane = random.choice(free)
        self.enemies.append({"lane": lane, "y": -CAR_H, "color": random.choice(ENEMY_COLORS), "passed": False})
        if random.random() < 0.4:
            others = [l for l in free if l != lane]
            if others:
                self.coins.append({"lane": random.choice(others), "y": -COIN_R * 2,
                                   "phase": random.uniform(0, 6.28)})

    def lane_x(self, lane):
        return ROAD_X + LANE_W * lane + LANE_W / 2 - CAR_W / 2

    def add_text(self, s, x, y, color):
        self.texts.append([s, x, y, 1.0, color])

    def update_play(self, dt, mult):
        dirn = 0
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dirn -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dirn += 1
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            if LEFT_RECT.collidepoint(mx, my):
                dirn -= 1
            elif RIGHT_RECT.collidepoint(mx, my):
                dirn += 1
        dirn = max(-1, min(1, dirn))
        self.left_down, self.right_down = dirn < 0, dirn > 0

        max_v = ROAD_W * 1.0
        self.vx += (dirn * max_v - self.vx) * min(1.0, dt * 9)
        self.px += self.vx * dt
        lo, hi = ROAD_X + 8, ROAD_X + ROAD_W - CAR_W - 8
        if self.px < lo or self.px > hi:
            self.px = max(lo, min(hi, self.px))
            self.vx = 0.0
        self.tilt = self.vx / max_v * 10

        self.score += dt * 12 * mult
        lvl = 1 + int(self.score // 250)
        if lvl > self.level:
            self.level = lvl
            self.banner_text, self.banner_t = "LEVEL %d" % lvl, 1.8
            self.sfx("level")

        self.spawn_t -= dt
        if self.spawn_t <= 0:
            self.spawn()
            self.spawn_t = max(0.38, random.uniform(0.7, 1.15) / mult)

        for e in self.enemies:
            e["y"] += self.speed * LANE_SPEED[e["lane"]] * dt
        self.enemies = [e for e in self.enemies if e["y"] < PLAY_H + CAR_H]
        for c in self.coins:
            c["y"] += self.speed * dt
            c["phase"] += dt * 7
        self.coins = [c for c in self.coins if c["y"] < PLAY_H + COIN_R * 2]

        # exhaust
        self.smoke_t -= dt
        if self.smoke_t <= 0:
            self.smoke_t = 0.04
            self.parts.append([self.px + CAR_W / 2 + random.uniform(-4, 4) * U, PY + CAR_H - 4,
                               random.uniform(-12, 12) * U, self.speed * random.uniform(0.7, 1.0),
                               0.45, 0.45, random.uniform(3, 5) * U, (190, 190, 190), "smoke"])

        prect = pygame.Rect(int(self.px), PY, CAR_W, CAR_H).inflate(-int(CAR_W * 0.25), -int(CAR_H * 0.15))
        # coins
        for c in list(self.coins):
            cx = ROAD_X + LANE_W * c["lane"] + LANE_W / 2
            if prect.inflate(COIN_R * 2, COIN_R * 2).collidepoint(cx, c["y"]):
                self.coins.remove(c)
                self.score += 25
                self.sfx("coin")
                self.add_text("+25", cx, c["y"], YELLOW)
                for _ in range(12):
                    a = random.uniform(0, 6.283)
                    sp = random.uniform(60, 200) * U
                    self.parts.append([cx, c["y"], math.cos(a) * sp, math.sin(a) * sp,
                                       0.5, 0.5, random.uniform(2, 4) * U, YELLOW, "spark"])
        # enemies: crash and near misses
        for e in self.enemies:
            ex = self.lane_x(e["lane"])
            er = pygame.Rect(int(ex), int(e["y"]), CAR_W, CAR_H).inflate(-int(CAR_W * 0.25), -int(CAR_H * 0.15))
            if prect.colliderect(er):
                self.crash(prect.clip(er).center)
                return
            if not e["passed"] and e["y"] > PY + CAR_H:
                e["passed"] = True
                if abs(ex - self.px) < LANE_W * 0.95:
                    self.score += 10
                    self.sfx("pass")
                    self.add_text("NEAR MISS +10", self.px + CAR_W / 2, PY - 10 * U, (120, 255, 200))

    def update(self, dt):
        self.t += dt
        mult = min(2.3, 1 + 0.12 * (self.level - 1))
        target = {"menu": 0.5, "play": mult, "crash": 0.0, "over": 0.0}[self.state] * BASE_SPEED
        self.speed += (target - self.speed) * min(1.0, dt * (2.5 if self.state in ("crash", "over") else 3))
        self.scroll += self.speed * dt

        for tr in self.trees:
            tr[1] += self.speed * dt
            if tr[1] > PLAY_H + 60:
                tr[1] -= PLAY_H + 120 + random.uniform(0, 40)

        self.left_down = self.right_down = False
        if self.state == "play":
            self.update_play(dt, mult)
        elif self.state == "menu":
            self.px = ROAD_X + ROAD_W / 2 - CAR_W / 2 + math.sin(self.t * 1.3) * LANE_W * 0.6
            self.tilt = math.cos(self.t * 1.3) * 6
        else:
            self.vx *= 0.9
            self.tilt *= 0.95
            self.smoke_t -= dt
            if self.smoke_t <= 0:
                self.smoke_t = 0.05
                self.parts.append([self.px + CAR_W / 2 + random.uniform(-8, 8) * U, PY + CAR_H * 0.3,
                                   random.uniform(-15, 15) * U, -70 * U, 0.9, 0.9,
                                   random.uniform(5, 9) * U, (70, 70, 70), "smoke"])
            if self.state == "crash":
                self.crash_t += dt
                for e in self.enemies:
                    e["y"] += self.speed * LANE_SPEED[e["lane"]] * dt
                if self.crash_t > 1.1:
                    self.state = "over"
                    self.sfx("over")
            else:
                self.over_t += dt

        # particles, rings, texts
        alive = []
        for p in self.parts:
            p[4] -= dt
            if p[4] > 0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                if p[8] == "spark":
                    p[3] += 200 * U * dt
                alive.append(p)
        self.parts = alive
        for r in self.rings:
            r[2] += dt
        self.rings = [r for r in self.rings if r[2] < 0.5]
        for tx in self.texts:
            tx[2] -= 70 * U * dt
            tx[3] -= dt
        self.texts = [tx for tx in self.texts if tx[3] > 0]
        self.banner_t = max(0.0, self.banner_t - dt)
        self.shake = max(0.0, self.shake - dt * 1.4)
        self.flash = max(0.0, self.flash - dt * 2.2)

        self.update_audio()

    def update_audio(self):
        if not AUDIO:
            return
        ducked = self.state in ("crash", "over")
        self.music_ch.set_volume(0 if self.muted else (0.12 if ducked else 0.3))
        self.engine_ch.set_volume(0 if self.muted else 0.2)
        if self.state in ("menu", "play"):
            ratio = self.speed / BASE_SPEED
            idx = 0 if ratio < 0.75 else 1 if ratio < 1.15 else 2 if ratio < 1.7 else 3
            if idx != self.engine_idx:
                self.engine_ch.play(SND["engine"][idx], loops=-1)
                self.engine_idx = idx
        elif self.engine_idx != -1:
            self.engine_ch.fadeout(400)
            self.engine_idx = -1

    # ---------- draw ----------
    def draw_world(self, s):
        s.fill(GRASS)
        band = max(30, int(PLAY_H * 0.12))
        y = -band * 2 + self.scroll % (band * 2)
        while y < PLAY_H:
            pygame.draw.rect(s, GRASS_DARK, (0, int(y), W, band))
            y += band * 2

        if ROAD_X > 14:
            for side, ty, sc, jx in self.trees:
                cx = ROAD_X * 0.5 + jx if side < 0 else W - ROAD_X * 0.5 + jx
                draw_tree(s, int(cx), int(ty), TREE_R * sc)

        pygame.draw.rect(s, ROAD_COL, (ROAD_X, 0, ROAD_W, PLAY_H))

        # animated curbs
        cl = max(20, int(30 * U))
        cw = max(6, int(10 * U))
        y = -cl * 2 + self.scroll % (cl * 2)
        while y < PLAY_H:
            for x in (ROAD_X - cw, ROAD_X + ROAD_W):
                pygame.draw.rect(s, RED, (x, int(y), cw, cl))
                pygame.draw.rect(s, WHITE, (x, int(y + cl), cw, cl))
            y += cl * 2
        pygame.draw.line(s, WHITE, (ROAD_X + 4, 0), (ROAD_X + 4, PLAY_H), 4)
        pygame.draw.line(s, WHITE, (ROAD_X + ROAD_W - 4, 0), (ROAD_X + ROAD_W - 4, PLAY_H), 4)

        # lane dashes
        dl = max(24, int(PLAY_H * 0.06))
        y = -dl * 2 + self.scroll % (dl * 2)
        while y < PLAY_H:
            for i in range(1, LANES):
                x = int(ROAD_X + LANE_W * i)
                pygame.draw.line(s, (225, 225, 225), (x, int(y)), (x, int(y + dl)), max(3, int(4 * U)))
            y += dl * 2

        for c in self.coins:
            draw_coin(s, ROAD_X + LANE_W * c["lane"] + LANE_W / 2, c["y"], COIN_R, c["phase"])

        for e in self.enemies:
            x = int(self.lane_x(e["lane"]))
            s.blit(self.shadow, (x - 5, int(e["y"]) + 4))
            s.blit(self.enemy_sprites[e["color"]], (x, int(e["y"])))

        if self.state != "over" or self.over_t < 99:
            s.blit(self.shadow, (int(self.px) - 5, PY + 4))
            rot = pygame.transform.rotate(self.player_sprite, -self.tilt)
            s.blit(rot, rot.get_rect(center=(int(self.px + CAR_W / 2), PY + CAR_H // 2)))

        for x, y, vx, vy, life, mx, size, col, kind in self.parts:
            k = max(0.0, life / mx)
            if kind == "smoke":
                c = lerp_col(col, ROAD_COL, 1 - k)
                r = size * (1 + (1 - k) * 1.4)
            else:
                c, r = col, size * k
            if r >= 1:
                pygame.draw.circle(s, c, (int(x), int(y)), int(r))
        for x, y, age in self.rings:
            k = age / 0.5
            pygame.draw.circle(s, ORANGE, (int(x), int(y)), max(2, int(age * 500 * U)),
                               max(1, int(7 * U * (1 - k))))

    def draw_hud(self):
        sc = F_S.render("Score %d" % int(self.score), True, WHITE)
        r = pygame.Rect(PAD, PAD, sc.get_width() + PAD * 2, HUD_H)
        pill(screen, r)
        screen.blit(sc, sc.get_rect(center=r.center))
        bt = F_S.render("Best %d" % max(self.high, int(self.score)), True, YELLOW)
        r2 = pygame.Rect(0, PAD, bt.get_width() + PAD * 2, HUD_H)
        r2.right = W - PAD
        pill(screen, r2)
        screen.blit(bt, bt.get_rect(center=r2.center))
        kmh = int(self.speed / BASE_SPEED * 70)
        lv = F_S.render("Level %d   %d km/h" % (self.level, kmh), True, WHITE)
        r3 = pygame.Rect(PAD, r.bottom + PAD // 2, lv.get_width() + PAD * 2, HUD_H)
        pill(screen, r3)
        screen.blit(lv, lv.get_rect(center=r3.center))

    def draw_mute(self):
        r = MUTE_RECT
        pill(screen, r)
        cx, cy = r.center
        s = r.w * 0.2
        pygame.draw.polygon(screen, WHITE, [(cx - s * 1.4, cy - s * 0.6), (cx - s * 0.6, cy - s * 0.6),
                                            (cx + s * 0.3, cy - s * 1.3), (cx + s * 0.3, cy + s * 1.3),
                                            (cx - s * 0.6, cy + s * 0.6), (cx - s * 1.4, cy + s * 0.6)])
        if self.muted:
            pygame.draw.line(screen, RED, (cx + s * 0.7, cy - s), (cx + s * 1.7, cy + s), 3)
            pygame.draw.line(screen, RED, (cx + s * 1.7, cy - s), (cx + s * 0.7, cy + s), 3)
        else:
            for k in (0.8, 1.3):
                pygame.draw.arc(screen, WHITE, (int(cx + s * 0.3 - s * k), int(cy - s * k),
                                                int(s * k * 2), int(s * k * 2)), -0.9, 0.9, 3)

    def draw_controls(self):
        for rect, side, down in ((LEFT_RECT, -1, self.left_down), (RIGHT_RECT, 1, self.right_down)):
            pygame.draw.rect(screen, (100, 100, 118) if down else (52, 52, 62), rect)
            cx, cy = rect.center
            a = int(CTRL_H * 0.22)
            pygame.draw.polygon(screen, WHITE, [(cx - side * a * 0.6, cy - a), (cx - side * a * 0.6, cy + a),
                                                (cx + side * a * 0.8, cy)])
        pygame.draw.line(screen, (20, 20, 28), (W // 2, PLAY_H), (W // 2, H), 4)
        pygame.draw.line(screen, (20, 20, 28), (0, PLAY_H), (W, PLAY_H), 4)

    def draw_menu(self):
        bob = math.sin(self.t * 2.5) * 6 * U
        draw_text(screen, "CAR", F_XL, YELLOW, (W // 2, H * 0.17 + bob))
        draw_text(screen, "RACING", F_XL, WHITE, (W // 2, H * 0.17 + F_XL.get_height() + bob))
        draw_button(screen, START_RECT, "START GAME", BLUE, 1 + 0.05 * math.sin(self.t * 4))
        draw_text(screen, "Best %d" % self.high, F_M, YELLOW, (W // 2, H * 0.6))
        draw_text(screen, "Hold LEFT or RIGHT to steer", F_S, WHITE, (W // 2, H * 0.66))
        draw_text(screen, "Grab coins and dodge traffic", F_S, WHITE, (W // 2, H * 0.66 + F_S.get_height() * 1.4))

    def draw_over(self):
        a = min(1.0, self.over_t * 2.5)
        DIM.set_alpha(int(170 * a))
        screen.blit(DIM, (0, 0))
        al = int(255 * a)
        y = H * 0.24 + (1 - a) * 30 * U
        draw_text(screen, "GAME OVER", F_L, RED, (W // 2, y), alpha=al)
        draw_text(screen, "Score %d" % int(self.score), F_M, WHITE, (W // 2, y + F_L.get_height()), alpha=al)
        draw_text(screen, "Best %d" % self.high, F_M, YELLOW, (W // 2, y + F_L.get_height() * 1.6), alpha=al)
        if self.new_record:
            pulse = 0.5 + 0.5 * math.sin(self.over_t * 8)
            draw_text(screen, "NEW RECORD!", F_M, lerp_col(YELLOW, WHITE, pulse),
                      (W // 2, y + F_L.get_height() * 2.3), alpha=al)
        if self.over_t > 0.4:
            draw_button(screen, RESTART_RECT, "RESTART", ORANGE, 1 + 0.05 * math.sin(self.t * 4))

    def draw(self):
        ox = oy = 0
        if self.shake > 0:
            amp = 16 * U * self.shake
            ox, oy = random.uniform(-amp, amp), random.uniform(-amp, amp)
        self.draw_world(world)
        screen.fill(GRASS_DARK)
        screen.blit(world, (int(ox), int(oy)))
        if self.flash > 0:
            FLASH.set_alpha(int(255 * self.flash * 0.7))
            screen.blit(FLASH, (0, 0))

        for s, x, y, life, col in self.texts:
            draw_text(screen, s, F_S, col, (x, y), alpha=int(255 * min(1.0, life * 2)))
        if self.banner_t > 0:
            k = self.banner_t / 1.8
            draw_text(screen, self.banner_text, F_L, YELLOW, (W // 2, PLAY_H * 0.3 - (1 - k) * 30 * U),
                      alpha=int(255 * min(1.0, k * 2)))

        if self.state in ("play", "crash"):
            self.draw_hud()
        elif self.state == "menu":
            self.draw_menu()
        else:
            self.draw_over()
        self.draw_controls()
        self.draw_mute()
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = min(clock.tick(60) / 1000.0, 0.05)
            for ev in pygame.event.get():
                if not self.handle(ev):
                    running = False
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    screen.fill((15, 20, 30))
    msg = F_M.render("Loading sounds...", True, WHITE)
    screen.blit(msg, msg.get_rect(center=(W // 2, H // 2)))
    pygame.display.flip()
    pygame.event.pump()
    build_audio()
    Game().run()
