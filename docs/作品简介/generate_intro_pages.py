from __future__ import annotations

from pathlib import Path
import math
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUT = ROOT / "out"
W, H = 920, 640

FONT_YH = Path("C:/Windows/Fonts/msyh.ttc")
FONT_YHB = Path("C:/Windows/Fonts/msyhbd.ttc")
FONT_ARIAL = Path("C:/Windows/Fonts/arial.ttf")


def font(size: int, bold: bool = False):
    path = FONT_YHB if bold and FONT_YHB.exists() else FONT_YH
    if not path.exists():
        path = FONT_ARIAL
    return ImageFont.truetype(str(path), size)


F = {
    "title": font(36, True),
    "title2": font(28, True),
    "h1": font(22, True),
    "h2": font(16, True),
    "body": font(12),
    "bodyb": font(12, True),
    "small": font(10),
    "tiny": font(9),
}


COL = {
    "ink": "#0b1730",
    "muted": "#58708f",
    "blue": "#0f7bb8",
    "blue2": "#176bff",
    "light": "#f6f9fc",
    "line": "#d7e3ee",
    "green": "#00a981",
    "orange": "#f0a202",
    "navy": "#111827",
}


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int, max_lines: int | None = None) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            trial = cur + ch
            if text_size(draw, trial, fnt)[0] <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = ch
                if max_lines and len(lines) >= max_lines:
                    break
        if cur and (not max_lines or len(lines) < max_lines):
            lines.append(cur)
        if max_lines and len(lines) >= max_lines:
            break
    if max_lines and len(lines) == max_lines:
        while lines and text_size(draw, lines[-1] + "...", fnt)[0] > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "..."
    return lines


def draw_textbox(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt,
    fill: str,
    max_w: int,
    line_gap: int = 4,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    lines = wrap(draw, text, fnt, max_w, max_lines)
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + line_gap
    return y


def paste_cover(base: Image.Image, img: Image.Image, box: tuple[int, int, int, int], radius: int = 10):
    x, y, w, h = box
    src = img.convert("RGB")
    scale = max(w / src.width, h / src.height)
    nw, nh = int(src.width * scale), int(src.height * scale)
    src = src.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    src = src.crop((left, top, left + w, top + h))
    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    base.paste(src, (x, y), mask)


def paste_contain(base: Image.Image, img: Image.Image, box: tuple[int, int, int, int]):
    x, y, w, h = box
    src = img.convert("RGBA")
    src.thumbnail((w, h), Image.LANCZOS)
    base.alpha_composite(src, (x + (w - src.width) // 2, y + (h - src.height) // 2))


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str = "#ffffff", outline: str = COL["line"], r: int = 8):
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=fill, outline=outline, width=1)


def wecraft_mark(size: int = 64) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size, size), radius=max(7, size // 7), fill="#111827")
    fnt = font(int(size * 0.48), True)
    tw, th = text_size(d, "W", fnt)
    d.text(((size - tw) / 2, (size - th) / 2 - size * 0.05), "W", font=fnt, fill="white")
    d.line((size * 0.22, size * 0.63, size * 0.37, size * 0.43, size * 0.50, size * 0.61, size * 0.70, size * 0.35), fill="#84e2ff", width=max(2, size // 18), joint="curve")
    return im


def draw_flow(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, steps: list[str], dark: bool = False):
    step_w = w // len(steps)
    for i, s in enumerate(steps):
        cx = x + i * step_w
        fill = "#ffffff" if not dark else "#1f2937"
        outline = "#cfe0ee" if not dark else "#334155"
        card(draw, (cx, y, step_w - 8, 45), fill, outline, 7)
        draw.ellipse((cx + 10, y + 12, cx + 30, y + 32), fill=COL["blue2"] if i < 3 else COL["green"])
        draw.text((cx + 16, y + 15), str(i + 1), font=F["tiny"], fill="white")
        draw_textbox(draw, (cx + 36, y + 11), s, F["tiny"], "#e5eefc" if dark else COL["ink"], step_w - 54, 2, 2)
        if i < len(steps) - 1:
            ax = cx + step_w - 10
            draw.line((ax, y + 23, ax + 12, y + 23), fill=COL["blue2"] if not dark else "#7dd3fc", width=2)
            draw.polygon([(ax + 12, y + 23), (ax + 7, y + 19), (ax + 7, y + 27)], fill=COL["blue2"] if not dark else "#7dd3fc")


def phone_mock(kind: str, size: tuple[int, int] = (140, 250)) -> Image.Image:
    w, h = size
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w, h), radius=18, fill="#111827")
    d.rounded_rectangle((6, 8, w - 6, h - 8), radius=14, fill="#f8fafc")
    d.rounded_rectangle((35, 8, w - 35, 18), radius=5, fill="#111827")
    d.rectangle((6, 25, w - 6, 58), fill="#176bff")
    titles = {"home": "校园二手书", "publish": "发布书籍", "admin": "审核中心"}
    d.text((16, 34), titles[kind], font=font(12, True), fill="white")
    if kind == "home":
        d.rounded_rectangle((16, 72, w - 16, 92), radius=10, fill="#eef5ff", outline="#cfe0ee")
        d.text((27, 76), "搜索书名 / 作者 / 课程", font=font(8), fill="#7a8aa0")
        for i, (title, tag, color) in enumerate([
            ("高等数学", "免费", "#00a981"),
            ("数据结构", "交换", "#176bff"),
            ("概率论", "免费", "#00a981"),
        ]):
            yy = 106 + i * 42
            d.rounded_rectangle((16, yy, w - 16, yy + 32), radius=8, fill="white", outline="#d7e3ee")
            d.rounded_rectangle((25, yy + 7, 48, yy + 27), radius=4, fill="#dbeafe")
            d.text((56, yy + 7), title, font=font(9, True), fill=COL["ink"])
            tag_x0 = min(max(52, w - 52), w - 34)
            tag_x1 = w - 18
            d.rounded_rectangle((tag_x0, yy + 8, tag_x1, yy + 24), radius=8, fill=color)
            d.text((tag_x0 + 6, yy + 10), tag, font=font(7, True), fill="white")
    elif kind == "publish":
        labels = ["书名", "作者", "新旧程度", "交换类型"]
        for i, lab in enumerate(labels):
            yy = 75 + i * 29
            d.text((17, yy), lab, font=font(8, True), fill=COL["muted"])
            d.rounded_rectangle((60, yy - 2, w - 16, yy + 17), radius=5, fill="white", outline="#d7e3ee")
        for i in range(3):
            d.rounded_rectangle((18 + i * 36, 198, 48 + i * 36, 228), radius=6, fill="#eef5ff", outline="#cfe0ee")
        d.text((21, 207), "+", font=font(14, True), fill=COL["blue2"])
    else:
        for i, (name, state) in enumerate([("算法导论", "待审核"), ("C语言程序", "已通过"), ("英语读本", "待审核")]):
            yy = 76 + i * 45
            d.rounded_rectangle((16, yy, w - 16, yy + 36), radius=8, fill="white", outline="#d7e3ee")
            d.text((25, yy + 7), name, font=font(9, True), fill=COL["ink"])
            d.text((25, yy + 21), state, font=font(7), fill=COL["muted"])
            if state == "待审核":
                bx = max(68, w - 58)
                d.rounded_rectangle((bx, yy + 18, bx + 24, yy + 31), radius=6, fill="#00a981")
                d.text((bx + 4, yy + 20), "通过", font=font(6, True), fill="white")
                if w >= 130:
                    d.rounded_rectangle((bx + 27, yy + 18, w - 22, yy + 31), radius=6, fill="#ef4444")
                    d.text((bx + 32, yy + 20), "驳回", font=font(6, True), fill="white")
    return im


def load_assets():
    return {
        "logo": Image.open(ASSETS / "csu-logo.png").convert("RGBA"),
        "ui": Image.open(ASSETS / "ui-main.png").convert("RGBA"),
        "ui_desktop": Image.open(ASSETS / "ui-desktop.png").convert("RGBA"),
        "ui_mobile": Image.open(ASSETS / "ui-mobile.png").convert("RGBA"),
    }


def version_one(assets: dict[str, Image.Image]) -> Image.Image:
    im = Image.new("RGBA", (W, H), COL["light"])
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 88), fill="#ffffff")
    d.line((0, 88, W, 88), fill="#d9e5ef")

    paste_contain(im, wecraft_mark(54), (28, 18, 54, 54))
    d.text((96, 20), "WeCraft AI", font=F["title"], fill=COL["ink"])
    d.text((99, 60), "基于多 Agent 协作的微信小程序生成平台", font=F["body"], fill=COL["muted"])
    d.text((655, 25), "所属院校：中南大学", font=F["h2"], fill=COL["ink"])
    paste_contain(im, assets["logo"], (810, 15, 58, 58))

    card(d, (28, 108, 410, 260), "#ffffff", "#cfe0ee", 9)
    ui_crop = assets["ui"].crop((0, 0, assets["ui"].width, 650))
    paste_cover(im, ui_crop, (38, 119, 390, 218), 7)
    d.text((44, 343), "本地 Web UI：需求共创、方案确认、质量档位与生成日志", font=F["small"], fill=COL["muted"])

    info = [
        ("设计目的", "降低微信小程序原型开发门槛，把自然语言想法整理成页面、数据、权限与云开发方案，并输出可导入工程。", COL["blue2"]),
        ("目前功能", "多轮需求澄清、三档质量控制、页面四件套生成、中间产物留存、校验重试。", COL["green"]),
        ("创新实用", "多 Agent 分工、上下文整理、文件清单自动补齐、页面级一致性检查，让生成结果更可维护。", COL["orange"]),
        ("待改进", "增量生成、项目级修复、任务历史、模型切换与真实预览部署。", "#8b5cf6"),
    ]
    x0, y0 = 458, 108
    for i, (title, body, accent) in enumerate(info):
        x = x0 + (i % 2) * 212
        y = y0 + (i // 2) * 128
        card(d, (x, y, 198, 115), "#ffffff", "#d7e3ee", 8)
        d.rounded_rectangle((x + 12, y + 12, x + 18, y + 33), radius=3, fill=accent)
        d.text((x + 28, y + 10), title, font=F["h2"], fill=COL["ink"])
        draw_textbox(d, (x + 14, y + 41), body, F["small"], COL["muted"], 170, 3, 4)

    card(d, (28, 388, 864, 70), "#ffffff", "#d7e3ee", 9)
    d.text((44, 402), "技术路线", font=F["h2"], fill=COL["ink"])
    draw_flow(d, 126, 399, 748, ["需求澄清", "需求分析", "架构设计", "文件规划", "上下文整理", "代码生成", "校验重试"])

    d.text((34, 480), "生成结果图：校园二手书交换小程序", font=F["h2"], fill=COL["ink"])
    for i, k in enumerate(["home", "publish", "admin"]):
        ph = phone_mock(k, (118, 132))
        im.alpha_composite(ph, (40 + i * 132, 501))
    card(d, (465, 478, 427, 134), "#ffffff", "#d7e3ee", 9)
    d.text((484, 494), "作品图徽与输出能力", font=F["h2"], fill=COL["ink"])
    paste_contain(im, wecraft_mark(56), (484, 520, 56, 56))
    bullets = [
        "输入：模糊小程序想法 / 课程或竞赛项目需求",
        "输出：app 配置、页面 JS/WXML/WXSS/JSON、组件与工具文件",
        "案例：二手书交换小程序，已生成 13 个页面与 5 组组件",
    ]
    yy = 520
    for b in bullets:
        d.ellipse((558, yy + 5, 564, yy + 11), fill=COL["blue2"])
        draw_textbox(d, (572, yy), b, F["small"], COL["muted"], 290, 2, 2)
        yy += 31

    return im.convert("RGB")


def version_two(assets: dict[str, Image.Image]) -> Image.Image:
    im = Image.new("RGBA", (W, H), "#f8fafc")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 170), fill="#111827")
    d.rectangle((0, 164, W, 170), fill=COL["green"])

    paste_contain(im, wecraft_mark(70), (32, 24, 70, 70))
    d.text((122, 24), "WeCraft AI", font=F["title"], fill="white")
    d.text((124, 68), "自然语言需求  →  小程序工程文件", font=F["h2"], fill="#bde7ff")
    draw_textbox(d, (34, 108), "基于 CrewAI 与 DeepSeek 的多 Agent 协作生成工具，面向校园服务、课程设计与竞赛原型，快速生成可导入微信开发者工具的小程序项目。", F["body"], "#e5eefc", 520, 4, 2)

    paste_contain(im, assets["logo"], (760, 24, 70, 70))
    d.text((705, 101), "所属院校：中南大学", font=F["h2"], fill="white")
    d.text((705, 126), "图徽：WeCraft AI", font=F["small"], fill="#bde7ff")

    draw_flow(d, 34, 184, 852, ["共创需求", "方案结构化", "上下文整理", "页面四件套", "一致性校验", "生成工程"], dark=False)

    card(d, (34, 248, 520, 240), "#ffffff", "#d7e3ee", 9)
    paste_cover(im, assets["ui_desktop"], (45, 259, 498, 198), 7)
    d.text((48, 464), "UI 截图：共创清单、示例灵感与生成日志让生成过程可见", font=F["small"], fill=COL["muted"])

    card(d, (574, 248, 312, 240), "#ffffff", "#d7e3ee", 9)
    d.text((592, 265), "生成结果示例", font=F["h2"], fill=COL["ink"])
    for i, k in enumerate(["home", "publish", "admin"]):
        ph = phone_mock(k, (86, 182))
        im.alpha_composite(ph, (592 + i * 94, 294))

    boxes = [
        ("设计目的", "把需求沟通、架构规划和页面代码生成串成可复用流程，缩短小程序从想法到原型的时间。"),
        ("已实现功能", "Web UI 多轮澄清、三档质量控制、分阶段生成、页面级校验与失败重试、中间产物可追踪。"),
        ("创新特点", "Agent 分工 + 上下文压缩 + 文件清单 schema 修复 + 页面四件套成组生成，降低代码不一致风险。"),
        ("待改进问题", "继续补齐增量生成、项目级自动修复、历史任务管理、模型选择和真实预览部署能力。"),
    ]
    for i, (title, body) in enumerate(boxes):
        x = 34 + i * 218
        card(d, (x, 512, 198, 92), "#ffffff", "#d7e3ee", 8)
        d.text((x + 14, 526), title, font=F["h2"], fill=COL["ink"])
        draw_textbox(d, (x + 14, 552), body, F["tiny"], COL["muted"], 168, 2, 4)

    d.text((34, 621), "输出案例：校园二手书交换小程序 / 扫雷小游戏", font=F["tiny"], fill="#8aa0b8")
    d.text((760, 621), "920 x 640 px", font=F["tiny"], fill="#8aa0b8")
    return im.convert("RGB")


def save_all():
    OUT.mkdir(parents=True, exist_ok=True)
    assets = load_assets()
    pages = {
        "wecraft_ai_intro_v1": version_one(assets),
        "wecraft_ai_intro_v2": version_two(assets),
    }
    for name, img in pages.items():
        png = OUT / f"{name}.png"
        pdf = OUT / f"{name}.pdf"
        img.save(png)
        img.save(pdf, "PDF", resolution=72.0)
        print(f"{png} {img.size}")
        print(f"{pdf}")


if __name__ == "__main__":
    save_all()
