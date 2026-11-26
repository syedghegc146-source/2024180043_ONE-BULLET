from pico2d import *
from PIL import Image, ImageDraw, ImageFilter
from types import SimpleNamespace
import numpy as np
import math
import os
import random
import time

from config import *
from player import Bullet
from boss import label_components, make_orb
from dg_config import *

BG_SAT = 40          # 체크무늬(채도가 낮은 밝은 색)로 보는 기준
BG_MIN = 150
ENEMY_DEATH_TIME = 0.4     # 몬스터가 쓰러지는 연출 시간(초)

ENEMY_SRC = {'slime': DP('slime.png'), 'gunner': DP('gunner.png'),
             'shielder': DP('shielder.png'), 'shielder_block': DP('shielder_block.png'),
             'spider': DP('spider.png'), 'thief': DP('thief.png'),
             'bomber': DP('bomber.png'), 'bomber_alert': DP('bomber_alert.png')}
# 사수 시트: 가로 6칸 x 세로 3줄 (1줄 걷기 / 2줄 조준 / 3줄 발사). 파일이 없으면 예전 그림을 그대로 씀
GUNNER_SHEET = DP('gunner_sheet.png')
GUNNER_SHEET_WHITE = OUT('dg_gunner_sheet_white.png')
GS_COLS, GS_ROWS = 6, 3
GS_CELL_W, GS_CELL_H = 300, 250      # 한 칸의 크기(px)
GS_CHAR_H = 212                      # 한 칸 안에서 캐릭터 키 (이 높이가 화면의 ENEMY_H가 됨)
GS_FOOT_Y = 240                      # 칸 위에서부터 발바닥까지 (px)
GS_ANCHOR_X = 135                    # 칸 왼쪽에서부터 몸 중심까지 (px)
GS_WALK_FPS = 9                      # 걷는 그림이 넘어가는 속도 (초당 칸 수)
ENEMY_OUT = {k: OUT('dg_%s.png' % k) for k in ENEMY_SRC}
ENEMY_WHITE = {k: OUT('dg_%s_white.png' % k) for k in ENEMY_SRC}     # 하얗게 번쩍일 때 쓰는 그림


# =============== 이미지 준비 (창 열기 전에 실행) ===============
def prepare_sprite(src, dst):
    """체크무늬 배경과 워터마크를 지우고 캐릭터만 남겨서 dst에 저장. (w, h) 또는 None"""
    if not os.path.exists(src):
        return None
    if fresh(src, dst):
        with Image.open(dst) as im:
            return im.size
    try:
        img = Image.open(src).convert('RGB')
        W, H = img.size
        sc = min(1.0, 384 / max(W, H))
        if sc < 1.0:
            img = img.resize((max(1, int(W * sc)), max(1, int(H * sc))), Image.LANCZOS)
        rgb = np.array(img)
        mx = rgb.max(axis=2).astype(np.int16)
        mn = rgb.min(axis=2).astype(np.int16)
        sat = mx - mn
        black_bg = int(rgb[0, 0].max()) < 45 and int(rgb[-1, -1].max()) < 45
        cand = (mx < 50) if black_bg else ((sat < BG_SAT) & (mn > BG_MIN))

        lab, n = label_components(cand)
        if n == 0:
            return None
        edge = np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))
        edge = edge[edge > 0]
        bg = np.isin(lab, edge)                    # 가장자리와 이어진 밝은 부분만 배경
        if not black_bg:
            ring = np.array(Image.fromarray((bg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
            bg = bg | (ring & (sat < 70) & (mn > 110))
        fg = ~bg

        lab2, n2 = label_components(fg)            # 가장 큰 덩어리만
        if n2 == 0:
            return None
        cnt = np.bincount(lab2.ravel())
        cnt[0] = 0
        fg = lab2 == int(cnt.argmax())

        out = Image.fromarray(np.dstack([rgb, (fg * 255).astype(np.uint8)]))
        box = out.getchannel('A').getbbox()
        if box:
            out = out.crop(box)
        s2 = min(1.0, 256 / max(out.size))
        if s2 < 1.0:
            out = out.resize((max(1, int(out.size[0] * s2)), max(1, int(out.size[1] * s2))), Image.LANCZOS)
        out.save(dst)
        return out.size
    except Exception as e:
        print(f'[던전] {src} 처리 실패: {e}')
        return None


def make_fallback(dst, kind):
    """이미지가 없을 때 대신 쓰는 임시 그림"""
    S = 160
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    colors = {'slime': (70, 200, 150), 'gunner': (150, 90, 200),
              'shielder': (130, 140, 160), 'shielder_block': (110, 170, 230),
              'spider': (90, 60, 120), 'thief': (95, 120, 95),
              'bomber': (205, 75, 65), 'bomber_alert': (255, 150, 40)}
    ink = (20, 10, 30, 255)
    d.ellipse((14, 22, S - 14, S - 14), fill=colors[kind] + (255,), outline=ink, width=6)
    d.ellipse((46, 60, 70, 92), fill=(255, 255, 255, 255))
    d.ellipse((90, 60, 114, 92), fill=(255, 255, 255, 255))
    d.ellipse((54, 70, 66, 88), fill=ink)
    d.ellipse((98, 70, 110, 88), fill=ink)
    if kind == 'gunner':
        d.rectangle((0, 86, 60, 112), fill=(90, 90, 100, 255), outline=ink, width=4)
    if kind == 'shielder':
        d.chord((0, 30, 64, 130), 90, 270, fill=(200, 200, 220, 255), outline=ink, width=4)
    if kind == 'shielder_block':
        d.chord((0, 14, 80, 146), 90, 270, fill=(150, 210, 255, 255), outline=ink, width=4)
    if kind == 'spider':
        for yy in (60, 80, 100, 120):
            d.line((14, yy, -6, yy + 14), fill=ink, width=5)
            d.line((S - 14, yy, S + 6, yy + 14), fill=ink, width=5)
    if kind == 'thief':
        d.ellipse((96, 96, 150, 150), fill=(150, 110, 60, 255), outline=ink, width=4)
    if kind in ('bomber', 'bomber_alert'):
        d.line((S // 2, 24, S // 2 + 10, 6), fill=ink, width=5)
        d.ellipse((S // 2 + 4, 0, S // 2 + 18, 14), fill=(255, 230, 80, 255))
    img.save(dst)
    return img.size


def make_white(src, dst):
    """그림의 모양은 그대로 두고 색만 전부 하얗게 만든 그림 (번쩍임 효과용)"""
    im = Image.open(src).convert('RGBA')
    w = Image.new('RGBA', im.size, (255, 255, 255, 255))
    w.putalpha(im.getchannel('A'))
    w.save(dst)


def prepare_enemy_images():
    sizes = {}
    for k in ENEMY_SRC:
        res = prepare_sprite(ENEMY_SRC[k], ENEMY_OUT[k])
        if res is None:
            if os.path.exists(ENEMY_SRC[k]):
                print(f'[던전] {k} 이미지를 처리하지 못해 임시 그림을 씁니다')
            else:
                print(f'[던전] {os.path.basename(ENEMY_SRC[k])} 없음 - 임시 그림을 씁니다')
            res = make_fallback(ENEMY_OUT[k], k)
        sizes[k] = res
        if not fresh(ENEMY_OUT[k], ENEMY_WHITE[k]):
            make_white(ENEMY_OUT[k], ENEMY_WHITE[k])
    if os.path.exists(GUNNER_SHEET) and not fresh(GUNNER_SHEET, GUNNER_SHEET_WHITE):
        make_white(GUNNER_SHEET, GUNNER_SHEET_WHITE)
    return sizes


def make_ring(path, color):
    W, H = 160, 80
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((12, 10, W - 12, H - 10), outline=color + (255,), width=9)
    glow = glow.filter(ImageFilter.GaussianBlur(4))
    core = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(core).ellipse((14, 12, W - 14, H - 12), outline=(255, 255, 255, 255), width=3)
    Image.alpha_composite(glow, core).save(path)


def make_arc(path):
    """방패병의 방패 범위를 보여 주는 호 (오른쪽을 향한 모양)"""
    S = 220
    box = (20, 20, S - 20, S - 20)
    half = math.degrees(SHIELD_HALF)
    spans = ((360 - half, 360), (0, half))
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for a0, a1 in spans:
        gd.arc(box, a0, a1, fill=(110, 190, 255, 255), width=14)
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    core = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(core)
    for a0, a1 in spans:
        cd.arc(box, a0, a1, fill=(235, 250, 255, 255), width=5)
    Image.alpha_composite(glow, core).save(path)


def make_disc(path):
    """붉은 원 (안은 반투명, 가장자리는 선명한 테두리). 폭탄병 위험 범위 표시와 폭발 효과"""
    S = 160
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, S - 5, S - 5), fill=(255, 50, 40, 70))
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((6, 6, S - 7, S - 7), outline=(255, 90, 50, 255), width=10)
    glow = glow.filter(ImageFilter.GaussianBlur(3))
    core = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(core).ellipse((5, 5, S - 6, S - 6), outline=(255, 235, 200, 255), width=4)
    Image.alpha_composite(Image.alpha_composite(img, glow), core).save(path)


def make_web(path):
    """거미줄 무늬: 방사형 줄 + 동심 다각형"""
    S = 192
    c = S / 2
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    R = c - 6
    d.ellipse((c - R, c - R, c + R, c + R), fill=(225, 225, 255, 38))
    n = 8
    line = (240, 240, 255, 235)
    for i in range(n):
        a = i * 2 * math.pi / n
        d.line((c, c, c + math.cos(a) * R, c + math.sin(a) * R), fill=line, width=3)
    for f in (0.28, 0.55, 0.82, 1.0):
        pts = []
        for i in range(n):
            a = i * 2 * math.pi / n
            pts.append((c + math.cos(a) * R * f, c + math.sin(a) * R * f))
        for i in range(n):                                   # 줄 사이는 안쪽으로 살짝 휘게
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            mx, my = c + (mx - c) * 0.9, c + (my - c) * 0.9
            d.line((x0, y0, mx, my), fill=line, width=3)
            d.line((mx, my, x1, y1), fill=line, width=3)
    glow = img.filter(ImageFilter.GaussianBlur(3))
    Image.alpha_composite(glow, img).save(path)


def make_soft(path, stops, seed, size=128, rough=0.28):
    """테두리 없는 부드러운 덩어리 (불꽃/연기). stops = 안쪽부터 바깥쪽까지 (위치 0~1, (R, G, B, 투명도))"""
    rng = np.random.RandomState(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    ang = np.arctan2(yy - c, xx - c)
    wob = np.zeros_like(ang)
    for k in (2, 3, 5):                                   # 가장자리가 울퉁불퉁하게
        wob += np.sin(ang * k + rng.uniform(0, 6.28)) / k
    d = np.hypot(xx - c, yy - c) / c / (1 + rough * wob * 0.35)
    d = np.clip(d, 0, 1)
    pos = [p for p, _ in stops]
    out = np.zeros((size, size, 4), np.float32)
    for ch in range(4):
        out[:, :, ch] = np.interp(d, pos, [col[ch] for _, col in stops])
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(path)


def make_shock(path):
    """충격파: 안은 비어 있고 가장자리만 밝은 고리"""
    S = 192
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((8, 8, S - 9, S - 9), outline=(255, 150, 60, 255), width=14)
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    core = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(core).ellipse((9, 9, S - 10, S - 10), outline=(255, 245, 210, 255), width=5)
    Image.alpha_composite(glow, core).save(path)


def prepare_fx():
    Image.new('RGBA', (4, 4), (255, 40, 40, 255)).save(OUT('dg_red.png'))
    Image.new('RGBA', (4, 4), (0, 0, 0, 255)).save(OUT('dg_black.png'))
    Image.new('RGBA', (4, 4), (190, 150, 255, 255)).save(OUT('dg_violet.png'))
    make_disc(OUT('dg_disc.png'))
    make_shock(OUT('dg_shock.png'))
    make_soft(OUT('dg_fire.png'), [(0.0, (255, 255, 235, 255)), (0.3, (255, 215, 110, 245)), (0.6, (255, 120, 35, 200)),
                                 (0.85, (190, 50, 20, 90)), (1.0, (120, 30, 15, 0))], 1)
    make_soft(OUT('dg_smoke.png'), [(0.0, (95, 85, 80, 210)), (0.6, (60, 52, 50, 150)), (1.0, (35, 30, 30, 0))], 2)
    make_web(OUT('dg_web.png'))
    make_orb(OUT('dg_web_ball.png'), (255, 255, 255), (170, 150, 255), 64)
    make_orb(OUT('dg_ball.png'), (255, 255, 225), (255, 120, 30), 64)
    make_orb(OUT('dg_spark.png'), (255, 255, 240), (255, 190, 60), 32)
    make_ring(OUT('dg_ring_red.png'), (255, 50, 50))
    make_ring(OUT('dg_ring_gold.png'), (255, 190, 60))
    make_arc(OUT('dg_arc.png'))


def load_assets(sizes):
    """창을 연 다음에 호출. 몬스터들이 같이 쓰는 이미지 묶음"""
    imgs = {k: load_image(ENEMY_OUT[k]) for k in ENEMY_OUT}
    for k in ENEMY_OUT:
        imgs[k + '_white'] = load_image(ENEMY_WHITE[k])
    sz = dict(sizes)
    for k in list(sizes):
        sz[k + '_white'] = sizes[k]
    A = SimpleNamespace(sizes=sz, imgs=imgs)
    A.gsheet = A.gsheet_white = None
    if os.path.exists(GUNNER_SHEET) and os.path.exists(GUNNER_SHEET_WHITE):
        A.gsheet = load_image(GUNNER_SHEET)
        A.gsheet_white = load_image(GUNNER_SHEET_WHITE)
        A.gsheet_h = GS_CELL_H * GS_ROWS
    A.red = load_image(OUT('dg_red.png'))
    A.black = load_image(OUT('dg_black.png'))
    A.violet = load_image(OUT('dg_violet.png'))
    A.disc = load_image(OUT('dg_disc.png'))
    A.shock = load_image(OUT('dg_shock.png'))
    A.smoke = load_image(OUT('dg_smoke.png'))
    A.fire = load_image(OUT('dg_fire.png'))
    A.web = load_image(OUT('dg_web.png'))
    A.web_ball = load_image(OUT('dg_web_ball.png'))
    A.ball = load_image(OUT('dg_ball.png'))
    A.spark = load_image(OUT('dg_spark.png'))
    A.ring_red = load_image(OUT('dg_ring_red.png'))
    A.arc = load_image(OUT('dg_arc.png'))
    return A


def turn_toward(cur, want, step):
    diff = (want - cur + math.pi) % (2 * math.pi) - math.pi
    if abs(diff) <= step:
        return want
    return cur + (step if diff > 0 else -step)


# =============== 사수의 포탄 ===============
class Cannonball:
    def __init__(self, x, y, ang, A):
        self.x, self.y = x, y
        self.vx = math.cos(ang) * GUNNER_BALL_SPEED
        self.vy = math.sin(ang) * GUNNER_BALL_SPEED
        self.A = A
        self.alive = True
        self.age = 0.0
        self.trail = []

    def update(self, dt):
        self.age += dt
        self.trail.append((self.x, self.y))
        self.trail = self.trail[-7:]
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not (-60 < self.x < CANVAS_W + 60 and -60 < self.y < CANVAS_H + 60):
            self.alive = False

    def touch(self, px, py, pr):
        return math.hypot(px - self.x, py - self.y) < GUNNER_BALL_R + pr

    def draw(self, ox, oy):
        n = len(self.trail)
        for i, (tx, ty) in enumerate(self.trail):          # 꼬리
            f = (i + 1) / (n + 1)
            s = GUNNER_BALL_SIZE * 0.8 * f
            self.A.ball.opacify(0.35 * f)
            self.A.ball.draw(tx + ox, ty + oy, s, s)
        pulse = 1 + 0.08 * math.sin(self.age * 20)
        self.A.ball.opacify(0.4)                           # 은은한 빛
        self.A.ball.draw(self.x + ox, self.y + oy, GUNNER_BALL_SIZE * 1.7 * pulse, GUNNER_BALL_SIZE * 1.7 * pulse)
        self.A.ball.opacify(1.0)
        self.A.ball.draw(self.x + ox, self.y + oy, GUNNER_BALL_SIZE * pulse, GUNNER_BALL_SIZE * pulse)


# =============== 몬스터 공통 ===============
SHOW_LINES = False      # True로 바꾸면 예전처럼 공격 전에 붉은/보라 선이 보임 (False: 선 없음)


class Enemy:
    def __init__(self, kind, x, y, A):
        self.kind = kind
        self.A = A
        self.x, self.y = x, y
        w, h = A.sizes[kind]
        self.spd = random.uniform(0.9, 1.1)        # 걸음 빠르기 개성
        self.rate = random.uniform(0.9, 1.15)      # 몸 흔들림 빠르기 개성
        self.vel = (0.0, 0.0)                      # 현재 이동 속도 (부드러운 가속용)
        self.steered = False
        self.dh = ENEMY_H[kind] * random.uniform(0.94, 1.06)    # 크기 개성
        self.dw = self.dh * w / h
        self.radius = ENEMY_HIT_R[kind] * self.dh
        self.alive = True
        self.state = 'spawn'
        self.t = 0.0
        self.age = random.uniform(0, 6)       # 움직임이 서로 어긋나게
        self.push = (0.0, 0.0)                # 맞아서 밀려나는 속도

    @property
    def hx(self):
        return self.x

    @property
    def hy(self):
        return self.y + HIT_DY_KIND.get(self.kind, HIT_DY) * self.dh

    def targetable(self):
        return self.alive and self.state not in ('spawn', 'dying')

    def dangerous_touch(self, px, py, pr):
        return False

    def bullet_result(self, bx, by):
        return 'kill'

    def on_block(self, ang_in):
        pass

    def die(self):
        """바로 사라지지 않고 쓰러지는 연출을 거친 뒤 사라진다"""
        if self.state != 'dying':
            self.state, self.t = 'dying', 0.0
            self.push = (0.0, 0.0)
            self.vel = (0.0, 0.0)

    def step_dying(self, dt):
        """쓰러지는 중이면 시간을 흘려보내고 True. 끝나면 사라진다"""
        if self.state != 'dying':
            return False
        self.update_common(dt)
        if self.t >= ENEMY_DEATH_TIME:
            self.alive = False
        return True

    def flip(self):
        return ''

    def update_common(self, dt):
        self.t += dt
        self.age += dt
        self.x += self.push[0] * dt
        self.y += self.push[1] * dt
        k = max(0.0, 1 - 9 * dt)
        self.push = (self.push[0] * k, self.push[1] * k)
        if not self.steered:                       # 지난 프레임에 걷지 않았으면 남은 속도로 미끄러지며 멈춤
            k2 = max(0.0, 1 - 8 * dt)
            self.vel = (self.vel[0] * k2, self.vel[1] * k2)
            self.x += self.vel[0] * dt
            self.y += self.vel[1] * dt
        self.steered = False

    def steer(self, tx, ty, dt, rate=6.0):
        """목표 속도(tx, ty)로 서서히 가속하며 이동. rate가 작을수록 묵직하게 움직임"""
        kk = min(1.0, rate * dt)
        self.vel = (self.vel[0] + (tx - self.vel[0]) * kk, self.vel[1] + (ty - self.vel[1]) * kk)
        self.x += self.vel[0] * dt
        self.y += self.vel[1] * dt
        self.steered = True

    def clamp(self):
        self.x, self.y = clamp_arena(self.x, self.y, 18)

    def draw_sprite(self, key, ox, oy, sx=1.0, sy=1.0, alpha=1.0, flip=None, dx=0.0, dy=0.0, at=None, rot=0.0):
        """key 그림을 그린다. sx, sy는 찌그러짐, rot는 기울기(라디안), dy는 위로 띄우는 높이.
        찌그러져도 발 위치는 그대로"""
        img = self.A.imgs[key]
        w, h = self.A.sizes[key]
        dh = self.dh * sy
        dw = self.dh * w / h * sx
        x, y = (self.x, self.y) if at is None else at
        cy = y + oy + dy + (sy - 1.0) * self.dh / 2
        img.opacify(max(0.0, min(1.0, alpha)))
        img.clip_composite_draw(0, 0, w, h, rot, self.flip() if flip is None else flip,
                                x + ox + dx, cy, dw, dh)

    def draw_spawn(self, ox, oy):
        """나타나는 연출: 작게 시작해서 살짝 커졌다가 자리를 잡고, 마지막에 번쩍임"""
        k = min(1.0, self.t / SPAWN_TIME)
        rw = self.dw * (1.9 - 0.7 * k)
        self.A.ring_red.opacify(0.9)
        self.A.ring_red.draw(self.x + ox, self.y + oy - self.dh * 0.42, rw, rw * 0.5)
        s = 0.4 + 0.6 * k + 0.14 * math.sin(k * math.pi)
        self.draw_sprite(self.kind, ox, oy, s, s, alpha=0.2 + 0.8 * k)
        if abs(k - 0.85) < 0.15:
            self.draw_sprite(self.kind + '_white', ox, oy, s, s, alpha=0.7 * (1 - abs(k - 0.85) / 0.15))

    def draw_dying(self, ox, oy):
        """쓰러지는 연출: 하얗게 번쩍이며 납작하게 찌그러지고 고리가 퍼진다"""
        k = min(1.0, self.t / ENEMY_DEATH_TIME)
        sx = 1 + 0.5 * k
        sy = max(0.06, 1 - 0.95 * k ** 1.5)
        a = 1 - k * k
        self.draw_sprite(self.kind, ox, oy, sx, sy, alpha=a)
        self.draw_sprite(self.kind + '_white', ox, oy, sx, sy, alpha=0.9 * a)
        rw = self.dw * (0.8 + 2.2 * k)
        self.A.ring_red.opacify(1 - k)
        self.A.ring_red.draw(self.x + ox, self.y + oy - self.dh * 0.40, rw, rw * 0.5)

    def draw_warn(self, ox, oy):
        pass

    def line(self, x0, y0, ang, length, width, alpha, ox, oy):
        """(x0, y0)에서 ang 방향으로 뻗는 붉은 띠"""
        cx = x0 + math.cos(ang) * length / 2 + ox
        cy = y0 + math.sin(ang) * length / 2 + oy
        self.A.red.opacify(alpha)
        self.A.red.clip_composite_draw(0, 0, 4, 4, ang, '', cx, cy, length, width)


# =============== 슬라임 ===============
class Slime(Enemy):
    def __init__(self, x, y, A):
        super().__init__('slime', x, y, A)
        self.hop_rate = 4.5 * self.rate
        self.cd = random.uniform(*SLIME_COOLDOWN)
        self.aim = 0.0
        self.ghosts = []

    def update(self, dt, ctx):
        if self.step_dying(dt):
            return
        self.update_common(dt)
        p = ctx.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        if self.state == 'spawn':
            if self.t >= SPAWN_TIME:
                self.state, self.t = 'chase', 0.0
            return
        if self.state == 'chase':
            hop = abs(math.sin(self.age * self.hop_rate))       # 통통 뛰면서 움직임
            sp = SLIME_SPEED * self.spd * (0.2 + 1.26 * hop)
            self.steer(dx / d * sp, dy / d * sp, dt, 10.0)
            self.cd -= dt
            if d < SLIME_LUNGE_RANGE and self.cd <= 0:
                self.state, self.t = 'crouch', 0.0
                self.aim = math.atan2(dy, dx)
        elif self.state == 'crouch':
            if self.t < SLIME_CROUCH - 0.2:              # 마지막 0.2초는 방향 고정
                self.aim = math.atan2(dy, dx)
            if self.t >= SLIME_CROUCH:
                self.state, self.t = 'lunge', 0.0
                self.vel = (0.0, 0.0)
                ctx.play('slime_attack')                 # 돌진하는 순간 소리
        elif self.state == 'lunge':
            self.x += math.cos(self.aim) * SLIME_LUNGE_SPEED * dt
            self.y += math.sin(self.aim) * SLIME_LUNGE_SPEED * dt
            self.ghosts.append([self.x, self.y, 0.0])
            if self.t >= SLIME_LUNGE_TIME:
                self.state, self.t = 'land', 0.0
        elif self.state == 'land':
            if self.t >= SLIME_LAND:
                self.state, self.t = 'chase', 0.0
                self.cd = random.uniform(*SLIME_COOLDOWN)
        for g in self.ghosts:
            g[2] += dt
        self.ghosts = [g for g in self.ghosts if g[2] < 0.22]
        self.clamp()

    def dangerous_touch(self, px, py, pr):
        if self.state in ('chase', 'lunge'):
            r = self.radius * (1.1 if self.state == 'lunge' else 0.85) + pr
            return math.hypot(px - self.hx, py - self.hy) < r
        return False

    def draw_warn(self, ox, oy):
        if not SHOW_LINES:
            return
        if self.state == 'crouch':
            locked = self.t >= SLIME_CROUCH - 0.2
            length = SLIME_LUNGE_SPEED * SLIME_LUNGE_TIME + 30
            self.line(self.hx, self.hy, self.aim, length, self.radius * 1.5, 0.30 if locked else 0.14, ox, oy)
            self.line(self.hx, self.hy, self.aim, length, 3, 0.8 if locked else 0.4, ox, oy)

    def draw(self, ox, oy):
        if self.state == 'spawn':
            self.draw_spawn(ox, oy)
            return
        if self.state == 'dying':
            self.draw_dying(ox, oy)
            return
        sx = sy = 1.0
        jx = lift = rot = 0.0
        if self.state == 'chase':
            s = math.sin(self.age * self.hop_rate)
            hop = abs(s)
            lift = hop * 8                                   # 통통 뜀
            sy = 0.88 + 0.22 * hop + 0.03 * math.sin(self.age * 13)
            sx = 1.08 - 0.14 * hop - 0.02 * math.sin(self.age * 13)
            rot = 0.08 * s                                   # 뛰면서 좌우로 기울어짐
        elif self.state == 'crouch':
            k = min(1.0, self.t / SLIME_CROUCH)
            sy, sx = 1 - 0.38 * k, 1 + 0.30 * k
            jx = random.uniform(-2.5, 2.5) * k
            rot = random.uniform(-0.05, 0.05) * k
        elif self.state == 'lunge':
            c, s = abs(math.cos(self.aim)), abs(math.sin(self.aim))
            sx = 1 + 0.38 * c - 0.22 * s
            sy = 1 + 0.38 * s - 0.22 * c
            for g in self.ghosts:
                self.draw_sprite('slime', ox, oy, sx, sy, alpha=0.35 * (1 - g[2] / 0.22), at=(g[0], g[1]))
        elif self.state == 'land':
            k = min(1.0, self.t / SLIME_LAND)
            sy = 0.65 + 0.35 * k + 0.08 * math.sin(k * 12) * (1 - k)
            sx = 1.35 - 0.35 * k
        self.draw_sprite('slime', ox, oy, sx, sy, dx=jx, dy=lift, rot=rot)


# =============== 사수 ===============
class Gunner(Enemy):
    def __init__(self, x, y, A):
        super().__init__('gunner', x, y, A)
        self.cd = random.uniform(1.0, 2.2)
        self.side = random.choice((-1, 1))
        self.side_t = random.uniform(1.0, 2.5)
        self.aim = 0.0
        self.face = -1
        self.turn_t = 0.0
        self.cell = (0, 0)                # 지금 그릴 시트 칸 (줄, 칸)

    def sheet(self):
        return self.A.gsheet is not None

    def flip(self):
        if self.sheet():                  # 시트 그림은 오른쪽을 보고 있음
            return 'h' if self.face == -1 else ''
        return 'h' if (self.face == 1) == FACES_LEFT['gunner'] else ''

    def muzzle(self):
        if self.sheet():
            return self.x + self.face * self.dh * 0.5, self.y - self.dh * 0.17
        return self.x + self.face * self.dw * 0.46, self.y - self.dh * 0.16

    def draw_sprite(self, key, ox, oy, sx=1.0, sy=1.0, alpha=1.0, flip=None, dx=0.0, dy=0.0, at=None, rot=0.0):
        """시트가 있으면 self.cell 칸을 그리고, 없으면 예전 그림. 찌그러져도 발 위치는 그대로"""
        if not self.sheet():
            return super().draw_sprite(key, ox, oy, sx, sy, alpha, flip, dx, dy, at, rot)
        A = self.A
        img = A.gsheet_white if key.endswith('_white') else A.gsheet
        kx = self.dh * sx / GS_CHAR_H
        ky = self.dh * sy / GS_CHAR_H
        f = self.flip() if flip is None else flip
        x, y = (self.x, self.y) if at is None else at
        row, col = self.cell
        cx = x + ox + dx + (GS_CELL_W / 2 - GS_ANCHOR_X) * kx * (-1 if f == 'h' else 1)
        cy = y + oy + dy - self.dh / 2 + (GS_CELL_H / 2 - (GS_CELL_H - GS_FOOT_Y)) * ky
        img.opacify(max(0.0, min(1.0, alpha)))
        img.clip_composite_draw(col * GS_CELL_W, A.gsheet_h - (row + 1) * GS_CELL_H, GS_CELL_W, GS_CELL_H,
                                rot, f, cx, cy, GS_CELL_W * kx, GS_CELL_H * ky)

    def update(self, dt, ctx):
        if self.step_dying(dt):
            return
        self.update_common(dt)
        p = ctx.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        want = -1 if dx < 0 else 1
        if want != self.face and abs(dx) > 14:      # 거의 같은 세로줄이면 안 돌아봄 (깜빡임 방지)
            self.face = want
            self.turn_t = 0.12                       # 돌아볼 때 몸이 잠깐 납작해졌다 펴짐
        self.turn_t = max(0.0, self.turn_t - dt)
        if self.state == 'spawn':
            if self.t >= SPAWN_TIME:
                self.state, self.t = 'move', 0.0
            return
        if self.state == 'move':
            lo, hi = GUNNER_KEEP
            if d < lo:
                vx, vy = -dx / d, -dy / d
            elif d > hi:
                vx, vy = dx / d, dy / d
            else:
                self.side_t -= dt
                if self.side_t <= 0:
                    self.side = -self.side
                    self.side_t = random.uniform(1.2, 2.6)
                vx, vy = -dy / d * self.side, dx / d * self.side
            self.steer(vx * GUNNER_SPEED * self.spd, vy * GUNNER_SPEED * self.spd, dt, 5.0)
            self.cd -= dt
            if self.cd <= 0:
                self.state, self.t = 'aim', 0.0
                mx, my = self.muzzle()
                self.aim = math.atan2(p.y - my, p.x - mx)
        elif self.state == 'aim':
            mx, my = self.muzzle()
            if self.t < GUNNER_AIM - GUNNER_AIM_LOCK:      # 마지막 0.35초는 방향 고정
                self.aim = math.atan2(p.y - my, p.x - mx)
            if self.t >= GUNNER_AIM:
                ctx.shots.append(Cannonball(mx, my, self.aim, self.A))
                ctx.play('cannon', 'shot')
                ctx.sparks(mx, my, 10)
                ctx.shake(0.1, 3)
                self.push = (-math.cos(self.aim) * 140, -math.sin(self.aim) * 140)
                self.state, self.t = 'recoil', 0.0
        elif self.state == 'recoil':
            if self.t >= GUNNER_RECOIL:
                self.state, self.t = 'move', 0.0
                self.cd = random.uniform(*GUNNER_CD)
        self.clamp()

    def draw_warn(self, ox, oy):
        if not SHOW_LINES:
            return
        if self.state != 'aim':
            return
        mx, my = self.muzzle()
        locked = self.t >= GUNNER_AIM - GUNNER_AIM_LOCK
        k = min(1.0, self.t / GUNNER_AIM)
        self.line(mx, my, self.aim, 900, (GUNNER_BALL_R + HIT_RADIUS) * 2, 0.16 if locked else 0.07, ox, oy)
        self.line(mx, my, self.aim, 900, 5 if locked else 3, 0.9 if locked else 0.25 + 0.25 * k, ox, oy)

    def draw(self, ox, oy):
        if self.state == 'spawn':
            self.draw_spawn(ox, oy)
            return
        if self.state == 'dying':
            self.draw_dying(ox, oy)
            return
        sx = sy = 1.0
        dx = lift = rot = 0.0
        if self.sheet():                                     # 시트: 걷기 / 조준 / 발사 줄에서 칸을 고름
            if self.state == 'aim':
                k = min(0.999, self.t / GUNNER_AIM)
                self.cell = (1, int(k * GS_COLS))
                if self.t >= GUNNER_AIM - GUNNER_AIM_LOCK:
                    dx = random.uniform(-1.5, 1.5)
            elif self.state == 'recoil':
                k = min(0.999, self.t / GUNNER_RECOIL)
                self.cell = (2, int(k * GS_COLS))
            else:
                self.cell = (0, int(self.age * GS_WALK_FPS * self.rate) % GS_COLS)
        elif self.state == 'aim':
            k = min(1.0, self.t / GUNNER_AIM)
            sy = 1 + 0.03 * math.sin(self.age * 14)
            rot = -self.face * 0.05 * k * (1 if FACES_LEFT['gunner'] else -1)    # 반동을 받으려고 살짝 뒤로 젖힘
            if self.t >= GUNNER_AIM - GUNNER_AIM_LOCK:
                dx = random.uniform(-1.5, 1.5)
        elif self.state == 'recoil':
            k = min(1.0, self.t / GUNNER_RECOIL)
            sx, sy = 1.12 - 0.12 * k, 0.90 + 0.10 * k
        else:                                                # 걸을 때: 통통 튀고 좌우로 흔들림
            s = math.sin(self.age * 7 * self.rate)
            lift = abs(s) * 3
            rot = 0.05 * s
            sy = 1 + 0.03 * math.sin(self.age * 14)
        if self.turn_t > 0:                                  # 돌아볼 때 잠깐 납작해졌다 펴짐
            sx *= 1 - 0.45 * self.turn_t / 0.12
        self.draw_sprite('gunner', ox, oy, sx, sy, dx=dx, dy=lift, rot=rot)

        mx, my = self.muzzle()
        if self.state == 'aim':                              # 대포 끝에 에너지가 모임
            k = min(1.0, self.t / GUNNER_AIM)
            sz = 8 + 34 * k
            self.A.spark.opacify(0.35 + 0.65 * k)
            self.A.spark.draw(mx + ox, my + oy, sz, sz)
        elif self.state == 'recoil' and self.t < 0.14:       # 발사 순간 번쩍임
            f = 1 - self.t / 0.14
            sz = 70 * f + 10
            self.A.spark.opacify(f)
            self.A.spark.draw(mx + ox, my + oy, sz, sz)


# =============== 방패병 ===============
class Shielder(Enemy):
    def __init__(self, x, y, A):
        super().__init__('shielder', x, y, A)
        self.face_ang = -math.pi / 2
        self.cd = random.uniform(*SHIELDER_COOLDOWN)
        self.bash_ang = 0.0
        self.block_t = 0.0

    @property
    def guard(self):
        return self.state in ('advance', 'windup')

    def flip(self):
        face = -1 if math.cos(self.face_ang) < 0 else 1
        return 'h' if (face == 1) == FACES_LEFT['shielder'] else ''

    def bullet_result(self, bx, by):
        if self.guard:
            a = math.atan2(by - self.hy, bx - self.hx)
            diff = abs((a - self.face_ang + math.pi) % (2 * math.pi) - math.pi)
            if diff < SHIELD_HALF:
                return 'block'
        return 'kill'

    def on_block(self, ang_in):
        self.block_t = 0.35
        self.push = (math.cos(ang_in) * 130, math.sin(ang_in) * 130)

    def update(self, dt, ctx):
        if self.step_dying(dt):
            return
        self.update_common(dt)
        self.block_t = max(0.0, self.block_t - dt)
        p = ctx.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        want = math.atan2(dy, dx)
        if self.state == 'spawn':
            self.face_ang = want
            if self.t >= SPAWN_TIME:
                self.state, self.t = 'advance', 0.0
            return
        if self.state == 'advance':
            self.face_ang = turn_toward(self.face_ang, want, SHIELD_TURN * dt)
            self.steer(dx / d * SHIELDER_SPEED * self.spd, dy / d * SHIELDER_SPEED * self.spd, dt, 4.0)
            self.cd -= dt
            if d < SHIELDER_BASH_RANGE and self.cd <= 0:
                self.state, self.t = 'windup', 0.0
        elif self.state == 'windup':
            if self.t < SHIELDER_WINDUP - 0.2:           # 마지막 0.2초는 방향 고정
                self.face_ang = turn_toward(self.face_ang, want, SHIELD_TURN * 1.3 * dt)
            if self.t >= SHIELDER_WINDUP:
                self.bash_ang = self.face_ang
                self.state, self.t = 'bash', 0.0
                self.vel = (0.0, 0.0)
        elif self.state == 'bash':
            self.x += math.cos(self.bash_ang) * SHIELDER_BASH_SPEED * dt
            self.y += math.sin(self.bash_ang) * SHIELDER_BASH_SPEED * dt
            if self.t >= SHIELDER_BASH_TIME:
                self.state, self.t = 'recover', 0.0
        elif self.state == 'recover':
            if self.t >= SHIELDER_RECOVER:
                self.state, self.t = 'advance', 0.0
                self.cd = random.uniform(*SHIELDER_COOLDOWN)
        self.clamp()

    def dangerous_touch(self, px, py, pr):
        if self.state in ('advance', 'bash'):
            r = self.radius * (1.1 if self.state == 'bash' else 0.8) + pr
            return math.hypot(px - self.hx, py - self.hy) < r
        return False

    def draw_warn(self, ox, oy):
        if not SHOW_LINES:
            return
        if self.state == 'windup':
            locked = self.t >= SHIELDER_WINDUP - 0.2
            length = SHIELDER_BASH_SPEED * SHIELDER_BASH_TIME + 30
            self.line(self.hx, self.hy, self.face_ang, length, self.radius * 1.6, 0.30 if locked else 0.14, ox, oy)
            self.line(self.hx, self.hy, self.face_ang, length, 3, 0.8 if locked else 0.4, ox, oy)

    def draw(self, ox, oy):
        if self.state == 'spawn':
            self.draw_spawn(ox, oy)
            return
        if self.state == 'dying':
            self.draw_dying(ox, oy)
            return
        key = 'shielder_block' if (self.guard or self.block_t > 0) else 'shielder'
        dx = dy = rot = 0.0
        sx = sy = 1.0
        if self.state == 'windup':
            k = min(1.0, self.t / SHIELDER_WINDUP)
            dx = -math.cos(self.face_ang) * 10 * k + random.uniform(-1.5, 1.5) * k
            dy = -math.sin(self.face_ang) * 10 * k + random.uniform(-1.5, 1.5) * k
        elif self.state == 'bash':
            sx, sy = 1.12, 0.94
        elif self.state == 'recover':
            sy = 1 - 0.05 * abs(math.sin(self.age * 8))
        else:                                                # 걸을 때: 묵직하게 좌우로 흔들림
            s = math.sin(self.age * 6 * self.rate)
            dy = abs(s) * 2.5
            rot = 0.045 * s
            sy = 1 + 0.025 * math.sin(self.age * 12)
        if self.block_t > 0:                                 # 막았을 때: 떨리고 하얗게 번쩍임
            f = self.block_t / 0.35
            dx += random.uniform(-2, 2) * f
            dy += random.uniform(-1, 1) * f
        self.draw_sprite(key, ox, oy, sx, sy, dx=dx, dy=dy, rot=rot)
        if self.block_t > 0:
            self.draw_sprite(key + '_white', ox, oy, sx, sy, alpha=0.75 * self.block_t / 0.35, dx=dx, dy=dy, rot=rot)

        if self.guard:                                    # 방패가 막는 범위
            R = self.dh * 0.62
            size = 220 * R / 90
            self.A.arc.opacify(1.0 if self.block_t > 0 else 0.6)
            self.A.arc.clip_composite_draw(0, 0, 220, 220, self.face_ang, '',
                                           self.hx + ox + dx, self.hy + oy + dy, size, size)
        if self.state == 'recover':                       # 방패를 내리고 헉헉대는 중 = 약점
            for k in range(3):
                a = self.age * 5 + k * 2.094
                self.A.spark.opacify(1.0)
                self.A.spark.draw(self.x + ox + math.cos(a) * self.dw * 0.28,
                                  self.y + oy + self.dh * 0.58 + math.sin(a) * 5, 14, 14)


# =============== 거미줄 (거미의 공격) ===============
def apply_web(p, slow=WEB_HIT_SLOW, lock=WEB_HIT_DASHLOCK):
    """플레이어를 거미줄에 걸리게 한다: 한동안 느려지고 대쉬를 못 씀"""
    now = time.time()
    p.slow_until = max(p.slow_until, now + slow)
    p.dash_block_until = max(p.dash_block_until, now + lock)


def add_puddle(ctx, x, y, A):
    """바닥에 거미줄을 남긴다. 너무 많으면 오래된 것부터 지움"""
    x, y = clamp_arena(x, y - 28, 20)
    puds = [s for s in ctx.shots if isinstance(s, WebPuddle) and s.alive]
    while len(puds) >= WEB_PUDDLE_MAX:
        puds.pop(0).alive = False
    ctx.shots.append(WebPuddle(x, y, A, ctx))


class WebShot:
    """거미가 뱉는 거미줄. 조준한 곳까지 날아가 바닥에 퍼지고, 날아가다 플레이어에게 닿으면 대쉬 봉인"""
    ground = False

    def __init__(self, x, y, tx, ty, A, ctx):
        self.x, self.y = x, y
        self.ang = math.atan2(ty - y, tx - x)
        self.left = max(30.0, math.hypot(tx - x, ty - y))
        self.A, self.ctx = A, ctx
        self.alive = True
        self.age = 0.0
        self.trail = []

    def land(self):
        self.alive = False
        add_puddle(self.ctx, self.x, self.y, self.A)

    def update(self, dt):
        self.age += dt
        self.trail.append((self.x, self.y))
        self.trail = self.trail[-6:]
        step = min(self.left, WEB_SPEED * dt)
        self.x += math.cos(self.ang) * step
        self.y += math.sin(self.ang) * step
        self.left -= step
        p = self.ctx.player
        hx, hy = p.x, p.y - p.base_h * HIT_OFFSET
        if not p.dashing and math.hypot(self.x - hx, self.y - hy) < WEB_R + HIT_RADIUS:
            apply_web(p)                                   # 직접 맞음: 느려짐 + 대쉬 봉인
            self.ctx.sparks(self.x, self.y, 8)
            self.land()
        elif self.left <= 0.01 or arena_d(self.x, self.y) > 1.0:
            self.land()

    def touch(self, px, py, pr):
        return False                                       # 피해는 없음

    def draw(self, ox, oy):
        n = len(self.trail)
        for i, (tx, ty) in enumerate(self.trail):
            f = (i + 1) / (n + 1)
            self.A.web_ball.opacify(0.35 * f)
            self.A.web_ball.draw(tx + ox, ty + oy, WEB_SIZE * 0.8 * f, WEB_SIZE * 0.8 * f)
        self.A.web_ball.opacify(0.45)
        self.A.web_ball.draw(self.x + ox, self.y + oy, WEB_SIZE * 1.6, WEB_SIZE * 1.6)
        self.A.web_ball.opacify(1.0)
        self.A.web_ball.draw(self.x + ox, self.y + oy, WEB_SIZE, WEB_SIZE)


class WebPuddle:
    """바닥에 남은 거미줄: 그 위에 서 있으면 느려짐"""
    ground = True

    def __init__(self, x, y, A, ctx):
        self.x, self.y = x, y
        self.A, self.ctx = A, ctx
        self.alive = True
        self.age = 0.0

    def update(self, dt):
        self.age += dt
        if self.age >= WEB_PUDDLE_TIME:
            self.alive = False
            return
        p = self.ctx.player
        foot_y = p.y - p.base_h / 2
        if math.hypot(p.x - self.x, foot_y - self.y) < WEB_PUDDLE_R:
            now = time.time()                                # 거미줄을 밟고 있는 동안: 느려지고 대쉬도 못 씀
            p.slow_until = max(p.slow_until, now + 0.12)
            p.dash_block_until = max(p.dash_block_until, now + 0.25)

    def touch(self, px, py, pr):
        return False

    def draw(self, ox, oy):
        grow = min(1.0, self.age / 0.15)
        fade = min(1.0, (WEB_PUDDLE_TIME - self.age) / 1.0)
        s = WEB_PUDDLE_R * 2 * (0.6 + 0.4 * grow)
        self.A.web.opacify(max(0.0, 0.9 * fade))
        self.A.web.draw(self.x + ox, self.y + oy, s, s)


# =============== 폭발 (폭탄병의 공격) ===============
class Blast:
    """폭발: 하얀 섬광 -> 사방으로 퍼지는 불덩이 -> 충격파 고리 -> 연기. 붉은 원(위험 범위) 안이 전부 피해 범위"""
    ground = False

    def __init__(self, x, y, A):
        self.x, self.y, self.A = x, y, A
        self.t = 0.0
        self.alive = True
        # 불덩이 조각: (방향, 거리 비율, 크기 비율, 시작 지연)
        self.puffs = [(random.uniform(0, 2 * math.pi), random.uniform(0.15, 0.8),
                       random.uniform(0.45, 0.85), random.uniform(0.0, 0.08)) for _ in range(10)]
        self.smoke = [(random.uniform(0, 2 * math.pi), random.uniform(0.1, 0.65),
                       random.uniform(0.45, 0.8)) for _ in range(6)]

    def update(self, dt):
        self.t += dt
        if self.t >= BOMB_FX:
            self.alive = False

    def touch(self, px, py, pr):
        return self.t < BOMB_ACTIVE and math.hypot(px - self.x, py - self.y) < BOMB_R + pr

    def draw(self, ox, oy):
        t = self.t
        k = min(1.0, t / BOMB_FX)
        R = BOMB_R
        x, y = self.x + ox, self.y + oy
        A = self.A
        # 연기 (뒤쪽, 위로 피어오르며 사라짐)
        sk0 = 0.10
        if t > sk0:
            kk = min(1.0, (t - sk0) / (BOMB_FX - sk0))
            for a, d, sz in self.smoke:
                A.smoke.opacify(0.6 * (1 - kk) ** 1.2)
                s = R * 2 * sz * (0.5 + 0.7 * kk)
                A.smoke.draw(x + math.cos(a) * R * d, y + math.sin(a) * R * d + 28 * kk, s, s)
        # 불덩이 조각들: 가운데에서 바깥으로 퍼지며 커졌다가 사라짐
        life = BOMB_FX * 0.75
        for a, d, sz, delay in self.puffs:
            kk = (t - delay) / life
            if kk < 0 or kk >= 1:
                continue
            grow = 1 - (1 - kk) ** 2
            px = x + math.cos(a) * R * d * (0.3 + 0.8 * grow)
            py = y + math.sin(a) * R * d * (0.3 + 0.8 * grow)
            s = R * 2 * sz * (0.35 + 0.75 * grow)
            A.fire.opacify(max(0.0, (1 - kk) ** 0.7))
            A.fire.draw(px, py, s, s)
        # 충격파 고리: 위험 범위 끝까지 빠르게 퍼짐
        e = 1 - (1 - k) ** 3
        rs = R * 2 * (0.2 + 0.85 * e)
        A.shock.opacify(max(0.0, 1 - k ** 1.4))
        A.shock.draw(x, y, rs, rs)
        # 처음 순간의 하얀 섬광
        f = max(0.0, 1 - t / 0.18)
        if f > 0:
            A.fire.opacify(f)
            sz = R * 1.7 * (0.5 + 0.7 * (1 - f))
            A.fire.draw(x, y, sz, sz)


# =============== 거미 ===============
class Spider(Enemy):
    def __init__(self, x, y, A):
        super().__init__('spider', x, y, A)
        self.cd = random.uniform(1.0, 2.0)
        self.side = random.choice((-1, 1))
        self.side_t = random.uniform(1.0, 2.5)
        self.tx = self.ty = 0.0

    def update(self, dt, ctx):
        if self.step_dying(dt):
            return
        self.update_common(dt)
        p = ctx.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        if self.state == 'spawn':
            if self.t >= SPAWN_TIME:
                self.state, self.t = 'move', 0.0
            return
        aim_y = p.y - p.base_h * HIT_OFFSET                      # 플레이어 몸통 위치를 겨눔
        if self.state == 'move':
            lo, hi = SPIDER_KEEP
            if d < lo:
                vx, vy = -dx / d, -dy / d
            elif d > hi:
                vx, vy = dx / d, dy / d
            else:
                self.side_t -= dt
                if self.side_t <= 0:
                    self.side = -self.side
                    self.side_t = random.uniform(1.2, 2.6)
                vx, vy = -dy / d * self.side, dx / d * self.side
            self.steer(vx * SPIDER_SPEED * self.spd, vy * SPIDER_SPEED * self.spd, dt, 5.0)
            self.cd -= dt
            if self.cd <= 0:
                self.state, self.t = 'aim', 0.0
                self.tx, self.ty = p.x, aim_y
        elif self.state == 'aim':
            if self.t < SPIDER_AIM - SPIDER_AIM_LOCK:             # 마지막 0.3초는 목표 고정
                self.tx, self.ty = p.x, aim_y
            if self.t >= SPIDER_AIM:
                ctx.shots.append(WebShot(self.x, self.hy, self.tx, self.ty, self.A, ctx))
                ctx.play('slime_attack', 'shot')
                ctx.sparks(self.x, self.hy, 6)
                ln = math.hypot(self.tx - self.x, self.ty - self.y) or 1.0
                self.push = (-(self.tx - self.x) / ln * 90, -(self.ty - self.y) / ln * 90)
                self.state, self.t = 'recoil', 0.0
        elif self.state == 'recoil':
            if self.t >= SPIDER_RECOIL:
                self.state, self.t = 'move', 0.0
                self.cd = random.uniform(*SPIDER_CD)
        self.clamp()

    def draw_warn(self, ox, oy):
        if not SHOW_LINES:
            return
        if self.state != 'aim':
            return
        locked = self.t >= SPIDER_AIM - SPIDER_AIM_LOCK
        k = min(1.0, self.t / SPIDER_AIM)
        ang = math.atan2(self.ty - self.hy, self.tx - self.x)
        length = math.hypot(self.tx - self.x, self.ty - self.hy)
        cx = self.x + math.cos(ang) * length / 2 + ox
        cy = self.hy + math.sin(ang) * length / 2 + oy
        self.A.violet.opacify(0.9 if locked else 0.25 + 0.25 * k)
        self.A.violet.clip_composite_draw(0, 0, 4, 4, ang, '', cx, cy, length, 4 if locked else 2)

    def draw(self, ox, oy):
        if self.state == 'span':
            self.draw_spawn(ox, oy)
            return
        if self.state == 'dying':
            self.draw_dying(ox, oy)
            return
        sx = sy = 1.0
        dx = lift = rot = 0.0
        if self.state == 'aim':
            k = min(1.0, self.t / SPIDER_AIM)
            sy, sx = 1 + 0.07 * k, 1 - 0.05 * k                    # 몸을 일으키며 부들부들
            dx = random.uniform(-1, 1) * (0.8 + 1.6 * k)
        elif self.state == 'recoil':
            k = min(1.0, self.t / SPIDER_RECOIL)
            sx, sy = 1.12 - 0.12 * k, 0.88 + 0.12 * k
        else:                                                      # 걸을 때: 잰걸음으로 떨림
            s = math.sin(self.age * 16 * self.rate)
            lift = abs(s) * 2
            rot = 0.035 * math.sin(self.age * 9 * self.rate)
            sx = 1 + 0.03 * s
        self.draw_sprite('spider', ox, oy, sx, sy, dx=dx, dy=lift, rot=rot)
        if self.state == 'aim':                                    # 입에 거미줄이 모임
            k = min(1.0, self.t / SPIDER_AIM)
            sz = 6 + 26 * k
            self.A.web_ball.opacify(0.4 + 0.6 * k)
            self.A.web_ball.draw(self.x + ox, self.hy + oy, sz, sz)


# =============== 폭탄병 ===============
class Bomber(Enemy):
    def __init__(self, x, y, A):
        super().__init__('bomber', x, y, A)

    def explode(self, ctx):
        ctx.shots.append(Blast(self.x, self.hy, self.A))
        ctx.sparks(self.x, self.hy, 32)
        ctx.shake(0.35, 10)
        ctx.play('explode', 'hit')
        self.alive = False                                         # 터지면 사라짐

    def update(self, dt, ctx):
        if self.step_dying(dt):
            return
        self.update_common(dt)
        p = ctx.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        if self.state == 'spawn':
            if self.t >= SPAWN_TIME:
                self.state, self.t = 'chase', 0.0
            return
        if self.state == 'chase':
            self.steer(dx / d * BOMBER_SPEED * self.spd, dy / d * BOMBER_SPEED * self.spd, dt, 7.0)
            if d < BOMBER_TRIGGER:
                self.state, self.t = 'fuse', 0.0
                ctx.play('warning')
        elif self.state == 'fuse':
            self.steer(dx / d * BOMBER_FUSE_SPEED, dy / d * BOMBER_FUSE_SPEED, dt, 5.0)
            if self.t >= BOMBER_FUSE:
                self.explode(ctx)
                return
        self.clamp()

    def draw_warn(self, ox, oy):
        if self.state != 'fuse':
            return
        k = min(1.0, self.t / BOMBER_FUSE)
        cx, cy = self.x + ox, self.hy + oy
        pulse = 0.5 + 0.5 * math.sin(self.t * (14 + 16 * k))
        D = BOMB_R * 2                                             # 붉은 원 = 실제 폭발 범위
        self.A.disc.opacify(0.30 + 0.25 * pulse)
        self.A.disc.draw(cx, cy, D, D)
        self.A.disc.opacify(0.6)
        s = max(10.0, D * k)                                       # 안쪽 원이 커지다가 꽉 차면 폭발
        self.A.disc.draw(cx, cy, s, s)

    def draw(self, ox, oy):
        if self.state == 'spawn':
            self.draw_spawn(ox, oy)
            return
        if self.state == 'dying':
            self.draw_dying(ox, oy)
            return
        if self.state == 'fuse':
            k = min(1.0, self.t / BOMBER_FUSE)
            amp = 1.0 + 3.0 * k
            dx, dy = random.uniform(-amp, amp), random.uniform(-amp, amp) * 0.6
            sc = 1.0 + 0.10 * k + 0.04 * math.sin(self.t * 30)
            self.draw_sprite('bomber', ox, oy, sc, sc, dx=dx, dy=dy)
        else:
            s = math.sin(self.age * 11 * self.rate)                # 뒤뚱뒤뚱 달림
            self.draw_sprite('bomber', ox, oy, 1 + 0.04 * s, 1 - 0.04 * s,
                             dy=abs(s) * 4, rot=0.07 * s)


# =============== 탄환 도둑 ===============
class Thief(Enemy):
    def __init__(self, x, y, A):
        super().__init__('thief', x, y, A)
        self.carry = False
        self.hold = 0.0
        self.cool = random.uniform(0.0, 1.0)
        self.side = random.choice((-1, 1))
        self.side_t = random.uniform(1.0, 2.5)
        self.face = -1

    def flip(self):
        return 'h' if (self.face == 1) == FACES_LEFT['thief'] else ''

    def drop(self, ctx):
        """들고 있던 총알을 근처에 던져 놓는다"""
        if not self.carry:
            return
        self.carry = False
        b = Bullet(self.x, self.y, 0.0)
        a = random.uniform(0, 2 * math.pi)
        d = random.uniform(50, 110)
        b.hop_to(self.x + math.cos(a) * d, self.y + math.sin(a) * d)
        ctx.bullets.append(b)
        ctx.sparks(self.x, self.y, 8)
        ctx.play('reload')

    def die(self):
        if self.state != 'dying':
            self._drop_on_death = True
        super().die()

    def nearest_bullet(self, ctx):
        best, bd = None, 1e9
        for b in ctx.bullets:
            if b.alive and b.on_ground:
                d = math.hypot(b.x - self.x, b.y - self.y)
                if d < bd:
                    best, bd = b, d
        return best, bd

    def update(self, dt, ctx):
        if getattr(self, '_drop_on_death', False):
            self._drop_on_death = False
            self.drop(ctx)
        if self.step_dying(dt):
            return
        self.update_common(dt)
        self.cool = max(0.0, self.cool - dt)
        p = ctx.player
        dx, dy = p.x - self.x, p.y - self.y
        d = math.hypot(dx, dy) or 1.0
        if self.state == 'spawn':
            if self.t >= SPAWN_TIME:
                self.state, self.t = 'seek', 0.0
            return

        if self.carry:                                             # 훔친 총알을 들고 도망
            self.hold -= dt
            ax, ay = -dx / d, -dy / d                              # 플레이어 반대 방향
            e = arena_d(self.x, self.y)
            w = max(0.0, min(1.0, (e - 0.6) / 0.4))                # 가장자리에 가까울수록 옆으로 돌아 빠져나감
            cdx, cdy = ARENA_CENTER_X - self.x, ARENA_CENTER_Y - self.y
            cd = math.hypot(cdx, cdy) or 1.0
            tx, ty = -ay * self.side, ax * self.side
            vx = ax * (1 - 0.8 * w) + tx * 0.6 * w + cdx / cd * 0.5 * w
            vy = ay * (1 - 0.8 * w) + ty * 0.6 * w + cdy / cd * 0.5 * w
            n = math.hypot(vx, vy) or 1.0
            self.steer(vx / n * THIEF_FLEE_SPEED * self.spd, vy / n * THIEF_FLEE_SPEED * self.spd, dt, 6.0)
            if abs(self.vel[0]) > 20:
                self.face = -1 if self.vel[0] < 0 else 1
            if self.hold <= 0:
                self.drop(ctx)
                self.cool = THIEF_COOLDOWN
                self.state, self.t = 'seek', 0.0
        else:
            b, bd = (self.nearest_bullet(ctx) if self.cool <= 0 else (None, 0.0))
            if b is not None:                                      # 떨어진 총알을 향해 달림
                bx, by = b.x - self.x, b.y - self.y
                n = bd or 1.0
                self.steer(bx / n * THIEF_SPEED * self.spd, by / n * THIEF_SPEED * self.spd, dt, 6.0)
                if abs(bx) > 8:
                    self.face = -1 if bx < 0 else 1
                if bd < THIEF_STEAL_R:                             # 훔침!
                    b.alive = False
                    self.carry = True
                    self.hold = THIEF_HOLD
                    self.state, self.t = 'flee', 0.0
                    self.side = random.choice((-1, 1))
                    ctx.sparks(b.x, b.y, 10)
                    ctx.play('reload')
            else:                                                  # 훔칠 게 없으면 멀찍이서 맴돎
                if d < THIEF_KEEP - 40:
                    vx, vy = -dx / d, -dy / d
                elif d > THIEF_KEEP + 80:
                    vx, vy = dx / d, dy / d
                else:
                    self.side_t -= dt
                    if self.side_t <= 0:
                        self.side = -self.side
                        self.side_t = random.uniform(1.2, 2.6)
                    vx, vy = -dy / d * self.side, dx / d * self.side
                self.steer(vx * THIEF_SPEED * 0.7 * self.spd, vy * THIEF_SPEED * 0.7 * self.spd, dt, 5.0)
                if abs(dx) > 14:
                    self.face = -1 if dx < 0 else 1
        self.clamp()

    def draw(self, ox, oy):
        if self.state == 'spawn':
            self.draw_spawn(ox, oy)
            return
        if self.state == 'dying':
            self.draw_dying(ox, oy)
            return
        fast = self.carry
        s = math.sin(self.age * (13 if fast else 9) * self.rate)
        self.draw_sprite('thief', ox, oy, 1 + 0.03 * s, 1 - 0.03 * s,
                         dy=abs(s) * (5 if fast else 3), rot=0.06 * s)
        if self.carry:                                             # 훔친 총알 + 남은 시간 막대
            top = self.y + self.dh * 0.62
            Bullet.draw_icon(self.x + ox, top + 14 + oy + 2 * math.sin(self.age * 8), 1.0)
            f = max(0.0, min(1.0, self.hold / THIEF_HOLD))
            w = 36
            self.A.black.opacify(0.8)
            self.A.black.draw(self.x + ox, top + oy, w + 4, 7)
            self.A.red.opacify(1.0)
            self.A.red.draw(self.x + ox - w / 2 + w * f / 2, top + oy, max(1, w * f), 4)


CLASSES = {'slime': Slime, 'gunner': Gunner, 'shielder': Shielder,
           'spider': Spider, 'bomber': Bomber, 'thief': Thief}