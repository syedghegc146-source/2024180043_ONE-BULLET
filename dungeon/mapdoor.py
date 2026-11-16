"""맵 그림 속 문을 열리게 만드는 모듈.

맵 그림(bg_red.png, bg_purple.png)에서 문 부분을 잘라 '왼쪽 문짝 / 오른쪽 문짝 / 문 안쪽 빛 / 번쩍임' 그림을 자동으로 만든다.
문 위치는 아래 MAP_DOORS 의 비율(그림 전체 가로, 세로를 0~1로 본 값)로 정한다.
  x0, x1 : 문 왼쪽 끝, 오른쪽 끝 (가로 비율, 왼쪽이 0)
  y0, y1 : 문 맨 위, 맨 아래 (세로 비율, 위쪽이 0)
문이 어긋나 보이면 이 숫자만 조금씩 바꾸세요. 그림 파일을 바꿔도 새로 자동 생성됩니다.
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw

MAP_DOORS = {
    # 붉은 맵: 두 짝 나무문
    'red': dict(file='bg_red.png', x0=0.443, x1=0.566, y0=0.032, y1=0.252, shape='round',
                dark=(14, 5, 6), hot=(255, 120, 45), glow=(255, 140, 60)),
    # 보라 맵: 룬 문
    'purple': dict(file='bg_purple.png', x0=0.466, x1=0.533, y0=0.021, y1=0.154, shape='point',
                   dark=(22, 8, 48), hot=(235, 190, 255), glow=(200, 140, 255)),
}
SIG_VER = 1


def _file_sig(path):
    try:
        st = os.stat(path)
        return f'{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}'
    except OSError:
        return None


def _mask(w, h, shape):
    m = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(m)
    if shape == 'round':                       # 둥근 아치
        d.ellipse((0, 0, w - 1, w - 1), fill=255)
        d.rectangle((0, w // 2, w - 1, h - 1), fill=255)
    else:                                       # 뾰족한 아치
        d.polygon([(0, h - 1), (0, int(h * 0.38)), (w // 2, 0), (w - 1, int(h * 0.38)), (w - 1, h - 1)], fill=255)
    return m


def _inner(w, h, mask, dark, hot, shape):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (xx - (w - 1) / 2) / (w / 2)
    v = yy / max(1, h - 1)
    if shape == 'round':
        inten = np.exp(-(u * u) / 0.45) * (0.20 + 0.80 * v)
    else:
        inten = np.exp(-(u * u) / 0.65) * (0.45 + 0.55 * (1 - np.abs(v - 0.55)))
    inten = np.clip(inten * (0.8 if shape == 'round' else 1.0), 0, 1)[..., None]
    col = np.array(dark, np.float32) * (1 - inten) + np.array(hot, np.float32) * inten
    a = np.array(mask, np.float32)[..., None]
    return Image.fromarray(np.concatenate([col, a], axis=2).astype(np.uint8), 'RGBA')


def _glow(size, color):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    r = np.sqrt(((xx - size / 2) / (size / 2)) ** 2 + ((yy - size / 2) / (size / 2)) ** 2)
    a = np.clip(1 - r, 0, 1) ** 2
    out = np.zeros((size, size, 4), np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = color
    out[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(out, 'RGBA')


def prepare_map_doors(find, out):
    """find(name)  : 맵 파일 이름 -> 경로, out(name): 만든 파일을 둘 경로.
    돌려주는 값: {'red': {...}, 'purple': {...}}  (맵 그림이 없는 항목은 빠짐)"""
    sig_file = out('dg_mdoor_sig.json')
    try:
        with open(sig_file, 'r', encoding='utf-8') as f:
            old = json.load(f)
    except Exception:
        old = {}
    res, new = {}, {}
    for name, spec in MAP_DOORS.items():
        src = find(spec['file'])
        if not os.path.exists(src):
            continue
        files = {k: out(f'dg_mdoor_{name}_{k}.png') for k in ('L', 'R', 'in', 'glow')}
        key = f"{_file_sig(src)}|{SIG_VER}|{spec['x0']},{spec['x1']},{spec['y0']},{spec['y1']},{spec['shape']}"
        new[name] = key
        size = None
        if old.get(name) == key and all(os.path.exists(p) for p in files.values()):
            with Image.open(files['in']) as im:
                size = im.size
        else:
            img = Image.open(src).convert('RGB')
            W, H = img.size
            x0, x1 = int(spec['x0'] * W), int(spec['x1'] * W)
            y0, y1 = int(spec['y0'] * H), int(spec['y1'] * H)
            w, h = x1 - x0, y1 - y0
            crop = img.crop((x0, y0, x1, y1)).convert('RGBA')
            crop.putalpha(_mask(w, h, spec['shape']))
            half = w // 2
            crop.crop((0, 0, half, h)).save(files['L'])
            crop.crop((half, 0, w, h)).save(files['R'])
            _inner(w, h, _mask(w, h, spec['shape']), spec['dark'], spec['hot'], spec['shape']).save(files['in'])
            _glow(256, spec['glow']).save(files['glow'])
            size = (w, h)
        res[name] = dict(files=files, spec=spec, size=size)
    try:
        with open(sig_file, 'w', encoding='utf-8') as f:
            json.dump(new, f)
    except Exception:
        pass
    return res


def door_parts(spec, p, cw, ch, t=0.0):
    """문 열림 진행도 p(0~1)에 따라 그려야 할 것들을 돌려준다. 좌표는 게임 화면 기준(y는 위쪽이 큼).
    각 항목: (그림 종류, 중심 x, 중심 y, 가로, 세로, 투명도). 그리는 순서대로 들어 있다.
    맵 그림은 (cw+40) x (ch+40) 크기로 -20 위치부터 그려지므로 같은 식으로 좌표를 바꾼다."""
    bw, bh = cw + 40, ch + 40
    gx0, gx1 = spec['x0'] * bw - 20, spec['x1'] * bw - 20
    gyt, gyb = (ch + 20) - spec['y0'] * bh, (ch + 20) - spec['y1'] * bh
    w, h = gx1 - gx0, gyt - gyb
    cx, cy = (gx0 + gx1) / 2, (gyt + gyb) / 2
    e = 1 - (1 - p) ** 3                                  # 처음에 빨리 열리고 끝에서 천천히
    flare = math.sin(math.pi * min(1.0, p * 1.4)) if p < 0.72 else 0.0   # 열리는 순간 번쩍임
    settle = 0.35 + 0.1 * math.sin(t * 3)                 # 다 열린 뒤 은은한 빛
    out = []
    if p > 0:
        out.append(('in', cx, cy, w, h, 1.0))
    lw = w / 2 * (1 - 0.88 * e)
    out.append(('L', gx0 + lw / 2, cy, lw, h, 1.0))
    out.append(('R', gx1 - lw / 2, cy, lw, h, 1.0))
    if p > 0:
        g_op = max(flare * 0.9, settle * e)
        out.append(('glow', cx, cy - h * 0.1, w * (1.6 + 1.2 * e), h * (1.4 + 0.8 * e), min(1.0, g_op)))
        out.append(('glow', cx, gyb - 6, w * (2.2 + 1.8 * e), h * 0.55, min(1.0, settle * e * 1.4)))   # 바닥에 번지는 빛
    return out
