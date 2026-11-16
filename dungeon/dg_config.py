import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))     # dungeon 폴더
PARENT = os.path.dirname(HERE)                          # config.py, player.py가 있는 기존 게임 폴더


def _build_search():
    """dungeon 폴더와 기존 폴더, 그리고 image*/img*/sound* 폴더와 그 안의 모든 하위 폴더"""
    dirs, seen = [], set()

    def add(p):
        if p not in seen:
            seen.add(p)
            dirs.append(p)

    for base in (HERE, PARENT):
        add(base)
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            p = os.path.join(base, name)
            if os.path.isdir(p) and name.lower().startswith(('image', 'img', 'sound')):
                for root, _sub, _files in os.walk(p):
                    add(root)
    return dirs


_SEARCH = _build_search()


def _rel(p):
    try:
        return os.path.relpath(p, PARENT)
    except ValueError:
        return p


def DP(name):
    """이미지/소리 파일을 여러 폴더에서 찾는다"""
    for d in _SEARCH:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return _rel(p)
    return _rel(os.path.join(HERE, name))


def OUT(name):
    """자동으로 만들어지는 파일의 위치 (dungeon 폴더 안)"""
    return _rel(os.path.join(HERE, name))


# =============== 던전 구성 (수치는 여기서 바꾸세요) ===============
DG_EXTRA_HP = 1                  # 난이도별 하트에 더해지는 하트 (던전은 층이 많아서)
DG_HEAL_PER_FLOOR = 1            # 층을 깰 때마다 회복되는 하트
DG_COUNT_MULT = 1.0              # 몬스터 마릿수 전체 배율
DG_DIFF_COUNT = {'easy': 0.8, 'normal': 1.0, 'hard': 1.25}   # 난이도별 마릿수 배율

# 각 층은 웨이브 목록이고, 웨이브는 {'몬스터': 마릿수}.
# 몬스터: slime / gunner / shielder / spider / bomber / thief
# 목록 대신 글자를 쓰면 보스층이에요: 'boss' = 중간 보스(기존 보스), 'shadow' = 최종 보스(그림자 플레이어)
# 층을 늘리거나 줄이려면 이 목록만 바꾸면 돼요 (층 수는 자동으로 계산됨)
FLOORS = [
    [{'gunner': 3}],                                                                       # 1층
    [{'gunner': 2, 'shielder': 2}],                                                        # 2층  (쉴더 등장)
    [{'gunner': 2, 'spider': 2, 'shielder': 1}],                                           # 3층  (거미 등장)
    [{'bomber': 1, 'gunner': 2, 'spider': 2, 'shielder': 1}],                              # 4층  (폭탄병 등장)
    'boss',                                                                                # 5층  중간 보스
    [{'bomber': 1, 'slime': 1, 'gunner': 3}],                                              # 6층  (슬라임 등장)
    [{'shielder': 2, 'spider': 2, 'bomber': 2, 'slime': 1}],                               # 7층
    [{'shielder': 2, 'slime': 2, 'bomber': 1, 'spider': 1, 'thief': 1}],                   # 8층  (탄환 도둑 등장)
    [{'thief': 2, 'slime': 2, 'bomber': 2, 'spider': 2, 'shielder': 1}],                   # 9층
    'shadow',                                                                              # 10층 최종 보스
]
FLOOR_DIM = [0.10, 0.14, 0.14, 0.20, 0.26, 0.28, 0.32, 0.36, 0.40, 0.44]   # 층마다 화면이 어두워지는 정도
BOSS_DIM = 0.20                  # 중간 보스층에서 화면이 어두워지는 정도
SHADOW_DIM = 0.38                # 최종 보스층에서 화면이 어두워지는 정도


def floor_kind(idx):
    """idx번째 층의 종류: 'wave'(몬스터 웨이브) / 'boss'(중간 보스) / 'shadow'(최종 보스)"""
    v = FLOORS[idx]
    return v if isinstance(v, str) else 'wave'


BOMBER_DELAY = 3.0               # 폭탄병은 다른 몬스터 뒤에 이 시간(초) 간격으로 한 마리씩 나옴
FIRST_WAVE_DELAY = 0.8           # 층에 들어오고 첫 웨이브까지 (초)
WAVE_DELAY = 1.3                 # 웨이브를 깬 뒤 다음 웨이브까지 (초)
SPAWN_TIME = 0.9                 # 몬스터가 나타나는 연출 시간
SPAWN_MIN_DIST = 230             # 몬스터가 플레이어에게서 최소한 떨어져서 나타남
TRANS_OUT = 0.8                  # 문으로 걸어 들어가는 시간
TRANS_IN = 0.55                  # 다음 층에서 밝아지는 시간

KILL_HOP_MIN = 110                # 몬스터를 맞히고 튕긴 총알이 플레이어 발밑에서 최소한 이만큼 떨어진 곳에 떨어짐 (바로 다시 주워지는 것 방지)
DG_HITSTOP = 0.05                # 몬스터를 맞힐 때 화면이 멈추는 시간
DG_MAGNET_RANGE = 0              # 떨어진 총알이 끌려오는 거리 (0이면 끔)
DG_MAGNET_SPEED = 0              # 끌려오는 속도

# =============== 몬스터 공통 ===============
ENEMY_SIZE_MULT = 0.86           # 몬스터 전체 크기 배율
_BASE_H = {'slime': 78, 'gunner': 92, 'shielder': 100, 'spider': 84, 'bomber': 88, 'thief': 84}
ENEMY_H = {k: v * ENEMY_SIZE_MULT for k, v in _BASE_H.items()}    # 화면에 그려지는 높이(px)
ENEMY_HIT_R = {'slime': 0.38, 'gunner': 0.34, 'shielder': 0.34,
               'spider': 0.38, 'bomber': 0.36, 'thief': 0.34}      # 총알 맞는 반경 (높이의 비율)
HIT_DY = 0.06                    # 몸 중심이 그림 중심보다 위로 올라가 있는 정도
# 몬스터마다 따로 정하고 싶을 때 (여기 없는 몬스터는 위의 HIT_DY). 몸 중심이 그림 중심보다 아래면 마이너스
HIT_DY_KIND = {'spider': -0.04, 'bomber': -0.06, 'thief': 0.0}
# 그림이 왼쪽을 보고 있으면 True. 좌우가 반대로 보이면 바꾸세요 (거미, 폭탄병은 정면이라 좌우 반전 없음)
FACES_LEFT = {'gunner': True, 'shielder': True, 'thief': True}

# =============== 슬라임 ===============
SLIME_SPEED = 95
SLIME_LUNGE_RANGE = 200
SLIME_CROUCH = 0.5               # 웅크리는 시간(경고). 길수록 쉬움
SLIME_LUNGE_TIME = 0.3
SLIME_LUNGE_SPEED = 560
SLIME_LAND = 0.45                # 착지 후 숨 고르는 시간
SLIME_COOLDOWN = (1.0, 1.8)

# =============== 사수 ===============
GUNNER_SPEED = 85
GUNNER_KEEP = (230, 380)
GUNNER_CD = (1.4, 2.0)
GUNNER_AIM = 0.95                # 조준선이 뜨는 시간. 길수록 쉬움
GUNNER_AIM_LOCK = 0.35
GUNNER_RECOIL = 0.7
GUNNER_BALL_SPEED = 405
GUNNER_BALL_R = 13
GUNNER_BALL_SIZE = 36

# =============== 방패병 ===============
SHIELD_HALF = math.radians(90)   # 방패가 막는 각도의 절반
SHIELD_TURN = 1.9
SHIELDER_SPEED = 75
SHIELDER_BASH_RANGE = 150
SHIELDER_WINDUP = 0.6
SHIELDER_BASH_TIME = 0.28
SHIELDER_BASH_SPEED = 560
SHIELDER_RECOVER = 1.1
SHIELDER_COOLDOWN = (1.2, 2.0)

# =============== 거미 ===============
SPIDER_SPEED = 70
SPIDER_KEEP = (220, 340)         # 플레이어와 유지하려는 거리
SPIDER_CD = (2.0, 3.0)           # 다음 거미줄까지의 대기
SPIDER_AIM = 0.9                 # 조준선이 뜨는 시간. 길수록 쉬움
SPIDER_AIM_LOCK = 0.3            # 발사 직전에 조준이 고정되는 시간
SPIDER_RECOIL = 0.5              # 쏜 뒤 멈추는 시간 (공격 기회)
WEB_SPEED = 330                  # 거미줄이 날아가는 속도
WEB_R = 22                       # 거미줄 판정 반경 (클수록 직접 맞기 쉬움)
WEB_SIZE = 32                    # 거미줄 그림 크기
WEB_SLOW = 0.5                   # 거미줄에 걸렸을 때 이동 속도 배율 (0.5 = 절반)
WEB_HIT_SLOW = 1.2               # 거미줄에 직접 맞았을 때 느려지는 시간(초)
WEB_HIT_DASHLOCK = 1.5           # 거미줄에 직접 맞았을 때 대쉬를 못 쓰는 시간(초)
WEB_PUDDLE_R = 52                # 바닥에 남는 거미줄 반경
WEB_PUDDLE_TIME = 6.0            # 바닥 거미줄이 남아 있는 시간(초)
WEB_PUDDLE_MAX = 6               # 화면에 동시에 남는 바닥 거미줄 수 (넘으면 오래된 것부터 사라짐)

# =============== 폭탄병 ===============
BOMBER_SPEED = 135               # 달려오는 속도
BOMBER_TRIGGER = 105             # 이 거리 안에 들어오면 터질 준비
BOMBER_FUSE = 1.0                # 터지기 전 깜빡이는 시간(초). 길수록 쉬움
BOMBER_FUSE_SPEED = 45           # 깜빡이는 동안 따라오는 속도
BOMB_R = 88                      # 폭발 반경 (붉은 원이 실제 위험 범위)
BOMB_ACTIVE = 0.16               # 폭발이 피해를 주는 시간
BOMB_FX = 0.6                    # 폭발 연출 시간

# =============== 탄환 도둑 ===============
THIEF_SPEED = 125                # 총알을 찾아 달리는 속도
THIEF_FLEE_SPEED = 150           # 총알을 훔치고 도망치는 속도
THIEF_STEAL_R = 28               # 이 거리 안에 들어오면 총알을 훔침
THIEF_HOLD = 4.0                 # 훔친 총알을 들고 있다가 떨어뜨리는 시간(초)
THIEF_COOLDOWN = 2.5             # 떨어뜨린 뒤 다시 훔치려 하기까지 (초)
THIEF_KEEP = 250                 # 훔칠 총알이 없을 때 플레이어와 유지하는 거리
NOBULLET_RESPAWN = 6.0           # 총알이 하나도 없는 채로 이만큼 지나면 한 발을 돌려줌 (먹통 방지)

# =============== 그림자 보스 (10층) ===============
SHADOW_HP = 28                   # 보통 난이도 체력 (쉬움 x0.7, 어려움 x1.2)
SHADOW_HP_MULT = {'easy': 0.7, 'normal': 1.0, 'hard': 1.2}
SHADOW_SCALE = 1.45              # 플레이어보다 몇 배 크게 그릴지
SHADOW_DARK = 0.34               # 플레이어 그림을 얼마나 어둡게 (작을수록 어두움)
SHADOW_DESAT = 0.55              # 색을 얼마나 빼는지 (1이면 흑백)
SHADOW_TINT = (26, 6, 44)        # 어둡게 만든 뒤 더하는 보라빛 (R, G, B)
SHADOW_WALK = 130                # 걷는 속도
SHADOW_KEEP = (230, 340)         # 플레이어와 유지하려는 거리
SHADOW_MAX_Y = 400               # 보스가 올라갈 수 있는 가장 높은 y (너무 위로 가서 못 맞추는 것 방지)
SHADOW_MIN_Y = 140
SHADOW_CD = [1.5, 1.2, 1.0]      # 단계별 공격 간격(초). 클수록 쉬움
SHADOW_AIM = [0.85, 0.75, 0.65]  # 단계별 조준선 시간(초). 길수록 쉬움
SHADOW_AIM_LOCK = 0.3            # 발사 직전에 조준이 고정되는 시간
SHADOW_LEAD = 0.55               # 플레이어가 가는 방향을 얼마나 미리 겨누는지 (0이면 지금 위치만)
SHADOW_BULLET_SPEED = 520
SHADOW_BULLET_LEN = 54           # 보라 탄환 그림 길이(px)
SHADOW_BULLET_HUE = 190          # 탄환 색 (PIL 색상환 0~255. 190=보라, 210=자주, 170=파랑)
SHADOW_DASH_WARN = 0.4           # 대쉬 예고선이 보이는 시간
SHADOW_DASH_TIME = 0.2
SHADOW_DASH_SPEED = 950
SHADOW_DASH_SHOT_AIM = 0.5       # 대쉬 직후 쏘는 조준 시간 (짧을수록 어려움)
SHADOW_FAN_N = 5                 # 부채꼴 탄 개수
SHADOW_FAN_STEP = 0.2            # 부채꼴 탄 사이 각도(라디안)
SHADOW_CLONE_N = 2               # 3단계 분신 수
SHADOW_CLONE_AIM = 1.0           # 분신이 조준하는 시간
