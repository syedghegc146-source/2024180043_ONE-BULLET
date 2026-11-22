"""10층 최종 보스: 암흑마법사.
dungeon 폴더에 아래 그림 파일을 넣어 두면 자동으로 사용합니다 (없으면 기존 그림자 보스가 나옵니다).
  darkmage_sheet.png  캐릭터 시트 (흰 배경 가능, 5줄: 대기 / 걷기 / 시전 / 후딜 / 쓰러짐)
  darkmage_fx.png     이펙트 시트 (투명 배경, 4줄: 마법진 / 유성 / 폭발 / 잔상)
  darkmage_base.png   서 있는 그림 한 장 (선택 - 시트가 없을 때만 사용)
수치는 이 파일 위쪽 DM_* 에서 바꾸세요."""
from pico2d import *
from PIL import Image
import numpy as np
import json
import math
import os
import random
from collections import deque

from config import *
from boss import make_orb
from dg_config import *

# =============== 바꿀 수 있는 수치 ===============
DM_HP = 30                       # 보통 난이도 체력 (쉬움 x0.7, 어려움 x1.2)
DM_HP_MULT = {'easy': 0.7, 'normal': 1.0, 'hard': 1.2}
DM_HEIGHT = 200                  # 보스 키(px). 크게 하려면 숫자를 올리세요
DM_INTRO = 1.8                   # 등장 연출 시간(초)
DM_WALK = 110                    # 걷는 속도
DM_KEEP = (250, 380)             # 플레이어와 유지하려는 거리
DM_CD = [1.7, 1.4, 1.1]          # 단계별 공격 간격(초). 클수록 쉬움
DM_CAST = [0.80, 0.70, 0.60]     # 단계별 시전 시간(초). 길수록 예고가 길어 쉬움
DM_ORB_SPEED = 300               # 마법탄 속도
DM_ORB_SIZE = 30                 # 마법탄 그림 크기(px)
DM_FAN_N = [5, 7, 9]             # 단계별 부채꼴 탄 개수
DM_FAN_STEP = 0.19               # 부채꼴 탄 사이 각도(라디안)
DM_RAIN_N = [3, 5, 7]            # 단계별 유성 개수
DM_RAIN_WARN = [1.15, 1.0, 0.9]  # 유성 경고 시간(초). 길수록 쉬움
DM_RAIN_R = 64                   # 유성 폭발 반경(px)
DM_FALL_T = 0.38                 # 유성이 떨어지는 시간
DM_BOOM_T = 0.5                  # 폭발이 지속되는 시간 (앞쪽 0.28초만 피해)
DM_SPIRAL_T = 2.2                # 나선 탄막 지속 시간
DM_SPIRAL_ARMS = [2, 2, 3]
DM_RING_N = 18                   # 원형 탄막 탄 개수
DM_TP_DIST = (270, 340)          # 순간이동 후 플레이어와의 거리

# 시트 줄 이름 (몇 번째 줄이 무슨 동작인지)
ROWS = ['idle', 'walk', 'cast', 'recover', 'die']
FX_ROWS = ['warn', 'meteor', 'boom', 'after']
# 이펙트 시트의 글자 상자(지울 부분)
FX_LABEL_BOXES = [(15, 60, 300, 125), (775, 60, 960, 125), (15, 545, 215, 615), (775, 545, 1045, 615)]
FX_QUADS = {'warn': (0, 0, 780, 520), 'meteor': (780, 0, 1536, 520),
            'boom': (0, 520, 780, 1024), 'after': (780, 520, 1536, 1024)}

ART_SHEET = DP('darkmage_sheet.png')
ART_FX = DP('darkmage_fx.png')
ART_BASE = DP('darkmage_base.png')
OUT_SHEET = OUT('dg_dm_sheet.png')
OUT_HURT = OUT('dg_dm_sheet_hurt.png')
OUT_FX = OUT('dg_dm_fx.png')
OUT_ORB = OUT('dg_dm_orb.png')
OUT_AURA = OUT('dg_dm_aura.png')
OUT_META = OUT('dg_dm_meta.json')


# =============== 그림 준비 (창 열기 전에 실행) ===============
def _runs(v, gap):
    r, s, last = [], None, None
    for i, x in enumerate(v):
        if x:
            if s is None:
                s = i
            last = i
        elif s is not None and i - last > gap:
            r.append((s, last))
            s = None
    if s is not None:
        r.append((s, last))
    return r


def _flood_bg(rgb, thr=238):
    """가장자리와 이어진 거의 흰색 부분 = 배경"""
    h, w = rgb.shape[:2]
    cand = rgb.min(axis=2) >= thr
    bg = np.zeros((h, w), bool)
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if cand[y, x] and not bg[y, x]:
                bg[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if cand[y, x] and not bg[y, x]:
                bg[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and cand[ny, nx] and not bg[ny, nx]:
                bg[ny, nx] = True
                dq.append((ny, nx))
    return bg


def _grow(m):
    """True 영역을 한 칸 넓힘"""
    o = m.copy()
    o[1:, :] |= m[:-1, :]
    o[:-1, :] |= m[1:, :]
    o[:, 1:] |= m[:, :-1]
    o[:, :-1] |= m[:, 1:]
    return o


def _white_to_alpha(path):
    """흰 배경 그림 -> 투명 배경 (RGBA numpy)"""
    im = np.array(Image.open(path).convert('RGB'))
    bg = _flood_bg(im)
    mn = im.min(axis=2)
    for thr in (215, 190, 170, 150, 135, 120):            # 배경과 맞닿은 밝은 테두리를 안쪽으로 조금씩 지움
        bg = bg | (_grow(bg) & ~bg & (mn > thr))
    a = np.dstack([im, np.where(bg, 0, 255).astype(np.uint8)])
    edge = _grow(bg) & ~bg                                # 남은 가장자리 한 겹은 어둡게 (흰 선 방지)
    a[:, :, :3][edge] = (a[:, :, :3][edge] * 0.45).astype(np.uint8)
    return a


def _char_frames(a):
    """캐릭터 시트에서 줄, 프레임 위치를 찾는다. 반환: {줄이름: [[x, y, w, h, 기준x, 바닥y], ...]}"""
    rgb = a[:, :, :3].astype(int)
    white = (rgb.min(axis=2) >= 246) & ((rgb.max(axis=2) - rgb.min(axis=2)) < 14)
    al = a[:, :, 3] > 0
    bands = _runs(al.any(axis=1), 10)
    cast_band = bands[2] if len(bands) > 2 else (0, -1)
    for i, (y0, y1) in enumerate(bands):                  # 시전 줄 말고는 몸 사이에 낀 흰 점도 지움
        if i != 2:
            a[y0:y1 + 1, :, 3][white[y0:y1 + 1, :]] = 0
    al = a[:, :, 3] > 0
    out = {}
    for name, (y0, y1) in zip(ROWS, bands):
        cols = _runs(al[y0:y1 + 1].any(axis=0), 4)
        rects = []
        for x0, x1 in cols:
            sub = al[y0:y1 + 1, x0:x1 + 1]
            ys = np.where(sub.any(axis=1))[0]
            rects.append([x0, y0 + int(ys.min()), x1 - x0 + 1, int(ys.max() - ys.min() + 1)])
        # 기준 위치: 칸(192px)의 가운데와 줄에서 가장 낮은 바닥
        base = max(r[1] + r[3] for r in rects)
        for r in rects:
            r.append(int(((r[0] + r[2] / 2) // 192) * 192 + 96))
            r.append(int(base))
        out[name] = rects
    return out


def _fx_frames(a):
    al = a[:, :, 3].copy()
    for x0, y0, x1, y1 in FX_LABEL_BOXES:
        a[y0:y1, x0:x1, 3] = 0
        al[y0:y1, x0:x1] = 0
    out = {}
    for name, (x0, y0, x1, y1) in FX_QUADS.items():
        m = al[y0:y1, x0:x1] > 40
        cr = []
        for gap in (6, 10, 16, 24, 40):
            cr = _runs(m.any(axis=0), gap)
            if len(cr) == 4:
                break
        rects = []
        for a0, a1 in cr:
            sub = m[:, a0:a1 + 1]
            ys = np.where(sub.any(axis=1))[0]
            rects.append([x0 + a0, y0 + int(ys.min()), a1 - a0 + 1, int(ys.max() - ys.min() + 1)])
        out[name] = rects
    return out


def _aura(path, size=256):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    d = np.hypot(xx - c, yy - c) / c
    out = np.zeros((size, size, 4), np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = 150, 50, 255
    out[:, :, 3] = (np.clip(1 - d, 0, 1) ** 1.8 * 255).astype(np.uint8)
    Image.fromarray(out).save(path)


def prepare_darkmage():
    """암흑마법사 그림을 준비한다. 돌려주는 값: {'ok': 성공 여부}. 원본이 바뀌면 자동으로 다시 만든다"""
    srcs = [ART_SHEET, ART_FX, ART_BASE]
    sig = ['v2']
    for p in srcs:
        try:
            st = os.stat(p)
            sig.append(f'{p}|{st.st_size}|{int(st.st_mtime)}')
        except OSError:
            sig.append(f'{p}|-')
    use_sheet = os.path.exists(ART_SHEET)
    if not os.path.exists(ART_FX) or not (use_sheet or os.path.exists(ART_BASE)):
        return {'ok': False}
    outs = [OUT_SHEET, OUT_HURT, OUT_FX, OUT_ORB, OUT_AURA, OUT_META]
    try:
        with open(OUT_META, 'r') as f:
            old = json.load(f)
    except Exception:
        old = None
    if old is not None and old.get('sig') == sig and all(os.path.exists(p) for p in outs):
        return {'ok': True}
    try:
        a = _white_to_alpha(ART_SHEET if use_sheet else ART_BASE)
        if use_sheet:
            frames = _char_frames(a)
        else:                                             # 한 장짜리: 모든 동작에 같은 그림을 씀
            al = a[:, :, 3] > 0
            ys, xs = np.where(al)
            r = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
            r += [r[0] + r[2] // 2, r[1] + r[3]]
            frames = {k: [list(r)] for k in ROWS}
        Image.fromarray(a).save(OUT_SHEET)
        hurt = a.copy()
        hurt[:, :, :3] = np.clip(hurt[:, :, :3] * 0.3 + np.array([235, 205, 255], np.float32) * 0.7, 0, 255)
        Image.fromarray(hurt.astype(np.uint8)).save(OUT_HURT)
        fx = np.array(Image.open(ART_FX).convert('RGBA'))
        fx[:, :, 3][fx[:, :, 3] < 30] = 0                 # 희미한 안개 지우기
        fxf = _fx_frames(fx)
        Image.fromarray(fx).save(OUT_FX)
        make_orb(OUT_ORB, (250, 230, 255), (150, 60, 255), 64)
        _aura(OUT_AURA)
        with open(OUT_META, 'w') as f:
            json.dump({'sig': sig, 'frames': frames, 'fx': fxf}, f)
        return {'ok': True}
    except Exception as e:
        print(f'[암흑마법사] 그림 준비 실패: {e}')
        return {'ok': False}


# =============== 공용 그림 ===============
class _Art:
    loaded = False

    @classmethod
    def load(cls):
        if cls.loaded:
            return
        with open(OUT_META, 'r') as f:
            m = json.load(f)
        cls.frames, cls.fx_rects = m['frames'], m['fx']
        cls.sheet = {'n': load_image(OUT_SHEET), 'h': load_image(OUT_HURT)}
        cls.fx = load_image(OUT_FX)
        cls.orb = load_image(OUT_ORB)
        cls.aura = load_image(OUT_AURA)
        cls.shadow = load_image(SHADOW)
        cls.bar_bg, cls.bar_fg = load_image(BAR_BG), load_image(BAR_FG)
        idle = cls.frames['idle'][0]
        cls.scale = DM_HEIGHT / idle[3]                   # 시트 그림 -> 화면 크기
        cls.loaded = True

    @classmethod
    def fx_draw(cls, row, i, x, y, k, anchor='bottom', alpha=1.0):
        """이펙트 그림 한 장. anchor: 'bottom'이면 (x, y)가 그림 아래 가운데, 'center'면 가운데"""
        rects = cls.fx_rects[row]
        rx, ry, rw, rh = rects[max(0, min(len(rects) - 1, i))]
        dw, dh = rw * k, rh * k
        cy = y + dh / 2 if anchor == 'bottom' else y
        cls.fx.opacify(max(0.0, min(1.0, alpha)))
        cls.fx.clip_composite_draw(rx, cls.fx.h - ry - rh, rw, rh, 0, '', x, cy, dw, dh)


# =============== 탄 ===============
class DMOrb:
    """보라 마법탄 (boss_bullets에 넣는 탄과 같은 방식: update / draw / x / y / alive)"""

    def __init__(self, x, y, ang, speed, turn=0.0, homing_time=0.0):
        self.x, self.y = x, y
        self.ang = ang
        self.speed = speed
        self.turn = turn
        self.homing_time = homing_time
        self.alive = True
        self.age = 0.0

    def update(self, dt, target=None):
        self.age += dt
        if self.turn and target is not None and self.age < self.homing_time:
            want = math.atan2(target.y - self.y, target.x - self.x)
            diff = (want - self.ang + math.pi) % (2 * math.pi) - math.pi
            step = self.turn * dt
            self.ang += max(-step, min(step, diff))
        self.x += math.cos(self.ang) * self.speed * dt
        self.y += math.sin(self.ang) * self.speed * dt
        if not (-50 < self.x < CANVAS_W + 50 and -50 < self.y < CANVAS_H + 50):
            self.alive = False

    def draw(self, imgs=None, metas=None):
        _Art.load()
        pulse = 1 + 0.12 * math.sin(self.age * 18)
        s = DM_ORB_SIZE
        _Art.orb.opacify(0.45)
        _Art.orb.draw(self.x, self.y, s * 2.0 * pulse, s * 2.0 * pulse)
        _Art.orb.opacify(1.0)
        _Art.orb.draw(self.x, self.y, s, s)


class DMMeteor:
    """유성: 바닥에 마법진(경고) -> 위에서 낙하 -> 폭발(잠깐만 피해) -> 잔상.
    피해를 주는 순간에만 x, y를 플레이어 위치로 옮겨서 main의 피격 판정에 걸리게 한다"""

    def __init__(self, tx, ty, warn, delay=0.0):
        self.tx, self.ty = tx, ty
        self.warn = warn
        self.delay = delay
        self.t = -delay
        self.x = self.y = -9999.0
        self.alive = True
        self.sound = False

    def update(self, dt, target=None):
        self.t += dt
        self.x = self.y = -9999.0
        end = self.warn + DM_FALL_T + DM_BOOM_T + 0.5
        if self.t >= end:
            self.alive = False
            return
        boom_t = self.t - self.warn - DM_FALL_T
        if 0 <= boom_t < 0.28 and target is not None:
            if not self.sound:
                self.sound = True
                Sound.play('explode')
            hx, hy = target.x, target.y - target.base_h * HIT_OFFSET
            if math.hypot(hx - self.tx, hy - self.ty) < DM_RAIN_R:
                self.x, self.y = hx, hy

    def draw(self, imgs=None, metas=None):
        if self.t < 0:
            return
        _Art.load()
        R = DM_RAIN_R
        t, W = self.t, self.warn
        kw = 2.3 * R / 180.0                                  # 마법진 그림 크기
        if t < W + DM_FALL_T:
            f = min(1.0, t / W)
            pulse = 0.75 + 0.25 * math.sin(t * 16)
            _Art.fx_draw('warn', min(3, int(f * 4)), self.tx, self.ty, kw, 'center', pulse)
        if W <= t < W + DM_FALL_T:                          # 낙하: 위에서 빠르게 내려옴
            p = (t - W) / DM_FALL_T
            y = self.ty + 30 + (1 - p * p) * 520
            _Art.fx_draw('meteor', min(3, int(p * 4)), self.tx, y, 0.34, 'bottom')
        elif t >= W + DM_FALL_T:
            b = t - W - DM_FALL_T
            if b < DM_BOOM_T:
                _Art.fx_draw('boom', min(3, int(b / DM_BOOM_T * 4)), self.tx, self.ty - 0.4 * R, 2.4 * R / 170.0, 'bottom')
            else:
                a = (b - DM_BOOM_T) / 0.5
                _Art.fx_draw('after', min(3, int(a * 4)), self.tx, self.ty - 0.4 * R, 2.4 * R / 170.0, 'bottom', 1 - a)


# =============== 보스 ===============
def _seg_free(x, y):
    return arena_d(x, y) < 0.86 and SHADOW_MIN_Y <= y <= SHADOW_MAX_Y


class DarkMage:
    def __init__(self, diff):
        _Art.load()
        self.max_hp = max(1, int(DM_HP * DM_HP_MULT.get(diff['id'], 1.0)))
        self.cd_mult = diff['cd']
        self.spd_mult = diff['speed']
        self.H = DM_HEIGHT
        self.radius = 44.0
        self.x, self.y = CANVAS_W / 2, SHADOW_MAX_Y - 30
        self._lx, self._ly = self.x, self.y
        self.hp = self.max_hp
        self.alive = True
        self.dying = False
        self.die_t = 0.0
        self.clock = 0.0
        self.hurt_clock = -10.0
        self.state, self.t = 'intro', 0.0
        self.flip = False                                     # True면 왼쪽을 봄
        self.vel = (0.0, 0.0)
        self.side = random.choice((-1, 1))
        self.side_t = random.uniform(1.0, 2.2)
        self.next_attack = DM_INTRO + 0.8
        self.last = None
        self.atk = None
        self.fired = False
        self.alpha = 0.0
        self.puffs = []                                       # 순간이동 연기 [x, y, 시간]
        self.spiral_a = 0.0
        self.spiral_acc = 0.0
        self.player = None
        self.bb = None
        self.prev_phase = 0
        self.phase_event = None
        self.laser_fired = False                              # 기존 보스와 모양을 맞춘 것 (쓰지 않음)
        self.lasers = []
        self.slam = False
        self.tp_shots = 0

    @property
    def phase(self):
        r = self.hp / self.max_hp
        return 0 if r > 0.66 else (1 if r > 0.33 else 2)

    def _off(self):
        return self.x - self._lx, self.y - self._ly

    def _to(self, st):
        self.state, self.t = st, 0.0
        self.fired = False

    def cooldown(self):
        return DM_CD[self.phase] * self.cd_mult

    def _hit_center(self):
        p = self.player
        return p.x, p.y - p.base_h * HIT_OFFSET

    def _ang_to_player(self, lead=0.0):
        hx, hy = self._hit_center()
        return math.atan2(hy - self.y, hx - self.x)

    def _hand(self):
        """손(마법구가 나오는 곳)의 위치"""
        sgn = -1 if self.flip else 1
        return self.x + sgn * 70, self.y + 10

    def _orb(self, x, y, ang, speed=None, **kw):
        self.bb.append(DMOrb(x, y, ang, (speed or DM_ORB_SPEED) * self.spd_mult, **kw))

    # ---------- 공격 고르기 ----------
    def _attack(self):
        ph = self.phase
        pool = {0: [('orb', 2), ('rain', 1)],
                1: [('orb', 2), ('rain', 2), ('teleport', 1), ('spiral', 1)],
                2: [('orb', 1), ('rain', 2), ('teleport', 2), ('spiral', 1), ('ring', 1)]}[ph]
        allk = [k for k, w in pool for _ in range(w)]
        k = random.choice([x for x in allk if x != self.last] or allk)
        self.last = k
        self.atk = k
        self.flip = self.player.x < self.x
        if k == 'rain':
            self._to('summon')
        elif k == 'teleport':
            self._to('vanish')
            Sound.play('warning')
        else:
            self._to('cast')
            Sound.play('warning')

    def _fire_cast(self):
        ph = self.phase
        hx, hy = self._hand()
        ang = math.atan2(self._hit_center()[1] - hy, self._hit_center()[0] - hx)
        if self.atk == 'orb':
            n = DM_FAN_N[ph]
            for i in range(n):
                self._orb(hx, hy, ang + (i - (n - 1) / 2) * DM_FAN_STEP)
            if ph == 2:                                       # 3단계: 천천히 따라가는 탄 2개
                for s in (-0.5, 0.5):
                    self._orb(hx, hy, ang + s, speed=190, turn=1.5, homing_time=2.4)
            Sound.play('shot')
            self._to('recover')
        elif self.atk == 'ring':
            for k in range(DM_RING_N):
                self._orb(self.x, self.y, k * 2 * math.pi / DM_RING_N, speed=230)
            Sound.play('shot')
            self.tp_shots = 1                                 # 반 칸 어긋난 두 번째 고리
            self.ring_t = 0.55
            self._to('recover')
        elif self.atk == 'spiral':
            self.spiral_a = ang
            self.spiral_acc = 0.0
            self._to('spiral')
        elif self.atk == 'burst':                             # 순간이동 직후 조준탄 3발
            for s in (-0.13, 0.0, 0.13):
                self._orb(hx, hy, ang + s, speed=DM_ORB_SPEED * 1.35)
            Sound.play('shot')
            self._to('recover')

    def _summon(self):
        p, ph = self.player, self.phase
        n = DM_RAIN_N[ph]
        hx, hy = self._hit_center()
        pos = [(hx + p.x * 0.0, hy)]                           # 첫 유성은 플레이어 발밑
        tries = 0
        while len(pos) < n and tries < 200:
            tries += 1
            a = random.uniform(0, 2 * math.pi)
            r = random.uniform(80, 280)
            cx, cy = hx + math.cos(a) * r, hy + math.sin(a) * r
            cx, cy = clamp_arena(cx, cy, 40)
            if all(math.hypot(cx - qx, cy - qy) > DM_RAIN_R * 1.7 for qx, qy in pos):
                pos.append((cx, cy))
        for i, (cx, cy) in enumerate(pos):
            self.bb.append(DMMeteor(cx, cy, DM_RAIN_WARN[ph], delay=i * 0.22))
        Sound.play('warning')

    # ---------- 갱신 ----------
    def update(self, dt, player, boss_bullets):
        self.clock += dt
        self.player, self.bb = player, boss_bullets
        if self.alive and self.phase != self.prev_phase:       # 단계가 바뀌면 탄을 지우고 잠깐 쉼
            self.prev_phase = self.phase
            self.phase_event = self.phase
            Sound.play('phase')
            self.bb.clear()
            self.vel = (0.0, 0.0)
            self.alpha = 1.0
            self._to('move')
            self.next_attack = self.clock + 1.6

        if not self.alive:
            if self.dying:
                self.die_t += dt
            self._lx, self._ly = self.x, self.y
            return

        self.t += dt
        self.puffs = [q for q in self.puffs if self.clock - q[2] < 0.5]
        st = self.state
        if st == 'intro':
            self.alpha = min(1.0, self.t / DM_INTRO)
            if self.t >= DM_INTRO:
                self._to('move')
        elif st == 'move':
            self.alpha = 1.0
            self._move(dt)
            if self.clock >= self.next_attack:
                self._attack()
        elif st == 'cast':
            self.vel = (self.vel[0] * 0.8, self.vel[1] * 0.8)
            self.flip = player.x < self.x
            if self.t >= DM_CAST[self.phase] and not self.fired:
                self.fired = True
                self._fire_cast()
        elif st == 'summon':
            self.vel = (self.vel[0] * 0.8, self.vel[1] * 0.8)
            if not self.fired and self.t >= 0.15:
                self.fired = True
                self._summon()
            if self.t >= 0.8:
                self._to('recover')
        elif st == 'spiral':
            arms = DM_SPIRAL_ARMS[self.phase]
            self.spiral_a += dt * 4.2
            self.spiral_acc += dt
            while self.spiral_acc >= 0.09:
                self.spiral_acc -= 0.09
                for k in range(arms):
                    self._orb(self.x, self.y + 10, self.spiral_a + k * 2 * math.pi / arms, speed=235)
            if self.t >= DM_SPIRAL_T:
                self._to('recover')
        elif st == 'vanish':
            self.alpha = max(0.0, 1 - self.t / 0.4)
            if self.t < 0.05 and not self.puffs:
                self.puffs.append([self.x, self.y - self.H / 2, self.clock])
            if self.t >= 0.4:
                self._teleport()
                self._to('appear')
        elif st == 'appear':
            self.alpha = min(1.0, self.t / 0.4)
            if self.t >= 0.4:
                self.alpha = 1.0
                self.atk = 'burst' if self.phase >= 1 else None
                if self.atk:
                    self._to('cast')
                    self.t = DM_CAST[self.phase] - 0.25          # 짧게 예고하고 바로 발사
                else:
                    self._to('recover')
        elif st == 'recover':
            self.alpha = 1.0
            if getattr(self, 'ring_t', 0) > 0:
                self.ring_t -= dt
                if self.ring_t <= 0:
                    off = math.pi / DM_RING_N
                    for k in range(DM_RING_N):
                        self._orb(self.x, self.y, off + k * 2 * math.pi / DM_RING_N, speed=230)
                    Sound.play('shot')
            if self.t >= 0.55:
                self._to('move')
                self.next_attack = self.clock + self.cooldown()
        self._lx, self._ly = self.x, self.y

    def _teleport(self):
        p = self.player
        self.puffs.append([self.x, self.y - self.H / 2, self.clock])
        for _ in range(40):
            a = random.uniform(0, 2 * math.pi)
            r = random.uniform(*DM_TP_DIST)
            cx, cy = p.x + math.cos(a) * r, p.y + math.sin(a) * r
            if _seg_free(cx, cy):
                break
        else:
            cx, cy = clamp_arena(self.x, self.y, 40)
            cy = max(SHADOW_MIN_Y, min(SHADOW_MAX_Y, cy))
        self.x, self.y = cx, cy
        self._lx, self._ly = cx, cy
        self.puffs.append([cx, cy - self.H / 2, self.clock])
        self.flip = p.x < cx

    def _move(self, dt):
        p = self.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        lo, hi = DM_KEEP
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
        sp = DM_WALK * self.spd_mult * (1 + 0.12 * self.phase)
        tvx, tvy = vx * sp, vy * sp
        if self.y >= SHADOW_MAX_Y - 10 and tvy > 0:
            tvy = 0.0
        if self.y <= SHADOW_MIN_Y + 10 and tvy < 0:
            tvy = 0.0
        k = min(1.0, 5 * dt)
        self.vel = (self.vel[0] + (tvx - self.vel[0]) * k, self.vel[1] + (tvy - self.vel[1]) * k)
        self.x += self.vel[0] * dt
        self.y += self.vel[1] * dt
        self.x, self.y = clamp_arena(self.x, self.y, 30)
        self.y = max(SHADOW_MIN_Y, min(SHADOW_MAX_Y, self.y))
        if abs(self.vel[0]) > 12:
            self.flip = self.vel[0] < 0

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

    def draw_lasers(self, *a):
        pass

    def draw_warning_hud(self):
        pass

    def draw_warning(self):
        pass

    # ---------- 그리기 ----------
    def _frame_for(self):
        """지금 상태에 맞는 (줄 이름, 프레임 번호, 뒤집기 기본값)"""
        F = _Art.frames
        st = self.state
        if self.dying:
            n = len(F['die'])
            return 'die', min(n - 1, int(self.die_t / (DEATH_TIME * 0.85) * n)), False
        if st in ('cast', 'summon', 'spiral') or (st == 'appear' and self.atk == 'burst'):
            if st == 'summon':                                # 손을 높이 듦
                return 'recover', 0 if self.t < 0.4 else 1, False
            n = len(F['cast'])
            dur = DM_CAST[self.phase]
            if st == 'spiral':
                return 'cast', n - 1 - int(self.t * 8) % 2, True
            return 'cast', min(n - 1, int(self.t / dur * n)), True
        if st == 'recover':
            n = len(F['recover'])
            if self.atk == 'rain':
                return 'recover', min(n - 1, 2 + int(self.t / 0.55 * (n - 2))), False
            return 'recover', min(n - 1, 2 + int(self.t / 0.55 * (n - 2))), False
        if st == 'move' and math.hypot(*self.vel) > 28:
            return 'walk', int(self.clock * 10) % len(F['walk']), False
        return 'idle', int(self.clock * 6) % 5, False

    def _draw_sprite(self, x, foot, row, i, flip, alpha, hurt, sx=1.0, sy=1.0):
        rx, ry, rw, rh, cx, base = _Art.frames[row][i]
        k = _Art.scale
        img = _Art.sheet['h' if hurt else 'n']
        sgn = -1 if flip else 1
        dx = sgn * (rx + rw / 2 - cx) * k * sx
        dy = (base - (ry + rh)) * k * sy
        img.opacify(max(0.0, min(1.0, alpha)))
        img.clip_composite_draw(rx, img.h - ry - rh, rw, rh, 0, 'h' if flip else '', x + dx,
                                foot + dy + rh * k * sy / 2, rw * k * sx, rh * k * sy)

    def draw(self):
        if self.alive or self.dying:
            ox, oy = self._off()
            jx = jy = 0.0
            a = max(self.alpha, 0.0) if self.alive else 1.0
            hurt = False
            if self.dying:
                a = max(0.0, min(1.0, (DEATH_TIME - self.die_t) / 0.3))
            else:
                hurt = self.clock - self.hurt_clock < HURT_FACE_TIME
                if hurt:
                    jx, jy = random.uniform(-1, 1) * HURT_SHAKE, random.uniform(-1, 1) * HURT_SHAKE
                elif self.state in ('cast', 'summon'):
                    jx, jy = random.uniform(-1, 1) * 1.2, random.uniform(-1, 1) * 1.2
            x, y = self._lx + ox + jx, self._ly + oy + jy
            row, i, cast_default = self._frame_for()
            flip = self.flip
            if row == 'walk':                                 # 걷기 그림은 왼쪽을 보고 있음
                flip = (self.vel[0] > 0)
            elif row == 'cast':                               # 시전 그림은 오른쪽을 보고 있음
                flip = self.flip
            elif row in ('idle', 'recover', 'die'):
                flip = False
            bob = 0.0
            if row == 'idle' or (self.state == 'move' and row == 'walk'):
                bob = math.sin(self.clock * 2.4) * 6
            foot = y - self.H / 2 + bob + (0 if self.alive else 0)

            ph = self.phase
            pulse = 0.5 + 0.5 * math.sin(self.clock * (3 if ph == 0 else 5 if ph == 1 else 8))
            base = {0: 0.14, 1: 0.22, 2: 0.34}[ph]
            _Art.aura.opacify(max(0.0, min(1.0, (base + 0.16 * pulse) * (a if not self.dying else 0.5))))
            sa = 330 * (1 + 0.05 * pulse)
            _Art.aura.draw(x, y, sa, sa)

            shw = self.H * 0.7
            _Art.shadow.opacify(SHADOW_ALPHA * a)
            _Art.shadow.draw(x, y - self.H / 2 + 6, shw, shw * 0.35)

            self._draw_sprite(x, foot, row, i, flip, a, hurt)

            if self.state in ('cast', 'summon') and self.alive:      # 시전 중 손에 모이는 빛
                hx, hy = self._hand()
                f = min(1.0, self.t / max(0.1, DM_CAST[ph]))
                _Art.orb.opacify(0.5 + 0.4 * f)
                _Art.orb.draw(hx + ox, hy + oy, 18 + 54 * f, 18 + 54 * f)

            for px, py, pt in self.puffs:                      # 순간이동 연기
                f = (self.clock - pt) / 0.5
                _Art.fx_draw('after', min(3, int(f * 4)), px + ox, py + oy, 0.85, 'bottom', 1 - f * 0.5)

        bw, bx, by = 400, CANVAS_W / 2, CANVAS_H - 28
        _Art.bar_bg.draw(bx, by, bw + 6, 18)
        ratio = max(self.hp, 0) / self.max_hp
        if ratio > 0:
            _Art.bar_fg.draw(bx - bw / 2 + bw * ratio / 2, by, bw * ratio, 12)