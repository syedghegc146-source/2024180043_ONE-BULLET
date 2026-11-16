from pico2d import *
from PIL import Image, ImageDraw, ImageFont
import json
import math
import os
import time

from config import *
from litfx import make_lit
from walkanim import prepare_walk

# =============== 타이틀 화면 설정 (이 파일에서만 바꾸세요) ===============
TITLE_BGM_VOL = 30          # 타이틀 화면에서의 배경음악 음량 (0~128)
TITLE_FADE_IN = 0.6         # 처음에 밝아지는 시간(초)
START_FADE_OUT = 0.3        # 난이도를 고르고 어두워지는 시간(초)
BTN_W, BTN_H = 170, 58      # 난이도 버튼 크기
BTN_GAP = 190               # 버튼 사이 간격
BTN_Y = 235                 # 버튼 높이 위치
BEST_Y = 182                # 최고 기록 글자 높이 위치 (선택한 버튼 아래에만 나타남)
HINT_Y = 55                 # 아래쪽 안내 글자 높이 위치
PRESS_Y = 110               # "아무 키나 누르세요" 높이 위치
LOGO_W, LOGO_H = 760, 150   # 제목 그림 크기
LOGO_FONT = 100             # 제목 글자 크기 (이름이 길면 자동으로 줄어듦)
BEST_FADE = 0.12            # 선택을 바꿀 때 기록이 나타나는 시간(초)

LOGO_IMG = P('ui_title_logo.png')
PRESS_IMG = P('ui_title_press.png')
HINT_IMG = P('ui_title_hint.png')
HELP_IMG = P('ui_title_help.png')


def btn_path(i, on):
    return P(f'ui_btn_{i}_{"on" if on else "off"}.png')


def best_path(i):
    return P(f'ui_best_{i}.png')


# =============== 도우미 ===============
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


def fit_size(kr, en, max_w, start, stroke=0):
    """글자가 max_w 안에 들어오는 가장 큰 글자 크기 (start부터 줄여 나감)"""
    size = start
    while size > 24:
        font, ok = load_font(size)
        text = kr if ok else en
        try:
            w = font.getlength(text)
        except Exception:
            w = len(text) * size * 0.6
        if w + stroke * 2 <= max_w:
            break
        size -= 4
    return size


def fmt_time(t):
    m = int(t // 60)
    return f'{m}:{t - m * 60:05.2f}'


def load_best():
    try:
        with open(BEST_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def make_text_img(path, kr, en, size, color, w, h, stroke=0, shadow=None):
    """글자만 있는 투명 그림. 한글 폰트가 없으면 영어를 쓴다. shadow=(dx, dy, 색)"""
    font, ok = load_font(size)
    text = kr if ok else en
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if shadow:
        draw_text(d, w / 2 + shadow[0], 4 + shadow[1], text, font, shadow[2], stroke)
    draw_text(d, w / 2, 4, text, font, color, stroke)
    img.save(path)


def make_panel(path, title, color, lines, size, title_size=60, bg_alpha=185):
    """제목 + 안내 문구가 있는 반투명 판. lines = [(한글, 영어, 글자크기, 색), ...]"""
    img = Image.new('RGBA', size, (0, 0, 0, bg_alpha))
    d = ImageDraw.Draw(img)
    font, _ = load_font(title_size)
    y = int(size[1] * 0.10)
    draw_text(d, size[0] / 2, y, title, font, color)
    y += int(title_size * 1.4)
    for kr, en, sz, col in lines:
        f, ok = load_font(sz)
        draw_text(d, size[0] / 2, y, kr if ok else en, f, col)
        y += int(sz * 1.6)
    img.save(path)


def make_button(path, kr, en, selected):
    """난이도 버튼"""
    img = Image.new('RGBA', (BTN_W, BTN_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (70, 25, 25, 235) if selected else (20, 20, 32, 190)
    edge = (255, 220, 80, 255) if selected else (150, 150, 175, 255)
    d.rounded_rectangle((2, 2, BTN_W - 3, BTN_H - 3), radius=12, fill=bg, outline=edge,
                        width=3 if selected else 2)
    font, ok = load_font(28)
    draw_text(d, BTN_W / 2, 10, kr if ok else en, font, edge if selected else (230, 230, 240, 255))
    img.save(path)


def button_at(mx, my):
    """(mx, my)에 있는 난이도 버튼 번호. 없으면 None"""
    for i in range(len(DIFFICULTIES)):
        cx = CANVAS_W / 2 + (i - 1) * BTN_GAP
        if abs(mx - cx) <= BTN_W / 2 and abs(my - BTN_Y) <= BTN_H / 2:
            return i
    return None


# =============== 이미지 준비 (창 열기 전에 실행) ===============
def prepare_title():
    """타이틀 화면에 쓰는 그림들을 만든다"""
    white = (255, 255, 255, 255)
    size = fit_size(GAME_TITLE, GAME_TITLE, LOGO_W - 40, LOGO_FONT, stroke=7)   # 이름이 길면 글자 크기를 줄임
    make_text_img(LOGO_IMG, GAME_TITLE, GAME_TITLE, size, (255, 215, 90, 255), LOGO_W, LOGO_H,
                  stroke=7, shadow=(0, 6, (200, 40, 40, 255)))
    make_text_img(PRESS_IMG, '아무 키나 누르세요', 'PRESS ANY KEY', 30, white, 500, 50, stroke=3)
    make_text_img(HINT_IMG, '1 2 3  /  ← →  Enter  /  클릭        H  조작법',
                  '1 2 3  /  arrows Enter  /  click        H  controls',
                  20, (225, 225, 240, 255), 760, 34, stroke=2)
    for i, d in enumerate(DIFFICULTIES):
        make_button(btn_path(i, False), d['kr'], d['en'], False)
        make_button(btn_path(i, True), d['kr'], d['en'], True)
    make_panel(HELP_IMG, 'CONTROLS', (255, 120, 120, 255), [
        ('WASD 이동   Shift 대쉬', 'WASD move   Shift dash', 24, white),
        ('우클릭 조준   좌클릭 발사', 'Right-click aim   Left-click shoot', 24, white),
        ('총알은 한 발! 바닥의 총알을 주워서 다시 쏘세요',
         'ONE bullet only - pick it up to shoot again', 22, (200, 200, 255, 255)),
        ('대쉬 중에는 맞지 않아요', 'You are invincible while dashing', 22, (255, 230, 120, 255)),
        ('P 일시정지     아무 키나 누르면 닫기', 'P pause     press any key to close', 20, white),
    ], (700, 330))
    if not os.path.exists(DIM_IMG):
        Image.new('RGBA', (4, 4), (0, 0, 0, 255)).save(DIM_IMG)


# =============== 타이틀 화면 실행 ===============
def run_title(default_sel=1):
    """타이틀 화면을 보여 주고 고른 난이도 번호를 돌려준다. 창을 닫으면 None.
    창(open_canvas)이 열린 다음에 호출해야 한다"""
    bg = load_image(BG_SRC) if os.path.exists(BG_SRC) else None
    dim = load_image(DIM_IMG)
    logo, press = load_image(LOGO_IMG), load_image(PRESS_IMG)
    hint, help_img = load_image(HINT_IMG), load_image(HELP_IMG)
    btn_off = [load_image(btn_path(i, False)) for i in range(len(DIFFICULTIES))]
    btn_on = [load_image(btn_path(i, True)) for i in range(len(DIFFICULTIES))]
    cursor = load_image(CROSSHAIR) if os.path.exists(CROSSHAIR) else None
    aura = load_image(AURA_IMG) if os.path.exists(AURA_IMG) else None

    # 주인공 그림: 걷기 앞모습 프레임(walk_front.png)을 쓰고, 없으면 front_clean.png
    hero_img, hero_cell, hero_ratio, hero_frame = None, None, 0.8, 0
    try:
        cuts = prepare_walk(P, ('front',))
        if 'front' in cuts:
            path, cw, ch = cuts['front']
            hero_img, hero_cell, hero_ratio, hero_frame = load_image(make_lit(path)), (cw, ch), cw / ch, 1   # 1번 프레임 = 발 모은 자세
    except Exception as e:
        print('[타이틀] 주인공 그림 준비 실패:', e)
    if hero_img is None and os.path.exists(FRONT_CLEAN):
        try:
            fw, fh = Image.open(FRONT_CLEAN).size
            hero_img, hero_cell, hero_ratio = load_image(FRONT_CLEAN), (fw, fh), fw / fh
        except Exception:
            hero_img = None
    shadow_img = load_image(SHADOW) if os.path.exists(SHADOW) else None

    Sound.bgm_volume(TITLE_BGM_VOL)

    scene = 'title'                 # title / select / help
    sel = max(0, min(len(DIFFICULTIES) - 1, default_sel))
    last_sel = sel                  # 선택이 바뀌었는지 알아내는 용도
    sel_t = 1.0                     # 선택이 바뀌고 지난 시간 (기록이 나타나는 효과)
    lp = 0.0                        # 0=타이틀, 1=난이도 선택 (부드럽게 바뀜)
    mouse = (CANVAS_W // 2, CANVAS_H // 2)
    leaving = None                  # (고른 번호, 시작 시각)
    t0 = prev = time.time()

    while True:
        now = time.time()
        dt = min(now - prev, 0.05)
        prev = now
        t = now - t0
        picked = None

        for e in get_events():
            if e.type == SDL_QUIT:
                return None
            if leaving is not None:
                continue
            if e.type == SDL_MOUSEMOTION:
                mouse = (e.x, CANVAS_H - 1 - e.y)
                if scene == 'select' and lp > 0.8:
                    i = button_at(*mouse)
                    if i is not None:
                        sel = i
            elif e.type == SDL_KEYDOWN:
                k = e.key
                if scene == 'title':
                    if k == SDLK_ESCAPE:
                        return None
                    scene = 'select'
                elif scene == 'help':
                    scene = 'select'
                else:
                    if k == SDLK_ESCAPE:
                        scene = 'title'
                    elif k in (SDLK_1, SDLK_2, SDLK_3):
                        if k - SDLK_1 < len(DIFFICULTIES):
                            picked = k - SDLK_1
                    elif k in (SDLK_LEFT, SDLK_a):
                        sel = max(0, sel - 1)
                    elif k in (SDLK_RIGHT, SDLK_d):
                        sel = min(len(DIFFICULTIES) - 1, sel + 1)
                    elif k in (SDLK_RETURN, SDLK_SPACE):
                        picked = sel
                    elif k == SDLK_h:
                        scene = 'help'
            elif e.type == SDL_MOUSEBUTTONDOWN and e.button == SDL_BUTTON_LEFT:
                mouse = (e.x, CANVAS_H - 1 - e.y)
                if scene in ('title', 'help'):
                    scene = 'select'
                elif lp > 0.8:
                    i = button_at(*mouse)
                    if i is not None:
                        picked = i

        if picked is not None and leaving is None:
            leaving = (picked, now)
            sel = picked
            Sound.play('reload')

        if sel != last_sel:                 # 선택이 바뀌면 기록이 새로 나타남
            last_sel = sel
            sel_t = 0.0
        sel_t += dt

        target = 1.0 if scene in ('select', 'help') else 0.0
        lp += (target - lp) * min(1.0, dt * 8)

        fade_out = 0.0
        if leaving is not None:
            fade_out = min(1.0, (now - leaving[1]) / START_FADE_OUT)
            if fade_out >= 1.0:
                return leaving[0]

        # ---------- 그리기 ----------
        clear_canvas()
        if bg:
            bg.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W + 40, CANVAS_H + 40)
        dim.opacify(0.28 + 0.25 * lp)
        dim.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)

        by = 300 + 60 * lp + 8 * math.sin(t * 2.0)       # 주인공 위치와 크기
        bh = 200 - 50 * lp
        if aura:
            pulse = 0.5 + 0.5 * math.sin(t * 3)
            aura.opacify(0.25 + 0.2 * pulse)
            s = bh * 2.6 * (1 + 0.05 * pulse)
            aura.draw(CANVAS_W // 2, by, s, s)
        if shadow_img:                                    # 발밑 그림자 (떠다니는 높이에 따라 크기가 변함)
            sh = 0.9 - 0.08 * math.sin(t * 2.0)
            shadow_img.opacify(0.7)
            shadow_img.draw(CANVAS_W // 2, by - bh / 2 - 6, bh * hero_ratio * 1.1 * sh, bh * 0.28 * sh)
        if hero_img:
            hero_img.opacify(1.0)
            breathe = 1.0 + 0.015 * math.sin(t * 3.0)      # 숨 쉬듯 살짝 커졌다 작아짐
            cw, ch = hero_cell
            hero_img.clip_draw(hero_frame * cw, 0, cw, ch, CANVAS_W // 2, by,
                               bh * hero_ratio * breathe, bh * breathe)

        ls = 1.0 - 0.3 * lp                               # 제목: 선택 화면에서는 작아지며 위로
        ly = 470 + 55 * lp + 5 * math.sin(t * 2.4)
        logo.opacify(1.0)
        logo.draw(CANVAS_W // 2, ly, LOGO_W * ls, LOGO_H * ls)

        pa = (1 - lp) * (0.55 + 0.45 * abs(math.sin(t * 3)))   # "아무 키나 누르세요" 깜빡임
        if pa > 0.02:
            press.opacify(pa)
            press.draw(CANVAS_W // 2, PRESS_Y)

        ba = max(0.0, (lp - 0.5) * 2)                      # 난이도 버튼
        if ba > 0.02:
            for i in range(len(DIFFICULTIES)):
                x = CANVAS_W / 2 + (i - 1) * BTN_GAP
                on = (i == sel)
                img = (btn_on if on else btn_off)[i]
                img.opacify(ba)
                k = 1.08 if on else 1.0
                img.draw(x, BTN_Y, BTN_W * k, BTN_H * k)

            hint.opacify(ba)
            hint.draw(CANVAS_W // 2, HINT_Y)

        if scene == 'help':
            dim.opacify(0.5)
            dim.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)
            help_img.draw(CANVAS_W // 2, CANVAS_H // 2)

        if cursor:
            cursor.opacify(0.9)
            cursor.draw(mouse[0], mouse[1], 26, 26)

        fade = max(max(0.0, 1.0 - t / TITLE_FADE_IN), fade_out)   # 시작할 때 밝아지고, 고르면 어두워짐
        if fade > 0.01:
            dim.opacify(fade)
            dim.draw(CANVAS_W // 2, CANVAS_H // 2, CANVAS_W, CANVAS_H)

        update_canvas()
        delay(0.01)