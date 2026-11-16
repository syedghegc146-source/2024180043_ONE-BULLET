from pico2d import *
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import json
import math
import os

# 어디서 실행해도 이미지/소리 파일을 찾도록 이 폴더로 이동
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 파일을 찾을 폴더들 (위에서부터 먼저 발견되는 것을 사용). 폴더 이름이 다르면 여기에 추가하세요
SEARCH_DIRS = ['.', 'image', 'images', 'sounds', 'sound']


def P(name):
    """파일 이름을 받아서 실제 있는 경로를 돌려준다. 어디에도 없으면 이름 그대로 (자동 생성 파일용)"""
    for d in SEARCH_DIRS:
        p = name if d == '.' else os.path.join(d, name)
        if os.path.exists(p):
            return p
    return name


# =============== 설정값 (수치는 여기서 전부 바꾸세요) ===============
CANVAS_W, CANVAS_H = 800, 600
SCALE = 0.38            # 캐릭터 크기 (예전 0.3)
FRONT_ADJUST = 1.0
BACK_ADJUST = 1.0

WALK_SPEED = 250
DASH_SPEED = 900
DASH_TIME = 0.15
DASH_COOLDOWN = 0.8

# 걷기 효과
STEP_FREQ = 14
BOUNCE_PX = 5
TILT_DEG = 4
SQUASH = 0.06
WALK_PROC = 0.35        # 걷기 프레임 그림이 있을 때 통통 튀는 효과의 세기 (0이면 끔, 1이면 예전 그대로)
SHADOW_ALPHA = 0.75
DASH_TILT_DEG = 15

# 사격
MAX_AMMO = 1
PICKUP_RADIUS = 35
FIRE_COOLDOWN = 0.18
BULLET_SPEED = 850
BULLET_LEN = 36          # 탄피 크기 (바닥/탄 표시 기준)
BULLET_FLY_SCALE = 0.8   # 날아가는 총알(불꽃 포함) 크기 배율
BULLET_RADIUS = 6
BULLET_ANGLE_FIX = 0.0   # 날아가는 총알 방향이 반대로 보이면 3.14159 로 변경
BULLET_ALPHA_GAIN = 3.0  # 검은 배경 투명화 강도 (총알이 흐리면 올리기)
AIM_SLOW = 0.5
SPREAD_DEG = 7
GUN_Y = 0
MUZZLE = 30

# 튕겨나감
HOP_TIME = 0.55
HOP_HEIGHT = 70
HOP_MIN, HOP_MAX = 130, 260
SPIN_TURNS = 2           # 튕길 때 도는 바퀴 수

# 보스
BOSS_H = 160
BOSS_HP = 15                       # 보통 난이도 기준 체력 (쉬움 x0.7, 어려움 x1.2)
BOSS_BASE_Y = CANVAS_H - 170        # 보스가 평소에 떠 있는 높이
BULLET_FRONT_GAP = 30               # 맞고 튕긴 총알이 보스 아래쪽 가장자리에서 최소 이만큼 앞(아래)에 떨어짐
HURT_FACE_TIME = 0.28               # 맞았을 때 표정이 바뀌어 있는 시간(초)
HURT_SHAKE = 5                      # 맞았을 때 보스가 떨리는 정도(px)
DEATH_TIME = 1.8                    # 보스가 쓰러지는 연출 시간(초)
AURA_SIZE_MULT = 2.4                # 2, 3단계 붉은 기운의 크기 (보스 크기의 몇 배)

# 보스 난이도
PHASE_COOLDOWN = [1.9, 1.5, 1.7]    # 단계별 공격 간격(초). 클수록 쉬움
PHASE3_DOUBLE = False               # 3단계에서 패턴 2개 동시 사용 (보통 난이도 기준)
PHASE2_ARROW_SPEED = 0.78           # 2단계에서 화살(가시) 탄 속도 배율. 낮을수록 쉬움
PHASE2_HOMING_TIME = 1.6            # 2단계 유도 구슬이 쫓아오는 시간(초)

# 보스 돌진
CHARGE_MIN_PHASE = 1                # 몇 단계부터 돌진 (0=1단계, 1=2단계, 2=3단계). 그 단계가 시작되면 첫 공격이 돌진
CHARGE_WARN = 1.2                   # 경고 띠가 보이는 시간(초). 길수록 쉬움
CHARGE_LOCK = 0.45                  # 돌진 직전에 방향이 고정되는 시간(초). 길수록 쉬움
CHARGE_SPEED = 650                  # 돌진 속도
CHARGE_MAX_DIST = 560               # 최대 돌진 거리
CHARGE_RETURN = 0.9                 # 돌진 후 제자리로 돌아오는 시간(초)
# 돌진이 끝난 뒤의 위협
CHARGE_STOP = 0.35                  # 돌진이 끝나고 멈춰 있는 시간(초). 이 사이에 충격파가 퍼짐
CHARGE_END_BURST = True             # 돌진이 끝나는 자리에서 충격파 탄 고리를 낼지
CHARGE_BURST_N = 16                 # 충격파 탄 수
CHARGE_BURST_GAP = 3                # 충격파에서 비어 있는 칸 수. 클수록 쉬움
CHARGE_BURST_SPEED = 210            # 충격파 탄 속도
CHARGE_CHAIN_PHASE = 2              # 몇 단계부터 연속 돌진 (0=1단계, 1=2단계, 2=3단계). 3으로 하면 끔
CHARGE_CHAIN_MAX = 1                # 연속 돌진 최대 횟수
CHARGE_CHAIN_PROB = 1             # 연속 돌진이 이어질 확률
CHARGE_CHAIN_WARN = 0.8             # 연속 돌진의 경고 시간(초). 길수록 쉬움

# 보스 레이저 (가는 레이저, 3단계)
LASER_MIN_PHASE = 2                 # 몇 단계부터 레이저 (0=1단계, 1=2단계, 2=3단계)
LASER_COUNT = 2                     # 한 번에 나가는 레이저 줄 수 (1~5). 적을수록 쉬움
LASER_SPREAD = 0.5                  # 줄 사이 각도(라디안). 클수록 사이 공간이 넓어서 쉬움
LASER_WARN = 1.3                    # 위험 표시가 나오는 시간(초). 길수록 쉬움
LASER_LOCK = 0.4                    # 발사 직전에 방향이 고정되는 시간(초). 길수록 쉬움
LASER_EXTEND = 0.1                  # 발사 후 끝까지 뻗는 시간(초). 짧을수록 빠름
LASER_FIRE = 0.55                   # 레이저가 유지되는 시간(초)
LASER_WIDTH = 46                    # 레이저 굵기(px)
LASER_HIT_HALF = 14                 # 레이저 피격 판정 반폭(px). 작을수록 쉬움
LASER_LEN = 900                     # 레이저 길이(px)
LASER_MOUTH_DY = 24                 # 레이저가 나오는 입 위치: 보스 몸 중심에서 아래로 몇 px (보스 그림이 바뀌면 여기를 조절)
LASER_BURST_LEN = 320               # 발사 순간 보스 앞에 터지는 효과 크기(px)
WARN_HUD_W = 330                    # 경고 판 가로 크기(px)
WARN_HUD_Y = CANVAS_H - 88          # 경고 판 높이 위치
WARN_PICK = (1, 1)                  # warning.png에서 쓸 판 (줄, 칸). 0부터 시작
LASER_BODY_BAND = (0.0, 0.28)       # laser_beam.png에서 몸통으로 쓸 위쪽 비율

# 굵은 레이저 (3단계, 가는 레이저와 번갈아 나옴)
THICK_MIN_PHASE = 2                 # 몇 단계부터 굵은 레이저
THICK_WARN = 1.8                    # 위험 표시 시간(초). 길수록 쉬움
THICK_LOCK = 0.7                    # 발사 직전에 방향이 고정되는 시간(초). 길수록 쉬움
THICK_FIRE = 0.9                    # 레이저가 유지되는 시간(초)
THICK_WIDTH = 130                   # 굵기(px)
THICK_HIT_HALF = 50                 # 피격 판정 반폭(px). 작을수록 쉬움
THICK_BURST_MULT = 1.7              # 발사 순간 터지는 효과를 가는 레이저보다 몇 배로

# 플레이어 체력
PLAYER_MAX_HP = 3        # 체력 칸 수 (보통 난이도 기준)
INV_TIME = 1.6           # 맞은 뒤 무적 시간(초)
CLEAR_RADIUS = 110       # 맞았을 때 주변 탄을 지우는 반경
HIT_RADIUS = 10          # 플레이어 피격 판정 반경 (작을수록 쉬움)
HIT_OFFSET = 0.1         # 판정 위치를 몸통 중앙에서 아래로 내리는 비율 (캐릭터 높이 기준)

# 타격감 연출
HITSTOP_HIT = 0.05       # 총알이 보스에 맞을 때 화면이 멈추는 시간(초). 0이면 끔
HITSTOP_KILL = 0.16      # 보스를 쓰러뜨리는 마지막 한 발
HITSTOP_PLAYER = 0.07    # 내가 맞을 때
DANGER_HP = 1            # 하트가 이 개수 이하로 남으면 위험 연출

# 난이도 (시작 화면에서 선택). 숫자는 여기서 바꾸세요
DIFFICULTIES = [
    {'id': 'easy', 'kr': '쉬움', 'en': 'EASY', 'player_hp': 5, 'boss_hp': int(BOSS_HP * 0.7),
     'cd': 1.3, 'speed': 0.85, 'double': False},
    {'id': 'normal', 'kr': '보통', 'en': 'NORMAL', 'player_hp': PLAYER_MAX_HP, 'boss_hp': BOSS_HP,
     'cd': 1.0, 'speed': 1.0, 'double': PHASE3_DOUBLE},
    {'id': 'hard', 'kr': '어려움', 'en': 'HARD', 'player_hp': 2, 'boss_hp': int(BOSS_HP * 1.2),
     'cd': 0.8, 'speed': 1.1, 'double': True},
]
DEFAULT_DIFFICULTY = 1   # 처음 선택돼 있는 난이도 (0=쉬움, 1=보통, 2=어려움)
BEST_FILE = 'best_time.json'    # 최고 기록 저장 파일

# 효과
PICKUP_FX_TIME = 0.5     # 총알 주울 때 효과 시간(초)
GAUGE_W = 44             # 대쉬 게이지 가로 크기(px)

# 아레나 (플레이어와 총알이 있을 수 있는 타원 영역). 넓히려면 RX, RY를 키우세요
ARENA_CENTER_X = CANVAS_W / 2 + 10
ARENA_CENTER_Y = CANVAS_H / 2 - 10
ARENA_RX = 340
ARENA_RY = 235
BULLET_MARGIN = 25       # 떨어진 총알이 아레나 가장자리에서 안쪽으로 떨어져 있는 거리

# 소리 파일 (sounds 폴더나 같은 폴더에 두기. 없는 소리는 건너뜀)
SFX_FILES = {
    'shot': P('shot.wav'),                # 총소리
    'reload': P('reload.wav'),            # 장전 (총알 줍기)
    'hit': P('hit.wav'),                  # 보스 피격
    'player_hit': P('player_hit.wav'),    # 플레이어 피격
    'dash': P('dash.wav'),                # 대쉬
    'gameover': P('gameover.wav'),        # 게임오버
    'clear': P('clear.wav'),              # 클리어
    'phase': P('phase.wav'),              # 보스 단계 전환
    'warning': P('warning.wav'),          # 레이저 위험 표시 (선택)
    'laser': P('laser.wav'),              # 레이저 발사 (선택)
    'laser_charge': P('laser_charge.wav'),  # 레이저 기 모으는 소리 (선택, 없으면 warning.wav)
    'explode': P('explode.wav'),          # 보스 쓰러지는 연출 (선택)
    'block': P('block.wav'),              # 방패에 튕김
    'door': P('door.wav'),                # 문 열림
    'slime_attack': P('slime_attack.wav'),  # 슬라임 돌진
    'step': P('step.wav'),                # 플레이어 발소리
    'boss_enter': P('boss_enter.wav'),    # 보스방 입장
    'slam': P('slam.wav'),                # 보스 돌진이 끝나고 부딪히는 소리 (선택)
}

SFX_VOL = {                            # 소리별 음량 (0~128)
    'shot': 50, 'reload': 20, 'hit': 80, 'player_hit': 90, 'dash': 128,
    'gameover': 100, 'clear': 100, 'phase': 50, 'warning': 90, 'laser': 100, 'explode': 100,
    'block': 85, 'door': 95, 'slime_attack': 75, 'step': 128,  'boss_enter': 50, 'slam': 110, 'laser_charge': 100
}
BGM_FILES = [P('bgm.mp3'), P('bgm.ogg'), P('bgm.wav')]   # 먼저 읽히는 파일을 사용
BGM_VOL = 45                                              # 배경음악 음량 (0~128)
BGM_VOL_END = 15                                          # 게임오버/클리어/시작 화면 음량

# 화면
GAME_TITLE = 'ONE BULLET'   # 시작 화면 제목
BG_SRC = P('background.png')

# 보스 탄 원본 시트 (체크무늬 배경 위에 여러 방향 그림이 모여 있는 이미지)
SHEET_FILES = [P('bullet_type1.png'), P('bullet_type2.png'), P('bullet_type3.png')]
BB_FILES = [P('boss_bullet_1.png'), P('boss_bullet_2.png'), P('boss_bullet_3.png')]   # 자동 생성
BB_META = P('boss_bullet_meta.json')                                                  # 자동 생성
BB_LEN = [46, 28, 40]    # 화면에 그려지는 탄 길이(px): 화살 / 핀 / 구슬
SAT_THRESH = 70          # 배경 제거 강도 (배경이 남으면 올리고, 탄이 깎이면 내리기)

# 시트 처리 실패 시 대신 쓰는 빛나는 구슬 (중심색, 바깥색)
ORB_COLORS = [
    ((255, 235, 230), (255, 40, 50)),
    ((255, 255, 220), (255, 170, 20)),
    ((255, 235, 255), (190, 60, 255)),
]

# 파일 이름 (대부분 자동 생성)
SRC = P('character.png')
CLEAN = P('character_clean.png')
RECTS = P('sheet_rects.json')
FRONT_SRC, FRONT_CLEAN = P('front.png'), P('front_clean.png')
BACK_SRC, BACK_CLEAN = P('back.png'), P('back_clean.png')
BULLET_SRC = P('bullet.png')
BULLET_ICON, BULLET_FLY, BULLET_GROUND = P('bullet_icon.png'), P('bullet_fly.png'), P('bullet_ground.png')
BOSS_SRC, BOSS_CLEAN = P('boss.png'), P('boss_clean.png')
BOSS_HURT_SRC, BOSS_HURT_CLEAN = P('boss_hurt.png'), P('boss_hurt_clean.png')   # 맞은 표정 (없으면 자동 생성)
BOSS_P2_CLEAN, BOSS_P3_CLEAN = P('boss_phase2.png'), P('boss_phase3.png')       # 2, 3단계 보스 모습 (자동 생성)
AURA_IMG = P('fx_aura.png')                                                     # 붉은 기운 (자동 생성)
VIGNETTE_IMG = P('fx_vignette.png')                                             # 체력 위험 화면 가장자리 (자동 생성)
WARNING_SRC, WARNING_CLEAN = P('warning.png'), P('warning_clean.png')           # 경고 판 시트
LASER_BEAM_SRC, LASER_BEAM_CLEAN = P('laser_beam.png'), P('laser_beam_clean.png')     # 가는 레이저
LASER_BURST_SRC, LASER_BURST_CLEAN = P('laser_burst.png'), P('laser_burst_clean.png') # 불꽃 모양 레이저
SHADOW, CROSSHAIR, DOT = P('shadow.png'), P('crosshair.png'), P('dot.png')
BAR_BG, BAR_FG = P('bar_bg.png'), P('bar_fg.png')

OVER_IMG, CLEAR_IMG = P('ui_gameover.png'), P('ui_clear.png')
TITLE_IMG, PAUSE_IMG = P('ui_title.png'), P('ui_pause.png')
BANNER_IMGS = [None, P('ui_phase2.png'), P('ui_phase3.png')]
DIM_IMG, FLASH_IMG, SPARK_IMG = P('fx_dim.png'), P('fx_flash.png'), P('fx_spark.png')
HEART_FULL, HEART_EMPTY = P('heart_full.png'), P('heart_empty.png')

BG_THRESH = 60
SINGLE_THRESH = 25
MIN_GAP = 15


# =============== 소리 ===============
class Sound:
    sfx = {}
    bgm = None

    @classmethod
    def load(cls):
        """open_canvas 다음에 한 번 호출. 파일이 없거나 실패한 소리는 건너뜀"""
        for name, path in SFX_FILES.items():
            if not os.path.exists(path):
                print(f'[소리] {path} 없음 - 건너뜁니다')
                continue
            try:
                w = load_wav(path)
                w.set_volume(SFX_VOL.get(name, 100))
                cls.sfx[name] = w
            except Exception as e:
                print(f'[소리] {path} 불러오기 실패: {e}')

        for path in BGM_FILES:
            if not os.path.exists(path):
                continue
            try:
                cls.bgm = load_music(path)
                cls.bgm.set_volume(BGM_VOL)
                break
            except Exception as e:
                print(f'[소리] {path} 불러오기 실패: {e}')
                cls.bgm = None
        if cls.bgm is None:
            print('[소리] 배경음악 없이 진행합니다')

    @classmethod
    def play(cls, name):
        w = cls.sfx.get(name)
        if w:
            try:
                w.play()
            except Exception:
                pass

    @classmethod
    def start_bgm(cls):
        if cls.bgm:
            try:
                cls.bgm.set_volume(BGM_VOL)
                cls.bgm.repeat_play()
            except Exception:
                pass

    @classmethod
    def bgm_volume(cls, vol):
        if cls.bgm:
            try:
                cls.bgm.set_volume(vol)
            except Exception:
                pass


# =============== 아레나 ===============
def arena_d(x, y):
    """아레나 중심 0, 가장자리 1"""
    return math.hypot((x - ARENA_CENTER_X) / ARENA_RX, (y - ARENA_CENTER_Y) / ARENA_RY)


def clamp_arena(x, y, margin=0):
    """아레나 밖이면 가장자리(margin만큼 안쪽)로 끌어당긴 좌표를 돌려준다"""
    lim = 1 - margin / min(ARENA_RX, ARENA_RY)
    d = arena_d(x, y)
    if d > lim:
        k = lim / d
        return ARENA_CENTER_X + (x - ARENA_CENTER_X) * k, ARENA_CENTER_Y + (y - ARENA_CENTER_Y) * k
    return x, y


def bullet_front_limit(boss_radius):
    """튕기거나 떨어진 총알이 있을 수 있는 가장 높은 y (보스 아래쪽 가장자리보다 앞쪽)"""
    return BOSS_BASE_Y - boss_radius - BULLET_FRONT_GAP


# =============== 캐릭터/총알 이미지 준비 (창 열기 전에 실행) ===============
def fresh(src, dst):
    return os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)


def remove_black_bg(img, thresh):
    w, h = img.size
    for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if img.getpixel(pt)[3] != 0:
            ImageDraw.floodfill(img, pt, (0, 0, 0, 0), thresh=thresh)
    return img


def prepare_sheet():
    if fresh(SRC, CLEAN) and os.path.exists(RECTS):
        with open(RECTS) as f:
            return json.load(f)

    img = Image.open(SRC).convert('RGBA')
    w, h = img.size
    img = remove_black_bg(img, BG_THRESH)
    img.save(CLEAN)
    alpha = np.array(img)[:, :, 3] > 40

    def runs(mask):
        idx = np.where(mask)[0]
        if len(idx) == 0:
            return []
        out, start, prev = [], idx[0], idx[0]
        for i in idx[1:]:
            if i - prev > MIN_GAP:
                out.append((start, prev + 1))
                start = i
            prev = i
        out.append((start, prev + 1))
        return out

    bands = runs(alpha.any(axis=1))
    if len(bands) < 2:
        bands = [(0, h // 2), (h // 2, h)]
    sprites = []
    for (y0, y1) in bands[:2]:
        row = []
        for (x0, x1) in runs(alpha[y0:y1].any(axis=0)):
            ys = np.where(alpha[y0:y1, x0:x1].any(axis=1))[0]
            ty0, ty1 = y0 + ys[0], y0 + ys[-1] + 1
            row.append((int(x0), int(h - ty1), int(x1 - x0), int(ty1 - ty0)))
        sprites.append(row)
    with open(RECTS, 'w') as f:
        json.dump(sprites, f)
    return sprites


def prepare_single(src, dst):
    """배경 제거 + 캐릭터 영역만 크롭. (w, h) 반환. 파일이 없으면 None"""
    if not os.path.exists(src):
        return None
    if fresh(src, dst):
        with Image.open(dst) as im:
            return im.size
    img = Image.open(src).convert('RGBA')
    img = remove_black_bg(img, SINGLE_THRESH)
    mask = img.getchannel('A').point(lambda a: 255 if a > 40 else 0)
    box = mask.getbbox()
    if box:
        img = img.crop(box)
    img.save(dst)
    return img.size


def _runs(mask1d, gap):
    """True가 이어진 구간 목록. gap 이하의 틈은 같은 구간으로 본다"""
    idx = np.where(mask1d)[0]
    if len(idx) == 0:
        return []
    out, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap:
            out.append((int(start), int(prev + 1)))
            start = i
        prev = i
    out.append((int(start), int(prev + 1)))
    return out


def _largest_component(m):
    """True 픽셀 중 가장 큰 덩어리만 남긴 마스크"""
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    best, best_n, n = 0, 0, 0
    for sy in range(h):
        for sx in range(w):
            if m[sy, sx] and lab[sy, sx] == 0:
                n += 1
                lab[sy, sx] = n
                stack, cnt = [(sy, sx)], 0
                while stack:
                    y, x = stack.pop()
                    cnt += 1
                    for ny in range(max(0, y - 1), min(h, y + 2)):
                        for nx in range(max(0, x - 1), min(w, x + 2)):
                            if m[ny, nx] and lab[ny, nx] == 0:
                                lab[ny, nx] = n
                                stack.append((ny, nx))
                if cnt > best_n:
                    best_n, best = cnt, n
    return (lab == best) if best else m


def _save_crop(arr, path):
    img = Image.fromarray(arr)
    box = img.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox()
    if box:
        img = img.crop(box)
    img.save(path)
    return img.size


def prepare_bullet():
    """bullet.png(발사 전 / 비행 중 / 바닥에 박힘)를 나눠서 저장.
    하단 텍스트 영역을 제외하여 글자 흐림 현상 방지.
    """
    if not os.path.exists(BULLET_SRC):
        return None
    outs = {'icon': BULLET_ICON, 'fly': BULLET_FLY, 'ground': BULLET_GROUND}
    if all(fresh(BULLET_SRC, p) for p in outs.values()):
        sizes = {}
        for k, p in outs.items():
            with Image.open(p) as im:
                sizes[k] = im.size
        return sizes

    img_raw = Image.open(BULLET_SRC).convert('RGBA')
    w_raw, h_raw = img_raw.size
    px = np.array(img_raw)

    if px[0, 0, 3] != 0:        # 검은 배경이면 밝기를 투명도로 변환
        bright = px[:, :, :3].max(axis=2)
        px[:, :, 3] = np.clip(bright.astype(np.float32) * BULLET_ALPHA_GAIN, 0, 255).astype(np.uint8)
        mask = bright > 30
    else:
        mask = px[:, :, 3] > 40

    # 하단 글자 영역이 섞이지 않도록 상단 영역(65% 범위)만 사용
    mask[int(h_raw * 0.65):, :] = False

    rows = _runs(mask.any(axis=1), 8)
    if not rows:
        return None
    y0, y1 = max(rows, key=lambda r: mask[r[0]:r[1]].sum())
    cols = _runs(mask[y0:y1].any(axis=0), 15)

    if len(cols) >= 3:
        c_icon, c_fly, c_ground = cols[0], cols[1], cols[2]
    else:                        # 시트 모양이 아니면 한 장을 전부 같이 사용
        c_icon = c_fly = c_ground = (cols[0][0], cols[-1][1])

    def region(c):
        return px[y0:y1, c[0]:c[1]].copy()

    sizes = {}
    sizes['icon'] = _save_crop(region(c_icon), BULLET_ICON)
    sizes['fly'] = _save_crop(region(c_fly), BULLET_FLY)

    # 3번: 주황/구리색 탄피만 남기고 흙, 돌, 풀은 지움
    g = region(c_ground)
    r = g[:, :, 0].astype(np.int32)
    b = g[:, :, 2].astype(np.int32)
    casing = (r > 150) & ((r - b) > 60)
    if casing.sum() > 10:
        comp = _largest_component(casing)
        dil = np.array(Image.fromarray((comp * 255).astype(np.uint8))
                       .filter(ImageFilter.MaxFilter(7))) > 0    # 검은 테두리까지 포함
        g[:, :, 3] = np.where(dil, g[:, :, 3], 0)
    sizes['ground'] = _save_crop(g, BULLET_GROUND)
    return sizes


def prepare_ui():
    """그림자, 조준점, 점선, 체력바 이미지를 없을 때만 생성"""
    if not os.path.exists(SHADOW):
        img = Image.new('RGBA', (128, 48), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((14, 10, 114, 38), fill=(0, 0, 0, 255))
        img.filter(ImageFilter.GaussianBlur(4)).save(SHADOW)

    if not os.path.exists(CROSSHAIR):
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        red = (255, 70, 70, 255)
        d.ellipse((10, 10, 54, 54), outline=red, width=3)
        for line in [(32, 2, 32, 18), (32, 46, 32, 62), (2, 32, 18, 32), (46, 32, 62, 32)]:
            d.line(line, fill=red, width=3)
        d.ellipse((29, 29, 35, 35), fill=red)
        img.save(CROSSHAIR)

    if not os.path.exists(DOT):
        img = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((3, 3, 13, 13), fill=(255, 90, 90, 255))
        img.save(DOT)

    if not os.path.exists(BAR_BG):
        Image.new('RGBA', (4, 4), (20, 20, 20, 255)).save(BAR_BG)
    if not os.path.exists(BAR_FG):
        Image.new('RGBA', (4, 4), (220, 40, 40, 255)).save(BAR_FG)