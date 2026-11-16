"""5층 보스 동작 그림(떠다니기 / 공격 / 피격·포효·돌진)을 게임에서 쓸 수 있게 자동으로 다듬는 모듈.

넣어야 하는 그림 (main.py 옆, 또는 image 폴더에, 배경은 흰색):
  boss_float.png   떠다니기 4프레임 (가로 한 줄)
  boss_attack.png  공격 4프레임 (평소 -> 웅크림 -> 입 벌림 -> 평소)
  boss_pose.png    3프레임 (피격 -> 포효 -> 돌진 자세)
세 그림 중 없는 것이 있어도 되고, 하나도 없으면 예전 보스 그림을 그대로 씁니다.

하는 일: 흰 배경과 워터마크, 바닥 그림자 지우기 -> 그림마다 크기 맞추기 -> 발 위치 맞추기 -> 1단계/2단계/3단계 색(눈, 몸) 만들기
결과: boss_anim_p0.png, boss_anim_p1.png, boss_anim_p2.png (+ boss_anim_meta.json). 그림을 바꾸면 알아서 다시 만들어집니다.
"""
import json
import os

import numpy as np
from PIL import Image, ImageFilter

from walkanim import _alpha_from_white, _split_columns, _spread

# (파일 이름, 프레임 수, 바닥 그림자를 지울지)
SHEETS = [('float', 'boss_float.png', 4, False),
          ('attack', 'boss_attack.png', 4, False),
          ('pose', 'boss_pose.png', 3, True)]
# 시트마다 '평소 크기' 기준이 되는 프레임 번호 (None이면 모든 프레임의 가운데 값). 크기를 서로 맞출 때 씀
REF_FRAME = {'float': None, 'attack': 0, 'pose': 1}
# 아틀라스 안에서의 프레임 번호
F_FLOAT, F_ATTACK, F_POSE = 0, 4, 8
PAD = 6
ANIM_VER = 2
# 단계별 (몸에 섞을 색의 비율, 섞을 색, 눈 색) - boss.py 의 prepare_boss_phases 와 같은 값
PHASE_TINT = [(0.0, (0, 0, 0), None), (0.15, (200, 30, 40), (255, 120, 30)), (0.32, (150, 10, 35), (255, 40, 40))]


def _main_blob(alpha):
    """덩어리 중 몸통(가운데 근처)과 이어진 것만 남긴다. 떨어진 워터마크, 불똥이 지워진다"""
    mask = alpha > 0
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return alpha
    cy, cx = int(np.median(ys)), int(np.median(xs))
    if not mask[cy, cx]:
        i = np.argmin((ys - cy) ** 2 + (xs - cx) ** 2)
        cy, cx = ys[i], xs[i]
    grown = np.array(Image.fromarray((mask * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(7))) > 0
    reach = np.zeros_like(mask)
    reach[cy, cx] = True
    for _ in range(300):
        new = _spread(_spread(reach, grown, 1), grown, 0)
        if new.sum() == reach.sum():
            break
        reach = new
    out = alpha.copy()
    out[~reach] = 0
    return out


def _kill_shadow(rgb, alpha):
    """바닥에 깔린 짙은 자주색 그림자를 지운다. 얇은 외곽선은 남기고 두껍고 납작한 덩어리만 지움"""
    ys, xs = np.nonzero(alpha > 0)
    if len(ys) == 0:
        return alpha
    top, bot = ys.min(), ys.max()
    h = bot - top + 1
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    dark = (r < 135) & (g < 55) & (b < 90) & (alpha > 0)
    m = Image.fromarray((dark * 255).astype(np.uint8), 'L')
    k = max(3, int(h * 0.025) * 2 + 1)
    thick = np.array(m.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))) > 0   # 얇은 선은 사라짐
    thick[: top + int(h * 0.62)] = False          # 몸 아래쪽 38%에 있는 것만
    thick = np.array(Image.fromarray((thick * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(5))) > 0
    out = alpha.copy()
    out[thick & dark] = 0
    return out


def _frames_from_sheet(key, path, n, kill_shadow):
    """시트 한 장 -> (프레임 RGBA 배열 n개, 기준 높이 정보). 프레임들은 같은 크기 칸으로 맞춰짐(원본 위치 유지)"""
    im = Image.open(path).convert('RGBA')
    arr = np.array(im)
    rgb = arr[..., :3]
    alpha = _alpha_from_white(rgb)
    groups = _split_columns(alpha, n)
    cleaned = []
    for x0, x1 in groups:
        sub = np.zeros_like(alpha)
        sub[:, x0:x1] = alpha[:, x0:x1]
        sub = _main_blob(sub)
        if kill_shadow:
            sub = _kill_shadow(rgb, sub)
            sub = _main_blob(sub)
        cleaned.append(sub)
    arr[..., 3] = 0
    boxes = []
    for sub in cleaned:
        ys = np.where((sub > 0).any(axis=1))[0]
        xs = np.where((sub > 0).any(axis=0))[0]
        boxes.append((ys[0], ys[-1] + 1, xs[0], xs[-1] + 1))
    top = min(b[0] for b in boxes)
    bot = max(b[1] for b in boxes)
    # 칸 가운데는 몸통 윗부분(머리, 뿔)의 가운데
    centers, ref_w, half = [], [], 0
    for sub, bx in zip(cleaned, boxes):
        hh = bx[1] - bx[0]
        head = sub[bx[0]: bx[0] + int(hh * 0.4)]
        xs = np.where((head > 0).any(axis=0))[0]
        centers.append((xs[0] + xs[-1]) / 2.0)
        ref_w.append(xs[-1] - xs[0] + 1)
        half = max(half, centers[-1] - bx[2], bx[3] - centers[-1])
    W = int(2 * half + PAD * 2) + 1
    H = bot - top + PAD * 2
    cells = []
    for sub, c, bx in zip(cleaned, centers, boxes):
        left = int(round(c - W / 2))
        out = np.zeros((H, W, 4), np.uint8)
        for y in range(H):
            sy = top - PAD + y
            if sy < 0 or sy >= sub.shape[0]:
                continue
            x_lo, x_hi = max(0, left), min(sub.shape[1], left + W)
            if x_hi <= x_lo:
                continue
            out[y, x_lo - left: x_hi - left, :3] = arr[sy, x_lo:x_hi, :3]
            out[y, x_lo - left: x_hi - left, 3] = sub[sy, x_lo:x_hi]
        cells.append(out)
    bottoms = sorted(b[1] for b in boxes)
    base = bottoms[len(bottoms) // 2] - top + PAD          # 칸 안에서 발 위치(위에서부터의 행 번호) = 가운데 값
    body_h = int(np.median([b[1] - b[0] for b in boxes]))
    rf = REF_FRAME.get(key)
    rw = float(ref_w[rf]) if rf is not None and rf < len(ref_w) else float(np.median(ref_w))
    return cells, dict(W=W, H=H, base=base, ref_w=rw, body_h=body_h)


def _resize(cell, s):
    if abs(s - 1.0) < 0.01:
        return cell
    im = Image.fromarray(cell, 'RGBA')
    w, h = max(1, round(im.width * s)), max(1, round(im.height * s))
    return np.array(im.convert('RGBa').resize((w, h), Image.LANCZOS).convert('RGBA'))


def _tint(atlas, mix, col, eye):
    a = atlas.astype(np.float32)
    if mix > 0:
        a[..., :3] = a[..., :3] * (1 - mix) + np.array(col, np.float32) * mix
    if eye is not None:
        r, g, b, al = atlas[..., 0].astype(int), atlas[..., 1].astype(int), atlas[..., 2].astype(int), atlas[..., 3]
        eyes = (r > 200) & (g > 150) & (b < 170) & (al > 128)
        a[eyes, :3] = eye
    return np.clip(a, 0, 255).astype(np.uint8)


def prepare_boss_anim(find, out_dir=None):
    """돌려주는 값: None(그림 없음) 또는 {'files': [p0, p1, p2 경로], 'cw', 'ch', 'base', 'body_h', 'have': {'float':True,...}}
    base = 칸 아래에서 발 위치까지의 높이(px), body_h = 몸 높이(px). 모두 아틀라스 그림 기준 픽셀"""
    found = [(k, find(f), n, sh) for k, f, n, sh in SHEETS if os.path.exists(find(f))]
    if not found:
        return None
    base_dir = out_dir or os.path.dirname(found[0][1]) or '.'
    files = [os.path.join(base_dir, f'boss_anim_p{i}.png') for i in range(3)]
    meta_f = os.path.join(base_dir, 'boss_anim_meta.json')
    sig = '|'.join(f'{k}:{os.stat(p).st_size}:{int(os.stat(p).st_mtime)}' for k, p, _, _ in found) + f'|{ANIM_VER}'
    try:
        with open(meta_f, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        if meta.get('sig') == sig and all(os.path.exists(p) for p in files):
            meta['files'] = files
            return meta
    except Exception:
        pass

    sheets = {}
    for k, p, n, sh in found:
        try:
            sheets[k] = _frames_from_sheet(k, p, n, sh)
        except Exception as e:
            print(f'[보스 동작] {os.path.basename(p)} 처리 실패: {e}')
    if not sheets:
        return None
    ref_key = 'float' if 'float' in sheets else next(iter(sheets))
    ref = sheets[ref_key][1]
    scaled = {}
    for k, (cells, info) in sheets.items():
        s = ref['ref_w'] / info['ref_w']                 # 몸 크기를 떠다니기 그림에 맞춤
        cs = [_resize(c, s) for c in cells]
        scaled[k] = (cs, dict(W=cs[0].shape[1], H=cs[0].shape[0], base=info['base'] * s, body_h=info['body_h'] * s))
    up = max(i['base'] for _, i in scaled.values())                                  # 발 위쪽 높이
    down = max(i['H'] - i['base'] for _, i in scaled.values())                       # 발 아래쪽 높이
    CW = max(i['W'] for _, i in scaled.values())
    CH = int(np.ceil(up + down))
    atlas = np.zeros((CH, CW * 11, 4), np.uint8)
    have = {}
    for k, start in (('float', F_FLOAT), ('attack', F_ATTACK), ('pose', F_POSE)):
        have[k] = k in scaled
        if k not in scaled:
            continue
        cs, info = scaled[k]
        oy = int(round(up - info['base']))              # 발 위치가 같아지도록 내림
        for i, c in enumerate(cs):
            ox = (CW - c.shape[1]) // 2
            x0 = (start + i) * CW + ox
            atlas[oy: oy + c.shape[0], x0: x0 + c.shape[1]] = c
    for p, (mix, col, eye) in zip(files, PHASE_TINT):
        Image.fromarray(_tint(atlas, mix, col, eye), 'RGBA').save(p)
    meta = dict(cw=int(CW), ch=int(CH), base=float(down), body_h=float(scaled[ref_key][1]['body_h']),
                have=have, sig=sig)
    with open(meta_f, 'w', encoding='utf-8') as f:
        json.dump(meta, f)
    meta['files'] = files
    return meta