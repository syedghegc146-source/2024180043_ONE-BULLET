"""캐릭터/몬스터 그림에 맵의 붉은 빛을 살짝 입혀서 배경과 어울리게 만든다.
원본 그림은 그대로 두고 '_lit.png' 복사본을 만들어 쓴다. 세기는 LIT_TINT, LIT_ADD 로 조절."""
import os

import numpy as np
from PIL import Image

LIT_TINT = (1.00, 0.84, 0.78)    # 곱하는 색 (R, G, B). 1보다 작을수록 그 색이 줄어든다
LIT_ADD = (16, 2, 0)             # 더하는 붉은 기운 (R, G, B)
LIT_VER = 1


def lit_path(path):
    base, ext = os.path.splitext(path)
    return base + '_lit' + ext


def make_lit(path):
    """path 그림을 색 보정한 복사본 경로를 돌려준다. 실패하면 원본 경로."""
    dst = lit_path(path)
    try:
        if (not os.path.exists(dst)) or os.path.getmtime(dst) < os.path.getmtime(path) \
                or os.path.getmtime(dst) < os.path.getmtime(__file__):
            im = np.array(Image.open(path).convert('RGBA'), np.float32)
            for c in range(3):
                im[..., c] = np.clip(im[..., c] * LIT_TINT[c] + LIT_ADD[c] * (im[..., 3] > 0), 0, 255)
            Image.fromarray(im.astype(np.uint8), 'RGBA').save(dst)
        return dst
    except Exception:
        return path