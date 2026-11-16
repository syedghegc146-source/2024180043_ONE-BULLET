from pico2d import *
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import numpy as np
import json
import math
import os
import random
import time

from config import *
from bossanim import prepare_boss_anim, F_FLOAT, F_ATTACK, F_POSE


# =============== 보스 탄 이미지 준비 ===============
def label_components(m):
    """True 픽셀의 연결된 덩어리에 번호를 붙인다 (8방향 연결)"""
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    ys, xs = np.nonzero(m)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if lab[sy, sx]:
            continue
        n += 1
        lab[sy, sx] = n
        stack = [(sy, sx)]
        while stack:
            y, x = stack.pop()
            for ny in (y - 1, y, y + 1):
                if 0 <= ny < h:
                    for nx in (x - 1, x, x + 1):
                        if 0 <= nx < w and m[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = n
                            stack.append((ny, nx))
    return lab, n


def runs1d(mask1d, gap):
    """True가 이어진 구간 목록. gap 이하의 틈은 같은 구간으로 본다"""
    idx = np.where(mask1d)[0]
    if len(idx) == 0:
        return []
    out, s, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > gap:
            out.append((int(s), int(p + 1)))
            s = i
        p = i
    out.append((int(s), int(p + 1)))
    return out


def extract_sprite(src, dst):
    """체크무늬 배경 시트에서 탄 하나를 골라, 진행 방향이 오른쪽(+x)이 되도록 돌려서 dst에 저장.
    (w, h, 머리 오프셋)을 돌려준다. 실패하면 None"""
    img = Image.open(src).convert('RGB')
    W, H = img.size
    rgb = np.array(img)
    sat = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    fg = sat > SAT_THRESH          # 흰색/회색 체크무늬와 글자는 채도가 낮아서 제외됨

    # 작게 줄여서 덩어리(탄 하나하나)를 찾는다
    f = max(1, round(max(W, H) / 400))
    lw, lh = W // f, H // f
    small = Image.fromarray((fg * 255).astype(np.uint8)).resize((lw, lh), Image.BOX)
    sm = np.array(small) > 40
    sm = np.array(Image.fromarray((sm * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
    lab, n = label_components(sm)
    if n == 0:
        return None

    min_a, max_a = 0.0004 * lw * lh, 0.06 * lw * lh
    cands = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        area = len(ys)
        if area < min_a or area > max_a:
            continue
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
        if x0 <= 0 or y0 <= 0 or x1 >= lw or y1 >= lh:   # 시트 가장자리에 잘린 것 제외
            continue
        cands.append((k, area, x0, y0, x1, y1))
    if not cands:
        return None

    # 가장 흔한 크기의 탄들 중에서 방향이 가장 뚜렷한 것(꼬리/불꽃이 분명한 것)을 고른다
    med = float(np.median([c[1] for c in cands]))
    cands = [c for c in cands if 0.5 * med <= c[1] <= 2.0 * med] or cands

    def region(c):
        k, _, x0, y0, x1, y1 = c
        comp = lab[y0:y1, x0:x1] == k
        up = np.repeat(np.repeat(comp, f, axis=0), f, axis=1)
        sub_rgb = rgb[y0 * f:y1 * f, x0 * f:x1 * f]
        sub_fg = fg[y0 * f:y1 * f, x0 * f:x1 * f] & up
        return sub_rgb, sub_fg

    best = None
    for c in cands:
        sub_rgb, sub_fg = region(c)
        g = sub_rgb[:, :, 1]
        body = sub_fg & (g < 100)          # 진한 빨강: 화살촉/구슬 머리
        trail = sub_fg & (g >= 125)        # 노랑/주황/연분홍: 불꽃/꼬리
        if body.sum() < 20 or trail.sum() < 20:
            dlen, vec = 0.0, (0.0, 0.0)
        else:
            by, bx = np.nonzero(body)
            ty, tx = np.nonzero(trail)
            vec = (bx.mean() - tx.mean(), by.mean() - ty.mean())    # 꼬리 -> 머리
            dlen = math.hypot(*vec) / max(sub_fg.shape)
        if best is None or dlen > best[0]:
            best = (dlen, vec, c)

    dlen, vec, c = best
    sub_rgb, sub_fg = region(c)
    mh, mw = sub_fg.shape

    # 안쪽 구멍(밝은 하이라이트 등)을 메운다
    pad = Image.new('L', (mw + 2, mh + 2), 0)
    pad.paste(Image.fromarray((sub_fg * 255).astype(np.uint8)), (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    filled = np.array(pad)[1:-1, 1:-1] != 128

    # 어두운 테두리선도 포함
    dil = np.array(Image.fromarray((filled * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
    ring = dil & ~filled & (sub_rgb.max(axis=2) < 150)
    mask = filled | ring

    out = sub_rgb.copy()
    out[~mask] = (60, 10, 20)             # 투명 부분 색이 번지지 않게 어두운 색으로
    alpha = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
    spr = Image.fromarray(np.dstack([out, np.array(alpha)]).astype(np.uint8))

    # 진행 방향이 오른쪽을 향하도록 회전
    ang = math.atan2(-vec[1], vec[0]) if dlen > 0.08 else 0.0
    spr = spr.rotate(-math.degrees(ang), resample=Image.BICUBIC, expand=True)
    box = spr.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        spr = spr.crop(box)

    # 머리(진한 빨강) 위치: 이미지 중심에서 앞쪽으로 얼마나 떨어져 있는지
    arr = np.array(spr)
    body = (arr[:, :, 3] > 128) & (arr[:, :, 1] < 100)
    off = 0.0
    if dlen > 0.08 and body.sum() >= 20:
        off = float(np.nonzero(body)[1].mean() - arr.shape[1] / 2)

    sc = min(1.0, 128 / max(spr.size))
    if sc < 1.0:
        spr = spr.resize((max(1, int(spr.size[0] * sc)), max(1, int(spr.size[1] * sc))), Image.LANCZOS)
        off *= sc
    spr.save(dst)
    return spr.size[0], spr.size[1], off


def make_orb(path, core, edge, size=64):
    """빛나는 구슬 이미지 (시트를 못 쓸 때의 보스 탄, 불꽃 파티클에 사용)"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    d = np.hypot(xx - c, yy - c) / c
    alpha = np.where(d < 0.6, 1.0, np.clip(1 - (d - 0.6) / 0.4, 0, 1) ** 2 * 0.55)
    t = np.clip(d / 0.62, 0, 1)[..., None]
    rgb = np.array(core, np.float32) * (1 - t) + np.array(edge, np.float32) * t
    ring = np.clip(1 - np.abs(d - 0.6) / 0.07, 0, 1)[..., None]
    rgb = rgb * (1 - 0.45 * ring)
    out = np.zeros((size, size, 4), np.uint8)
    out[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[:, :, 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(out).save(path)


def prepare_boss_bullets():
    """보스 탄 이미지 3종 준비. 각 탄의 정보 [{'w','h','off','len'}, ...] 반환.
    한 번 만들면 저장해 두고 재사용 (원본을 바꾸면 자동으로 다시 만듦)"""
    srcs = [s for s in SHEET_FILES if os.path.exists(s)]
    newest = max([os.path.getmtime(s) for s in srcs] or [0])
    if os.path.exists(BB_META) and all(os.path.exists(p) for p in BB_FILES) \
            and os.path.getmtime(BB_META) >= newest:
        with open(BB_META) as fp:
            return json.load(fp)

    metas = []
    for i in range(3):
        res = None
        if os.path.exists(SHEET_FILES[i]):
            try:
                res = extract_sprite(SHEET_FILES[i], BB_FILES[i])
            except Exception as e:
                print(f'[보스 탄 {i + 1}] 시트 처리 실패: {e}')
        if res:
            w, h, off = res
            metas.append({'w': w, 'h': h, 'off': off, 'len': BB_LEN[i]})
        else:
            print(f'[보스 탄 {i + 1}] {SHEET_FILES[i]}를 쓸 수 없어 구슬 탄으로 대체합니다')
            make_orb(BB_FILES[i], *ORB_COLORS[i])
            metas.append({'w': 64, 'h': 64, 'off': 0.0, 'len': 30})
    with open(BB_META, 'w') as fp:
        json.dump(metas, fp)
    return metas


def prepare_boss_hurt():
    """맞았을 때의 보스 모습. boss_hurt.png가 있으면 그걸 쓰고,
    없으면 boss_clean.png를 붉게 물들여서 자동으로 만든다. (w, h) 반환"""
    if os.path.exists(BOSS_HURT_SRC):
        size = prepare_single(BOSS_HURT_SRC, BOSS_HURT_CLEAN)
        if size:
            return size
    if not os.path.exists(BOSS_CLEAN):
        return None
    if fresh(BOSS_CLEAN, BOSS_HURT_CLEAN):
        with Image.open(BOSS_HURT_CLEAN) as im:
            return im.size
    arr = np.array(Image.open(BOSS_CLEAN).convert('RGBA')).astype(np.float32)
    red = np.array([255, 60, 60], np.float32)
    arr[:, :, :3] = arr[:, :, :3] * 0.4 + red * 0.6
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img.save(BOSS_HURT_CLEAN)
    return img.size


def make_aura(path, size=256):
    """보스 뒤에서 번지는 붉은 기운 이미지"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    d = np.hypot(xx - c, yy - c) / c
    alpha = np.clip(1 - d, 0, 1) ** 1.8
    out = np.zeros((size, size, 4), np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = 255, 40, 40
    out[:, :, 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(out).save(path)


def prepare_boss_phases():
    """2, 3단계 보스 모습(눈 색, 몸 색)과 붉은 기운 이미지를 자동으로 만든다. 성공하면 True.
    눈은 노랗게 밝은 픽셀을 찾아서 색을 바꾼다"""
    if not os.path.exists(BOSS_CLEAN):
        return False
    if not os.path.exists(AURA_IMG):
        make_aura(AURA_IMG)
    if fresh(BOSS_CLEAN, BOSS_P2_CLEAN) and fresh(BOSS_CLEAN, BOSS_P3_CLEAN):
        return True
    arr0 = np.array(Image.open(BOSS_CLEAN).convert('RGBA')).astype(np.float32)
    r, g, b, al = arr0[:, :, 0], arr0[:, :, 1], arr0[:, :, 2], arr0[:, :, 3]
    eyes = (r > 200) & (g > 150) & (b < 170) & (al > 128)
    # (저장 위치, 몸에 섞을 색의 비율, 섞을 색, 눈 색)
    for dst, mix, col, eye in ((BOSS_P2_CLEAN, 0.15, (200, 30, 40), (255, 120, 30)),
                               (BOSS_P3_CLEAN, 0.32, (150, 10, 35), (255, 40, 40))):
        a = arr0.copy()
        a[:, :, :3] = a[:, :, :3] * (1 - mix) + np.array(col, np.float32) * mix
        a[eyes, :3] = eye
        Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(dst)
    return True


# =============== 레이저 / 경고 이미지 준비 ===============
def _warn_font(size):
    for name in ('arialbd.ttf', 'arial.ttf', 'malgunbd.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_warning_fallback():
    """warning.png가 없을 때 대신 쓰는 경고 판 (코드로 그림)"""
    W, H = 420, 130
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    red = (235, 40, 40, 255)
    d.rectangle((4, 4, W - 5, H - 5), outline=red, width=4)
    for x in range(14, W - 24, 24):
        d.polygon([(x, 10), (x + 10, 10), (x + 4, 24), (x - 6, 24)], fill=red)
        d.polygon([(x, H - 11), (x + 10, H - 11), (x + 4, H - 25), (x - 6, H - 25)], fill=red)
    font = _warn_font(56)
    try:
        d.text((W / 2, H / 2), 'WARNING!', font=font, fill=(255, 255, 255, 255), anchor='mm')
    except (ValueError, TypeError):
        d.text((90, 36), 'WARNING!', font=font, fill=(255, 255, 255, 255))
    img.save(WARNING_CLEAN)
    return img.size


def prepare_warning():
    """warning.png(검은 배경에 경고 판이 여러 개 모인 그림)에서 한 개를 골라 투명하게 저장. (w, h) 반환"""
    if os.path.exists(WARNING_SRC):
        if fresh(WARNING_SRC, WARNING_CLEAN):
            with Image.open(WARNING_CLEAN) as im:
                return im.size
        try:
            rgb = np.array(Image.open(WARNING_SRC).convert('RGB'))
            mask = rgb.max(axis=2) > 45
            rows = runs1d(mask.any(axis=1), 6)
            y0, y1, x0, x1 = 0, rgb.shape[0], 0, rgb.shape[1]
            if len(rows) >= 2:
                y0, y1 = rows[min(WARN_PICK[0], len(rows) - 1)]
                cols = runs1d(mask[y0:y1].any(axis=0), 8)
                if len(cols) >= 2:
                    x0, x1 = cols[min(WARN_PICK[1], len(cols) - 1)]
                else:
                    y0, y1, x0, x1 = 0, rgb.shape[0], 0, rgb.shape[1]
            sub = rgb[y0:y1, x0:x1].copy()
            a = np.clip(sub.max(axis=2).astype(np.float32) * 3.0, 0, 255).astype(np.uint8)   # 검은 부분은 투명
            img = Image.fromarray(np.dstack([sub, a]))
            box = img.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox()
            if box:
                img = img.crop(box)
            img.save(WARNING_CLEAN)
            return img.size
        except Exception as e:
            print(f'[경고 판] warning.png 처리 실패: {e}')
    print('[경고 판] warning.png를 쓸 수 없어 기본 경고 판을 씁니다')
    return make_warning_fallback()


def process_laser(src, dst, band=None):
    """체크무늬 배경 위의 레이저 그림에서 배경을 지우고 투명하게 저장. (w, h) 반환. 실패하면 None
    진한 빨강/주황은 본체, 연한 분홍은 빛 번짐, 가운데 흰 심지는 본체 사이를 메워서 살린다"""
    rgb = np.array(Image.open(src).convert('RGB'))
    h, w = rgb.shape[:2]
    sat = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    strong = sat > 140
    soft = np.clip((sat - 40) * 2.5, 0, 255)

    # 본체와 이어진 가장 큰 덩어리만 남긴다 (떨어진 불똥, 워터마크 제거)
    f = max(1, round(max(h, w) / 400))
    lw, lh = w // f, h // f
    small = np.array(Image.fromarray((strong * 255).astype(np.uint8)).resize((lw, lh), Image.BOX)) > 20
    small = np.array(Image.fromarray((small * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
    lab, n = label_components(small)
    if n == 0:
        return None
    counts = np.bincount(lab.ravel())
    counts[0] = 0
    keep = lab == int(counts.argmax())

    def up(m):
        u = np.repeat(np.repeat(m, f, axis=0), f, axis=1)
        out = np.zeros((h, w), bool)
        out[:u.shape[0], :u.shape[1]] = u[:h, :w]
        return out

    big = up(keep)
    grow = up(np.array(Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(11))) > 0)

    # 가로줄마다 본체 양 끝 사이를 채운다 (가운데 흰 심지)
    sb = strong & big
    core = np.zeros((h, w), bool)
    for r in np.nonzero(sb.any(axis=1))[0]:
        cs = np.nonzero(sb[r])[0]
        core[r, cs[0]:cs[-1] + 1] = True

    alpha = np.maximum(np.where(grow, soft, 0), core * 255).astype(np.uint8)
    img = Image.fromarray(np.dstack([rgb, alpha]))
    if band:
        img = img.crop((0, int(h * band[0]), w, max(int(h * band[1]), int(h * band[0]) + 2)))
    box = img.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        img = img.crop(box)
    sc = min(1.0, 512 / max(img.size))
    if sc < 1.0:
        img = img.resize((max(1, int(img.size[0] * sc)), max(1, int(img.size[1] * sc))), Image.LANCZOS)
    img.save(dst)
    return img.size


def make_beam_fallback():
    """laser_beam.png가 없을 때 대신 쓰는 레이저 몸통 (코드로 그림)"""
    w, h = 64, 256
    x = np.abs(np.linspace(-1, 1, w))[None, :].repeat(h, 0)
    alpha = np.where(x < 0.25, 1.0, np.clip(1 - (x - 0.25) / 0.75, 0, 1) ** 1.5)
    t = np.clip(x / 0.7, 0, 1)[..., None]
    rgb = np.array([255, 245, 230], np.float32) * (1 - t) + np.array([255, 40, 60], np.float32) * t
    out = np.zeros((h, w, 4), np.uint8)
    out[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[:, :, 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(out).save(LASER_BEAM_CLEAN)
    return (w, h)


def prepare_lasers():
    """경고 판, 레이저 몸통, 발사 효과 이미지를 준비해서 크기 정보를 돌려준다"""
    info = {'warn': prepare_warning()}

    beam = None
    if os.path.exists(LASER_BEAM_SRC):
        if fresh(LASER_BEAM_SRC, LASER_BEAM_CLEAN):
            with Image.open(LASER_BEAM_CLEAN) as im:
                beam = im.size
        else:
            try:
                beam = process_laser(LASER_BEAM_SRC, LASER_BEAM_CLEAN, LASER_BODY_BAND)
            except Exception as e:
                print(f'[레이저] laser_beam.png 처리 실패: {e}')
    if beam is None:
        print('[레이저] laser_beam.png를 쓸 수 없어 기본 레이저를 씁니다')
        beam = make_beam_fallback()
    info['beam'] = beam

    burst, rnd = None, False
    if os.path.exists(LASER_BURST_SRC):
        if fresh(LASER_BURST_SRC, LASER_BURST_CLEAN):
            with Image.open(LASER_BURST_CLEAN) as im:
                burst = im.size
        else:
            try:
                burst = process_laser(LASER_BURST_SRC, LASER_BURST_CLEAN)
            except Exception as e:
                print(f'[레이저] laser_burst.png 처리 실패: {e}')
    if burst is None:
        print('[레이저] laser_burst.png를 쓸 수 없어 기본 발사 효과를 씁니다')
        make_orb(LASER_BURST_CLEAN, (255, 255, 230), (255, 80, 40), 128)
        burst, rnd = (128, 128), True
    info['burst'] = burst
    info['burst_round'] = rnd
    return info


# =============== 보스 탄환 ===============
class BossBullet:
    def __init__(self, x, y, ang, speed=360, b_type=1, turn=0.0, homing_time=0.0, accel=0.0, vmax=600.0):
        self.x, self.y = x, y
        self.ang = ang
        self.speed = speed
        self.vx = math.cos(ang) * speed
        self.vy = math.sin(ang) * speed
        self.alive = True
        self.b_type = b_type
        self.turn = turn                # 초당 회전 가능한 각도(라디안). 0이면 직진
        self.homing_time = homing_time  # 이 시간 동안만 플레이어를 따라감
        self.accel = accel              # 초당 속도 증가량
        self.vmax = vmax
        self.age = 0.0

    def update(self, dt, target=None):
        self.age += dt
        if self.turn and target is not None and self.age < self.homing_time:
            want = math.atan2(target.y - self.y, target.x - self.x)
            diff = (want - self.ang + math.pi) % (2 * math.pi) - math.pi
            step = self.turn * dt
            self.ang += max(-step, min(step, diff))
        if self.accel:
            self.speed = min(self.vmax, self.speed + self.accel * dt)
        self.vx = math.cos(self.ang) * self.speed
        self.vy = math.sin(self.ang) * self.speed
        self.x += self.vx * dt
        self.y += self.vy * dt
        if not (-40 < self.x < CANVAS_W + 40 and -40 < self.y < CANVAS_H + 40):
            self.alive = False

    def draw(self, imgs, metas):
        i = self.b_type - 1
        m = metas[i]
        s = m['len'] / max(m['w'], m['h'])
        off = m['off'] * s
        # 판정 위치(self.x, self.y)가 탄의 머리에 오도록 그림을 뒤로 당겨서 그린다
        cx = self.x - math.cos(self.ang) * off
        cy = self.y - math.sin(self.ang) * off
        imgs[i].clip_composite_draw(0, 0, m['w'], m['h'], self.ang, '', cx, cy, m['w'] * s, m['h'] * s)


# =============== 보스 ===============
class Boss:
    def __init__(self, size, hurt_size=None, lasers=None, diff=None, phases=False):
        diff = diff or DIFFICULTIES[DEFAULT_DIFFICULTY]
        self.max_hp = diff['boss_hp']          # 난이도별 체력
        self.cd_mult = diff['cd']              # 공격 간격 배율
        self.spd_mult = diff['speed']          # 탄 속도 배율
        self.double = diff['double']           # 3단계 패턴 동시 사용

        self.img = load_image(BOSS_CLEAN)
        w, h = size
        sc = BOSS_H / h
        self.dw, self.dh = w * sc, h * sc
        self.radius = min(self.dw, self.dh) * 0.4

        # 단계별 보스 모습 (눈 색, 몸 색). 없으면 같은 그림을 씀
        if phases:
            self.phase_imgs = [self.img, load_image(BOSS_P2_CLEAN), load_image(BOSS_P3_CLEAN)]
            self.aura = load_image(AURA_IMG)
        else:
            self.phase_imgs = [self.img, self.img, self.img]
            self.aura = None

        self.hurt_img = None                     # 맞았을 때 모습
        if hurt_size:
            self.hurt_img = load_image(BOSS_HURT_CLEAN)
            hw, hh = hurt_size
            hsc = BOSS_H / hh
            self.hdw, self.hdh = hw * hsc, hh * hsc

        # 동작 그림 (boss_float / boss_attack / boss_pose .png). 떠다니기 그림이 없으면 예전 그림 한 장을 씀
        self.anim = None
        self.roar_until = -10.0                  # 이 시각까지 포효 자세 (단계가 바뀔 때)
        self.shadow_img = load_image(SHADOW) if os.path.exists(SHADOW) else None
        try:
            info = prepare_boss_anim(P)
            if info and info['have'].get('float'):
                self.anim = dict(imgs=[load_image(f) for f in info['files']], cw=info['cw'], ch=info['ch'],
                                 base=info['base'], body_h=info['body_h'], have=info['have'])
        except Exception as e:
            print('[보스 동작] 그림 준비 실패:', e)
            self.anim = None

        self.warn_img = load_image(FLASH_IMG)    # 돌진/레이저 경고 띠 (붉은 사각형)
        self.dim_img = load_image(DIM_IMG)
        self.bar_bg = load_image(BAR_BG)
        self.bar_fg = load_image(BAR_FG)

        self.has_laser = lasers is not None      # 레이저 그림이 준비됐으면 레이저 패턴 사용
        if self.has_laser:
            self.warn_hud = load_image(WARNING_CLEAN)
            self.warn_wh = lasers['warn']
            self.beam_img = load_image(LASER_BEAM_CLEAN)
            self.beam_wh = lasers['beam']
            self.burst_img = load_image(LASER_BURST_CLEAN)
            self.burst_wh = lasers['burst']
            self.burst_round = lasers['burst_round']

        self.x, self.y = CANVAS_W / 2, BOSS_BASE_Y
        self.hp = self.max_hp
        self.alive = True
        self.dying = False          # 쓰러지는 연출 중
        self.die_t = 0.0

        self.clock = 0.0            # 보스 전용 시계 (게임이 멈추면 같이 멈춤)
        self.hurt_clock = -10.0     # 마지막으로 맞은 시각
        self.mv_phase = 0.0
        self.next_attack = 1.2      # 시작하고 첫 공격까지의 여유
        self.emitters = []          # 시간차로 탄을 내보내는 패턴들
        self.charge = None          # 돌진 중이면 상태 정보가 들어감
        self.lasers = []            # 레이저들 (위험 표시 -> 발사)
        self.laser_fired = False    # 레이저가 발사된 순간 True (main이 읽고 비움)
        self.slam = False           # 돌진이 끝나서 부딪힌 순간 True (main이 읽고 비움)
        self.force_charge = False   # 단계가 시작되고 첫 공격을 돌진으로 할지
        self.bb = None
        self.player = None
        self.pvel = (0.0, 0.0)      # 플레이어 이동 속도 (예측 조준용)
        self.ppos = None
        self.last = []
        self.spiral_dir = 1
        self.prev_phase = 0         # 단계 전환 감지용
        self.phase_event = None     # 단계가 바뀐 순간 새 단계 번호가 들어감 (main이 읽고 비움)

    @property
    def phase(self):
        r = self.hp / self.max_hp
        return 0 if r > 0.66 else (1 if r > 0.33 else 2)

    def cooldown(self):
        return PHASE_COOLDOWN[self.phase] * self.cd_mult

    # ---------- 도우미 ----------
    def shoot(self, ang, speed, b_type, x=None, y=None, **kw):
        speed *= self.spd_mult
        if 'vmax' in kw:
            kw['vmax'] *= self.spd_mult
        if b_type == 1 and self.phase == 1:      # 2단계 화살(가시)은 느리게
            speed *= PHASE2_ARROW_SPEED
            if 'vmax' in kw:
                kw['vmax'] *= PHASE2_ARROW_SPEED
        self.bb.append(BossBullet(self.x if x is None else x, self.y if y is None else y,
                                  ang, speed, b_type, **kw))

    def add(self, delay, interval, count, fn):
        self.emitters.append({'next': self.clock + delay, 'interval': interval,
                              'left': count, 'fn': fn, 'i': 0})

    def aim(self, speed, lead):
        """플레이어가 움직이는 방향을 미리 계산한 조준 각도 (lead가 클수록 더 앞을 겨눔)"""
        px, py = self.player.x, self.player.y
        vx, vy = self.pvel
        d = math.hypot(px - self.x, py - self.y)
        t = d / speed * lead
        return math.atan2(py + vy * t - self.y, px + vx * t - self.x)

    def normal_pos(self):
        """평소에 좌우로 떠다니는 보스의 위치"""
        return (CANVAS_W / 2 + math.sin(self.mv_phase) * 220,
                BOSS_BASE_Y + math.sin(self.mv_phase * 2) * 6)

    # ---------- 패턴 ----------
    def p_spiral(self):
        ph = self.phase
        arms, count = [2, 3, 3][ph], [26, 30, 34][ph]
        base = random.uniform(0, 2 * math.pi)
        step = 0.21 * self.spiral_dir
        self.spiral_dir *= -1

        def fire(i):
            for a in range(arms):
                self.shoot(base + i * step + a * 2 * math.pi / arms, 240 + ph * 20, 1)
        self.add(0, 0.07, count, fire)

    def p_double_spiral(self):
        arms, count = 2, 24
        for d, delay in ((1, 0.0), (-1, 0.5)):
            base = random.uniform(0, 2 * math.pi)

            def fire(i, d=d, base=base):
                for a in range(arms):
                    self.shoot(base + d * i * 0.18 + a * 2 * math.pi / arms, 230, 1)
            self.add(delay, 0.08, count, fire)

    def p_gap_ring(self):
        ph = self.phase
        n, gap = [22, 24, 26][ph], [3, 4, 4][ph]     # 2단계: 탄 26->24, 구멍 3->4칸

        def ring(sign):
            aim = math.atan2(self.player.y - self.y, self.player.x - self.x)
            center = aim + sign * random.uniform(0.5, 1.1)
            step = 2 * math.pi / n
            for k in range(n):
                ang = center + (k + 0.5) * step
                diff = (ang - center + math.pi) % (2 * math.pi) - math.pi
                if abs(diff) < gap * step / 2:
                    continue
                self.shoot(ang, 220, 3)

        self.add(0.0, 1, 1, lambda i: ring(1))
        self.add(0.6, 1, 1, lambda i: ring(-1))

    def p_aimed(self):
        ph = self.phase
        volleys, spread = [3, 3, 3][ph], [1, 2, 1][ph]   # 2단계: 4연발 -> 3연발
        lead = [0.6, 0.7, 1.0][ph]                        # 2단계: 예측을 약하게
        accel = ph >= 2

        def fire(i):
            a = self.aim(400 if accel else 430, lead)
            for k in range(-spread, spread + 1):
                if accel:       # 느리게 시작해서 점점 빨라지는 탄
                    self.shoot(a + k * 0.14, 250, 1, accel=220, vmax=560)
                else:
                    self.shoot(a + k * 0.14, 430, 1)
        self.add(0, 0.3, volleys, fire)

    def p_rain(self):
        ph = self.phase
        count = [18, 22, 26][ph]

        def fire(i):
            x = random.uniform(ARENA_CENTER_X - ARENA_RX, ARENA_CENTER_X + ARENA_RX)
            if i % 3 == 0:      # 세 발에 한 발은 플레이어가 서 있는 줄로
                x = self.player.x + random.uniform(-20, 20)
            self.shoot(-math.pi / 2 + random.uniform(-0.06, 0.06), 300 + ph * 30, 2,
                       x=x, y=CANVAS_H + 10)
        self.add(0, 0.12, count, fire)

    def p_homing(self):
        n = 6 if self.phase == 1 else 8
        ht = PHASE2_HOMING_TIME if self.phase == 1 else 2.4   # 2단계는 덜 쫓아옴

        def fire(i):
            base = random.uniform(0, 2 * math.pi)
            for k in range(n):
                self.shoot(base + k * 2 * math.pi / n, 150, 3, turn=1.5, homing_time=ht)
        self.add(0, 1.0, 1 if self.phase == 1 else 2, fire)

    def p_charge(self):
        """돌진: 경고 띠 -> 방향 고정 -> 돌진 -> (충격파) -> 제자리로 복귀 / 3단계는 연속 돌진"""
        self.charge = {'state': 'warn', 't': 0.0, 'locked': False, 'dist': 0.0,
                       'ang': math.atan2(self.player.y - self.y, self.player.x - self.x),
                       'from': (self.x, self.y), 'chain': 0,
                       'warn': CHARGE_WARN, 'lock': CHARGE_LOCK}

    def make_laser(self, ang, off, thick):
        """레이저 하나의 정보. thick이면 굵은 레이저"""
        if thick:
            w, hh, warn, lock, fire, burst = (THICK_WIDTH, THICK_HIT_HALF, THICK_WARN, THICK_LOCK,
                                              THICK_FIRE, LASER_BURST_LEN * THICK_BURST_MULT)
        else:
            w, hh, warn, lock, fire, burst = (LASER_WIDTH, LASER_HIT_HALF, LASER_WARN, LASER_LOCK,
                                              LASER_FIRE, LASER_BURST_LEN)
        return {'ox': self.x, 'oy': self.y - LASER_MOUTH_DY, 'off': off, 'ang': ang, 't': 0.0, 'state': 'warn',
                'locked': False, 'w': w, 'hh': hh, 'warn': warn, 'lock': lock, 'fire': fire,
                'burst': burst, 'thick': thick}

    def laser_charge_sound(self):
        """레이저 기 모으는 소리. laser_charge.wav 가 없으면 예전처럼 warning.wav"""
        Sound.play('laser_charge' if 'laser_charge' in Sound.sfx else 'warning')

    def p_laser(self):
        """가는 레이저: 경고 판 + 붉은 띠 -> 방향 고정 -> 순식간에 발사 (여러 줄)"""
        base = math.atan2(self.player.y - self.y, self.player.x - self.x)
        sign = random.choice((-1, 1))
        mult = [0, 1, -1, 2, -2]
        self.lasers = []
        for i in range(max(1, min(LASER_COUNT, 5))):
            off = mult[i] * sign * LASER_SPREAD
            self.lasers.append(self.make_laser(base + off, off, False))
        self.laser_charge_sound()

    def p_laser_thick(self):
        """굵은 레이저: 경고가 길고 한 줄. 옆으로 크게 움직이거나 대쉬로 통과"""
        base = math.atan2(self.player.y - self.y, self.player.x - self.x)
        self.lasers = [self.make_laser(base, 0.0, True)]
        self.laser_charge_sound()

    # ---------- 돌진 ----------
    def begin_return(self):
        self.charge = {'state': 'return', 't': 0.0, 'from': (self.x, self.y)}

    def charge_burst(self):
        """돌진이 끝나는 자리에서 퍼지는 충격파 탄 고리. 구멍은 플레이어 쪽에서 비껴나 있다"""
        n = CHARGE_BURST_N
        aim = math.atan2(self.player.y - self.y, self.player.x - self.x)
        center = aim + random.choice((-1, 1)) * random.uniform(0.5, 1.1)
        step = 2 * math.pi / n
        for k in range(n):
            ang = center + (k + 0.5) * step
            diff = (ang - center + math.pi) % (2 * math.pi) - math.pi
            if abs(diff) < CHARGE_BURST_GAP * step / 2:
                continue
            self.shoot(ang, CHARGE_BURST_SPEED, 3)

    def end_dash(self):
        """돌진이 끝난 순간: 충격파를 내고 잠깐 멈춤"""
        c = self.charge
        self.slam = True
        Sound.play('slam')                       # 부딪히는 소리 (slam.wav)
        if CHARGE_END_BURST:
            self.charge_burst()
        c['state'], c['t'] = 'stop', 0.0

    def after_stop(self):
        """멈춘 뒤: 3단계에서는 확률적으로 플레이어의 새 위치로 연속 돌진, 아니면 제자리로 복귀"""
        c = self.charge
        if self.phase >= CHARGE_CHAIN_PHASE and c.get('chain', 0) < CHARGE_CHAIN_MAX \
                and random.random() < CHARGE_CHAIN_PROB:
            self.charge = {'state': 'warn', 't': 0.0, 'locked': False, 'dist': 0.0,
                           'ang': math.atan2(self.player.y - self.y, self.player.x - self.x),
                           'from': (self.x, self.y), 'chain': c.get('chain', 0) + 1,
                           'warn': CHARGE_CHAIN_WARN,
                           'lock': min(CHARGE_LOCK, CHARGE_CHAIN_WARN * 0.55)}
            Sound.play('warning')
        else:
            self.begin_return()

    def update_charge(self, dt):
        c = self.charge
        c['t'] += dt
        if c['state'] == 'warn':
            if c['t'] < c['warn'] - c['lock']:          # 처음에는 플레이어를 따라 조준
                c['ang'] = math.atan2(self.player.y - self.y, self.player.x - self.x)
            else:                                        # 돌진 직전에는 방향 고정
                c['locked'] = True
            if c['t'] >= c['warn']:
                c['state'], c['t'] = 'dash', 0.0          # 돌진 시작에는 소리 없음
        elif c['state'] == 'dash':
            step = CHARGE_SPEED * dt
            self.x += math.cos(c['ang']) * step
            self.y += math.sin(c['ang']) * step
            c['dist'] += step
            out = self.x < 70 or self.x > CANVAS_W - 70 or self.y < 130 or self.y > CANVAS_H - 70
            if c['dist'] >= CHARGE_MAX_DIST or out:
                self.end_dash()
        elif c['state'] == 'stop':
            if c['t'] >= CHARGE_STOP:
                self.after_stop()
        else:                                            # return
            k = min(1.0, c['t'] / CHARGE_RETURN)
            e = k * k * (3 - 2 * k)
            self.mv_phase += dt * (0.8 + 0.3 * self.phase)
            nx, ny = self.normal_pos()
            fx, fy = c['from']
            self.x, self.y = fx + (nx - fx) * e, fy + (ny - fy) * e
            if k >= 1.0:
                self.charge = None
                self.next_attack = self.clock + self.cooldown() + 0.5

    # ---------- 레이저 ----------
    def update_lasers(self, dt):
        fired = False
        for L in self.lasers:
            L['t'] += dt
            if L['t'] < L['warn']:
                if L['t'] < L['warn'] - L['lock']:       # 처음에는 플레이어를 따라 조준
                    L['ang'] = math.atan2(self.player.y - L['oy'], self.player.x - L['ox']) + L['off']
                else:                                     # 발사 직전에는 방향 고정
                    L['locked'] = True
            elif L['state'] == 'warn':
                L['state'] = 'fire'
                fired = True
        if fired:
            Sound.play('laser')
            self.laser_fired = True
        self.lasers = [L for L in self.lasers if L['t'] < L['warn'] + L['fire']]
        if not self.lasers:
            self.next_attack = max(self.next_attack, self.clock + self.cooldown())

    @staticmethod
    def laser_wscale(tf, fire):
        """발사 후 tf초 지났을 때 레이저 굵기 비율 (처음에 확 커지고, 끝에서 가늘어짐)"""
        ws = min(1.0, 0.35 + tf / 0.08)
        remain = fire - tf
        if remain < 0.15:
            ws *= max(0.0, remain / 0.15)
        return ws

    @staticmethod
    def laser_length(tf):
        return min(LASER_LEN, LASER_LEN * tf / LASER_EXTEND)

    def laser_hit(self, hx, hy):
        """(hx, hy)가 발사 중인 레이저에 닿는지"""
        if not self.alive:
            return False
        for L in self.lasers:
            if L['state'] != 'fire':
                continue
            tf = L['t'] - L['warn']
            ws = self.laser_wscale(tf, L['fire'])
            if ws < 0.4:                      # 끝나갈 때 가늘어지면 판정도 없음
                continue
            length = self.laser_length(tf)
            dx, dy = math.cos(L['ang']), math.sin(L['ang'])
            px, py = hx - L['ox'], hy - L['oy']
            proj = max(0.0, min(length, px * dx + py * dy))
            d = math.hypot(px - proj * dx, py - proj * dy)
            if d < L['hh'] * ws + HIT_RADIUS:
                return True
        return False

    # ---------- 공격 선택 ----------
    def attack(self):
        if self.force_charge:                      # 단계가 시작된 직후 첫 공격은 돌진
            self.force_charge = False
            self.last = [self.p_charge]
            self.p_charge()
            return
        ph = self.phase
        pool = [self.p_spiral, self.p_gap_ring, self.p_aimed]
        if ph >= 1:
            pool += [self.p_rain, self.p_homing]
        if ph >= 2:
            pool += [self.p_double_spiral]
        if ph >= CHARGE_MIN_PHASE and not self.emitters:
            pool += [self.p_charge] * 2            # 돌진은 조금 더 자주 나오게
        if self.has_laser and ph >= THICK_MIN_PHASE and not self.emitters:
            pool += [self.p_laser_thick] * 2       # 굵은 레이저
        avail = [p for p in pool if p not in self.last] or pool
        n = 2 if (ph >= 2 and self.double) else 1
        chosen = list(dict.fromkeys(random.sample(avail, min(n, len(avail)))))
        for solo in (self.p_charge, self.p_laser, self.p_laser_thick):   # 돌진, 레이저는 다른 패턴과 같이 쓰지 않음
            if solo in chosen:
                chosen = [solo]
        self.last = chosen
        for p in chosen:
            p()

    # ---------- 갱신 ----------
    def update(self, dt, player, boss_bullets):
        self.clock += dt
        self.player, self.bb = player, boss_bullets

        # 단계가 바뀌면: 소리, 알림, 남은 탄 정리, 잠깐 공격 멈춤
        if self.alive and self.phase != self.prev_phase:
            self.prev_phase = self.phase
            self.phase_event = self.phase
            Sound.play('phase')
            self.roar_until = self.clock + 1.0     # 단계가 바뀌면 잠깐 포효
            self.emitters = []
            self.lasers = []
            self.bb.clear()
            self.next_attack = self.clock + 1.6
            self.force_charge = (self.phase == CHARGE_MIN_PHASE)    # 돌진이 처음 나오는 단계는 돌진으로 시작
            if self.charge and self.charge['state'] != 'return':
                self.begin_return()

        # 플레이어 속도 추정 (너무 큰 값은 제한)
        if self.ppos is not None and dt > 0:
            vx, vy = (player.x - self.ppos[0]) / dt, (player.y - self.ppos[1]) / dt
            k = min(1.0, dt * 8)
            self.pvel = (self.pvel[0] + (vx - self.pvel[0]) * k, self.pvel[1] + (vy - self.pvel[1]) * k)
            sp = math.hypot(*self.pvel)
            if sp > 280:
                self.pvel = (self.pvel[0] * 280 / sp, self.pvel[1] * 280 / sp)
        self.ppos = (player.x, player.y)

        if not self.alive:
            self.emitters = []
            self.charge = None
            self.lasers = []
            if self.dying:
                self.die_t += dt
            return

        # 이동: 돌진 중이면 돌진 상태가, 레이저 중이면 제자리, 아니면 평소처럼 좌우로 떠다님
        if self.charge:
            self.update_charge(dt)
        elif self.lasers:
            pass
        else:
            self.mv_phase += dt * (0.8 + 0.3 * self.phase)
            self.x, self.y = self.normal_pos()

        if self.lasers:
            self.update_lasers(dt)

        for em in self.emitters:
            while em['left'] > 0 and self.clock >= em['next']:
                em['fn'](em['i'])
                em['i'] += 1
                em['left'] -= 1
                em['next'] += em['interval']
        self.emitters = [e for e in self.emitters if e['left'] > 0]

        if self.charge is None and not self.lasers:
            if self.phase < 2 and self.emitters:
                # 1, 2단계: 앞 패턴이 끝나야 다음 공격 (패턴이 겹쳐서 피하기 어려운 것을 막음)
                self.next_attack = self.clock + self.cooldown()
            elif self.clock >= self.next_attack:
                self.attack()
                self.next_attack = self.clock + self.cooldown()

    def hit(self):
        self.hp -= 1
        self.hurt_clock = self.clock
        Sound.play('hit')
        if self.hp <= 0:
            self.alive = False
            self.dying = True            # 쓰러지는 연출 시작
            self.die_t = 0.0
            Sound.play('explode')

    # ---------- 그리기 ----------
    def draw_warning(self):
        """돌진 경고 띠: 띠가 칠해진 곳이 실제 위험 범위"""
        c = self.charge
        if not self.alive or not c or c['state'] != 'warn':
            return
        length = 760
        width = (self.radius + HIT_RADIUS) * 2
        ang = c['ang']
        cx = self.x + math.cos(ang) * length / 2
        cy = self.y + math.sin(ang) * length / 2
        a = 0.5 if c['locked'] else 0.18 + 0.12 * math.sin(c['t'] * 14)   # 방향이 고정되면 진하게
        self.warn_img.opacify(a)
        self.warn_img.clip_composite_draw(0, 0, 4, 4, ang, '', cx, cy, length, width)

    def draw_lasers(self, ox=0.0, oy=0.0, layer='all'):
        """레이저 위험 띠와 레이저 본체. ox, oy는 화면 흔들림.
        layer: 'under' = 띠와 레이저 몸통(보스 뒤에 깔림), 'over' = 발사 순간 입 앞의 번쩍임(보스 위), 'all' = 한 번에"""
        if not self.has_laser or not self.alive:
            return
        for L in self.lasers:
            a = L['ang']
            c, s = math.cos(a), math.sin(a)
            x0, y0 = L['ox'] + ox, L['oy'] + oy

            under = layer in ('all', 'under')
            over = layer in ('all', 'over')
            if L['state'] == 'warn':
                if not under:
                    continue
                length = LASER_LEN
                cx, cy = x0 + c * length / 2, y0 + s * length / 2
                band_w = (L['hh'] + HIT_RADIUS) * 2           # 띠가 칠해진 곳이 실제 위험 범위
                band = 0.28 if L['locked'] else 0.10 + 0.08 * math.sin(L['t'] * 16)
                self.warn_img.opacify(band)
                self.warn_img.clip_composite_draw(0, 0, 4, 4, a, '', cx, cy, length, band_w)
                self.warn_img.opacify(0.95 if L['locked'] else 0.5)
                self.warn_img.clip_composite_draw(0, 0, 4, 4, a, '', cx, cy, length, 3)
                continue

            tf = L['t'] - L['warn']
            ws = self.laser_wscale(tf, L['fire'])
            length = self.laser_length(tf)
            if length < 1 or ws <= 0:
                continue
            cx, cy = x0 + c * length / 2, y0 + s * length / 2
            bw, bh = self.beam_wh
            if under:
                # 그림은 위쪽이 앞이라서 (진행 방향 - 90도) 만큼 돌려서 그린다
                self.beam_img.opacify(0.35)                      # 바깥 빛 번짐
                self.beam_img.clip_composite_draw(0, 0, bw, bh, a - math.pi / 2, '', cx, cy,
                                                  L['w'] * ws * 1.6, length)
                self.beam_img.opacify(1.0)                       # 본체
                self.beam_img.clip_composite_draw(0, 0, bw, bh, a - math.pi / 2, '', cx, cy,
                                                  L['w'] * ws, length)

            if over and tf < 0.35:                         # 발사 순간 보스 앞에서 터지는 효과
                fw, fh = self.burst_wh
                bl = L['burst'] * (1 + 0.6 * tf)
                bwid = bl * fw / fh
                self.burst_img.opacify(max(0.0, 1 - tf / 0.35))
                if self.burst_round:
                    self.burst_img.clip_composite_draw(0, 0, fw, fh, 0, '', x0, y0, bl, bl)
                else:
                    bx, by = x0 + c * bl / 2, y0 + s * bl / 2
                    self.burst_img.clip_composite_draw(0, 0, fw, fh, a - math.pi / 2, '', bx, by, bwid, bl)

    def draw_warning_hud(self):
        """레이저 위험 표시 (화면 위쪽에 깜빡이는 경고 판)"""
        warns = [L for L in self.lasers if L['state'] == 'warn']
        if not self.has_laser or not self.alive or not warns:
            return
        t = max(L['t'] for L in warns)
        locked = any(L['locked'] for L in warns)
        blink = 1.0 if locked else 0.55 + 0.45 * abs(math.sin(t * 9))
        w0, h0 = self.warn_wh
        W = WARN_HUD_W
        H = W * h0 / w0
        x, y = CANVAS_W / 2, WARN_HUD_Y
        self.dim_img.opacify(0.55 * blink)
        self.dim_img.draw(x, y, W + 16, H + 10)
        self.warn_hud.opacify(blink)
        self.warn_hud.draw(x, y, W, H)

    def anim_frame(self, use_hurt):
        """지금 보여줄 동작 그림 번호 (아틀라스 안의 프레임 번호)"""
        h = self.anim['have']
        flo = F_FLOAT + int(self.clock * 6) % 4                   # 평소: 둥둥 떠다니는 4프레임
        atk = lambda i: (F_ATTACK + i) if h.get('attack') else flo
        pose = lambda i: (F_POSE + i) if h.get('pose') else flo
        if use_hurt:
            return pose(0)                                        # 맞음
        if self.clock < self.roar_until:
            return pose(1)                                        # 단계가 바뀔 때 포효
        c = self.charge
        if c:
            if c['state'] == 'dash':
                return pose(2)                                    # 돌진
            if c['state'] in ('warn', 'stop'):
                return atk(1)                                     # 웅크림
            return flo
        if self.lasers:
            return atk(1) if any(L['state'] == 'warn' for L in self.lasers) else atk(2)
        if self.emitters:
            return atk(2)                                         # 탄을 쏘는 동안 입을 벌림
        if self.alive and 0 < self.next_attack - self.clock < 0.3:
            return atk(1)                                         # 공격 직전 웅크림
        return flo

    def draw(self):
        if self.alive or self.dying:
            a = 1.0
            jx = jy = 0.0
            if self.dying:                                      # 쓰러지는 중: 크게 떨리고 깜빡이다가 사라짐
                jx = random.uniform(-1, 1) * 8
                jy = random.uniform(-1, 1) * 8
                use_hurt = (self.hurt_img is not None or self.anim is not None) and int(self.die_t * 16) % 2 == 0
                a = max(0.0, min(1.0, (DEATH_TIME - self.die_t) / 0.3))
            else:
                use_hurt = (self.hurt_img is not None or self.anim is not None) and self.clock - self.hurt_clock < HURT_FACE_TIME
                if use_hurt:                                    # 맞으면 표정이 바뀌고 떨림
                    jx = random.uniform(-1, 1) * HURT_SHAKE
                    jy = random.uniform(-1, 1) * HURT_SHAKE
                elif self.clock < self.roar_until:                      # 포효: 몸을 부르르 떪
                    jx = random.uniform(-1, 1) * 4
                    jy = random.uniform(-1, 1) * 4
                elif self.charge and self.charge['state'] == 'warn':   # 돌진 준비 중에는 부들부들
                    jx = random.uniform(-1, 1) * 3
                    jy = random.uniform(-1, 1) * 3
                elif any(L['state'] == 'warn' for L in self.lasers):   # 레이저 준비 중에도 부들부들
                    jx = random.uniform(-1, 1) * 2
                    jy = random.uniform(-1, 1) * 2

            ph = self.phase
            if self.aura is not None and ph >= 1:               # 2, 3단계: 뒤에서 번지는 붉은 기운
                pulse = 0.5 + 0.5 * math.sin(self.clock * (4 if ph == 1 else 7))
                base = 0.22 if ph == 1 else 0.42
                self.aura.opacify(max(0.0, min(1.0, (base + 0.2 * pulse) * a)))
                s = self.dw * AURA_SIZE_MULT * (1 + 0.06 * pulse)
                self.aura.draw(self.x + jx, self.y + jy, s, s)

            if self.anim is not None:
                A = self.anim
                k = 1.0 + 0.03 * math.sin(self.clock * 6) if (ph == 2 and not self.dying) else 1.0
                if self.clock < self.roar_until:                # 포효할 때 몸을 부풀림
                    k *= 1.0 + 0.06 * math.sin(min(1.0, (self.roar_until - self.clock)) * math.pi)
                sc = BOSS_H / A['body_h'] * k
                feet = self.y + jy - BOSS_H / 2                 # 발 위치 (몸이 커져도 발은 그대로)
                if self.shadow_img is not None:                 # 떠 있는 보스 아래의 그림자
                    sh = 1.0 - 0.06 * math.sin(self.clock * 3.7)
                    self.shadow_img.opacify(0.38 * a)
                    self.shadow_img.draw(self.x + jx, feet - 26, self.dw * 0.95 * sh, self.dh * 0.22 * sh)
                dw_, dh_ = A['cw'] * sc, A['ch'] * sc
                cy = feet - A['base'] * sc + dh_ / 2
                img = A['imgs'][ph]
                img.opacify(a)
                img.clip_draw(self.anim_frame(use_hurt) * A['cw'], 0, A['cw'], A['ch'], self.x + jx, cy, dw_, dh_)
            else:
                if use_hurt and self.hurt_img is not None:
                    img, w, h = self.hurt_img, self.hdw, self.hdh
                else:
                    img, w, h = self.phase_imgs[ph], self.dw, self.dh
                if ph == 2 and not self.dying:                  # 3단계: 숨 쉬듯 커졌다 작아짐
                    k = 1.0 + 0.03 * math.sin(self.clock * 6)
                    w, h = w * k, h * k
                img.opacify(a)
                img.draw(self.x + jx, self.y + jy, w, h)

        bw, bx, by = 400, CANVAS_W / 2, CANVAS_H - 28
        self.bar_bg.draw(bx, by, bw + 6, 18)
        ratio = max(self.hp, 0) / self.max_hp
        if ratio > 0:
            self.bar_fg.draw(bx - bw / 2 + bw * ratio / 2, by, bw * ratio, 12)