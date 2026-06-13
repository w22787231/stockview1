# -*- coding: utf-8 -*-
"""把 lite 池 Buy 股的業務類別(中文 sector)寫進 data/<pool>.json 的 cross_signals 列。
讀各股已產生的 data/stock/<sym>.json 的 metrics.sector(英文)→中文,免重抓。
用法: cd engine && python patch_lite_sector.py <us5000|tw_all>
"""
import sys, json, io, os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
STOCK = os.path.join(DATA, "stock")

SECTOR_ZH = {
    "Technology": "科技", "Information Technology": "科技",
    "Financial Services": "金融", "Financials": "金融",
    "Healthcare": "醫療保健", "Health Care": "醫療保健",
    "Consumer Cyclical": "非必需消費", "Consumer Discretionary": "非必需消費",
    "Consumer Defensive": "必需消費", "Consumer Staples": "必需消費",
    "Industrials": "工業",
    "Energy": "能源",
    "Basic Materials": "原物料", "Materials": "原物料",
    "Real Estate": "房地產",
    "Utilities": "公用事業",
    "Communication Services": "通訊服務",
}

INDUSTRY_ZH = {
    # 科技
    "Semiconductors": "半導體",
    "Semiconductor Equipment & Materials": "半導體設備",
    "Software - Application": "應用軟體",
    "Software - Infrastructure": "基礎設施軟體",
    "Consumer Electronics": "消費電子",
    "Electronic Components": "電子零件",
    "Electronic Gaming & Multimedia": "電玩/多媒體",
    "Computer Hardware": "電腦硬體",
    "Information Technology Services": "IT服務",
    "Scientific & Technical Instruments": "科儀/測量",
    "Solar": "太陽能",
    "Data Storage": "儲存裝置",
    "Communication Equipment": "通訊設備",
    "Telecom Services": "電信服務",
    # 醫療保健
    "Biotechnology": "生技",
    "Drug Manufacturers - General": "大型製藥",
    "Drug Manufacturers - Specialty & Generic": "學名藥/特殊",
    "Medical Devices": "醫療器材",
    "Medical Instruments & Supplies": "醫療器材用品",
    "Diagnostics & Research": "診斷/研究",
    "Health Information Services": "醫療資訊",
    "Medical Care Facilities": "醫療機構",
    "Healthcare Plans": "健保計畫",
    "Pharmaceutical Retailers": "藥局零售",
    # 金融
    "Banks - Diversified": "多元銀行",
    "Banks - Regional": "地區銀行",
    "Insurance - Life": "人壽保險",
    "Insurance - Property & Casualty": "產物保險",
    "Insurance - Diversified": "多元保險",
    "Asset Management": "資產管理",
    "Capital Markets": "資本市場",
    "Credit Services": "信用服務",
    "Financial Data & Stock Exchanges": "金融數據/交易所",
    "Mortgage Finance": "房貸金融",
    # 非必需消費
    "Auto Manufacturers": "汽車製造",
    "Auto Parts": "汽車零件",
    "Auto & Truck Dealerships": "汽車/卡車經銷",
    "Apparel Retail": "服飾零售",
    "Apparel Manufacturing": "服飾製造",
    "Specialty Retail": "特殊零售",
    "Restaurants": "餐飲",
    "Internet Retail": "網路零售",
    "Lodging": "住宿",
    "Leisure": "休閒",
    "Residential Construction": "住宅建設",
    "Home Improvement Retail": "居家改善零售",
    "Home Furnishings & Fixtures": "家具/裝潢",
    # 必需消費
    "Beverages - Non-Alcoholic": "非酒精飲料",
    "Beverages - Alcoholic": "酒精飲料",
    "Beverages - Brewers": "啤酒",
    "Tobacco": "菸草",
    "Household & Personal Products": "家用/個人護理",
    "Food Distribution": "食品配送",
    "Grocery Stores": "超市",
    "Packaged Foods": "包裝食品",
    "Farm Products": "農產品",
    # 工業
    "Aerospace & Defense": "航太與國防",
    "Airlines": "航空",
    "Farm & Heavy Construction Machinery": "重型機械",
    "Industrial Distribution": "工業配銷",
    "Engineering & Construction": "工程建設",
    "Specialty Industrial Machinery": "特殊工業機械",
    "Trucking": "貨運",
    "Waste Management": "廢棄物處理",
    "Railroads": "鐵路",
    "Air Freight & Logistics": "空運/物流",
    "Marine Shipping": "海運",
    "Security & Protection Services": "安全/保全服務",
    "Staffing & Employment Services": "人力資源",
    "Tools & Accessories": "工具/配件",
    "Electrical Equipment & Parts": "電力設備零件",
    # 能源
    "Oil & Gas E&P": "石油天然氣勘採",
    "Oil & Gas Integrated": "石油天然氣整合",
    "Oil & Gas Midstream": "油氣中游",
    "Oil & Gas Refining & Marketing": "煉油/行銷",
    "Oil & Gas Equipment & Services": "油氣設備服務",
    "Oil & Gas Drilling": "石油鑽探",
    "Uranium": "鈾",
    # 原物料
    "Specialty Chemicals": "特化材料",
    "Steel": "鋼鐵",
    "Aluminum": "鋁業",
    "Gold": "黃金",
    "Silver": "白銀",
    "Copper": "銅業",
    "Agricultural Inputs": "農業原材料",
    "Coking Coal": "焦煤",
    "Other Industrial Metals & Mining": "工業金屬採礦",
    "Paper & Paper Products": "紙業",
    "Lumber & Wood Production": "木材",
    # 通訊服務
    "Internet Content & Information": "網路內容/資訊",
    "Entertainment": "娛樂",
    "Broadcasting": "廣播",
    "Advertising Agencies": "廣告",
    "Publishing": "出版",
    # 房地產
    "REIT - Office": "辦公室型REITs",
    "REIT - Retail": "零售型REITs",
    "REIT - Residential": "住宅型REITs",
    "REIT - Industrial": "工業型REITs",
    "REIT - Diversified": "多元REITs",
    "REIT - Healthcare Facilities": "醫療型REITs",
    "REIT - Hotel & Motel": "旅館型REITs",
    "Real Estate Services": "房仲服務",
    # 公用事業
    "Utilities - Regulated Electric": "管制電力",
    "Utilities - Renewable": "再生能源",
    "Utilities - Regulated Gas": "管制天然氣",
    "Utilities - Diversified": "多元公用事業",
}

def _sector_zh(sym):
    fp = os.path.join(STOCK, sym.replace(".", "_").upper() + ".json")
    try:
        sec = json.load(io.open(fp, encoding="utf-8")).get("metrics", {}).get("sector")
        return SECTOR_ZH.get(sec, sec) if sec else None
    except Exception:
        return None

def _industry_zh(sym):
    fp = os.path.join(STOCK, sym.replace(".", "_").upper() + ".json")
    try:
        ind = json.load(io.open(fp, encoding="utf-8")).get("metrics", {}).get("industry")
        return INDUSTRY_ZH.get(ind, ind) if ind else None
    except Exception:
        return None

def main():
    if len(sys.argv) < 2:
        print("用法: python patch_lite_sector.py <us5000|tw_all>"); raise SystemExit(1)
    pool = sys.argv[1]
    fp = os.path.join(DATA, pool + ".json")
    d = json.load(io.open(fp, encoding="utf-8"))
    cs = d.get("cross_signals", {})
    n = 0
    for r in cs.get("golden", []) + cs.get("death", []):
        z = _sector_zh(r["sym"])
        if z:
            r["sector_zh"] = z; n += 1
    json.dump(d, io.open(fp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"[sector] {pool}: 標了 {n} 檔業務類別")

    # 順便補強勢股檔(us5000→strong.json、tw_all→strong_tw.json):從個股詳情 metrics.sector 補(可靠來源)
    strong_file = {"us5000": "strong.json", "tw_all": "strong_tw.json"}.get(pool)
    if strong_file:
        sp = os.path.join(DATA, strong_file)
        try:
            sd = json.load(io.open(sp, encoding="utf-8"))
            m = 0
            for r in sd.get("rows", []):
                if not r.get("sector_zh"):
                    z = _sector_zh(r["sym"])
                    if z:
                        r["sector_zh"] = z; m += 1
                if not r.get("industry_zh"):
                    iz = _industry_zh(r["sym"])
                    if iz:
                        r["industry_zh"] = iz
            json.dump(sd, io.open(sp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            print(f"[sector] {strong_file}: 補了 {m} 檔(sector), 細分產業 {sum(1 for r in sd.get('rows',[]) if r.get('industry_zh'))} 檔")
        except Exception as e:
            print(f"[sector] {strong_file} 略過:", e)

if __name__ == "__main__":
    main()
