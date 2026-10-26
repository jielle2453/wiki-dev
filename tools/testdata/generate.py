r"""生成「林小姐室內設計」假來源資料。全假、全程式生成。

用法：python tools/testdata/generate.py <測試環境>   → 在 <測試環境> 底下輸出 來源\ 與 來源.zip
平常不用跑：tools/testdata/來源.zip 就是它的輸出，直接解到 <測試環境>。改了假資料才重跑，再把新的 來源.zip 放回這裡。
字型用 Windows 的標楷體（C:/Windows/Fonts/kaiu.ttf）。
相依：python-docx openpyxl reportlab pikepdf pillow
"""
import csv
import hashlib
import random
import shutil
import struct
import sys
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
import pikepdf

if len(sys.argv) != 2:
    sys.exit("用法：python tools/testdata/generate.py <測試環境>")
ROOT = Path(sys.argv[1]).resolve()
OUT = ROOT / "來源"
FONT_DIR = Path("C:/Windows/Fonts")
PDF_PASSWORD = "lin2026"
random.seed(20261011)

pdfmetrics.registerFont(TTFont("kaiu", str(FONT_DIR / "kaiu.ttf")))


# ---------- 小工具 ----------
def p(*parts):
    path = OUT.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def make_docx(path, title, paragraphs, table=None):
    d = Document()
    d.add_heading(title, 1)
    for t in paragraphs:
        d.add_paragraph(t)
    if table:
        tb = d.add_table(rows=0, cols=len(table[0]))
        tb.style = "Table Grid"
        for row in table:
            cells = tb.add_row().cells
            for c, v in zip(cells, row):
                c.text = str(v)
    d.core_properties.author = "林小姐室內設計（假資料）"
    d.save(path)


def make_xlsx(path, sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.properties.creator = "林小姐室內設計（假資料）"
    wb.save(path)


def make_text_pdf(path, title, lines):
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setFont("kaiu", 18)
    c.drawString(60, 790, title)
    c.setFont("kaiu", 12)
    y = 755
    for ln in lines:
        if y < 60:
            c.showPage()
            c.setFont("kaiu", 12)
            y = 790
        c.drawString(60, y, ln)
        y -= 22
    c.save()


def pil_font(size):
    return ImageFont.truetype(str(FONT_DIR / "kaiu.ttf"), size)


def make_scanned_pdf(path, title, lines):
    """掃描型：整頁是帶雜訊、微傾斜的影像，沒有文字層。"""
    img = Image.new("L", (1240, 1754), 245)
    dr = ImageDraw.Draw(img)
    dr.text((100, 120), title, font=pil_font(56), fill=30)
    y = 240
    for ln in lines:
        dr.text((100, y), ln, font=pil_font(34), fill=40)
        y += 64
    img = img.rotate(1.2, resample=Image.BICUBIC, fillcolor=235)
    px = img.load()
    for _ in range(60000):
        x, yy = random.randrange(img.width), random.randrange(img.height)
        px[x, yy] = max(0, px[x, yy] - random.randrange(40, 120))
    img = img.filter(ImageFilter.GaussianBlur(0.8)).convert("RGB")
    img.save(path, "PDF", resolution=150)


def make_floorplan_pdf(path):
    """圖片型：一張平面配置圖（線條與色塊），只有零星標註，不是文字頁。"""
    img = Image.new("RGB", (1600, 1100), "white")
    dr = ImageDraw.Draw(img)
    dr.rectangle([100, 100, 1500, 1000], outline="black", width=8)
    dr.line([700, 100, 700, 600], fill="black", width=6)
    dr.line([100, 600, 1500, 600], fill="black", width=6)
    dr.line([1100, 600, 1100, 1000], fill="black", width=6)
    for box, col in [([120, 120, 680, 580], "#cfe8ff"), ([720, 120, 1480, 580], "#ffe9c7"),
                     ([120, 620, 1080, 980], "#dff5d8"), ([1120, 620, 1480, 980], "#f3d9f5")]:
        dr.rectangle(box, fill=col)
    for xy, t in [((300, 330), "主臥"), ((1000, 330), "客廳"), ((520, 780), "廚房餐廳"), ((1220, 780), "浴室")]:
        dr.text(xy, t, font=pil_font(48), fill="black")
    dr.text((100, 1030), "信義王宅 1:50", font=pil_font(36), fill="gray")
    img.save(path, "PDF", resolution=150)


# ---------- 最小 Word 97 .doc（OLE 複合檔）----------
def make_doc97(path, text):
    """手寫最小 .doc：WordDocument + 0Table(CLX 單一 piece，UTF-16)。
    沒裝 Word/LibreOffice，故自行組檔；以 antiword 驗證可讀。"""
    text = text.replace("\n", "\r") + "\r"
    ccp = len(text)
    raw = text.encode("utf-16-le")
    text_off = 0x400
    fib = bytearray(text_off)
    struct.pack_into("<HHHHHHH", fib, 0, 0xA5EC, 0x00C1, 0, 0x0404, 0, 0x0000, 0x00BF)
    struct.pack_into("<H", fib, 32, 0x000E)          # csw
    struct.pack_into("<H", fib, 62, 0x0016)          # cslw
    struct.pack_into("<I", fib, 64 + 3 * 4, ccp)     # FibRgLw97.ccpText (offset 0x34 = 52? 見下)
    # FibRgLw97 起於 64；ccpText 為第 4 個 long
    fib[64 + 3 * 4:64 + 3 * 4 + 4] = struct.pack("<I", ccp)
    struct.pack_into("<I", fib, 0x0C, 0)
    # fcMin/fcMac（舊讀取器會看）
    struct.pack_into("<I", fib, 0x18, text_off)
    struct.pack_into("<I", fib, 0x1C, text_off + len(raw))
    struct.pack_into("<H", fib, 152, 0x005D)         # cbRgFcLcb
    clx_fc = 154 + 33 * 8
    plc = struct.pack("<II", 0, ccp) + struct.pack("<HIH", 0, text_off, 0)  # PCD: flags, fc, prm
    clx = b"\x02" + struct.pack("<I", len(plc)) + plc
    struct.pack_into("<II", fib, clx_fc, 0, len(clx))
    # 最小 PlcfSed / PlcBteChpx / PlcBtePapx（antiword 需要）
    text_end = text_off + len(raw)
    pg_chpx, pg_papx = 4, 5            # FKP 頁號（每頁 512 bytes，位於 WordDocument 內）
    def fkp(papx):
        pg = bytearray(512)
        struct.pack_into("<II", pg, 0, text_off, text_end)
        pg[8] = 0                      # rgb[0]
        if papx:
            pg[8:21] = bytes(13)
        pg[511] = 1                    # crun
        return bytes(pg)
    sed = struct.pack("<II", 0, ccp) + struct.pack("<HIHI", 0, 0xFFFFFFFF, 0, 0)[:12]
    plc_chpx = struct.pack("<III", text_off, text_end, pg_chpx)
    plc_papx = struct.pack("<III", text_off, text_end, pg_papx)
    tail = bytearray()
    offs = {}
    stsh = struct.pack("<H", 18) + struct.pack("<HHHHHH", 0, 10, 0, 0, 0, 0) + bytes(6)
    for k, blob in (("stsh", stsh), ("clx", clx), ("sed", sed), ("chpx", plc_chpx), ("papx", plc_papx)):
        offs[k] = (len(tail), len(blob))
        tail += blob
    for idx, k in ((0, "stsh"), (1, "stsh"), (6, "sed"), (12, "chpx"), (13, "papx"), (33, "clx")):
        struct.pack_into("<II", fib, 154 + idx * 8, *offs[k])
    fib_b = bytes(fib)
    raw_pad = raw + bytes(-len(raw) % 512)
    word = fib_b + raw_pad
    word += bytes(pg_chpx * 512 - len(word))
    word += fkp(False) + fkp(True)
    word += bytes(max(0, 4096 - len(word)))
    clx = bytes(tail)
    table = clx + b"\0" * max(0, 4096 - len(clx))
    table += b"\0" * (-len(table) % 512)

    SEC = 512
    END, FATSEC = 0xFFFFFFFE, 0xFFFFFFFD
    nw, nt = len(word) // SEC, len(table) // SEC
    fat = [FATSEC, END]                              # 0: FAT 本身, 1: 目錄
    w_start = len(fat)
    fat += list(range(w_start + 1, w_start + nw)) + [END]
    t_start = len(fat)
    fat += list(range(t_start + 1, t_start + nt)) + [END]
    fat += [0xFFFFFFFF] * (128 - len(fat))
    fat_b = struct.pack("<128I", *fat)

    def entry(name, typ, left, right, child, start, size, color=1):
        nb = name.encode("utf-16-le")
        e = nb.ljust(64, b"\0") + struct.pack("<H", len(nb) + 2 if name else 0)
        e += struct.pack("<BBIII", typ, color, left, right, child)
        e += b"\0" * 16 + b"\0" * 4 + b"\0" * 16
        e += struct.pack("<IQ", start, size)
        return e
    NO = 0xFFFFFFFF
    dirs = (entry("Root Entry", 5, NO, NO, 1, END, 0)
            + entry("WordDocument", 2, 2, NO, NO, w_start, len(word))
            + entry("0Table", 2, NO, NO, NO, t_start, len(table))
            + b"\0" * 128)
    hdr = bytearray(512)
    hdr[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", hdr, 24, 0x003E, 0x0003, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIIII", hdr, 40, 0, 1, 1, 0, 4096, END, 0, END, 0)
    difat = [0] + [NO] * 108
    struct.pack_into("<109I", hdr, 76, *difat)
    Path(path).write_bytes(bytes(hdr) + fat_b + dirs + word + table)


# ---------- 內容 ----------
def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    # === 客戶案件\信義王 ===
    make_docx(p("客戶案件", "信義王", "平面圖說明.docx"), "信義王宅 平面圖說明", [
        "地址：台北市信義區（假地址）松仁路 000 號 12 樓。坪數 38 坪，三房兩廳兩衛。",
        "原屋況：屋齡 18 年，浴室防水層老化，廚房為封閉式，客廳與餐廳之間有一道非承重隔間牆。",
        "設計方向：打開廚房與餐廳，主臥增設更衣間，主浴室乾濕分離。",
        "木地板採用海島型實木，客廳天花板做間接照明。",
    ])
    for i, (d, items) in enumerate([
        ("2026-07-03", ["初次丈量，確認坪數與管線位置", "王先生希望廚房改開放式", "預算上限 180 萬，不含家具"]),
        ("2026-07-17", ["確認平面配置 B 案", "主臥更衣間加大 20 公分", "下次會議帶材質樣本"]),
        ("2026-08-02", ["確認木地板與磁磚樣本", "浴室改用大尺寸磁磚", "王太太要求增加書牆，追加預算 8 萬，待報價 v2 反映"]),
    ], 1):
        make_docx(p("客戶案件", "信義王", f"會議紀錄_{i}.docx"), f"信義王宅 會議紀錄 第 {i} 次", [
            f"日期：{d}", "出席：林小姐（設計師）、王先生、王太太", "討論事項：", *[f"- {x}" for x in items],
        ])
    make_xlsx(p("客戶案件", "信義王", "進度.xlsx"), {"進度": [
        ["階段", "預計開始", "預計完成", "狀態"],
        ["丈量與設計", "2026-07-03", "2026-08-15", "完成"],
        ["拆除", "2026-09-01", "2026-09-10", "進行中"],
        ["水電", "2026-09-11", "2026-09-25", "未開始"],
        ["木作與油漆", "2026-09-26", "2026-11-05", "未開始"],
        ["驗收", "2026-11-20", "2026-11-20", "未開始"],
    ]})
    make_floorplan_pdf(p("客戶案件", "信義王", "平面配置圖.pdf"))        # 圖片型 PDF

    # === 報價與合約\信義王 ===
    q1 = [("拆除工程", 1, 85000), ("水電工程", 1, 240000), ("木作工程", 1, 520000), ("油漆工程", 1, 160000), ("磁磚工程", 1, 210000)]
    q2 = q1 + [("書牆（追加）", 1, 80000)]
    def quote_lines(items):
        lines = ["客戶：信義王宅　　報價日期：{}".format("2026-07-20" if len(items) == 5 else "2026-08-05"), ""]
        total = 0
        for n, q, pr in items:
            lines.append(f"{n}　x{q}　NT$ {pr:,}")
            total += pr * q
        lines += ["", f"合計：NT$ {total:,}（未稅）", f"含稅：NT$ {round(total * 1.05):,}"]
        return lines
    make_text_pdf(p("報價與合約", "信義王", "報價_v1.pdf"), "林小姐室內設計 報價單（v1）", quote_lines(q1))
    make_text_pdf(p("報價與合約", "信義王", "報價_v2.pdf"), "林小姐室內設計 報價單（v2）", quote_lines(q2))
    shutil.copy(p("報價與合約", "信義王", "報價_v2.pdf"), p("客戶案件", "信義王", "報價_v2.pdf"))  # 完全相同、兩處

    contract_common = [
        "甲方（業主）：王○○　　乙方（設計施工）：林小姐室內設計",
        "工程地點：信義王宅（假地址）。工程總價：NT$ 1,296,750（含稅）。",
        "工期：自 2026-09-01 起 90 個工作天。",
    ]
    make_docx(p("報價與合約", "信義王", "合約.docx"), "室內裝修工程合約", contract_common + [
        "付款條件：簽約時付 50%，工程完成驗收後付 50%。逾期超過 7 日，每日加收千分之一違約金。",
    ])
    make_docx(p("客戶案件", "信義王", "合約_用印版.docx"), "室內裝修工程合約（用印版）", contract_common + [
        "付款條件：簽約時付 30%，水電完成付 40%，驗收後付 30%。逾期超過 14 日，每日加收萬分之五違約金。",
        "備註：本版為雙方用印版本。",
    ])  # 與上一份付款條件矛盾

    # === 客戶案件\大安陳 ===
    make_docx(p("客戶案件", "大安陳", "報價_v1.docx"), "大安陳宅 報價單 v1", ["報價日期：2026-08-10"],
              [["項目", "數量", "單價"], ["拆除", 1, 60000], ["水電", 1, 180000], ["木作", 1, 350000], ["合計", "", 590000]])
    make_docx(p("客戶案件", "大安陳", "報價_v2.docx"), "大安陳宅 報價單 v2", ["報價日期：2026-08-24", "修訂：水電改走明管，木作增加玄關櫃。"],
              [["項目", "數量", "單價"], ["拆除", 1, 60000], ["水電", 1, 150000], ["木作", 1, 410000], ["合計", "", 620000]])
    make_docx(p("客戶案件", "大安陳", "會議紀錄_1.docx"), "大安陳宅 會議紀錄 第 1 次", [
        "日期：2026-08-08", "出席：林小姐、陳小姐", "- 屋況 25 坪兩房，預算 60 萬內", "- 陳小姐偏好北歐風，希望玄關有收納"])
    make_xlsx(p("客戶案件", "大安陳", "進度.xlsx"), {"進度": [["階段", "狀態"], ["報價確認", "進行中"], ["簽約", "未開始"]]})

    # === 客戶案件\內湖李 ===
    make_docx(p("客戶案件", "內湖李", "需求訪談.docx"), "內湖李宅 需求訪談", [
        "日期：2026-09-15", "屋主：李先生，45 坪電梯大樓，三代同堂。", "需求：長輩房需無障礙動線，浴室防滑；預算 250 萬。"])
    make_text_pdf(p("客戶案件", "內湖李", "估價單.pdf"), "內湖李宅 估價單", [
        "估價日期：2026-09-28", "", "無障礙浴室改造　NT$ 280,000", "全室地板（防滑）　NT$ 310,000", "木作與櫃體　NT$ 640,000", "", "合計 NT$ 1,230,000（未稅）"])
    make_docx(p("客戶案件", "內湖李", "現場照片說明.docx"), "內湖李宅 現場照片說明", [
        "照片 1：入口玄關，地面有高低差約 3 公分。", "照片 2：長輩房現況，窗戶朝西。", "（本檔僅文字說明，照片檔未提供。）"])

    # === 報價與合約\大安陳 ===
    make_xlsx(p("報價與合約", "大安陳", "報價.xlsx"), {"報價": [
        ["項目", "數量", "單價", "小計"], ["拆除", 1, 60000, 60000], ["水電", 1, 150000, 150000], ["木作", 1, 410000, 410000], ["合計", "", "", 620000]]})
    make_docx(p("報價與合約", "大安陳", "合約.docx"), "室內裝修工程合約", [
        "甲方：陳○○　乙方：林小姐室內設計。工程總價 NT$ 651,000（含稅）。",
        "付款條件：簽約 40%，木作進場 30%，完工 30%。"])

    # === 報價與合約\內湖李（密碼 PDF）===
    tmp = p("報價與合約", "內湖李", "_tmp.pdf")
    make_text_pdf(tmp, "內湖李宅 工程合約（保密）", [
        "甲方：李○○　乙方：林小姐室內設計", "工程總價 NT$ 1,291,500（含稅）", "付款條件：簽約 30%，中期 40%，驗收 30%。"])
    with pikepdf.open(tmp) as pdf:
        pdf.save(p("報價與合約", "內湖李", "合約_加密.pdf"),
                 encryption=pikepdf.Encryption(user=PDF_PASSWORD, owner=PDF_PASSWORD))
    tmp.unlink()

    # === 報價與合約\範本 ===
    make_docx(p("報價與合約", "範本", "合約範本.docx"), "室內裝修工程合約（範本）", [
        "甲方：＿＿＿　乙方：林小姐室內設計", "工程總價：＿＿＿", "付款條件：簽約 30%，期中 40%，驗收 30%。"])
    make_xlsx(p("報價與合約", "範本", "報價單範本.xlsx"), {"報價": [["項目", "數量", "單價", "小計"], ["", "", "", ""]]})
    make_docx(p("報價與合約", "範本", "請款單範本.docx"), "請款單", ["請款對象：＿＿＿", "請款事由：＿＿＿", "金額：＿＿＿", "匯款帳號：000-000-0000000（假）"])

    # === 廠商資料 ===
    make_text_pdf(p("廠商資料", "型錄_磁磚_大成.pdf"), "大成磁磚 2026 型錄（假）", [
        "TL-6001 大理石紋拋光磚 60x120　每坪 NT$ 3,800", "TL-6002 木紋磚 20x120　每坪 NT$ 2,900", "TL-6003 水泥灰霧面磚 60x60　每坪 NT$ 2,300",
        "聯絡：業務部 02-2000-0001"])
    make_text_pdf(p("廠商資料", "型錄_木地板_森活.pdf"), "森活木地板 型錄（假）", [
        "海島型橡木 15mm　每坪 NT$ 6,800", "超耐磨 8mm　每坪 NT$ 2,600", "實木複合 12mm　每坪 NT$ 4,500", "聯絡：04-2000-0002"])
    make_scanned_pdf(p("廠商資料", "型錄_燈具_明亮.pdf"), "明亮燈飾 型錄（掃描）", [
        "LED 嵌燈 9W　單價 NT$ 280", "軌道燈 12W　單價 NT$ 650", "吊燈 北歐款　單價 NT$ 4,200", "聯絡電話：02-2000-0003"])      # 掃描型 PDF
    make_xlsx(p("廠商資料", "廠商聯絡表.xlsx"), {"廠商": [
        ["廠商", "統一編號", "電話", "手機", "聯絡人", "品項"],
        ["大成磁磚有限公司", "12345678", "02-2000-0001", "0912-000-001", "陳經理", "磁磚"],
        ["森活木業股份有限公司", "23456789", "04-2000-0002", "0912-000-002", "黃小姐", "木地板"],
        ["明亮燈飾行", "34567890", "02-2000-0003", "0912-000-003", "吳先生", "燈具"],
        ["順發水電工程行", "45678901", "02-2000-0004", "0912-000-004", "趙師傅", "水電"],
    ]})

    # === 公司行政 ===
    make_xlsx(p("公司行政", "薪資", "薪資表_2026Q3.xlsx"), {"Q3": [
        ["員工", "身分證字號", "底薪", "7月", "8月", "9月"],
        ["測試員甲", "A100000001", 42000, 42000, 42000, 45000],
        ["測試員乙", "B200000002", 38000, 38000, 40000, 38000],
        ["測試員丙", "C100000003", 35000, 35000, 35000, 35000]]})
    make_xlsx(p("公司行政", "薪資", "員工資料.xlsx"), {"員工": [
        ["姓名", "身分證字號", "生日", "手機", "地址", "薪轉帳號"],
        ["測試員甲", "A100000001", "1990-01-01", "0900-000-001", "台北市某區某路 1 號（假）", "812-0000-0000001"],
        ["測試員乙", "B200000002", "1992-02-02", "0900-000-002", "新北市某區某路 2 號（假）", "812-0000-0000002"],
        ["測試員丙", "C100000003", "1995-03-03", "0900-000-003", "台北市某區某路 3 號（假）", "812-0000-0000003"]]})
    with open(p("公司行政", "薪資", "薪轉帳號.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerows([["姓名", "身分證字號", "銀行代碼", "帳號"], ["測試員甲", "A100000001", "812", "0000000001"], ["測試員乙", "B200000002", "812", "0000000002"]])
    for n, (nm, pid, amt) in enumerate([("測試員甲", "A100000001", 45000), ("測試員乙", "B200000002", 38000)], 1):
        make_text_pdf(p("公司行政", "薪資", f"薪資單_2026-09_{n}.pdf"), "薪資單 2026-09（假）", [
            f"姓名：{nm}", f"身分證字號：{pid}", f"實發金額：NT$ {amt:,}", "匯入帳號：812-0000-0000000（假）"])

    for i, (who, amt, why) in enumerate([("順發水電工程行", 120000, "信義王宅水電第一期款"), ("大成磁磚有限公司", 98000, "信義王宅磁磚材料款"),
                                         ("森活木業股份有限公司", 143000, "信義王宅木地板材料款"), ("明亮燈飾行", 36500, "信義王宅燈具款")], 1):
        make_docx(p("公司行政", "請款", f"請款_{i}_{who}.docx"), "請款單", [f"請款對象：{who}", f"事由：{why}", f"金額：NT$ {amt:,}", "請款日期：2026-09-%02d" % (5 * i)])
    shutil.copy(p("報價與合約", "範本", "請款單範本.docx"), p("公司行政", "請款", "請款單範本.docx"))  # 完全相同、兩處（docx 以 shutil 複製，位元組一致）

    make_docx(p("公司行政", "公司簡介.docx"), "林小姐室內設計 公司簡介", ["成立於 2019 年（假），專注住宅室內設計與施工，團隊 4 人。", "服務範圍：台北、新北。"])
    make_xlsx(p("公司行政", "報稅時程.xlsx"), {"時程": [["項目", "期限"], ["營業稅（9-10 月）", "2026-11-15"], ["營所稅暫繳", "2026-09-30"]]})

    # 舊檔
    make_doc97(p("公司行政", "舊檔", "舊合約.doc"), "舊合約（2022）\n甲方：某業主　乙方：林小姐室內設計\n付款條件：簽約 50%，完工 50%。\n本檔為舊版 Word 格式。")  # .doc
    make_doc97(p("公司行政", "舊檔", "舊報價單.doc"), "舊報價單（2021）\n拆除 NT$ 50,000\n水電 NT$ 120,000\n合計 NT$ 170,000")
    p("公司行政", "舊檔", "Big5備忘.txt").write_bytes(
        "備忘（2023）\n水電師傅趙師傅電話 02-2000-0004，統編 45678901。\n付款習慣：材料款月結 30 天。\n小心：大成磁磚的交期常延誤。\n".encode("cp950"))  # Big5

    # 生成後搬到別夾：大安陳的會議紀錄，先生到客戶案件\大安陳，再搬到 公司行政\舊檔
    moved = p("客戶案件", "大安陳", "會議紀錄_2.docx")
    make_docx(moved, "大安陳宅 會議紀錄 第 2 次", ["日期：2026-08-20", "出席：林小姐、陳小姐", "- 確認改走明管", "- 玄關櫃加高到 240 公分", "- 報價改 v2"])
    shutil.move(str(moved), str(p("公司行政", "舊檔", "會議紀錄_2.docx")))


def package():
    zp = ROOT / "來源.zip"
    if zp.exists():
        zp.unlink()
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(ROOT).as_posix())
    return zp


def report():
    files = sorted(f for f in OUT.rglob("*") if f.is_file())
    print(f"總份數：{len(files)}")
    for f in files:
        print(" ", f.relative_to(OUT))
    h = {}
    for f in files:
        h.setdefault(hashlib.sha256(f.read_bytes()).hexdigest(), []).append(f.relative_to(OUT).as_posix())
    for v in h.values():
        if len(v) > 1:
            print("完全相同：", v)


if __name__ == "__main__":
    build()
    package()
    report()
