"""10층 최종 보스: 그림자 플레이어.
플레이어 그림을 어둡게 만든 모습으로, 대쉬하고 정밀하게 조준해서 보라빛 탄환을 쏜다.
수치는 전부 dg_config.py 의 '그림자 보스' 부분에서 바꾸세요."""
from pico2d import *
from PIL import Image
import numpy as np
import json
import math
import os
import random

from config import *
from boss import make_orb
from dg_config import *

SH_SHEET = OUT('dg_shadow_sheet.png')
SH_FRONT = OUT('dg_shadow_front.png')
SH_BACK = OUT('dg_shadow_back.png')
SH_SHEET_H = OUT('dg_shadow_sheet_hurt.png')
SH_FRONT_H = OUT('dg_shadow_front_hurt.png')
SH_BACK_H = OUT('dg_shadow_back_hurt.png')
SH_BULLET = OUT('dg_shadow_bullet.png')
SH_GLOW = OUT('dg_shadow_glow.png')
SH_AURA = OUT('dg_shadow_aura.png')
SH_PURPLE = OUT('dg_purple.png')
SH_SIG = OUT('dg_shadow_sig.json')

# ---- 직접 만든 그림 (dungeon 폴더나 image 폴더에 두면 자동으로 사용. 없으면 플레이어 그림을 어둡게 해서 씀) ----
SH_ART = DP('shadow_atlas.png')               # 정면/측면/후면/대쉬 12프레임을 한 장에 모은 그림
SH_ART_BULLET = DP('shadow_bullet.png')       # 탄환 그림 (오른쪽을 향한 모습)
SH_ART_HURT = OUT('dg_shadow_atlas_hurt.png')  # 맞았을 때 번쩍이는 그림 (자동 생성)
ART_RECTS = {'side': [0, 0, 171, 215], 'up': [175, 0, 169, 212], 'down': [348, 0, 154, 194],
             'dash0': [506, 0, 170, 168], 'dash1': [680, 0, 170, 170], 'dash2': [854, 0, 184, 170],
             'dash3': [1042, 0, 178, 168], 'dash4': [1224, 0, 154, 170], 'dash5': [1382, 0, 178, 168],
             'dash6': [1564, 0, 168, 170], 'dash7': [1736, 0, 148, 168], 'dash8': [1888, 0, 176, 166],
             'dash9': [2068, 0, 160, 166], 'dash10': [2232, 0, 192, 166], 'dash11': [2428, 0, 176, 162]}
ART_SCALE = 1.5                               # 보스 크기 = 플레이어의 몇 배 (줄이려면 이 숫자를 낮추세요)
ART_REL = {'side': 1.0, 'up': 1.0, 'down': 1.0, 'dash': 1.1}   # 그림별 상대 크기 (대쉬 그림은 조금 크게)
ART_BULLET_LEN = 2.2                          # 탄환 그림 길이 = SHADOW_BULLET_LEN 의 몇 배 (불꽃 꼬리 포함)
ART_DASH_FPS = 60                             # 대쉬 그림이 넘어가는 속도(프레임/초)

SHADOW_AIM_N = globals().get('SHADOW_AIM_N', 3)              # 정밀 조준 탄 개수 (dg_config.py 에서 바꾸세요)
SHADOW_AIM_SPREAD = globals().get('SHADOW_AIM_SPREAD', 0.16)  # 정밀 조준 탄 사이 각도 (dg_config.py 에서 바꾸세요)

SHADOW_INTRO = 1.5          # 나타나는 시간(초)
SHADOW_MUZZLE = 40          # 몸 중심에서 탄이 나오는 거리


# =============== 이미지 준비 (창 열기 전에 실행) ===============
def _dark(rgb):
    """색을 빼고 어둡게 한 뒤 보랏빛을 살짝 더함"""
    lum = (rgb * np.array([0.299, 0.587, 0.114], np.float32)).sum(axis=2, keepdims=True)
    base = rgb * (1 - SHADOW_DESAT) + lum * SHADOW_DESAT
    return base * SHADOW_DARK + np.array(SHADOW_TINT, np.float32)


def _dark_hurt(rgb):
    """맞았을 때: 어두운 모습이 밝은 보랏빛으로 번쩍"""
    return _dark(rgb) * 0.35 + np.array([235, 205, 255], np.float32) * 0.65


def _flash(rgb):
    """직접 만든 그림용: 맞았을 때 밝은 보랏빛으로 번쩍"""
    return rgb * 0.3 + np.array([235, 205, 255], np.float32) * 0.7


def _recolor(src, dst, fn):
    a = np.array(Image.open(src).convert('RGBA')).astype(np.float32)
    a[:, :, :3] = np.clip(fn(a[:, :, :3]), 0, 255)
    Image.fromarray(a.astype(np.uint8)).save(dst)


def _make_bullet(dst):
    """플레이어 탄환(날아가는 모습)의 색을 보랏빛으로 바꾼 그림. (w, h) 반환"""
    if not os.path.exists(BULLET_FLY):
        make_orb(dst, (245, 215, 255), (150, 60, 255), 64)
        return (64, 64)
    im = Image.open(BULLET_FLY).convert('RGBA')
    alpha = im.getchannel('A')
    h, s, v = [np.array(c, np.float32) for c in im.convert('RGB').convert('HSV').split()]
    h2 = (SHADOW_BULLET_HUE + h * 0.6) % 256          # 빨강~노랑 계열이 보라~자주 계열로
    s2 = np.clip(s * 1.1, 0, 255)
    v2 = np.clip(v * 1.05 + 10, 0, 255)
    out = Image.merge('HSV', [Image.fromarray(x.astype(np.uint8)) for x in (h2, s2, v2)]).convert('RGB')
    out.putalpha(alpha)
    out.save(dst)
    return out.size


def _make_aura(path, size=256):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    d = np.hypot(xx - c, yy - c) / c
    alpha = np.clip(1 - d, 0, 1) ** 1.8
    out = np.zeros((size, size, 4), np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = 150, 50, 255
    out[:, :, 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(out).save(path)


def prepare_shadow():
    """그림자 보스에 쓰는 그림들을 만든다. 돌려주는 값: {'ok': 성공 여부, 'bullet_wh': (w, h)}
    플레이어 그림이나 아래 SHADOW_* 수치가 바뀌면 자동으로 새로 만든다"""
    srcs = [CLEAN, FRONT_CLEAN, BACK_CLEAN, BULLET_FLY]
    sig = [str((SHADOW_DARK, SHADOW_DESAT, SHADOW_TINT, SHADOW_BULLET_HUE, 3))]
    art = os.path.exists(SH_ART)
    art_b = os.path.exists(SH_ART_BULLET)
    for p in srcs + [SH_ART, SH_ART_BULLET]:
        try:
            st = os.stat(p)
            sig.append(f'{p}|{st.st_size}|{int(st.st_mtime)}')
        except OSError:
            sig.append(f'{p}|-')
    try:
        with open(SH_SIG, 'r') as f:
            old = json.load(f)
    except Exception:
        old = None
    outs = [SH_SHEET, SH_FRONT, SH_BACK, SH_SHEET_H, SH_FRONT_H, SH_BACK_H, SH_BULLET] + ([SH_ART_HURT] if art else [])
    same = (old is not None and old.get('sig') == sig and all(os.path.exists(p) for p in outs))
    if not os.path.exists(CLEAN):
        print('[그림자 보스] character_clean.png가 없어 준비하지 못했어요')
        return {'ok': False, 'bullet_wh': (64, 64)}
    if same:
        return {'ok': True, 'bullet_wh': tuple(old['bullet_wh']), 'art': art, 'bullet_art': art_b}

    try:
        _recolor(CLEAN, SH_SHEET, _dark)
        _recolor(CLEAN, SH_SHEET_H, _dark_hurt)
        for src, d, dh in ((FRONT_CLEAN, SH_FRONT, SH_FRONT_H), (BACK_CLEAN, SH_BACK, SH_BACK_H)):
            if os.path.exists(src):
                _recolor(src, d, _dark)
                _recolor(src, dh, _dark_hurt)
        wh = _make_bullet(SH_BULLET)
        if art:
            _recolor(SH_ART, SH_ART_HURT, _flash)
        if art_b:
            wh = Image.open(SH_ART_BULLET).size
            Image.open(SH_ART_BULLET).convert('RGBA').save(SH_BULLET)
        make_orb(SH_GLOW, (245, 215, 255), (150, 60, 255), 64)
        _make_aura(SH_AURA)
        Image.new('RGBA', (4, 4), (175, 95, 255, 255)).save(SH_PURPLE)
        with open(SH_SIG, 'w') as f:
            json.dump({'sig': sig, 'bullet_wh': list(wh)}, f)
        return {'ok': True, 'bullet_wh': wh, 'art': art, 'bullet_art': art_b}
    except Exception as e:
        print(f'[그림자 보스] 그림 준비 실패: {e}')
        return {'ok': False, 'bullet_wh': (64, 64)}


# =============== 보라 탄환 ===============
class ShadowBullet:
    """보스 탄환과 같은 방식으로 동작함 (update / draw / x / y / alive). 플레이어가 주울 수 없음"""
    img = glow = None
    wh = (64, 64)
    art = False

    @classmethod
    def setup(cls, info):
        cls.img = load_image(SH_BULLET)
        cls.glow = load_image(SH_GLOW)
        cls.wh = info['bullet_wh']
        cls.art = bool(info.get('bullet_art'))

    def __init__(self, x, y, ang, speed):
        self.x, self.y = x, y
        self.ang = ang
        self.vx = math.cos(ang) * speed
        self.vy = math.sin(ang) * speed
        self.alive = True
        self.age = 0.0
        self.trail = []

    def update(self, dt, target=None):
        self.age += dt
        self.trail.append((self.x, self.y))
        self.trail = self.trail[-6:]
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not (-60 < self.x < CANVAS_W + 60 and -60 < self.y < CANVAS_H + 60):
            self.alive = False

    def draw(self, imgs=None, metas=None):
        w, h = self.wh
        if self.art:                                            # 직접 만든 탄환 그림: 불꽃 꼬리가 달린 큰 그림
            dw = SHADOW_BULLET_LEN * ART_BULLET_LEN
            dh = dw * h / w
            self.img.opacify(1.0)
            self.img.clip_composite_draw(0, 0, w, h, self.ang, '', self.x - math.cos(self.ang) * dw * 0.42,
                                         self.y - math.sin(self.ang) * dw * 0.42, dw, dh)
            return
        dw = SHADOW_BULLET_LEN
        dh = dw * h / w
        n = len(self.trail)
        for i, (tx, ty) in enumerate(self.trail):               # 보라 꼬리
            f = (i + 1) / (n + 1)
            self.glow.opacify(0.30 * f)
            self.glow.draw(tx, ty, 30 * f, 30 * f)
        pulse = 1 + 0.1 * math.sin(self.age * 22)
        self.glow.opacify(0.55)
        self.glow.draw(self.x, self.y, 44 * pulse, 44 * pulse)
        cx = self.x - math.cos(self.ang) * dw * 0.25            # 머리가 판정 위치에 오도록
        cy = self.y - math.sin(self.ang) * dw * 0.25
        self.img.opacify(1.0)
        self.img.clip_composite_draw(0, 0, w, h, self.ang + BULLET_ANGLE_FIX, '', cx, cy, dw, dh)


# =============== 그림자 보스 ===============
def _seg_dist(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    u = 0.0 if l2 < 1e-9 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / l2))
    return math.hypot(px - (x0 + dx * u), py - (y0 + dy * u))


def _face_of(dx, dy):
    if abs(dx) >= abs(dy):
        return 'right' if dx > 0 else 'left'
    return 'up' if dy > 0 else 'down'


class ShadowBoss:
    def __init__(self, sprites, front_size, back_size, diff):
        self.max_hp = max(1, int(SHADOW_HP * SHADOW_HP_MULT.get(diff['id'], 1.0)))
        self.cd_mult = diff['cd']
        self.spd_mult = diff['speed']
        self.K = SHADOW_SCALE

        self.sets = {
            'normal': self._build(sprites, front_size, back_size, SH_SHEET, SH_FRONT, SH_BACK),
            'hurt': self._build(sprites, front_size, back_size, SH_SHEET_H, SH_FRONT_H, SH_BACK_H),
        }
        spr = self.sets['normal'][0]
        self.base_w = max(s[3] * s[5] for s in spr.values()) * self.K
        self.base_h = max(s[4] * s[5] for s in spr.values()) * self.K
        self.art = None                                          # 직접 만든 그림이 있으면 그걸 씀
        if os.path.exists(SH_ART) and os.path.exists(SH_ART_HURT):
            self.art = {'normal': load_image(SH_ART), 'hurt': load_image(SH_ART_HURT)}
            self.art_ah = self.art['normal'].h
            self.art_unit = self.base_h / self.K * ART_SCALE      # 플레이어 키 x 배율
            self.base_h = ART_REL['side'] * self.art_unit
            self.base_w = self.base_h * ART_RECTS['side'][2] / ART_RECTS['side'][3]
        self.radius = max(26.0, min(self.base_w, self.base_h) * 0.42)

        self.shadow = load_image(SHADOW)
        self.aura = load_image(SH_AURA)
        self.glow = load_image(SH_GLOW)
        self.warn_img = load_image(SH_PURPLE)
        self.bar_bg = load_image(BAR_BG)
        self.bar_fg = load_image(BAR_FG)

        self.x, self.y = CANVAS_W / 2, SHADOW_MAX_Y - 40
        self._lx, self._ly = self.x, self.y
        self.hp = self.max_hp
        self.alive = True
        self.dying = False
        self.die_t = 0.0
        self.clock = 0.0
        self.hurt_clock = -10.0
        self.state, self.t = 'intro', 0.0
        self.facing = 'down'
        self.walk_phase = 0.0
        self.walk_amp = 0.0
        self.vel = (0.0, 0.0)
        self.side = random.choice((-1, 1))
        self.side_t = random.uniform(1.0, 2.2)
        self.ghosts = []
        self.clones = []
        self.next_attack = SHADOW_INTRO + 0.8
        self.last = None
        self.atk = 'aim'
        self.aim_ang = -math.pi / 2
        self.aim_dur = 1.0
        self.shots_left = 0
        self.dash_dir = (0.0, 0.0)
        self.dash_len = SHADOW_DASH_SPEED * SHADOW_DASH_TIME
        self.dash_from = (self.x, self.y)
        self.flash_t = 0.0
        self.player = None
        self.bb = None
        self.pvel = (0.0, 0.0)
        self.ppos = None
        self.prev_phase = 0
        self.phase_event = None          # main이 읽고 비움 (단계 알림)
        self.laser_fired = False         # 기존 보스와 같은 모양으로 맞춰 둔 것 (쓰지 않음)
        self.slam = False

    # ---------- 준비 ----------
    def _build(self, sprites, front_size, back_size, sheet_p, front_p, back_p):
        sheet = load_image(sheet_p)
        top, bottom = sprites[0], sprites[1]
        spr = {'side': (sheet, *bottom[0], SCALE)}
        imgs = [sheet]
        if front_size and os.path.exists(front_p):
            im = load_image(front_p)
            fw, fh = front_size
            spr['down'] = (im, 0, 0, fw, fh, SCALE * top[2][3] / fh * FRONT_ADJUST)
            imgs.append(im)
        else:
            spr['down'] = (sheet, *top[2], SCALE)
        if back_size and os.path.exists(back_p):
            im = load_image(back_p)
            bw, bh = back_size
            spr['up'] = (im, 0, 0, bw, bh, SCALE * top[3][3] / bh * BACK_ADJUST)
            imgs.append(im)
        else:
            spr['up'] = (sheet, *top[3], SCALE)
        return spr, imgs

    @property
    def phase(self):
        r = self.hp / self.max_hp
        return 0 if r > 0.66 else (1 if r > 0.33 else 2)

    def _off(self):
        """그릴 때 화면 흔들림만큼 옮겨진 정도 (main이 그리는 동안만 x, y를 옮겨 놓음)"""
        return self.x - self._lx, self.y - self._ly

    # ---------- 도우미 ----------
    def _to(self, state):
        self.state, self.t = state, 0.0

    def _face_toward(self, dx, dy):
        ax, ay = abs(dx), abs(dy)
        side = self.facing in ('left', 'right')
        go_side = ax * 1.25 >= ay if side else ax >= ay * 1.25      # 경계에서 깜빡이지 않게
        if go_side:
            self.facing = 'right' if dx > 0 else 'left'
        else:
            self.facing = 'up' if dy > 0 else 'down'

    def _hit_center(self):
        p = self.player
        return p.x, p.y - p.base_h * HIT_OFFSET

    def _predict(self, ox, oy):
        """(ox, oy)에서 쐈을 때 움직이는 플레이어를 맞힐 각도"""
        hx, hy = self._hit_center()
        d = math.hypot(hx - ox, hy - oy)
        t = d / (SHADOW_BULLET_SPEED * self.spd_mult) * SHADOW_LEAD
        return math.atan2(hy + self.pvel[1] * t - oy, hx + self.pvel[0] * t - ox)

    def _track(self, player, dt):
        if self.ppos is not None and dt > 0:
            vx, vy = (player.x - self.ppos[0]) / dt, (player.y - self.ppos[1]) / dt
            k = min(1.0, dt * 8)
            self.pvel = (self.pvel[0] + (vx - self.pvel[0]) * k, self.pvel[1] + (vy - self.pvel[1]) * k)
            sp = math.hypot(*self.pvel)
            if sp > 280:
                self.pvel = (self.pvel[0] * 280 / sp, self.pvel[1] * 280 / sp)
        self.ppos = (player.x, player.y)

    def cooldown(self):
        return SHADOW_CD[self.phase] * self.cd_mult

    def _shoot(self, x, y, ang):
        self.bb.append(ShadowBullet(x + math.cos(ang) * SHADOW_MUZZLE, y + math.sin(ang) * SHADOW_MUZZLE,
                                    ang, SHADOW_BULLET_SPEED * self.spd_mult))

    # ---------- 공격 시작 ----------
    def _start_aim(self, dur, shots, kind):
        self.atk = kind
        self.aim_dur = dur
        self.shots_left = shots
        self.aim_ang = self._predict(self.x, self.y)
        self._to('aim')

    def _start_dash(self):
        """플레이어 옆으로 대쉬해서 자리를 바꾼 뒤 바로 쏜다. 대쉬 길은 미리 보여 줌"""
        p = self.player
        dx, dy = p.x - self.x, p.y - self.y
        base = math.atan2(dy, dx)
        L = self.dash_len
        pick = None
        for sgn in random.sample((-1, 1), 2):
            for deg in (85, 105, 65):
                a = base + sgn * math.radians(deg)
                vx, vy = math.cos(a), math.sin(a)
                ex, ey = self.x + vx * L, self.y + vy * L
                if arena_d(ex, ey) > 0.85 or not (SHADOW_MIN_Y <= ey <= SHADOW_MAX_Y):
                    continue
                if math.hypot(ex - p.x, ey - p.y) < 150:
                    continue
                if _seg_dist(p.x, p.y, self.x, self.y, ex, ey) < self.radius + 40:
                    continue
                pick = (vx, vy)
                break
            if pick:
                break
        if pick is None:                                   # 갈 곳이 없으면 대쉬 대신 그냥 조준 사격
            self._start_aim(SHADOW_AIM[self.phase], 1, 'aim')
            return
        self.atk = 'dash'
        self.dash_dir = pick
        self.dash_from = (self.x, self.y)
        self._face_toward(*pick)
        self._to('dash_warn')
        Sound.play('warning')

    def _start_clone(self):
        """분신 2개를 불러내고, 본체와 분신이 같은 순간에 쏜다"""
        p = self.player
        self.clones = []
        base = random.uniform(0, 2 * math.pi)
        for i in range(SHADOW_CLONE_N):
            for _ in range(30):
                a = base + i * 2 * math.pi / SHADOW_CLONE_N + random.uniform(-0.5, 0.5)
                r = random.uniform(210, 300)
                cx, cy = p.x + math.cos(a) * r, p.y + math.sin(a) * r
                if arena_d(cx, cy) < 0.86 and cy < ARENA_CENTER_Y + 160 and \
                        all(math.hypot(cx - c['x'], cy - c['y']) > 120 for c in self.clones):
                    break
            else:
                cx, cy = clamp_arena(p.x + math.cos(base) * 220, p.y + math.sin(base) * 220, 40)
            self.clones.append({'x': cx, 'y': cy, 't': 0.0, 'ang': math.atan2(p.y - cy, p.x - cx),
                                'fired': False, 'face': 'down'})
        Sound.play('warning')
        self._start_aim(SHADOW_CLONE_AIM, 1, 'clone')

    def _attack(self):
        ph = self.phase
        pool = {0: [('aim', 2), ('dash', 1)],
                1: [('aim', 2), ('dash', 2), ('fan', 1)],
                2: [('aim', 1), ('dash', 2), ('fan', 1), ('clone', 2)]}[ph]
        allk = [k for k, w in pool for _ in range(w)]
        k = random.choice([x for x in allk if x != self.last] or allk)
        self.last = k
        if k == 'aim':
            self._start_aim(SHADOW_AIM[ph], 1, 'aim')
        elif k == 'fan':
            self._start_aim(SHADOW_AIM[ph] + 0.15, 1, 'fan')
        elif k == 'dash':
            self._start_dash()
        else:
            self._start_clone()

    def _fire(self):
        if self.atk == 'fan':
            n = SHADOW_FAN_N
            for i in range(n):
                self._shoot(self.x, self.y, self.aim_ang + (i - (n - 1) / 2) * SHADOW_FAN_STEP)
        elif self.atk == 'aim':                            # 정밀 조준: 탄 여러 발이 동시에 좁게 퍼져서 나감
            n = SHADOW_AIM_N
            for i in range(n):
                self._shoot(self.x, self.y, self.aim_ang + (i - (n - 1) / 2) * SHADOW_AIM_SPREAD)
        else:
            self._shoot(self.x, self.y, self.aim_ang)
        Sound.play('shot')
        self.flash_t = 0.15
        self.shots_left -= 1
        if self.shots_left > 0:                            # 연사: 짧게 다시 조준
            self.aim_dur = 0.5
            self._to('aim')
            self.aim_ang = self._predict(self.x, self.y)
        else:
            self._to('recover')

    # ---------- 갱신 ----------
    def update(self, dt, player, boss_bullets):
        self.clock += dt
        self.player, self.bb = player, boss_bullets
        self._track(player, dt)
        self.flash_t = max(0.0, self.flash_t - dt)

        if self.alive and self.phase != self.prev_phase:       # 단계가 바뀌면 탄을 지우고 잠깐 쉼
            self.prev_phase = self.phase
            self.phase_event = self.phase
            Sound.play('phase')
            self.bb.clear()
            self.clones = []
            self.ghosts = []
            self.vel = (0.0, 0.0)
            self._to('move')
            self.next_attack = self.clock + 1.6

        if not self.alive:
            self.clones = []
            self.ghosts = []
            if self.dying:
                self.die_t += dt
            self._lx, self._ly = self.x, self.y
            return

        self.t += dt
        self.ghosts = [g for g in self.ghosts if self.clock - g[4] < 0.2]
        st = self.state

        if st == 'intro':
            self._face_toward(0, -1)
            if self.t >= SHADOW_INTRO:
                self._to('move')
        elif st == 'move':
            self._move(dt)
            if self.clock >= self.next_attack:
                self._attack()
        elif st == 'aim':
            self.vel = (self.vel[0] * 0.8, self.vel[1] * 0.8)
            if self.t < self.aim_dur - SHADOW_AIM_LOCK:
                self.aim_ang = self._predict(self.x, self.y)
            self._face_toward(math.cos(self.aim_ang), math.sin(self.aim_ang))
            if self.t >= self.aim_dur:
                self._fire()
        elif st == 'recover':
            if self.t >= 0.4:
                self._to('move')
                self.next_attack = self.clock + self.cooldown()
        elif st == 'dash_warn':
            if self.t >= SHADOW_DASH_WARN:
                self._to('dash')
                self.dash_from = (self.x, self.y)
                Sound.play('dash')
        elif st == 'dash':
            step = SHADOW_DASH_SPEED * dt
            self.x += self.dash_dir[0] * step
            self.y += self.dash_dir[1] * step
            self.ghosts.append((self.x, self.y, self.facing, -self.dash_dir[0] * math.radians(15), self.clock))
            if self.t >= SHADOW_DASH_TIME:
                self.x, self.y = clamp_arena(self.x, self.y, 30)
                self.y = max(SHADOW_MIN_Y, min(SHADOW_MAX_Y, self.y))
                self.vel = (0.0, 0.0)
                shots = (1, 1, 2)[self.phase]
                self._start_aim(SHADOW_DASH_SHOT_AIM, shots, 'dash')   # 대쉬 직후 바로 조준

        # 분신
        for c in self.clones:
            c['t'] += dt
            if c['t'] < SHADOW_CLONE_AIM - SHADOW_AIM_LOCK:
                c['ang'] = self._predict(c['x'], c['y'])
            c['face'] = _face_of(math.cos(c['ang']), math.sin(c['ang']))
            if c['t'] >= SHADOW_CLONE_AIM and not c['fired']:
                c['fired'] = True
                self._shoot(c['x'], c['y'], c['ang'])
        self.clones = [c for c in self.clones if c['t'] < SHADOW_CLONE_AIM + 0.4]

        self._lx, self._ly = self.x, self.y

    def _move(self, dt):
        p = self.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        lo, hi = SHADOW_KEEP
        if d < lo:
            vx, vy = -dx / d, -dy / d
        elif d > hi:
            vx, vy = dx / d, dy / d
        else:
            self.side_t -= dt
            if self.side_t <= 0:
                self.side = -self.side
                self.side_t = random.uniform(1.0, 2.4)
            vx, vy = -dy / d * self.side, dx / d * self.side
        sp = SHADOW_WALK * self.spd_mult * (1 + 0.15 * self.phase)
        tvx, tvy = vx * sp, vy * sp
        if self.y >= SHADOW_MAX_Y - 10 and tvy > 0:
            tvy = 0.0
        if self.y <= SHADOW_MIN_Y + 10 and tvy < 0:
            tvy = 0.0
        k = min(1.0, 6 * dt)
        self.vel = (self.vel[0] + (tvx - self.vel[0]) * k, self.vel[1] + (tvy - self.vel[1]) * k)
        self.x += self.vel[0] * dt
        self.y += self.vel[1] * dt
        self.x, self.y = clamp_arena(self.x, self.y, 30)
        self.y = max(SHADOW_MIN_Y, min(SHADOW_MAX_Y, self.y))
        moving = math.hypot(*self.vel) > 25
        self.walk_amp += ((1.0 if moving else 0.0) - self.walk_amp) * min(1.0, dt * 12)
        if moving:
            self.walk_phase += dt * STEP_FREQ * 0.8
        self._face_toward(dx, dy)

    def hit(self):
        self.hp -= 1
        self.hurt_clock = self.clock
        Sound.play('hit')
        if self.hp <= 0:
            self.alive = False
            self.dying = True
            self.die_t = 0.0
            Sound.play('explode')

    # ---------- 기존 보스와 모양을 맞추기 위한 것들 ----------
    def laser_hit(self, hx, hy):
        return False

    def draw_lasers(self, ox=0.0, oy=0.0):
        pass

    def draw_warning_hud(self):
        pass

    # ---------- 그리기 ----------
    def _line(self, x0, y0, ang, length, width, alpha):
        cx = x0 + math.cos(ang) * length / 2
        cy = y0 + math.sin(ang) * length / 2
        self.warn_img.opacify(max(0.0, min(1.0, alpha)))
        self.warn_img.clip_composite_draw(0, 0, 4, 4, ang, '', cx, cy, length, width)

    def _aim_lines(self, x, y, ang, t, dur, fan, multi=False):
        """조준선: 선이 칠해진 곳이 실제 탄이 지나가는 길. 마지막 순간에는 진하게 고정"""
        locked = t >= dur - SHADOW_AIM_LOCK
        k = min(1.0, t / dur)
        width = HIT_RADIUS * 2 + 4
        angs = [ang]
        if fan:
            angs = [ang + (i - (SHADOW_FAN_N - 1) / 2) * SHADOW_FAN_STEP for i in range(SHADOW_FAN_N)]
        elif multi:
            angs = [ang + (i - (SHADOW_AIM_N - 1) / 2) * SHADOW_AIM_SPREAD for i in range(SHADOW_AIM_N)]
        for a in angs:
            sx, sy = x + math.cos(a) * SHADOW_MUZZLE, y + math.sin(a) * SHADOW_MUZZLE
            if not fan and not multi:
                self._line(sx, sy, a, 900, width, 0.30 if locked else 0.08 + 0.10 * k)
            self._line(sx, sy, a, 900, 3 if locked else 2, 0.9 if locked else 0.25 + 0.25 * k)

    def draw_warning(self):
        if not self.alive or self.player is None:
            return
        ox, oy = self._off()
        if self.state == 'aim':
            self._aim_lines(self._lx + ox, self._ly + oy, self.aim_ang, self.t, self.aim_dur, self.atk == 'fan',
                            self.atk == 'aim' and SHADOW_AIM_N > 1)
        elif self.state == 'dash_warn':        # 대쉬 길 (보스 몸이 지나가는 범위)
            fx, fy = self.dash_from
            ang = math.atan2(self.dash_dir[1], self.dash_dir[0])
            k = self.t / SHADOW_DASH_WARN
            self._line(fx + ox, fy + oy, ang, self.dash_len + self.radius, self.radius * 2, 0.10 + 0.22 * k)
            self._line(fx + ox, fy + oy, ang, self.dash_len + self.radius, 3, 0.8)
        for c in self.clones:
            if c['t'] < SHADOW_CLONE_AIM:
                self._aim_lines(c['x'] + ox, c['y'] + oy, c['ang'], c['t'], SHADOW_CLONE_AIM, False)

    def _draw_at(self, x, y, facing, lift=0.0, tilt=0.0, sx=1.0, sy=1.0, alpha=1.0, hurt=False, frame=None):
        if self.art:                                             # 직접 만든 그림
            if frame:
                key, flip = frame, ('h' if facing == 'left' else '')
            elif facing in ('left', 'right'):
                key, flip = 'side', ('h' if facing == 'left' else '')
            else:
                key, flip = facing, ''
            rx, ry, rw, rh = ART_RECTS[key]
            dh = ART_REL['dash' if key.startswith('dash') else key] * self.art_unit * sy
            dw = dh * rw / rh * sx
            img = self.art['hurt' if hurt else 'normal']
            img.opacify(max(0.0, min(1.0, alpha)))
            img.clip_composite_draw(rx, self.art_ah - ry - rh, rw, rh, tilt, flip, x,
                                    y - self.base_h / 2 + dh / 2 + lift, dw, dh)
            return
        spr, _imgs = self.sets['hurt' if hurt else 'normal']
        if facing in ('left', 'right'):
            key, flip = 'side', ('h' if facing == 'left' else '')
        else:
            key, flip = facing, ''
        img, l, b, w, h, sc = spr[key]
        dw, dh = w * sc * self.K * sx, h * sc * self.K * sy
        foot = y - self.base_h / 2
        cy = foot + dh / 2 + lift
        img.opacify(max(0.0, min(1.0, alpha)))
        img.clip_composite_draw(l, b, w, h, tilt, flip, x, cy, dw, dh)

    def draw(self):
        if self.alive or self.dying:
            ox, oy = self._off()
            a = 1.0
            jx = jy = 0.0
            hurt = False
            if self.dying:                                       # 쓰러지는 중: 떨리고 깜빡이다 사라짐
                jx, jy = random.uniform(-1, 1) * 8, random.uniform(-1, 1) * 8
                hurt = int(self.die_t * 16) % 2 == 0
                a = max(0.0, min(1.0, (DEATH_TIME - self.die_t) / 0.3))
            else:
                hurt = self.clock - self.hurt_clock < HURT_FACE_TIME
                if hurt:
                    jx, jy = random.uniform(-1, 1) * HURT_SHAKE, random.uniform(-1, 1) * HURT_SHAKE
                elif self.state in ('aim', 'dash_warn'):
                    jx, jy = random.uniform(-1, 1) * 1.5, random.uniform(-1, 1) * 1.5
                if self.state == 'intro':
                    a = min(1.0, self.t / SHADOW_INTRO)
            x, y = self._lx + ox + jx, self._ly + oy + jy        # 흔들림이 적용된 위치

            ph = self.phase
            pulse = 0.5 + 0.5 * math.sin(self.clock * (3 if ph == 0 else 5 if ph == 1 else 8))
            base = {0: 0.16, 1: 0.26, 2: 0.40}[ph]
            if self.state == 'intro':
                base, pulse = 0.5 * a, 1.0
            self.aura.opacify(max(0.0, min(1.0, (base + 0.18 * pulse) * (a if self.dying else 1.0))))
            s = self.base_w * 2.6 * (1 + 0.05 * pulse)
            self.aura.draw(x, y, s, s)

            shw = self.base_w * 0.9
            self.shadow.opacify(SHADOW_ALPHA * a)
            self.shadow.draw(x, y - self.base_h / 2 + shw * 0.35 * 0.2, shw, shw * 0.35)

            for gx, gy, gf, gtilt, gt in self.ghosts:            # 대쉬 잔상
                self._draw_at(gx + ox, gy + oy, gf, 0.0, gtilt, 1.1, 0.92,
                              alpha=0.45 * (1 - (self.clock - gt) / 0.2))

            for c in self.clones:                                # 분신: 반투명
                fade = 1.0
                if c['t'] < 0.4:
                    fade = c['t'] / 0.4
                elif c['t'] > SHADOW_CLONE_AIM:
                    fade = max(0.0, 1 - (c['t'] - SHADOW_CLONE_AIM) / 0.4)
                self._draw_at(c['x'] + ox, c['y'] + oy, c['face'], alpha=0.5 * fade)

            s_ = abs(math.sin(self.walk_phase))
            lift = s_ * BOUNCE_PX * self.walk_amp
            tilt = math.sin(self.walk_phase) * math.radians(TILT_DEG) * self.walk_amp
            sy = 1.0 + SQUASH * (s_ - 0.5) * 2 * self.walk_amp
            sx = 1.0 - SQUASH * (s_ - 0.5) * 2 * self.walk_amp * 0.7
            if self.state == 'dash':
                lift, tilt, sx, sy = 0.0, -self.dash_dir[0] * math.radians(15), 1.1, 0.92
            elif self.state == 'recover':
                k = min(1.0, self.t / 0.4)
                sx, sy = 1.08 - 0.08 * k, 0.94 + 0.06 * k
            elif self.state == 'aim':
                tilt = -math.cos(self.aim_ang) * math.radians(4)
            fr, ff = None, self.facing
            if self.art and self.state == 'dash':                # 대쉬: 달리는 그림이 빠르게 넘어감
                fr = 'dash%d' % (int(self.t * ART_DASH_FPS) % 12)
                ff = 'left' if self.dash_dir[0] < 0 else 'right'
            self._draw_at(x, y, ff, lift, tilt, sx, sy, alpha=a, hurt=hurt, frame=fr)

            if self.flash_t > 0:                                 # 발사 순간 번쩍
                f = self.flash_t / 0.15
                mx = x + math.cos(self.aim_ang) * SHADOW_MUZZLE
                my = y + math.sin(self.aim_ang) * SHADOW_MUZZLE
                self.glow.opacify(f)
                self.glow.draw(mx, my, 20 + 60 * f, 20 + 60 * f)

        bw, bx, by = 400, CANVAS_W / 2, CANVAS_H - 28
        self.bar_bg.draw(bx, by, bw + 6, 18)
        ratio = max(self.hp, 0) / self.max_hp
        if ratio > 0:
            self.bar_fg.draw(bx - bw / 2 + bw * ratio / 2, by, bw * ratio, 12)
