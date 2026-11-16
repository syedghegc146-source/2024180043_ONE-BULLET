from pico2d import *
import math
import random
import time

from config import *
from litfx import make_lit
from walkanim import prepare_walk


# =============== 총알 ===============
class Bullet:
    shadow = None
    icon_img = fly_img = ground_img = None
    icon_wh = fly_wh = ground_wh = (1, 1)
    sc = 1.0

    @classmethod
    def setup(cls, sizes, shadow):
        cls.shadow = shadow
        cls.icon_img = load_image(BULLET_ICON)
        cls.fly_img = load_image(BULLET_FLY)
        cls.ground_img = load_image(BULLET_GROUND)
        cls.icon_wh = sizes['icon']
        cls.fly_wh = sizes['fly']
        cls.ground_wh = sizes['ground']
        # 탄피(1번) 긴 변이 BULLET_LEN이 되도록 공통 배율 결정
        cls.sc = BULLET_LEN / max(cls.icon_wh)

    @classmethod
    def draw_icon(cls, x, y, alpha=1.0):
        w, h = cls.icon_wh
        cls.icon_img.opacify(alpha)
        cls.icon_img.draw(x, y, w * cls.sc, h * cls.sc)

    def __init__(self, x, y, ang, max_dist=None):
        self.x, self.y = x, y
        self.vx = math.cos(ang) * BULLET_SPEED
        self.vy = math.sin(ang) * BULLET_SPEED
        self.ang0 = ang
        self.spin = 0.0
        self.state = 'fly'      # fly -> hop -> landed
        self.alive = True
        self.height = 0.0
        self.t = 0.0
        self.spin_dir = 1
        self.sx0, self.sy0 = x, y          # 날아가기 시작한 위치
        self.max_dist = max_dist           # 이 거리까지만 날아감 (None이면 끝까지)

    def hop_to(self, lx, ly):
        """지금 위치에서 (lx, ly)로 튕겨서 떨어진다"""
        self.sx, self.sy = self.x, self.y
        self.lx = min(CANVAS_W - 10, max(10, lx))
        self.ly = min(CANVAS_H - 10, max(10, ly))
        self.spin_dir = random.choice((-1, 1))
        self.state = 'hop'
        self.t = 0.0

    def start_hop(self, boss):
        """보스에 맞았을 때: 보스 반대쪽으로 튕기되, 보스 뒤(위쪽)로는 못 가고 앞쪽에 떨어진다"""
        away = math.atan2(self.y - boss.y, self.x - boss.x)
        a = away + random.uniform(-1.2, 1.2)
        d = random.uniform(HOP_MIN, HOP_MAX)
        ly = min(self.y + math.sin(a) * d, bullet_front_limit(boss.radius))
        self.hop_to(self.x + math.cos(a) * d, ly)

    def update(self, dt, boss):
        if self.state == 'fly':
            self.x += self.vx * dt
            self.y += self.vy * dt
            if boss.alive and math.hypot(self.x - boss.x, self.y - boss.y) < boss.radius + BULLET_RADIUS:
                boss.hit()
                self.start_hop(boss)
            elif self.max_dist is not None and \
                    math.hypot(self.x - self.sx0, self.y - self.sy0) >= self.max_dist:
                self.state = 'landed'              # 조준한 곳에 도착: 그 자리에 떨어짐
                self.height = 0.0
                self.spin = 0.0
            elif not (0 < self.x < CANVAS_W and 0 < self.y < CANVAS_H):
                self.x = min(CANVAS_W - 10, max(10, self.x))
                self.y = min(CANVAS_H - 10, max(10, self.y))
                self.state = 'landed'
                self.height = 0.0
                self.spin = 0.0
        elif self.state == 'hop':
            self.t += dt / HOP_TIME
            k = min(self.t, 1.0)
            self.x = self.sx + (self.lx - self.sx) * k
            self.y = self.sy + (self.ly - self.sy) * k
            self.height = math.sin(math.pi * k) * HOP_HEIGHT
            # 정확히 SPIN_TURNS 바퀴 돌아서 끝나면 3번 그림과 같은 모양으로 눕는다
            self.spin = self.spin_dir * 2 * math.pi * SPIN_TURNS * k
            if self.t >= 1.0:
                self.state = 'landed'
                self.height = 0.0
                self.spin = 0.0

    @property
    def on_ground(self):
        return self.state == 'landed'

    def draw(self):
        if self.state == 'fly':
            # 2번 그림: 불꽃 꼬리가 뒤로 가도록, 총알 머리가 앞에 오게 위치를 당겨서 그림
            w, h = self.fly_wh
            dw, dh = w * self.sc * BULLET_FLY_SCALE, h * self.sc * BULLET_FLY_SCALE
            rot = self.ang0 + BULLET_ANGLE_FIX
            cx = self.x - math.cos(self.ang0) * dw * 0.25
            cy = self.y - math.sin(self.ang0) * dw * 0.25
            self.fly_img.opacify(1.0)
            self.fly_img.clip_composite_draw(0, 0, w, h, rot, '', cx, cy, dw, dh)
        else:
            f = 1 - 0.4 * self.height / HOP_HEIGHT
            self.shadow.opacify(0.4 * f)
            self.shadow.draw(self.x, self.y - 2, 22 * f, 8 * f)
            # 3번 그림(흙 제거): 튕길 때만 돌고, 멈추면 그림 그대로
            w, h = self.ground_wh
            self.ground_img.opacify(1.0)
            self.ground_img.clip_composite_draw(0, 0, w, h, self.spin, '',
                                                self.x, self.y + self.height,
                                                w * self.sc, h * self.sc)


# =============== 플레이어 ===============
class Player:
    def __init__(self, sprites, front_size, back_size):
        self.sheet = load_image(make_lit(CLEAN))
        self.shadow = load_image(SHADOW)
        self.crosshair = load_image(CROSSHAIR)
        self.dot = load_image(DOT)
        top, bottom = sprites[0], sprites[1]

        self.spr = {'side': (self.sheet, *bottom[0], SCALE)}
        self.extra = []

        if front_size:
            self.front = load_image(make_lit(FRONT_CLEAN))
            fw, fh = front_size
            sc = SCALE * top[2][3] / fh * FRONT_ADJUST
            self.spr['down'] = (self.front, 0, 0, fw, fh, sc)
            self.extra.append(self.front)
        else:
            self.spr['down'] = (self.sheet, *top[2], SCALE)

        if back_size:
            self.back = load_image(make_lit(BACK_CLEAN))
            bw, bh = back_size
            sc = SCALE * top[3][3] / bh * BACK_ADJUST
            self.spr['up'] = (self.back, 0, 0, bw, bh, sc)
            self.extra.append(self.back)
        else:
            self.spr['up'] = (self.sheet, *top[3], SCALE)

        self.base_w = max(s[3] * s[5] for s in self.spr.values())
        self.base_h = max(s[4] * s[5] for s in self.spr.values())

        # 걷기 프레임 그림 (walk_side / walk_front / walk_back .png). 없으면 예전 방식(그림 한 장)으로 걸음
        self.walk = {}
        try:
            cuts = prepare_walk(P)
        except Exception as e:
            print('[걷기] 그림 준비 실패:', e)
            cuts = {}
        for name, key in (('side', 'side'), ('front', 'down'), ('back', 'up')):
            if name in cuts:
                path, cw, ch = cuts[name]
                im = load_image(make_lit(path))
                old = self.spr[key]
                sc = old[4] * old[5] / ch            # 예전 그림과 같은 키로 맞춤
                self.walk[key] = (im, cw, ch, sc)
                self.extra.append(im)

        self.reset(CANVAS_W // 2, CANVAS_H // 3)

    def reset(self, x, y):
        """게임 시작/재시작 때 상태 초기화"""
        self.x, self.y = x, y
        self.keys = {'w': False, 'a': False, 's': False, 'd': False}
        self.dir = (0, 1)
        self.facing = 'up'

        self.mouse = (CANVAS_W // 2, CANVAS_H // 2)
        self.aiming = False
        self.last_shot = -999.0
        self.ammo = MAX_AMMO

        self.walk_phase = 0.0
        self.walk_amp = 0.0

        self.dashing = False
        self.dash_start = 0.0
        self.last_dash = -999.0
        self.dash_dir = (0, 0)
        self.ghosts = []

        self.slow_until = 0.0           # 거미줄에 걸려 느려지는 시간 (이 시각까지)
        self.dash_block_until = 0.0     # 대쉬를 못 쓰는 시간 (이 시각까지)

    def handle_event(self, e):
        keymap = {SDLK_w: 'w', SDLK_a: 'a', SDLK_s: 's', SDLK_d: 'd'}
        if e.type == SDL_KEYDOWN:
            if e.key in keymap:
                self.keys[keymap[e.key]] = True
            elif e.key in (SDLK_LSHIFT, SDLK_RSHIFT):
                self.start_dash()
        elif e.type == SDL_KEYUP:
            if e.key in keymap:
                self.keys[keymap[e.key]] = False
        elif e.type == SDL_MOUSEMOTION:
            self.mouse = (e.x, CANVAS_H - 1 - e.y)
        elif e.type == SDL_MOUSEBUTTONDOWN:
            self.mouse = (e.x, CANVAS_H - 1 - e.y)
            if e.button == SDL_BUTTON_RIGHT:
                self.aiming = True
        elif e.type == SDL_MOUSEBUTTONUP:
            if e.button == SDL_BUTTON_RIGHT:
                self.aiming = False

    def try_fire(self):
        now = time.time()
        if now - self.last_shot < FIRE_COOLDOWN or self.dashing or self.ammo <= 0:
            return None
        self.ammo -= 1
        gx, gy = self.x, self.y + GUN_Y
        dist = math.hypot(self.mouse[0] - gx, self.mouse[1] - gy)      # 마우스까지의 거리
        ang = math.atan2(self.mouse[1] - gy, self.mouse[0] - gx)
        if not self.aiming:
            ang += math.radians(random.uniform(-SPREAD_DEG, SPREAD_DEG))
        self.last_shot = now
        Sound.play('shot')
        return Bullet(gx + math.cos(ang) * MUZZLE, gy + math.sin(ang) * MUZZLE, ang,
                      max_dist=max(0.0, dist - MUZZLE))

    def pickup(self, bullet):
        if not bullet.on_ground or self.ammo >= MAX_AMMO:
            return False
        foot_y = self.y - self.base_h / 2
        if math.hypot(bullet.x - self.x, bullet.y - foot_y) < PICKUP_RADIUS:
            self.ammo += 1
            Sound.play('reload')
            return True
        return False

    def start_dash(self):
        now = time.time()
        if self.dashing or now - self.last_dash < DASH_COOLDOWN or now < self.dash_block_until:
            return
        dx = self.keys['d'] - self.keys['a']
        dy = self.keys['w'] - self.keys['s']
        if dx == 0 and dy == 0:
            dx, dy = self.dir
        length = (dx * dx + dy * dy) ** 0.5
        self.dash_dir = (dx / length, dy / length)
        self.dashing = True
        self.dash_start = now
        self.last_dash = now
        Sound.play('dash')

    def dash_tilt(self):
        return -self.dash_dir[0] * math.radians(DASH_TILT_DEG)

    def update(self, dt):
        now = time.time()
        dx = self.keys['d'] - self.keys['a']
        dy = self.keys['w'] - self.keys['s']
        moving = (dx != 0 or dy != 0) and not self.dashing
        speed = WALK_SPEED * (AIM_SLOW if self.aiming else 1.0)
        if now < self.slow_until:                           # 거미줄에 걸리면 느려짐
            speed *= 0.5

        if self.dashing:
            if now - self.dash_start >= DASH_TIME:
                self.dashing = False
            else:
                self.x += self.dash_dir[0] * DASH_SPEED * dt
                self.y += self.dash_dir[1] * DASH_SPEED * dt
                self.ghosts.append((self.x, self.y, self.facing, self.dash_tilt(), now))
        else:
            if dx != 0 and dy != 0:
                dx *= 0.7071
                dy *= 0.7071
            self.x += dx * speed * dt
            self.y += dy * speed * dt

        self.x = max(self.base_w / 2, min(CANVAS_W - self.base_w / 2, self.x))
        self.y = max(self.base_h / 2, min(CANVAS_H - self.base_h / 2, self.y))

        target = 1.0 if moving else 0.0
        self.walk_amp += (target - self.walk_amp) * min(1.0, dt * 12)
        if moving:
            prev_step = int(self.walk_phase / math.pi)
            self.walk_phase += dt * STEP_FREQ
            if int(self.walk_phase / math.pi) != prev_step:     # 발이 땅에 닿을 때마다
                self.step_n = getattr(self, 'step_n', 0) + 1
                if self.step_n % 2 == 0:
                    Sound.play('step')

        if dx != 0 or dy != 0:
            length = (dx * dx + dy * dy) ** 0.5
            self.dir = (dx / length, dy / length)
            if dx > 0:
                self.facing = 'right'
            elif dx < 0:
                self.facing = 'left'
            elif dy > 0:
                self.facing = 'up'
            else:
                self.facing = 'down'

        if not self.dashing and (self.aiming or now - self.last_shot < 0.4):
            mx, my = self.mouse
            ddx, ddy = mx - self.x, my - self.y
            if abs(ddx) >= abs(ddy):
                self.facing = 'right' if ddx > 0 else 'left'
            else:
                self.facing = 'up' if ddy > 0 else 'down'
            n = math.hypot(ddx, ddy)
            if n > 1 and self.aiming:
                self.dir = (ddx / n, ddy / n)

        self.ghosts = [g for g in self.ghosts if now - g[4] < 0.2]

    def _draw_at(self, x, y, facing, lift=0.0, tilt=0.0, sx=1.0, sy=1.0, frame=None):
        if facing in ('left', 'right'):
            key, flip = 'side', ('h' if facing == 'left' else '')
        else:
            key, flip = facing, ''
        if frame is not None and key in self.walk:            # 걷기 프레임 그림 사용
            img, w, h, sc = self.walk[key]
            l, b = (frame % 4) * w, 0
        else:
            img, l, b, w, h, sc = self.spr[key]
        dw, dh = w * sc * sx, h * sc * sy
        foot = y - self.base_h / 2
        cy = foot + dh / 2 + lift
        img.clip_composite_draw(l, b, w, h, tilt, flip, x, cy, dw, dh)

    def _set_opacity(self, a):
        self.sheet.opacify(a)
        for im in self.extra:
            im.opacify(a)

    def draw(self):
        now = time.time()
        s = abs(math.sin(self.walk_phase))
        lift = s * BOUNCE_PX * self.walk_amp
        tilt = math.sin(self.walk_phase) * math.radians(TILT_DEG) * self.walk_amp
        sy = 1.0 + SQUASH * (s - 0.5) * 2 * self.walk_amp
        sx = 1.0 - SQUASH * (s - 0.5) * 2 * self.walk_amp * 0.7
        key = 'side' if self.facing in ('left', 'right') else self.facing
        frame = None
        if key in self.walk:
            # 진짜 걷기 프레임이 있으면 튀는 효과는 약하게 (발 모양이 이미 움직이므로)
            lift, tilt = lift * WALK_PROC, tilt * WALK_PROC
            sy = 1.0 + (sy - 1.0) * WALK_PROC
            sx = 1.0 + (sx - 1.0) * WALK_PROC
            # 한 걸음(phase 가 pi 만큼) = 2프레임, 두 걸음 = 4프레임 한 바퀴
            frame = int(self.walk_phase / (math.pi / 2)) % 4 if self.walk_amp > 0.15 else 1
        if self.dashing:
            lift, tilt, sx, sy = 0.0, self.dash_tilt(), 1.1, 0.92
            if frame is not None:
                frame = 0

        shadow_w = self.base_w * 1.15 * (1 - 0.15 * lift / max(BOUNCE_PX, 1))
        shadow_h = shadow_w * 0.40
        self.shadow.opacify(SHADOW_ALPHA * (1 - 0.3 * lift / max(BOUNCE_PX, 1)))
        self.shadow.draw(self.x, self.y - self.base_h / 2 + shadow_h * 0.2, shadow_w, shadow_h)

        for gx, gy, gf, gtilt, gt in self.ghosts:
            self._set_opacity(max(0.0, 0.4 * (1 - (now - gt) / 0.2)))
            self._draw_at(gx, gy, gf, 0.0, gtilt, 1.1, 0.92, 0)

        self._set_opacity(1.0)
        self._draw_at(self.x, self.y, self.facing, lift, tilt, sx, sy, frame)

    def draw_aim(self):
        mx, my = self.mouse
        gx, gy = self.x, self.y + GUN_Y
        if self.aiming:
            d = math.hypot(mx - gx, my - gy)
            if d > 1:
                ux, uy = (mx - gx) / d, (my - gy) / d
                self.dot.opacify(0.75)
                dist = MUZZLE + 6
                while dist < d - 16:
                    self.dot.draw(gx + ux * dist, gy + uy * dist, 6, 6)
                    dist += 16
            self.crosshair.opacify(0.95)
            self.crosshair.draw(mx, my, 40, 40)
        else:
            self.crosshair.opacify(0.5)
            self.crosshair.draw(mx, my, 22, 22)