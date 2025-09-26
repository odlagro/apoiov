from flask import Flask, render_template, jsonify
import requests, csv, io

app = Flask(__name__)

URL_PROD = "https://docs.google.com/spreadsheets/d/1Ycsc6ksvaO5EwOGq_w-N8awTKUyuo7awwu2IzRNfLVg/export?format=csv&gid=0"
URL_FRETE = "https://docs.google.com/spreadsheets/d/1Ycsc6ksvaO5EwOGq_w-N8awTKUyuo7awwu2IzRNfLVg/export?format=csv&gid=117017797"

def fetch_rows(url):
    r = requests.get(url, timeout=25)
    r.raise_for_status()
    text = r.content.decode("utf-8", errors="ignore").replace("\r\n","\n").replace("\r","\n")
    return list(csv.reader(io.StringIO(text)))

def to_float_brl(s):
    s = (s or "").strip()
    if not s: return 0.0
    s = s.replace("R$","").replace(".","").replace(",",".")
    try: return float(s)
    except: return 0.0

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/produtos")
def api_produtos():
    rows = fetch_rows(URL_PROD)
    if len(rows) < 5:
        return jsonify(ok=False, error="CSV de produtos vazio")
    header = [c.strip().upper() for c in rows[3]]  # linha 4
    def col(name, fb):
        try: return header.index(name)
        except ValueError: return fb

    # Mapeamento conforme sua planilha
    i_modelo   = col("MODELO", 2)           # C
    i_avista   = col("A VISTA", 3)          # D
    i_cartao   = col("CARTÃO", 4)           # E
    i_10x      = col("PARCELA EM 10X", 5)   # F
    i_ind      = col("INDICADA", 6)         # G
    # imagem exatamente como na coluna I (URL completa .webp)
    i_img      = 8                          # I

    data = []
    for r in rows[4:]:  # a partir da linha 5
        if len(r) < 9: r += [""]*(9-len(r))
        nome = (r[i_modelo] or "").strip()
        if not nome: continue
        produto = {
            "produto": nome,
            "cartao": to_float_brl(r[i_cartao]),
            "avista": to_float_brl(r[i_avista]),
            "dezx": to_float_brl(r[i_10x]),
            "indicada": r[i_ind],
            "imagem": (r[i_img] or "").strip(),  # usar exatamente a URL da coluna I
        }
        data.append(produto)
    return jsonify(ok=True, data=data)

@app.route("/api/fretes")
def api_fretes():
    rows = fetch_rows(URL_FRETE)
    out = []
    start = 4  # linha 5
    uf_col = 1 # B
    val_col = 2 # C
    for r in rows[start:]:
        if len(r) <= uf_col: continue
        uf = (r[uf_col] or '').strip()
        if not uf: continue
        val = to_float_brl(r[val_col] if len(r)>val_col else '0')
        out.append({"uf": uf, "valor": val})
    return jsonify(ok=True, data=out)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
