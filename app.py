# app.py (fix8)
import csv, io, time, re, requests
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

SHEET_ID = "1Ycsc6ksvaO5EwOGq_w-N8awTKUyuo7awwu2IzRNfLVg"
GID_PROD = "0"
GID_FRETE = "117017797"

def csv_url(sheet_id, gid):
    return "https://docs.google.com/spreadsheets/d/{}/export?format=csv&gid={}".format(sheet_id, gid)

PROD_CSV = csv_url(SHEET_ID, GID_PROD)
FRETE_CSV = csv_url(SHEET_ID, GID_FRETE)

_cache = {"prod":{"ts":0,"rows":[]}, "frete":{"ts":0,"map":{},"ufs":[]}}

EXPECTED_UFS = ["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA",
                "PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"]

def norm(s): return (s or "").strip()
def to_float_br(x):
    if x is None: return None
    t = str(x).strip()
    if not t: return None
    t = t.replace("R$","").replace(" ","").replace(".", "").replace(",", ".")
    try: return float(t)
    except:
        m = re.search(r"([0-9]+[\.,]?[0-9]*)", str(x))
        if m:
            txt = m.group(1).replace(".","").replace(",",".")
            try: return float(txt)
            except: pass
        return None

def fetch_csv_rows(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    txt = r.content.decode("utf-8", errors="ignore")
    return list(csv.reader(io.StringIO(txt)))

def is_header_row_candidato(row):
    labels = {norm(x).lower() for x in row[:9]}
    return any(x in labels for x in ["código","codigo","modelo","a vista","à vista","cartão","cartao","parcela em 10x","link"])

def load_produtos():
    now = time.time()
    if now - _cache["prod"]["ts"] < 300 and _cache["prod"]["rows"]:
        return _cache["prod"]["rows"]
    rows = fetch_csv_rows(PROD_CSV)
    out = []
    if rows:
        for r in rows[1:]:
            if len(r) < 6:
                continue
            if is_header_row_candidato(r):
                continue
            modelo = norm(r[2])      # C
            avista = to_float_br(r[3])  # D
            cartao = to_float_br(r[4])  # E
            parcela10 = to_float_br(r[5])  # F
            img = norm(r[8]) if len(r) > 8 else ""  # I
            if not modelo:
                continue
            out.append({"modelo": modelo, "avista": avista, "cartao": cartao, "parcela10": parcela10, "img": img})
    _cache["prod"] = {"ts": now, "rows": out}
    return out

def load_frete_map():
    now = time.time()
    if now - _cache["frete"]["ts"] < 1800 and _cache["frete"]["map"]:
        return _cache["frete"]["map"], _cache["frete"]["ufs"]
    rows = fetch_csv_rows(FRETE_CSV)
    mp, ufs = {}, []
    if rows:
        for r in rows[1:]:
            if len(r) < 3: continue
            uf = norm(r[1]).upper().replace(" ", "").replace("-", "")  # B
            val = to_float_br(r[2])  # C
            if len(uf)==2 and val is not None:
                mp[uf] = val
                if uf not in ufs: ufs.append(uf)
    if not ufs: ufs = EXPECTED_UFS
    _cache["frete"] = {"ts": now, "map": mp, "ufs": sorted(ufs)}
    return mp, sorted(ufs)

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/api/produtos")
def api_produtos():
    try:
        return jsonify({"ok": True, "items": load_produtos()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/api/ufs")
def api_ufs():
    _, ufs = load_frete_map()
    return jsonify({"ok": True, "ufs": ufs})

@app.get("/api/frete")
def api_frete():
    uf = norm(request.args.get("uf")).upper().replace(" ", "").replace("-", "")
    if not uf: return jsonify({"ok": False, "error":"UF não informada"}), 400
    mp, _ = load_frete_map()
    v = mp.get(uf)
    if v is None: return jsonify({"ok": False, "error": "UF '{}' não encontrada".format(uf)}), 404
    return jsonify({"ok": True, "uf": uf, "frete": v})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
