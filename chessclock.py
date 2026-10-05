#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chessclock -- 终端国际象棋钟(双人计时器)。

用法示例:
    python -m chessclock 5+3      # 5 分钟包干, 每步加 3 秒
    python -m chessclock --blitz   # 快棋预设 3+2
    python -m chessclock 1:30+2    # 1 分 30 秒包干, 每步加 2 秒

交互: 回车(或空格+回车)=换边, q=退出, Ctrl-C=退出。
开局白方先行, 白方用时先走。
"""

import argparse
import re
import select
import sys
import time

SIDES = ("白方", "黑方")

PRESETS = {
    "bullet": "1+1",    # 超快棋
    "blitz": "3+2",     # 快棋
    "rapid": "10+5",    # 快棋(慢)
}


def parse_time_control(spec):
    """解析时间制, 返回 (base_seconds, inc_seconds)。

    接受格式: '5+3'(5 分钟+3 秒加秒)、'10'(10 分钟无加秒)、'1:30+2'。
    """
    m = re.fullmatch(
        r"\s*(?:(\d+)\s*:\s*)?(\d+(?:\.\d+)?)\s*(?:\+\s*(\d+(?:\.\d+)?))?\s*",
        spec or "",
    )
    if not m:
        raise ValueError(f"时间格式不正确: {spec!r}, 期望形如 5+3 / 10 / 1:30+2")
    minutes, main, inc = m.group(1), float(m.group(2)), m.group(3)
    if minutes is not None:
        if main >= 60:
            raise ValueError(f"秒数部分必须 < 60: {spec!r}")
        base = int(minutes) * 60 + main
    else:
        base = main * 60.0
    inc_s = float(inc) if inc else 0.0
    if base <= 0:
        raise ValueError("基本用时必须大于 0")
    if inc_s < 0:
        raise ValueError("加秒不能为负数")
    return base, inc_s


def fmt(seconds):
    """把秒数格式化成 h:mm:ss.t / m:ss.t(先舍入到 0.1 秒, 避免 4:60.0)。"""
    tenths = int(round(max(0.0, seconds) * 10))
    total_s, tenth = divmod(tenths, 10)
    m, s = divmod(total_s, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}.{tenth}"
    return f"{m}:{s:02d}.{tenth}"


class ChessClock:
    """双人棋钟核心, 与界面解耦以便单元测试。

    now: 时间来源, 默认 time.monotonic(单调时钟, 防系统时间跳变)。
    """

    def __init__(self, base_s, inc_s, now=None):
        self.now = now or time.monotonic
        self.times = [float(base_s), float(base_s)]
        self.inc = float(inc_s)
        self.active = 0  # 白方先行
        self.last = None
        self.over = False
        self.winner = None
        self.moves = [0, 0]

    def start(self):
        self.last = self.now()

    def _elapse(self):
        if self.over or self.last is None:
            return
        t = self.now()
        dt = t - self.last
        self.last = t
        if dt < 0:
            dt = 0.0  # 防御: 单调时钟理论上不会倒退
        self.times[self.active] -= dt
        if self.times[self.active] <= 0:
            self.times[self.active] = 0.0
            self.over = True
            self.winner = 1 - self.active

    def poll(self):
        """推进时间、检查是否超时(不换边)。"""
        self._elapse()

    def switch(self):
        """当前行棋方走完一步: 加秒并换边。"""
        if self.over:
            return
        self._elapse()
        if self.over:
            return
        self.times[self.active] += self.inc
        self.moves[self.active] += 1
        self.active = 1 - self.active


def render(clock):
    """同行刷新双边用时, ▶ 标记走棋方。"""
    parts = []
    for i in (0, 1):
        mark = "▶" if (i == clock.active and not clock.over) else " "
        parts.append(f"{mark}{SIDES[i]} {fmt(clock.times[i])}")
    sys.stdout.write("\r" + " | ".join(parts) + "   (回车换边, q 退出)")
    sys.stdout.flush()


def play_interactive(base, inc):
    clock = ChessClock(base, inc)
    clock.start()
    print(f"国际象棋钟 {fmt(base)}+{inc:g}s: 白方先行。回车=换边, q=退出")
    try:
        while not clock.over:
            clock.poll()
            render(clock)
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                line = sys.stdin.readline()
                if not line:  # EOF
                    break
                if line.strip().lower() == "q":
                    break
                clock.switch()
    except KeyboardInterrupt:
        pass
    print()
    if clock.over:
        w = clock.winner
        print(f"⏰ {SIDES[1 - w]} 超时! {SIDES[w]} 获胜。")
        print(f"最终: 白方 {fmt(clock.times[0])}({clock.moves[0]} 步) - "
              f"黑方 {fmt(clock.times[1])}({clock.moves[1]} 步)")
        return 0
    print("对局中止。")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="chessclock",
        description="终端国际象棋钟: 双人计时, 加秒, 超时判负。纯标准库。",
    )
    ap.add_argument("control", nargs="?",
                    help="时间制, 如 5+3 / 10 / 1:30+2 (分钟+加秒)")
    ap.add_argument("--bullet", action="store_true", help="预设 1+1")
    ap.add_argument("--blitz", action="store_true", help="预设 3+2")
    ap.add_argument("--rapid", action="store_true", help="预设 10+5")
    args = ap.parse_args(argv)

    spec = args.control
    for name in ("bullet", "blitz", "rapid"):
        if getattr(args, name):
            if spec:
                ap.error("时间制和预设不能同时指定")
            spec = PRESETS[name]
    if not spec:
        ap.error("请指定时间制, 如: chessclock 5+3")
    try:
        base, inc = parse_time_control(spec)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return play_interactive(base, inc)


if __name__ == "__main__":
    raise SystemExit(main())
