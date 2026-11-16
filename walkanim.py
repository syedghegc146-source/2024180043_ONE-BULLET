"""걷기 그림(4프레임 가로 시트)을 게임에서 쓸 수 있게 자동으로 다듬는 모듈.

넣어야 하는 그림 (main.py 옆, 또는 image 폴더에):
  walk_side.png   옆모습 (오른쪽을 보는 그림)
  walk_front.png  앞모습
  walk_back.png   뒷모습
각 그림은 '가로 한 줄에 4프레임'이고 배경이 흰색(또는 투명)이면 됩니다.
프레임 순서: 왼발 앞 -> 가운데 -> 오른발 앞 -> 가운데

하는 일: 흰 배경 지우기 -> 4칸 나누기 -> 칸마다 머리 위치를 맞춰서 같은 크기 칸으로 만들기 -> walk_xxx_cut.png 로 저장.
그림을 바꾸면 알아서 다시 만들어집니다.
"""
import os

import numpy as np
from PIL import Image, ImageFilter

WHITE_MIN = 226          # 이 값보다 밝고 색이 거의 없으면 배경으로 봄 (RGB 모두)
WHITE_SAT = 22           # 색 차이(max-min)가 이보다 작아야 배경
FRINGE_MIN = 95          # 가장자리 찌꺼기로 볼 최소 밝기
FRINGE_SAT = 50          # 색 차이가 이보다 작은(회색빛) 것만 지움
FRINGE_PASSES = 3        # 바깥에서 몇 겹까지 벗길지
PAD = 4                  # 칸 가장자리 여백(px)
CUT_VER = 2


def _spread(reach, white, axis):
    """흰색 구간(한 줄에서 끊기지 않은 부분) 안에 이미 닿은 칸이 있으면 그 구간 전체를 닿은 것으로 만든다"""
    if axis == 0:
        return _spread(reach.T, white.T, 1).T
    h, w = white.shape
    seg = np.cumsum(~white, axis=1) + np.arange(h)[:, None] * (w + 1)       # 줄마다 구간 번호
    has = np.zeros(h * (w + 1) + 1, bool)
    has[seg[reach & white]] = True
    return has[seg] & white


def _alpha_from_white(rgb):
    """바깥에서 이어진 흰색만 배경으로 지운다 (캐릭터 안쪽의 흰 옷은 그대로). numpy/PIL만 사용"""
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    white = (mn >= WHITE_MIN) & ((mx - mn) <= WHITE_SAT)
    reach = np.zeros_like(white)
    reach[0, :] = reach[-1, :] = reach[:, 0] = reach[:, -1] = True
    reach &= white
    for _ in range(400):                          # 가로, 세로로 번갈아 퍼뜨림 (몇 번이면 끝남)
        new = _spread(_spread(reach, white, 1), white, 0)
        if new.sum() == reach.sum():
            break
        reach = new
    bg = reach
    a = np.where(bg, 0, 255).astype(np.uint8)
    # 배경과 닿은 가장자리 한 겹 중 밝은 찌꺼기 제거
    grown = np.array(Image.fromarray((bg * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(3))) > 0
    a[(mn > 190) & grown & ~bg] = 0
    # 바깥 테두리를 따라 남는 회색/흰색 줄(배경과 섞인 가장자리)을 몇 겹 벗겨냄. 어두운 외곽선과 색 있는 부분은 그대로
    gray = (mn > FRINGE_MIN) & ((mx - mn) < FRINGE_SAT)
    for _ in range(FRINGE_PASSES):
        opaque = a > 0
        edge = opaque & ~(np.roll(opaque, 1, 0) & np.roll(opaque, -1, 0) & np.roll(opaque, 1, 1) & np.roll(opaque, -1, 1))
        kill = edge & gray
        if not kill.any():
            break
        a[kill] = 0
    return a


def _split_columns(alpha, n=4):
    """빈 세로줄을 기준으로 n개 덩어리로 나눈다. 안 나뉘면 같은 폭으로 자른다."""
    cols = (alpha > 0).any(axis=0)
    xs = np.where(cols)[0]
    if len(xs) == 0:
        return None
    groups, start, prev = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - prev > 12:                       # 12px 이상 비어 있으면 다른 프레임
            groups.append((start, prev + 1))
            start = x
        prev = x
    groups.append((start, prev + 1))
    if len(groups) == n:
        return groups
    left, right = xs[0], xs[-1] + 1
    w = (right - left) / n
    return [(int(left + i * w), int(left + (i + 1) * w)) for i in range(n)]


def make_walk_cut(src, dst, n=4):
    """src 시트 -> dst (가로 n칸, 칸 크기 같음, 투명 배경). 돌려주는 값: (칸 폭, 칸 높이)"""
    im = Image.open(src).convert('RGBA')
    arr = np.array(im)
    if (arr[..., 3] < 250).sum() > arr.shape[0] * arr.shape[1] * 0.1:      # 이미 투명 배경
        alpha = arr[..., 3]
    else:
        alpha = _alpha_from_white(arr[..., :3])
    arr[..., 3] = alpha
    groups = _split_columns(alpha, n)
    if groups is None:
        raise ValueError('그림에서 캐릭터를 찾지 못했어요')

    cells, boxes = [], []
    for x0, x1 in groups:
        sub = alpha[:, x0:x1]
        ys = np.where((sub > 0).any(axis=1))[0]
        boxes.append((ys[0], ys[-1] + 1))
    top = min(b[0] for b in boxes)                 # 모든 칸에서 같은 높이 범위를 써서 머리 높이가 유지됨
    bot = max(b[1] for b in boxes)
    H = bot - top + PAD * 2
    # 칸마다 머리 부분(위쪽 40%)의 가운데를 기준으로 가로 위치를 맞춤
    centers, half = [], 0
    for (x0, x1) in groups:
        sub = alpha[top:top + int((bot - top) * 0.4), x0:x1]
        xs = np.where((sub > 0).any(axis=0))[0]
        c = x0 + (xs[0] + xs[-1]) / 2.0
        centers.append(c)
        full = np.where((alpha[top:bot, x0:x1] > 0).any(axis=0))[0]
        half = max(half, c - (x0 + full[0]), (x0 + full[-1] + 1) - c)
    W = int(2 * half + PAD * 2) + 1
    out = Image.new('RGBA', (W * n, H), (0, 0, 0, 0))
    for i, ((x0, x1), c) in enumerate(zip(groups, centers)):
        left = int(round(c - W / 2))
        crop = Image.fromarray(arr).crop((left, top - PAD, left + W, bot + PAD))
        # 이웃 프레임이 섞여 들어오지 않게 자기 칸 밖은 지움
        a = np.array(crop)
        lo = max(0, x0 - left)
        hi = min(W, x1 - left)
        a[:, :lo, 3] = 0
        a[:, hi:, 3] = 0
        out.paste(Image.fromarray(a), (i * W, 0))
    out.save(dst)
    return int(W), int(H)


def prepare_walk(find, keys=('side', 'front', 'back')):
    """find(이름) -> 경로. 돌려주는 값: {'side': (잘라낸 그림 경로, 칸 폭, 칸 높이), ...}  (그림이 없는 항목은 빠짐)"""
    res = {}
    for k in keys:
        name = f'walk_{k}.png'
        src = find(name)
        if not os.path.exists(src):
            continue
        dst = os.path.splitext(src)[0] + '_cut.png'
        try:
            st = os.stat(src)
            sig = f'{st.st_size}|{int(st.st_mtime)}|{CUT_VER}'
            sigf = dst + '.sig'
            old = open(sigf).read() if os.path.exists(sigf) else ''
            if old == sig and os.path.exists(dst):
                with Image.open(dst) as im:
                    W, H = im.size[0] // 4, im.size[1]
            else:
                W, H = make_walk_cut(src, dst)
                with open(sigf, 'w') as f:
                    f.write(sig)
            res[k] = (dst, W, H)
        except Exception as e:
            print(f'[걷기] {name} 처리 실패: {e}')
    return res