import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DG_DIR = os.path.join(ROOT, 'dungeon')          # 던전 몬스터 파일(enemies.py, dg_config.py)이 있는 폴더
for _p in (DG_DIR, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pico2d import *
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from types import SimpleNamespace
import json
import math
import random
import time
import numpy as np

from config import *
from player import Player, Bullet
from boss import (Boss, prepare_boss_bullets, prepare_boss_hurt, prepare_boss_phases,
                  prepare_lasers, make_orb, label_components)
import title as title_mod
from title import prepare_title, run_title
from dg_config import *
from enemies import CLASSES, prepare_enemy_images, prepare_fx, load_assets, prepare_sprite
from shadow import ShadowBoss, ShadowBullet, prepare_shadow
from mapdoor import prepare_map_doors, door_parts, MAP_DOORS

# 던전 전체를 깨는 기록이라서 예전 보스전 기록과 파일을 따로 쓴다
BEST_FILE = 'best_time_dungeon.json'
title_mod.BEST_FILE = BEST_FILE

PICKUP_DELAY = 0.4        # 쏜 총알은 이 시간(초)이 지나야 주울 수 있음 (발밑에 쏴서 바로 다시 줍는 것 방지)
VOL_FILE = 'dg_volume.json'        # 소리 크기 저장 파일 (일시정지 P 화면에서 조절)
VOL = {'bgm': 1.0, 'sfx': 1.0}    # 배경음악 / 효과음 크기 (0.0 ~ 1.0)


def load_volume():
    try:
        with open(VOL_FILE, 'r') as f:
            d = json.load(f)
        for k in VOL:
            VOL[k] = max(0.0, min(1.0, float(d.get(k, 1.0))))
    except Exception:
        pass


def save_volume():
    try:
        with open(VOL_FILE, 'w') as f:
            json.dump(VOL, f)
    except Exception as e:
        print(f'[소리] 설정 저장 실패: {e}')


AMMO_LOG = True           # True면 총알이 늘어나는 순간을 터미널에 찍어 줌 (문제 찾을 때만 켜기)
TOTAL_FLOORS = len(FLOORS)         # 전체 층 수 (보스층 포함). 층 구성은 dungeon/dg_config.py 의 FLOORS
DEV_MODE = True                    # True면 N: 다음 층, B: 이전 층으로 이동 (발표할 땐 False)      # 전체 층 수 (보스층 포함). 층 구성은 dungeon/dg_config.py 의 FLOORS

GAUGE_FG, GAUGE_READY = 'fx_gauge.png', 'fx_gauge_ready.png'
WHITE_IMG, RING_IMG, RAY_IMG = 'fx_white.png', 'fx_ring.png', 'fx_ray.png'

DOOR_X, DOOR_Y, DOOR_R = ARENA_CENTER_X, 470, 62     # DOOR_Y는 문 발밑 높이 (숫자가 클수록 위)
MON_DOOR_GAP = 40                  # 몬스터가 문 앞에서 떨어져 있는 거리(px). 클수록 문에서 멀리 막힘
DOOR_BLOCK = 10                    # 닫힌 문 앞에서 막히는 거리(px). 작을수록 문에 가까이 갈 수 있음
DOOR_H = 130                       # 문 그림의 높이(px). 가로는 그림 비율에 맞춰 자동으로 정해짐
DOOR_MAX_W = 260                   # 문이 너무 넓게 그려지지 않게 하는 한계
DOOR_OPEN_TIME = 1.4                # 맵 속 문이 열리는 데 걸리는 시간(초)
FINAL_DOOR_TIME = 2.2              # 마지막 보스를 잡고 문이 열린 뒤 클리어 화면까지 기다리는 시간(초)
DOOR_BG_TOL = 26                   # 문 그림의 배경으로 볼 색 차이 (배경이 남으면 올리고, 문이 깎이면 내리기)
DG_START = (ARENA_CENTER_X, ARENA_CENTER_Y - ARENA_RY * 0.55)    # 던전 층에서 시작하는 위치
BOSS_START = (ARENA_CENTER_X, ARENA_CENTER_Y - 90)               # 보스층에서 시작하는 위치


# =============== 기록 ===============
def load_best():
    try:
        with open(BEST_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_best(d):
    try:
        with open(BEST_FILE, 'w') as f:
            json.dump(d, f)
    except Exception as e:
        print(f'[기록] 저장 실패: {e}')


def fmt_time(t):
    m = int(t // 60)
    return f'{m}:{t - m * 60:05.2f}'


# =============== 글자/그림 만들기 ===============
def load_font(size):
    """(폰트, 한글 가능 여부). 한글 폰트가 없으면 영어 문구를 쓴다"""
    for name in ('malgunbd.ttf', 'malgun.ttf'):
        try:
            return ImageFont.truetype(name, size), True
        except OSError:
            pass
    for name in ('arialbd.ttf', 'arial.ttf'):
        try:
            return ImageFont.truetype(name, size), False
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size), False
    except TypeError:
        return ImageFont.load_default(), False


def draw_text(d, x, y, text, font, fill, stroke=0):
    """가운데 정렬로 글자 그리기 (anchor를 못 쓰는 환경이면 직접 계산)"""
    try:
        d.text((x, y), text, font=font, fill=fill, anchor='mt',
               stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    except (ValueError, TypeError):
        try:
            w = d.textlength(text, font=font)
        except Exception:
            w = len(text) * 8
        d.text((x - w / 2, y), text, font=font, fill=fill)


def make_text_img(path, kr, en, size, color, w, h, stroke=0):
    font, ok = load_font(size)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw_text(ImageDraw.Draw(img), w / 2, 4, kr if ok else en, font, color, stroke)
    img.save(path)


def make_panel(path, title, color, lines, size, title_size=64, bg_alpha=170):
    """제목 + 안내 문구가 있는 반투명 판. lines = [(한글, 영어, 글자크기, 색), ...]"""
    img = Image.new('RGBA', size, (0, 0, 0, bg_alpha))
    d = ImageDraw.Draw(img)
    font, _ = load_font(title_size)
    y = int(size[1] * 0.12)
    draw_text(d, size[0] / 2, y, title, font, color)
    y += int(title_size * 1.35)
    for kr, en, sz, col in lines:
        f, ok = load_font(sz)
        draw_text(d, size[0] / 2, y, kr if ok else en, f, col)
        y += int(sz * 1.6)
    img.save(path)


def make_banner(path, text, color, size=84, w=520):
    """배경 없는 큰 글자 (PHASE, FLOOR 알림용)"""
    img = Image.new('RGBA', (w, 120), (0, 0, 0, 0))
    font, _ = load_font(size)
    draw_text(ImageDraw.Draw(img), w / 2, 8, text, font, color, stroke=5)
    img.save(path)


def make_heart(path, full):
    S = 96
    mask = Image.new('L', (S, S), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((8, 12, 52, 56), fill=255)
    md.ellipse((44, 12, 88, 56), fill=255)
    md.polygon([(10, 46), (86, 46), (48, 88)], fill=255)
    outline = mask.filter(ImageFilter.MaxFilter(7))
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    img.paste((255, 215, 225, 255) if full else (110, 95, 115, 255), mask=outline)
    img.paste((235, 50, 70, 255) if full else (45, 35, 52, 255), mask=mask)
    if full:
        ImageDraw.Draw(img).ellipse((17, 20, 31, 33), fill=(255, 200, 210, 255))
    img.resize((48, 48), Image.LANCZOS).save(path)


def make_ring(path):
    """총알을 주울 때 퍼지는 황금빛 고리"""
    W, H = 160, 80
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((12, 10, W - 12, H - 10), outline=(255, 190, 60, 255), width=10)
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    core = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(core).ellipse((14, 12, W - 14, H - 12), outline=(255, 245, 190, 255), width=4)
    Image.alpha_composite(glow, core).save(path)


def make_ray(path):
    """총알을 주울 때 솟는 빛줄기"""
    w, h = 24, 96
    x = np.abs(np.linspace(-1, 1, w))[None, :].repeat(h, 0)
    y = np.linspace(0, 1, h)[:, None].repeat(w, 1)
    alpha = np.clip(1 - x, 0, 1) ** 1.5 * y ** 0.8
    out = np.zeros((h, w, 4), np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = 255, 230, 130
    out[:, :, 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(out).save(path)


def make_vignette(path):
    """체력이 위험할 때 화면 가장자리를 붉게 물들이는 이미지"""
    W, H = 200, 150
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xx - (W - 1) / 2) / ((W - 1) / 2)
    ny = (yy - (H - 1) / 2) / ((H - 1) / 2)
    d = np.sqrt(nx ** 2 + ny ** 2) / 1.4142
    alpha = np.clip((d - 0.45) / 0.55, 0, 1) ** 1.4
    out = np.zeros((H, W, 4), np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = 255, 20, 30
    out[:, :, 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(out).save(path)


def _arch(d, box, fill):
    x0, y0, x1, y1 = box
    w = x1 - x0
    d.ellipse((x0, y0, x1, y0 + w), fill=fill)
    d.rectangle((x0, y0 + w // 2, x1, y1), fill=fill)


def make_door(path, opened):
    """코드로 그린 출구 문 (문 그림이 없을 때 대신 씀)"""
    W, H = 150, 112
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _arch(d, (4, 2, W - 4, H - 1), (130, 118, 165, 255))
    _arch(d, (10, 8, W - 10, H - 1), (52, 46, 72, 255))
    if opened:
        _arch(d, (24, 24, W - 24, H - 1), (255, 215, 120, 255))
        _arch(d, (40, 40, W - 40, H - 1), (255, 250, 225, 255))
        glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        _arch(ImageDraw.Draw(glow), (20, 20, W - 20, H - 1), (255, 200, 80, 120))
        glow = glow.filter(ImageFilter.GaussianBlur(7))
        img = Image.alpha_composite(img, glow)
    else:
        _arch(d, (24, 24, W - 24, H - 1), (30, 20, 40, 255))
        for bx in (50, 75, 100):
            d.rectangle((bx - 3, 40, bx + 3, H - 1), fill=(150, 40, 50, 255))
        d.rectangle((26, 62, W - 26, 68), fill=(150, 40, 50, 255))
    img.save(path)


def prepare_door_img(src, dst):
    """직접 만든 문 그림에서 배경을 지우고 dst에 저장. (w, h)를 돌려준다. 실패하면 None.
    그림 가장자리에 가장 많이 보이는 색들을 배경으로 보고, 바깥과 이어진 같은 색 영역을 지운다."""
    if not os.path.exists(src):
        return None
    if fresh(src, dst):
        with Image.open(dst) as im:
            return im.size
    try:
        im = Image.open(src).convert('RGBA')
        sc = min(1.0, 384 / max(im.size))
        if sc < 1.0:
            im = im.resize((max(1, int(im.size[0] * sc)), max(1, int(im.size[1] * sc))), Image.LANCZOS)
        arr = np.array(im)
        rgb = arr[:, :, :3].astype(np.int16)
        a = arr[:, :, 3]
        H, W = a.shape

        border = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
        balpha = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
        border = border[balpha >= 40]
        bgcols = []
        if len(border) > 0:
            q = (border // 24).astype(np.int32)
            keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
            uniq, cnt = np.unique(keys, return_counts=True)
            for idx in np.argsort(-cnt)[:4]:
                if cnt[idx] >= max(6, 0.06 * len(border)):
                    bgcols.append(border[keys == uniq[idx]].mean(axis=0))

        cand = a < 40                                          # 투명한 곳은 배경
        near = np.full((H, W), 999, np.int16)                  # 가장 가까운 배경색과의 차이
        for c in bgcols:
            dist = np.abs(rgb - c.astype(np.int16)).max(axis=2)
            near = np.minimum(near, dist)
        cand = cand | (near <= DOOR_BG_TOL)

        lab, n = label_components(cand)
        if n == 0:
            return prepare_sprite(src, dst)
        edge = np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))
        edge = edge[edge > 0]
        bg = np.isin(lab, edge)                                # 바깥과 이어진 배경만 지움
        fg = ~bg

        ring = np.array(Image.fromarray((bg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
        fg = fg & ~(ring & (near <= DOOR_BG_TOL * 2))

        lab2, n2 = label_components(fg)                        # 가장 큰 덩어리만 (문)
        if n2 == 0:
            return prepare_sprite(src, dst)
        cnt2 = np.bincount(lab2.ravel())
        cnt2[0] = 0
        fg = lab2 == int(cnt2.argmax())

        out_a = np.where(fg, 255, 0).astype(np.uint8)
        out = Image.fromarray(np.dstack([arr[:, :, :3], out_a]))
        box = out.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox()
        if box:
            out = out.crop(box)
        out.save(dst)
        return out.size
    except Exception as e:
        print(f'[문] {src} 처리 실패: {e}')
        return prepare_sprite(src, dst)


def _file_sig(path):
    """파일의 이름, 크기, 수정 시각을 합친 값"""
    try:
        st = os.stat(path)
        return f'{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}'
    except OSError:
        return None


def _darken(src_path, dst_path):
    """그림을 어둡고 붉게 보정해서 닫힌 문처럼 만든다. (w, h) 반환"""
    base = Image.open(src_path).convert('RGBA')
    arr = np.array(base).astype(np.float32)
    arr[:, :, :3] = arr[:, :, :3] * 0.45
    arr[:, :, 0] = arr[:, :, 0] + 28
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(dst_path)
    return base.size


def prepare_doors():
    """문 그림을 준비한다. door_closed.png, door_open.png 또는 door.png가 있으면 그걸 쓰고,
    없으면 코드로 그린 문을 쓴다. 돌려주는 값: {'closed': (경로, (w, h)), 'open': (경로, (w, h))}"""
    c_src, o_src, s_src = DP('door_closed.png'), DP('door_open.png'), DP('door.png')
    c_out, o_out, b_out = OUT('dg_door_c_img.png'), OUT('dg_door_o_img.png'), OUT('dg_door_base_img.png')
    sig_file = OUT('dg_door_sig.json')

    def shown(p):
        return p if os.path.exists(p) else '(없음)'

    print(f'[문] 닫힌 문 그림: {shown(c_src)} / 열린 문 그림: {shown(o_src)} / door.png: {shown(s_src)}')

    now_sig = {'c': _file_sig(c_src), 'o': _file_sig(o_src), 's': _file_sig(s_src), 'v': 4, 'tol': DOOR_BG_TOL}
    try:
        with open(sig_file, 'r') as f:
            old_sig = json.load(f)
    except Exception:
        old_sig = None
    if old_sig != now_sig:                          # 이름, 내용, 처리 방식이 바뀌었으면 새로 만든다
        for p in (c_out, o_out, b_out):
            try:
                os.remove(p)
            except OSError:
                pass

    sz_c = prepare_door_img(c_src, c_out)
    sz_o = prepare_door_img(o_src, o_out)
    sz_b = None
    if sz_c is None or sz_o is None:
        sz_b = prepare_door_img(s_src, b_out)       # door.png 한 장

    if sz_o is None:                                 # 열린 문이 없으면 door.png 또는 닫힌 문 그림을 그대로
        ref = b_out if sz_b else (c_out if sz_c else None)
        if ref:
            im = Image.open(ref).convert('RGBA')
            im.save(o_out)
            sz_o = im.size
    if sz_c is None and sz_o is not None:            # 닫힌 문이 없으면 열린 문을 어둡고 붉게
        sz_c = _darken(o_out, c_out)

    try:
        with open(sig_file, 'w') as f:
            json.dump(now_sig, f)
    except Exception:
        pass

    info = {}
    if sz_c is not None:
        info['closed'] = (c_out, sz_c)
    else:
        make_door(OUT('dg_door_closed.png'), False)
        info['closed'] = (OUT('dg_door_closed.png'), (150, 112))
    if sz_o is not None:
        info['open'] = (o_out, sz_o)
    else:
        make_door(OUT('dg_door_open.png'), True)
        info['open'] = (OUT('dg_door_open.png'), (150, 112))
    if sz_c is None and sz_o is None:
        print('[문] 문 그림이 없어 코드로 그린 문을 씁니다 (door_closed.png, door_open.png 또는 door.png를 넣어 보세요)')
    return info


def make_clear_panel(tsec, best, new_rec, diff):
    white, gold = (255, 255, 255, 255), (255, 220, 80, 255)
    lines = [(f'난이도  {diff["kr"]}', f'Difficulty  {diff["en"]}', 24, white),
             (f'걸린 시간  {fmt_time(tsec)}', f'Time  {fmt_time(tsec)}', 34, gold)]
    if new_rec:
        lines.append(('NEW RECORD!', 'NEW RECORD!', 30, (255, 120, 120, 255)))
    else:
        lines.append((f'최고 기록  {fmt_time(best)}', f'Best  {fmt_time(best)}', 26, white))
    lines.append(('R 다시 시작     T 타이틀', 'R restart     T title', 24, (200, 200, 255, 255)))
    make_panel(CLEAR_IMG, 'CLEAR!', gold, lines, (600, 330))


def make_over_panel(floor_idx, boss_pct, tsec, diff):
    white = (255, 255, 255, 255)
    lines = [(f'난이도  {diff["kr"]}', f'Difficulty  {diff["en"]}', 24, white),
             (f'도달한 층  {floor_idx + 1}층 / {TOTAL_FLOORS}층',
              f'Reached floor {floor_idx + 1} / {TOTAL_FLOORS}', 30, (255, 200, 120, 255))]
    if boss_pct is not None:
        lines.append((f'보스 체력 {boss_pct}% 남음', f'Boss HP left {boss_pct}%', 28, (255, 170, 120, 255)))
    lines.append((f'버틴 시간  {fmt_time(tsec)}', f'Survived  {fmt_time(tsec)}', 26, white))
    lines.append(('R 다시 시작     T 타이틀', 'R restart     T title', 24, (200, 200, 255, 255)))
    make_panel(OVER_IMG, 'GAME OVER', (255, 80, 80, 255), lines, (600, 390))


def prepare_screens():
    """화면 이미지와 효과 이미지 생성"""
    white = (255, 255, 255, 255)
    make_panel(PAUSE_IMG, 'PAUSED', (200, 220, 255, 255),
               [('P키로 계속', 'Press P to resume', 28, white)], (480, 190))
    make_banner(BANNER_IMGS[1], 'PHASE 2', (255, 200, 80, 255))
    make_banner(BANNER_IMGS[2], 'PHASE 3', (255, 80, 80, 255))

    for path, col in ((DIM_IMG, (0, 0, 0, 255)), (FLASH_IMG, (255, 30, 30, 255)),
                      (WHITE_IMG, (255, 255, 255, 255)), (GAUGE_FG, (80, 190, 255, 255)),
                      (GAUGE_READY, (110, 235, 120, 255))):
        if not os.path.exists(path):
            Image.new('RGBA', (4, 4), col).save(path)
    if not os.path.exists(SPARK_IMG):
        make_orb(SPARK_IMG, (255, 255, 230), (255, 150, 30), 32)
    if not os.path.exists(RING_IMG):
        make_ring(RING_IMG)
    if not os.path.exists(RAY_IMG):
        make_ray(RAY_IMG)
    if not os.path.exists(VIGNETTE_IMG):
        make_vignette(VIGNETTE_IMG)
    if not os.path.exists(HEART_FULL):
        make_heart(HEART_FULL, True)
    if not os.path.exists(HEART_EMPTY):
        make_heart(HEART_EMPTY, False)
    make_clear_panel(0.0, 0.0, True, DIFFICULTIES[DEFAULT_DIFFICULTY])
    make_over_panel(0, None, 0.0, DIFFICULTIES[DEFAULT_DIFFICULTY])


def prepare_floor_ui():
    """던전 층에 쓰는 층 알림, 층 표시 이미지 (dungeon 폴더에 만들어짐)"""
    for i in range(TOTAL_FLOORS):
        kind = floor_kind(i)
        if kind == 'boss':
            make_banner(OUT(f'dg_banner_{i + 1}.png'), f'FLOOR {i + 1}  BOSS', (255, 80, 80, 255), size=72, w=640)
        elif kind == 'shadow':
            make_banner(OUT(f'dg_banner_{i + 1}.png'), 'FINAL BOSS', (190, 100, 255, 255), size=76, w=640)
        else:
            make_banner(OUT(f'dg_banner_{i + 1}.png'), f'FLOOR {i + 1}', (255, 200, 80, 255))
    make_banner(OUT('dg_banner_clear.png'), 'FLOOR CLEAR!', (120, 255, 150, 255), size=72, w=640)
    for i in range(TOTAL_FLOORS):
        make_text_img(OUT(f'dg_tag_{i + 1}.png'), f'{i + 1}층 / {TOTAL_FLOORS}층',
                      f'FLOOR {i + 1} / {TOTAL_FLOORS}', 26, (255, 255, 255, 255), 240, 40, stroke=3)
    make_text_img(OUT('dg_go.png'), '▲ 문으로 가세요', 'GO TO THE DOOR', 28, (255, 230, 120, 255), 400, 46, stroke=3)


def seg_hit(x0, y0, x1, y1, cx, cy, r):
    """선분(총알이 이번 프레임에 지나간 길)이 원에 닿았는지. 닿으면 선분 위의 위치(0~1)"""
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    u = 0.0 if l2 < 1e-9 else max(0.0, min(1.0, ((cx - x0) * dx + (cy - y0) * dy) / l2))
    qx, qy = x0 + dx * u, y0 + dy * u
    return u if math.hypot(cx - qx, cy - qy) <= r else None


def load_extra_sounds():
    """던전에서만 쓰는 선택 소리: block.wav(방패 막는 소리), cannon.wav(포탄 발사). 없으면 건너뜀"""
    for name in ('block', 'cannon'):
        p = DP(name + '.wav')
        if os.path.exists(p):
            try:
                w = load_wav(p)
                w.set_volume(100)
                Sound.sfx[name] = w
            except Exception as e:
                print(f'[소리] {p} 불러오기 실패: {e}')


def main():
    # 무거운 이미지 처리는 창을 열기 전에 끝낸다
    sprites = prepare_sheet()
    front_size = prepare_single(FRONT_SRC, FRONT_CLEAN)
    back_size = prepare_single(BACK_SRC, BACK_CLEAN)
    bullet_sizes = prepare_bullet()
    boss_size = prepare_single(BOSS_SRC, BOSS_CLEAN)
    hurt_size = prepare_boss_hurt()
    phases_ok = prepare_boss_phases()
    prepare_ui()
    bb_metas = prepare_boss_bullets()
    prepare_screens()
    prepare_floor_ui()
    door_info = prepare_doors()
    mdoor_info = prepare_map_doors(P, OUT)          # 맵 속 문 (bg_red.png, bg_purple.png 에서 자동 생성)
    prepare_title()
    laser_info = prepare_lasers()
    esizes = prepare_enemy_images()
    prepare_fx()
    shadow_info = prepare_shadow()          # 10층 그림자 보스 그림 (플레이어 그림을 어둡게)

    open_canvas(CANVAS_W, CANVAS_H)
    import pico2d.pico2d as p2d
    SDL_RenderSetLogicalSize(p2d.renderer, CANVAS_W, CANVAS_H)      # 전체화면에서도 800x600 비율로 늘려 그림

    def toggle_fullscreen():                                        # M 키로 전체화면 <-> 창 모드
        full = SDL_GetWindowFlags(p2d.window) & SDL_WINDOW_FULLSCREEN
        r = SDL_SetWindowFullscreen(p2d.window, 0 if full else SDL_WINDOW_FULLSCREEN_DESKTOP)
        print('[전체화면] M 키 입력, 결과 코드:', r, SDL_GetError().decode('utf8', 'ignore'))     # 안 될 때 원인 확인용

    hide_cursor()

    Sound.load()
    try:
        Mix_AllocateChannels(32)        # 동시에 재생할 수 있는 효과음 수를 8개에서 32개로
    except Exception as ex:
        print(f'[소리] 채널 늘리기 실패: {ex}')
    load_extra_sounds()

    # ---- 소리 크기 조절: 배경음악/효과음 크기에 설정값(VOL)을 곱해서 적용 ----
    load_volume()
    _bgm_set = Sound.bgm_volume.__func__
    _bgm_start = Sound.start_bgm.__func__
    Sound.bgm_volume = classmethod(lambda cls, vol: _bgm_set(cls, int(vol * VOL['bgm'])))

    def _start_scaled(cls):
        _bgm_start(cls)
        Sound.bgm_volume(BGM_VOL)
    Sound.start_bgm = classmethod(_start_scaled)

    def apply_sfx():
        for nm, w in Sound.sfx.items():
            try:
                w.set_volume(int(SFX_VOL.get(nm, 100) * VOL['sfx']))
            except Exception:
                pass
    apply_sfx()
    Sound.start_bgm()

    # ---- 5층, 10층 전용 배경음악 (파일이 없으면 기본 곡을 계속 씀) ----
    BGM_ALT_FILES = {                       # 곡 이름을 바꾸려면 여기만 고치세요
        'boss': ['bgm_boss.mp3', 'bgm_boss.ogg', 'bgm_boss.wav'],       # 5층 중간 보스
        'final': ['bgm_final.mp3', 'bgm_final.ogg', 'bgm_final.wav'],   # 10층 최종 보스
    }
    bgm_default = Sound.bgm
    bgm_alt = {}
    for _key, _names in BGM_ALT_FILES.items():
        for _nm in _names:
            _p = P(_nm)
            if not os.path.exists(_p):
                continue
            try:
                bgm_alt[_key] = load_music(_p)
                bgm_alt[_key].set_volume(BGM_VOL)
                print(f'[소리] {_key} 배경음악: {_p}')
                break
            except Exception as ex:
                print(f'[소리] {_p} 불러오기 실패: {ex}')
    bgm_state = {'key': None}

    def set_floor_bgm(key):
        """key: None(기본 곡) / 'boss'(5층) / 'final'(10층). 곡이 바뀔 때만 새로 재생"""
        if key == bgm_state['key']:
            return
        bgm_state['key'] = key
        want = bgm_alt.get(key) if key else None
        print(f'[소리] 층 배경음악 변경 요청: {key} / 전용 곡 {"있음" if want else "없음"} / 기본 곡 {"있음" if bgm_default else "없음"}')
        want = want or bgm_default
        if want is None or want is Sound.bgm:
            return
        Sound.bgm = want
        Sound.start_bgm()

    A = load_assets(esizes)

    def L(name):
        return load_image(OUT(name))

    # 1~5층은 붉은 맵, 6~10층은 보라 맵 (둘 다 없으면 예전 background.png)
    bg_red = load_image(P('bg_red.png')) if os.path.exists(P('bg_red.png')) else None
    bg_purple = load_image(P('bg_purple.png')) if os.path.exists(P('bg_purple.png')) else None
    bg_old = load_image(BG_SRC) if os.path.exists(BG_SRC) else None
    mdoor_imgs = {nm: {k: load_image(v) for k, v in d['files'].items()} for nm, d in mdoor_info.items()}

    def map_name(floor):
        return 'red' if floor < 5 else 'purple'
    boss_bullet_imgs = [load_image(p) for p in BB_FILES]
    over_image, clear_image = load_image(OVER_IMG), load_image(CLEAR_IMG)
    pause_image = load_image(PAUSE_IMG)

    # 일시정지 화면의 소리 조절 UI와, 조준 안내 문구
    white4 = (255, 255, 255, 255)
    make_text_img(OUT('dg_ui_bgm.png'), '배경음악', 'Music', 28, white4, 160, 44, 3)
    make_text_img(OUT('dg_ui_sfx.png'), '효과음', 'SFX', 28, white4, 160, 44, 3)
    make_text_img(OUT('dg_ui_volhint.png'), '↑↓ 선택     ←→ 소리 조절', 'UP/DOWN select    LEFT/RIGHT volume',
                  24, (200, 220, 255, 255), 560, 40, 3)
    make_text_img(OUT('dg_ui_aimhint.png'), '우클릭으로 조준하세요', 'Hold right-click to aim',
                  28, (255, 230, 120, 255), 480, 44, 4)
    ui_bgm, ui_sfx = load_image(OUT('dg_ui_bgm.png')), load_image(OUT('dg_ui_sfx.png'))
    ui_volhint, ui_aimhint = load_image(OUT('dg_ui_volhint.png')), load_image(OUT('dg_ui_aimhint.png'))
    vbar_fg = load_image(BAR_FG)
    pct_imgs = {}
    vui = {'row': 0}

    def pct_img(p):
        if p not in pct_imgs:
            path = OUT(f'dg_ui_pct{p}.png')
            make_text_img(path, f'{p}%', f'{p}%', 26, white4, 90, 40, 3)
            pct_imgs[p] = load_image(path)
        return pct_imgs[p]
    dim_image, flash_image = load_image(DIM_IMG), load_image(FLASH_IMG)
    spark_image, white_image = load_image(SPARK_IMG), load_image(WHITE_IMG)
    ring_image, ray_image = load_image(RING_IMG), load_image(RAY_IMG)
    vignette_image = load_image(VIGNETTE_IMG)
    gauge_bg, gauge_fg, gauge_ready = load_image(BAR_BG), load_image(GAUGE_FG), load_image(GAUGE_READY)
    heart_full, heart_empty = load_image(HEART_FULL), load_image(HEART_EMPTY)
    IM = SimpleNamespace(
        door_c=load_image(door_info['closed'][0]), door_o=load_image(door_info['open'][0]),
        go=L('dg_go.png'),
        phase=[None, load_image(BANNER_IMGS[1]), load_image(BANNER_IMGS[2])],
        floors=[L(f'dg_banner_{i + 1}.png') for i in range(TOTAL_FLOORS)],
        clear=L('dg_banner_clear.png'),
        tags=[L(f'dg_tag_{i + 1}.png') for i in range(TOTAL_FLOORS)])

    player = Player(sprites, front_size, back_size)
    Bullet.setup(bullet_sizes, player.shadow)
    if shadow_info['ok']:
        ShadowBullet.setup(shadow_info)

    g = SimpleNamespace()
    g.diff = DEFAULT_DIFFICULTY
    g.boss = None
    g.shake_t = g.shake_dur = g.shake_amp = 0.0
    parts, fx, enemies, shots, bullets, boss_bullets = [], [], [], [], [], []
    noboss = SimpleNamespace(alive=False, x=0, y=0, radius=0)    # 던전 층에서 총알이 보스를 맞히지 않게

    def snd(name, fallback=None):
        if name in Sound.sfx:
            Sound.play(name)
        elif fallback:
            Sound.play(fallback)

    def shake(dur, amp):
        cur = g.shake_amp * (g.shake_t / g.shake_dur) if g.shake_dur > 0 else 0.0
        if amp >= cur:                      # 지금 흔들리는 것보다 센 것만 덮어씀 (약한 흔들림이 겹쳐 어지러운 것 방지)
            g.shake_t, g.shake_dur, g.shake_amp = dur, dur, amp

    def sparks(x, y, n):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(80, 280)
            life = random.uniform(0.3, 0.6)
            parts.append([x, y, math.cos(a) * sp, math.sin(a) * sp, life, life])

    ctx = SimpleNamespace(player=player, shots=shots, sparks=sparks, shake=shake, play=snd, bullets=bullets)

    def keep_away(b):
        """몬스터를 맞히거나 방패에 튕긴 총알이 플레이어 발밑 가까이에 떨어지면 바로 다시 주워져서 총알이 무한처럼 보임.
        최소 KILL_HOP_MIN 만큼 떨어진 곳에 떨어지게 밀어 줌"""
        fx_, fy_ = player.x, player.y - player.base_h / 2
        dd = math.hypot(b.lx - fx_, b.ly - fy_)
        if dd < KILL_HOP_MIN:
            if dd < 1:
                ux, uy = b.lx - b.sx, b.ly - b.sy
                n = math.hypot(ux, uy) or 1.0
                ux, uy = ux / n, uy / n
            else:
                ux, uy = (b.lx - fx_) / dd, (b.ly - fy_) / dd
            b.lx, b.ly = fx_ + ux * KILL_HOP_MIN, fy_ + uy * KILL_HOP_MIN

    def set_banner(img, dur, w=520):
        g.banner_img, g.banner_t, g.banner_dur, g.banner_w = img, dur, dur, w

    def find_spot():
        for _ in range(60):
            a = random.uniform(0, 2 * math.pi)
            r = random.uniform(0.35, 0.85)
            x = ARENA_CENTER_X + math.cos(a) * ARENA_RX * r
            y = ARENA_CENTER_Y + math.sin(a) * ARENA_RY * r
            if math.hypot(x - player.x, y - player.y) < SPAWN_MIN_DIST:
                continue
            if any(math.hypot(x - e.x, y - e.y) < 90 for e in enemies):
                continue
            if y > DOOR_Y - DOOR_BLOCK - MON_DOOR_GAP - 30:      # 문 근처에서는 소환하지 않음
                continue
            return x, y
        return clamp_arena(2 * ARENA_CENTER_X - player.x, 2 * ARENA_CENTER_Y - player.y, 40)

    def split_slime(s):
        """처치된 큰 슬라임이 반 크기 슬라임 2마리로 분열 (작은 슬라임은 더 안 갈라짐)"""
        for sgn in (-1, 1):
            m = CLASSES['slime'](s.x, s.y, A)
            m.gen = 1
            m.dh *= 0.7
            m.dw *= 0.7
            m.radius *= 0.7
            m.state, m.t = 'chase', 0.0
            a = random.uniform(0, math.pi) + (0 if sgn < 0 else math.pi)
            m.push = (math.cos(a) * 280, math.sin(a) * 280)
            enemies.append(m)

    def spawn_wave():
        g.wave += 1
        g.wave_timer = 0.0
        mult = DG_COUNT_MULT * DG_DIFF_COUNT.get(DIFFICULTIES[g.diff]['id'], 1.0)
        g.pending = []
        others = 0
        bombers = 0
        for kind, n in FLOORS[g.floor][g.wave].items():
            for _ in range(max(1, round(n * mult))):
                if kind == 'bomber':
                    bombers += 1
                    continue
                others += 1
                x, y = find_spot()
                enemies.append(CLASSES[kind](x, y, A))
        # 폭탄병은 다른 몬스터가 나온 뒤 BOMBER_DELAY초 후에 한 마리씩 차례로 등장
        first = BOMBER_DELAY if others > 0 else 0.0
        for i in range(bombers):
            g.pending.append(first + BOMBER_DELAY * i)
        snd('warning')

    def start_floor(idx):
        g.floor = idx
        if idx >= 1 and floor_kind(idx - 1) == 'boss':
          g.checkpoint = idx                  # 보스층을 깨고 다음 층에 들어가면 여기서 저장                 # 보스층에 들어가면 여기서 저장
        g.wave = -1
        g.wave_timer = FIRST_WAVE_DELAY
        g.pending = []                        # 아직 나오지 않은 폭탄병들의 남은 대기 시간
        g.cleared = False
        g.door_t = None                       # 맵 속 문: None = 닫힘, 숫자 = 열리기 시작한 뒤 지난 시간
        g.fin_t = None                        # 마지막 보스를 잡은 뒤 문이 열리는 동안의 시간
        g.nobullet = 0.0
        enemies.clear()
        shots.clear()
        bullets.clear()
        boss_bullets.clear()
        parts.clear()
        fx.clear()
        player.dashing = False
        player.ammo = MAX_AMMO                    # 새 층에서는 총알이 돌아옴
        player.slow_until = player.dash_block_until = 0.0
        kind = floor_kind(idx)
        if kind == 'shadow' and not shadow_info['ok']:
            print('[던전] 그림자 보스 그림을 만들지 못해 이 층은 기존 보스로 대신합니다')
            kind = 'boss'
        g.kind = kind
        if kind == 'wave':
            g.boss = None
            player.x, player.y = DG_START
            set_banner(IM.floors[idx], 1.8)
        else:                                     # 보스층
            if kind == 'shadow':
                g.boss = ShadowBoss(sprites, front_size, back_size, DIFFICULTIES[g.diff])
            else:
                g.boss = Boss(boss_size, hurt_size, laser_info, DIFFICULTIES[g.diff], phases_ok)
            player.x, player.y = BOSS_START
            set_banner(IM.floors[idx], 2.0, 640)
            if kind != 'shadow':                  # 10층(그림자 보스)은 입장 소리 없음
                snd('boss_enter', 'phase')
        set_floor_bgm({'boss': 'boss', 'shadow': 'final'}.get(kind))      # 5층, 10층만 다른 곡

    def floor_clear():
        g.cleared = True
        g.door_t = 0.0                            # 맵 속 문이 열리기 시작
        shake(0.5, 5)
        g.hp = min(g.max_hp, g.hp + DG_HEAL_PER_FLOOR)
        shots.clear()
        set_banner(IM.clear, 1.8, 640)
        snd('door', 'phase')

    def new_game(i):
        g.diff = i
        player.reset(*DG_START)
        g.max_hp = DIFFICULTIES[i]['player_hp'] + DG_EXTRA_HP
        g.hp = g.max_hp
        g.t = 0.0
        g.inv = -1.0
        g.flash = g.wflash = 0.0
        g.freeze = 0.0
        g.shake_t = g.shake_dur = g.shake_amp = 0.0
        g.banner_t = g.banner_dur = 0.0
        g.banner_img, g.banner_w = None, 520
        g.clear_time = 0.0
        g.spark_acc = 0.0
        g.trans = None
        g.boss = None
        g.kind = 'wave'
        g.nobullet = 0.0
        start_floor(getattr(g, 'checkpoint', 0))

    # 타이틀 화면 (title.py): 난이도를 고르면 그 번호가 돌아옴
    sel = run_title(g.diff)
    if sel is None:
        close_canvas()
        return
    Sound.bgm_volume(BGM_VOL)
    new_game(sel)
    state = 'play'          # play / pause / dying / over / clear
    prev_state = ''

    running = True
    prev = time.time()
    while running:
        now = time.time()
        dt = min(now - prev, 0.05)
        prev = now
        start_idx = None
        go_title = False

        # ---------- 입력 ----------
        for e in get_events():
            if e.type == SDL_QUIT:
                running = False
            elif e.type == SDL_KEYDOWN and e.key == SDLK_ESCAPE:
                running = False
            elif e.type == SDL_KEYDOWN and e.key == SDLK_m:
                toggle_fullscreen()
            elif DEV_MODE and e.type == SDL_KEYDOWN and e.key in (SDLK_n, SDLK_b) and state == 'play':
                g.trans = None
                start_floor(max(0, min(TOTAL_FLOORS - 1, g.floor + (1 if e.key == SDLK_n else -1))))
            elif e.type == SDL_KEYDOWN and e.key == SDLK_p and state in ('play', 'pause'):
                state = 'pause' if state == 'play' else 'play'
            elif state == 'pause' and e.type == SDL_KEYDOWN and e.key in (SDLK_UP, SDLK_DOWN, SDLK_LEFT, SDLK_RIGHT):
                if e.key in (SDLK_UP, SDLK_DOWN):                  # 위/아래: 배경음악 <-> 효과음 선택
                    vui['row'] = 1 - vui['row']
                else:                                              # 좌/우: 소리 크기 10%씩
                    key = ('bgm', 'sfx')[vui['row']]
                    VOL[key] = max(0.0, min(1.0, round(VOL[key] + (0.1 if e.key == SDLK_RIGHT else -0.1), 2)))
                    if key == 'bgm':
                        Sound.bgm_volume(BGM_VOL)
                    else:
                        apply_sfx()
                        Sound.play('reload')
                    save_volume()
            elif e.type == SDL_KEYDOWN and state in ('over', 'clear') and e.key in (SDLK_r, SDLK_t):
                if e.key == SDLK_r:
                    start_idx = g.diff
                else:                                   # T: 타이틀 화면으로
                    go_title = True
            elif state in ('play', 'dying'):
                player.handle_event(e)
                if e.type == SDL_MOUSEBUTTONDOWN and e.button == SDL_BUTTON_LEFT and g.trans is None:
                    if not player.aiming:                          # 우클릭으로 조준 중일 때만 발사
                        g.hint_until = time.time() + 1.4
                    else:
                        b = player.try_fire()
                        if b:
                            b.born = time.time()
                            bullets.append(b)
            else:
                if e.type in (SDL_MOUSEMOTION, SDL_KEYUP, SDL_MOUSEBUTTONUP):
                    player.handle_event(e)

        if go_title:
            sel = run_title(g.diff)
            prev = time.time()
            if sel is None:
                running = False
            else:
                start_idx = sel
                g.checkpoint = 0
                Sound.bgm_volume(BGM_VOL)
        if start_idx is not None and running:
            new_game(start_idx)
            state = 'play'
        boss = g.boss

        # ---------- 히트 스톱 ----------
        frozen = g.freeze > 0 and state in ('play', 'dying')
        if frozen:
            g.freeze = max(0.0, g.freeze - dt)

        # ---------- 층 이동 연출 ----------
        if state == 'play' and g.trans is not None:
            g.trans['t'] += dt
            if g.trans['dir'] == 'out':                  # 문 안으로 걸어 들어감
                k = min(1.0, g.trans['t'] / TRANS_OUT)
                e_ = k * k * (3 - 2 * k)
                player.x = g.trans['sx'] + (DOOR_X - g.trans['sx']) * e_
                player.y = g.trans['sy'] + (DOOR_Y + player.base_h / 2 + 20 - g.trans['sy']) * e_
            if g.trans['dir'] == 'out' and g.trans['t'] >= TRANS_OUT:
                start_floor(g.floor + 1)
                g.trans = {'dir': 'in', 't': 0.0}
                boss = g.boss
            elif g.trans['dir'] == 'in' and g.trans['t'] >= TRANS_IN:
                g.trans = None

        # ---------- 게임 진행 ----------
        if state in ('play', 'dying') and g.trans is None and not frozen:
            if state == 'play':
                g.t += dt
            player.update(dt)
            player.x, player.y = clamp_arena(player.x, player.y)
            if boss is None and not g.cleared:                    # 문이 닫혀 있는 동안은 문 쪽으로 못 감
                lim = DOOR_Y - DOOR_BLOCK
                if player.y > lim:
                    player.y = lim

            if boss is not None:
                # ----- 보스층 -----
                boss.update(dt, player, boss_bullets)
                if boss.phase_event is not None:
                    set_banner(IM.phase[boss.phase_event], 1.6)
                    shake(0.4, 6)
                    boss.phase_event = None
                if boss.laser_fired:
                    thick = bool(boss.lasers and boss.lasers[0].get('thick'))
                    shake(0.5 if thick else 0.3, 11 if thick else 7)
                    boss.laser_fired = False
                if boss.slam:
                    shake(0.35, 9)
                    sparks(boss.x, boss.y, 14)
                    boss.slam = False
            else:
                # ----- 던전 층: 웨이브 -----
                if not g.cleared:
                    if g.wave_timer > 0:
                        g.wave_timer -= dt
                        if g.wave_timer <= 0:
                            spawn_wave()
                    elif g.pending:                   # 아직 안 나온 폭탄병이 있음
                        g.pending = [t - dt for t in g.pending]
                        while g.pending and g.pending[0] <= 0:
                            g.pending.pop(0)
                            x, y = find_spot()
                            enemies.append(CLASSES['bomber'](x, y, A))
                            snd('warning')
                    elif not enemies:
                        if g.wave + 1 < len(FLOORS[g.floor]):
                            g.wave_timer = WAVE_DELAY
                        else:
                            floor_clear()

                for en in enemies:
                    en.update(dt, ctx)
                n = len(enemies)
                for i in range(n):                    # 몬스터끼리 부드럽게 밀어냄
                    a = enemies[i]
                    if a.state in ('spawn', 'dying'):
                        continue
                    for j in range(i + 1, n):
                        c = enemies[j]
                        if c.state in ('spawn', 'dying'):
                            continue
                        dx, dy = c.x - a.x, c.y - a.y
                        d = math.hypot(dx, dy)
                        m = (a.radius + c.radius) * (1.25 if a.kind == c.kind else 0.95)   # 같은 종류는 더 퍼짐
                        if d < m:
                            if d < 0.01:
                                ang = random.uniform(0, 2 * math.pi)
                                dx, dy, d = math.cos(ang), math.sin(ang), 1.0
                            push = (m - d) * 0.5 * min(1.0, 8 * dt)
                            ux, uy = dx / d, dy / d
                            a.x -= ux * push
                            a.y -= uy * push
                            c.x += ux * push
                            c.y += uy * push
                for en in enemies:                    # 몬스터도 문 앞 선을 못 넘음 (문 안쪽으로 못 들어감)
                    if en.y > DOOR_Y - DOOR_BLOCK - MON_DOOR_GAP:
                        en.y = DOOR_Y - DOOR_BLOCK - MON_DOOR_GAP
                for s in shots:
                    s.update(dt)
                shots[:] = [s for s in shots if s.alive]

            # ----- 총알 -----
            foot_x, foot_y = player.x, player.y - player.base_h / 2
            if boss is not None:
                front = bullet_front_limit(boss.radius)
            elif not g.cleared:
                front = DOOR_Y - DOOR_BLOCK            # 문이 닫힌 동안 총알도 플레이어가 갈 수 있는 곳까지만
            else:
                front = 9999
            tgt = boss if boss is not None else noboss
            for b in bullets:
                px_, py_ = b.x, b.y
                was = b.state
                b.update(dt, tgt)
                hit_boss = boss is not None and was == 'fly' and b.state == 'hop'

                if b.state == 'fly' and enemies:                       # 몬스터에게 맞았는지
                    best, hit_e = 2.0, None
                    for en in enemies:
                        if not en.targetable():
                            continue
                        u = seg_hit(px_, py_, b.x, b.y, en.hx, en.hy, en.radius + BULLET_RADIUS)
                        if u is not None and u < best:
                            best, hit_e = u, en
                    if hit_e is not None:
                        cx = px_ + (b.x - px_) * best
                        cy = py_ + (b.y - py_) * best
                        b.x, b.y = cx, cy
                        if hit_e.bullet_result(px_, py_) == 'block':    # 방패에 막힘
                            hit_e.on_block(math.atan2(cy - py_, cx - px_))
                            a = math.atan2(py_ - hit_e.hy, px_ - hit_e.hx) + random.uniform(-0.5, 0.5)
                            d = random.uniform(110, 190)
                            b.hop_to(cx + math.cos(a) * d, cy + math.sin(a) * d)
                            keep_away(b)
                            sparks(cx, cy, 8)
                            shake(0.12, 3)
                            snd('block', 'hit')
                        else:                                            # 처치
                            hit_e.die()
                            if hit_e.kind == 'slime' and getattr(hit_e, 'gen', 0) == 0:
                                split_slime(hit_e)
                            a = math.atan2(player.y - hit_e.hy, player.x - hit_e.hx) + random.uniform(-0.9, 0.9)
                            d = random.uniform(70, 150)
                            b.hop_to(cx + math.cos(a) * d, cy + math.sin(a) * d)
                            keep_away(b)
                            sparks(hit_e.x, hit_e.y, 14)
                            shake(0.15, 4)
                            snd('hit')
                            g.freeze = max(g.freeze, DG_HITSTOP)

                if b.state == 'hop':
                    b.lx, b.ly = clamp_arena(b.lx, min(b.ly, front), BULLET_MARGIN)
                elif b.state == 'fly' and boss is not None and boss.alive and b.vy > 0 and b.y > BOSS_BASE_Y:
                    # 보스를 지나쳐 뒤로 가려는 총알: 튕겨서 보스 앞쪽에 떨어뜨림
                    b.hop_to(b.x, front - random.uniform(10, 90))
                    b.lx, b.ly = clamp_arena(b.lx, b.ly, BULLET_MARGIN)
                elif b.state == 'fly' and arena_d(b.x, b.y) > 1.0:
                    b.x, b.y = clamp_arena(b.x, min(b.y, front), BULLET_MARGIN)
                    b.state, b.height, b.spin = 'landed', 0.0, 0.0
                elif b.state == 'landed':
                    b.x, b.y = clamp_arena(b.x, min(b.y, front), BULLET_MARGIN)
                    if boss is None and player.ammo < MAX_AMMO and DG_MAGNET_RANGE > 0:   # 던전 층: 가까우면 끌려옴
                        d = math.hypot(foot_x - b.x, foot_y - b.y)
                        if 1 < d < DG_MAGNET_RANGE:
                            step = min(d, DG_MAGNET_SPEED * dt)
                            b.x += (foot_x - b.x) / d * step
                            b.y += (foot_y - b.y) / d * step

                if hit_boss:                                              # 보스에 맞은 순간
                    if boss.alive:
                        sparks(b.x, b.y, 10)
                        shake(0.12, 4)
                        g.freeze = max(g.freeze, HITSTOP_HIT)
                    else:
                        sparks(boss.x, boss.y, 20)
                        shake(0.3, 8)
                        g.freeze = max(g.freeze, HITSTOP_KILL)

                if b.alive and time.time() - getattr(b, 'born', -9.0) > PICKUP_DELAY and player.pickup(b):                          # 총알을 주움 (도둑이 막 훔쳐 간 총알은 못 줍음)
                    fx.append([b.x, b.y, 0.0])
                    sparks(b.x, b.y, 8)
                    b.alive = False
            bullets[:] = [b for b in bullets if b.alive]
            enemies[:] = [en for en in enemies if en.alive]

            # ----- 총알이 하나도 없는 채로 오래 지나면(도둑이 계속 훔치는 등) 한 발을 돌려줌 -----
            if state == 'play' and player.ammo == 0 and not bullets:
                g.nobullet += dt
                if g.nobullet >= NOBULLET_RESPAWN:
                    g.nobullet = 0.0
                    player.ammo = MAX_AMMO
                    fx.append([player.x, player.y - player.base_h / 2, 0.0])
                    sparks(player.x, player.y, 10)
                    snd('reload')
            else:
                g.nobullet = 0.0

            # ----- 보스가 마지막 한 발을 맞은 순간: 쓰러지는 연출 시작 -----
            if boss is not None and not boss.alive and state == 'play':
                state = 'dying'
                g.clear_time = g.t
                g.spark_acc = 0.0
                boss_bullets.clear()

            if AMMO_LOG and player.ammo != getattr(g, 'last_ammo', player.ammo):
                print(f'[탄환] {g.last_ammo} -> {player.ammo}  ({g.floor + 1}층, 바닥/날아가는 총알 {len(bullets)}개)')
            g.last_ammo = player.ammo

            # ----- 플레이어 피격 -----
            hx, hy = player.x, player.y - player.base_h * HIT_OFFSET
            vulnerable = state == 'play' and (not player.dashing) and g.t >= g.inv
            got_hit = by_boss = False

            for bb in boss_bullets:
                bb.update(dt, player)
                if vulnerable and not got_hit and math.hypot(bb.x - hx, bb.y - hy) < HIT_RADIUS:
                    got_hit = True
            boss_bullets[:] = [bb for bb in boss_bullets if bb.alive]

            if boss is not None and boss.alive and vulnerable and not got_hit and \
                    math.hypot(boss.x - hx, boss.y - hy) < boss.radius + HIT_RADIUS:
                got_hit = by_boss = True
            if boss is not None and vulnerable and not got_hit and boss.laser_hit(hx, hy):
                got_hit = True
            if vulnerable and not got_hit:
                for s in shots:
                    if s.touch(hx, hy, HIT_RADIUS):
                        got_hit = True
                        break
            if vulnerable and not got_hit:
                for en in enemies:
                    if en.dangerous_touch(hx, hy, HIT_RADIUS):
                        got_hit = True
                        break

            if got_hit:
                g.hp -= 1
                snd('player_hit')
                g.flash = 0.55
                shake(0.4, 10)
                g.freeze = max(g.freeze, HITSTOP_PLAYER)
                if g.hp <= 0:
                    pct = None
                    if boss is not None:
                        pct = max(1, math.ceil(100 * boss.hp / boss.max_hp))
                    make_over_panel(g.floor, pct, g.t, DIFFICULTIES[g.diff])
                    over_image = load_image(OVER_IMG)
                    state = 'over'
                else:
                    g.inv = g.t + INV_TIME
                    boss_bullets[:] = [bb for bb in boss_bullets
                                       if math.hypot(bb.x - hx, bb.y - hy) > CLEAR_RADIUS]
                    shots[:] = [s for s in shots if getattr(s, 'ground', False) or
                                math.hypot(s.x - hx, s.y - hy) > CLEAR_RADIUS]
                    if by_boss:                      # 보스 몸에 부딪히면 밖으로 튕겨 나감
                        d = math.hypot(hx - boss.x, hy - boss.y) or 1.0
                        r = boss.radius + HIT_RADIUS + 40
                        player.x = boss.x + (hx - boss.x) / d * r
                        player.y = boss.y + (hy - boss.y) / d * r + player.base_h * HIT_OFFSET
                        player.x, player.y = clamp_arena(player.x, player.y)

            # ----- 문으로 들어가기 -----
            if state == 'play' and boss is None and g.cleared and g.trans is None and \
                    math.hypot(player.x - DOOR_X, player.y - DOOR_Y) < DOOR_R:
                g.trans = {'dir': 'out', 't': 0.0, 'sx': player.x, 'sy': player.y}
                snd('stop')

            # ----- 쓰러지는 연출: 불꽃이 계속 터지다가 마지막에 크게 폭발 -----
            if state == 'dying':
                if g.fin_t is None:
                    g.spark_acc += dt
                    while g.spark_acc >= 0.07:
                        g.spark_acc -= 0.07
                        sparks(boss.x + random.uniform(-70, 70), boss.y + random.uniform(-60, 60), 4)
                        shake(0.12, 4)
                if boss.die_t >= DEATH_TIME:
                    if g.fin_t is None:
                        boss.dying = False
                        sparks(boss.x, boss.y, 70)
                        shake(0.6, 12)
                        g.wflash = 1.0
                        if g.floor < TOTAL_FLOORS - 1:             # 중간 보스: 쓰러지면 문이 열림
                            g.boss = boss = None
                            state = 'play'
                            floor_clear()
                        else:                                      # 최종 보스: 문이 열리는 걸 보여 준 뒤 클리어
                            g.fin_t = 0.0
                            g.door_t = 0.0
                            snd('door', 'phase')
                    else:
                        g.fin_t += dt
                        if g.fin_t >= FINAL_DOOR_TIME:
                            key = DIFFICULTIES[g.diff]['id']
                            best = load_best()
                            old = best.get(key)
                            new_rec = old is None or g.clear_time < old
                            if new_rec:
                                best[key] = g.clear_time
                                save_best(best)
                            make_clear_panel(g.clear_time, old if old is not None else g.clear_time,
                                             new_rec, DIFFICULTIES[g.diff])
                            clear_image = load_image(CLEAR_IMG)
                            state = 'clear'

        # ---------- 효과 갱신 (일시정지에서는 멈추고, 히트 스톱 중에도 멈춤) ----------
        if state != 'pause':
            fdt = 0.0 if frozen else dt
            g.shake_t = max(0.0, g.shake_t - fdt)
            g.flash = max(0.0, g.flash - fdt * 1.6)
            g.wflash = max(0.0, g.wflash - fdt * 1.2)
            g.banner_t = max(0.0, g.banner_t - fdt)
            if g.door_t is not None:
                g.door_t += fdt
            for p in parts:
                p[0] += p[2] * fdt
                p[1] += p[3] * fdt
                k = max(0.0, 1 - 4 * fdt)
                p[2] *= k
                p[3] *= k
                p[4] -= fdt
            parts[:] = [p for p in parts if p[4] > 0]
            for f in fx:
                f[2] += fdt
            fx[:] = [f for f in fx if f[2] < PICKUP_FX_TIME]

        # ---------- 상태가 바뀐 순간 소리 ----------
        if state != prev_state:
            if state == 'over':
                Sound.play('gameover')
            elif state == 'clear':
                Sound.play('clear')
            Sound.bgm_volume(BGM_VOL if state in ('play', 'dying') else BGM_VOL_END)
            prev_state = state

        # ---------- 그리기 ----------
        ox = oy = 0.0
        if g.shake_t > 0 and g.shake_dur > 0:
            k = g.shake_t / g.shake_dur
            ox = random.uniform(-1, 1) * g.shake_amp * k
            oy = random.uniform(-1, 1) * g.shake_amp * k

        clear_canvas()
        bg_image = (bg_red if g.floor < 5 else bg_purple) or bg_old
        if bg_image:
            bg_image.draw(CANVAS_W // 2 + ox, CANVAS_H // 2 + oy, CANVAS_W + 40, CANVAS_H + 40)
        # 맵 속 문 열리기 (모든 층). 닫힌 모습은 맵 그림에 이미 있음
        md = mdoor_info.get(map_name(g.floor))
        if md is not None and g.door_t is not None:
            for key, cx, cy, w, h, op in door_parts(md['spec'], min(1.0, g.door_t / DOOR_OPEN_TIME),
                                                    CANVAS_W, CANVAS_H, time.time()):
                im = mdoor_imgs[map_name(g.floor)][key]
                im.opacify(op)
                im.draw(cx + ox, cy + oy, w, h)
        if boss is None:
            tone = FLOOR_DIM[min(g.floor, len(FLOOR_DIM) - 1)]
        else:
            tone = SHADOW_DIM if g.kind == 'shadow' else BOSS_DIM
        if tone > 0:
            dim_image.opacify(tone)
            dim_image.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)

        if boss is None:                                   # 출구 문
            if g.cleared:
                pulse = 0.5 + 0.5 * math.sin(time.time() * 5)
                ring_image.opacify(0.10 + 0.12 * pulse)       # 바닥 링은 아주 은은하게
                ring_image.draw(DOOR_X + ox, DOOR_Y + 6 + oy, 130 + 14 * pulse, 56 + 6 * pulse)
                IM.go.opacify(0.6 + 0.4 * pulse)
                IM.go.draw(DOOR_X + ox, DOOR_Y - 40 + oy, 200, 23)        # 안내 글자는 문 아래쪽 (한 번만)

        # 화면 흔들림: 그리는 동안만 위치를 옮겼다가 되돌림
        shifted = [player] + bullets + boss_bullets + ([boss] if boss is not None else [])
        for o in shifted:
            o.x += ox
            o.y += oy

        for b in bullets:
            if b.on_ground:
                b.draw()

        for s in shots:                                    # 바닥에 깔린 것(거미줄)은 몬스터 아래에
            if getattr(s, 'ground', False):
                s.draw(ox, oy)

        if boss is not None:
            boss.draw_warning()
            if isinstance(boss, Boss):                 # 5층 보스: 레이저를 보스 뒤에 깔아서 입에서 나오는 것처럼 보이게
                boss.draw_lasers(ox, oy, 'under')
                boss.draw()
                boss.draw_lasers(ox, oy, 'over')
            else:
                boss.draw()
                boss.draw_lasers(ox, oy)
        for en in enemies:
            en.draw_warn(ox, oy)
        for en in sorted(enemies, key=lambda q: -q.y):     # 아래쪽 몬스터가 위에 그려짐
            en.draw(ox, oy)
        for s in shots:
            if not getattr(s, 'ground', False):
                s.draw(ox, oy)
        for bb in boss_bullets:
            bb.draw(boss_bullet_imgs, bb_metas)

        for p in parts:
            f = p[4] / p[5]
            spark_image.opacify(f)
            sz = 4 + 12 * f
            spark_image.draw(p[0] + ox, p[1] + oy, sz, sz)

        if state in ('play', 'dying') and g.trans is None and time.time() < player.slow_until:   # 거미줄에 걸림
            A.web.opacify(0.6 + 0.3 * math.sin(time.time() * 10))
            A.web.draw(player.x, player.y - player.base_h / 2 + 4, 64, 64)

        blink = state == 'play' and g.t < g.inv and int(g.t * 14) % 2 == 0
        if g.trans is not None and g.trans['dir'] == 'out':      # 문으로 걸어 들어가며 작아짐
            k = min(1.0, g.trans['t'] / TRANS_OUT)
            s = 1.0 - 0.5 * k
            player.shadow.opacify(SHADOW_ALPHA * (1 - k))
            player.shadow.draw(player.x, player.y - player.base_h / 2 + 4,
                               player.base_w * 0.9 * s, player.base_w * 0.3 * s)
            player._set_opacity(1.0)
            player._draw_at(player.x, player.y, 'up', abs(math.sin(k * 16)) * BOUNCE_PX, 0.0, s, s, int(k * 10) % 4)
        elif not blink:
            player.draw()

        if state in ('play', 'dying') and g.trans is None:  # 대쉬 게이지
            ready = min(1.0, (time.time() - player.last_dash) / DASH_COOLDOWN)
            gx, gy = player.x, player.y - player.base_h / 2 - 9
            gauge_bg.opacify(0.8)
            gauge_bg.draw(gx, gy, GAUGE_W + 4, 8)
            if time.time() < player.dash_block_until:                  # 대쉬 봉인: 빨간 게이지
                A.red.opacify(0.9)
                A.red.draw(gx, gy, GAUGE_W, 4)
            elif ready >= 1.0:
                gauge_ready.opacify(0.65)
                gauge_ready.draw(gx, gy, GAUGE_W, 4)
            else:
                gauge_fg.opacify(1.0)
                gauge_fg.draw(gx - GAUGE_W / 2 + GAUGE_W * ready / 2, gy, max(1, GAUGE_W * ready), 4)

        for b in bullets:
            if not b.on_ground:
                b.draw()

        for o in shifted:
            o.x -= ox
            o.y -= oy

        for f in fx:                                       # 총알 줍는 효과
            k = f[2] / PICKUP_FX_TIME
            a = 1 - k
            rw = 40 + 120 * k
            ring_image.opacify(a)
            ring_image.draw(f[0] + ox, f[1] + oy - 4, rw, rw * 0.5)
            ray_image.opacify(a)
            for ang in (-0.35, 0.0, 0.35):
                ray_image.clip_composite_draw(0, 0, 24, 96, -ang, '',
                                              f[0] + ox + ang * 90 * k, f[1] + oy + 30 + 60 * k,
                                              14, 56 * (0.5 + 0.5 * k))

        danger = state in ('play', 'dying') and 0 < g.hp <= DANGER_HP
        beat = max(0.0, math.sin(time.time() * 6.5)) ** 3
        if danger:
            vignette_image.opacify(0.22 + 0.45 * beat)
            vignette_image.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)

        player.draw_aim()
        for i in range(MAX_AMMO):
            Bullet.draw_icon(30 + i * 30, CANVAS_H - 30, 1.0 if i < player.ammo else 0.2)
        for i in range(g.max_hp):
            size = 30 + (7 * beat if (danger and i < g.hp) else 0)
            (heart_full if i < g.hp else heart_empty).draw(30 + i * 34, CANVAS_H - 66, size, size)
        IM.tags[min(g.floor, TOTAL_FLOORS - 1)].draw(CANVAS_W - 100, CANVAS_H - 28)

        if boss is not None:
            boss.draw_warning_hud()

        if g.banner_t > 0 and g.banner_img is not None:
            r = g.banner_t
            a = max(0.0, min(1.0, r / 0.4, (g.banner_dur - r) / 0.15))
            g.banner_img.opacify(a)
            g.banner_img.draw(CANVAS_W // 2, int(CANVAS_H * 0.62), g.banner_w, 120)

        if g.flash > 0:
            flash_image.opacify(min(0.35, g.flash * 0.6))
            flash_image.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)
        if g.wflash > 0:
            white_image.opacify(min(0.85, g.wflash))
            white_image.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)

        if g.trans is not None:                            # 층 이동: 걷는 동안은 밝고 뒤쪽에서 어두워짐
            if g.trans['dir'] == 'out':
                fa = max(0.0, min(1.0, (g.trans['t'] / TRANS_OUT - 0.45) / 0.55))
            else:
                fa = max(0.0, 1.0 - g.trans['t'] / TRANS_IN)
            dim_image.opacify(fa)
            dim_image.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)

        if state == 'play' and time.time() < getattr(g, 'hint_until', 0.0):      # 조준 안 하고 클릭했을 때 안내
            ui_aimhint.opacify(min(1.0, (g.hint_until - time.time()) * 3))
            ui_aimhint.draw(CANVAS_W // 2, 70)

        if state == 'pause':
            dim_image.opacify(0.45)
            dim_image.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)
            pause_image.draw(CANVAS_W // 2, CANVAS_H // 2)
            dim_image.opacify(0.55)                                    # 소리 조절 판
            dim_image.draw(CANVAS_W // 2, 95, 560, 150)
            for row, (lab, key, ry) in enumerate(((ui_bgm, 'bgm', 135), (ui_sfx, 'sfx', 85))):
                if vui['row'] == row:
                    white_image.opacify(0.14)
                    white_image.draw(CANVAS_W // 2, ry, 540, 40)
                lab.draw(190, ry)
                gauge_bg.draw(480, ry, 266, 18)
                if VOL[key] > 0:
                    vbar_fg.draw(480 - 130 + 130 * VOL[key], ry, 260 * VOL[key], 12)
                pct_img(int(round(VOL[key] * 100))).draw(685, ry)
            ui_volhint.draw(CANVAS_W // 2, 40)
        elif state == 'over':
            over_image.draw(CANVAS_W // 2, CANVAS_H // 2)
        elif state == 'clear':
            clear_image.draw(CANVAS_W // 2, CANVAS_H // 2)

        update_canvas()
        delay(0.01)

    close_canvas()


if __name__ == '__main__':
    main()