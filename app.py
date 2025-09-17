# app.py (v6 - link fixo)
import os, re, json
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse, parse_qs
import pandas as pd

from flask import Flask, render_template, request, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---- CONFIG: link fixo da planilha ----
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Ycsc6ksvaO5EwOGq_w-N8awTKUyuo7awwu2IzRNfLVg/edit?pli=1&gid=0#gid=0"
DEFAULT_DESCONTO = float(os.environ.get("DEFAULT_DESCONTO", 12.0))
# ---------------------------------------

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

def to_gsheet_export(url: str):
    if not url:
        return url, url
    parsed = urlparse(url)
    if "docs.google.com" in parsed.netloc and "/spreadsheets" in parsed.path:
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9\-_]+)", parsed.path)
        gid = None
        if parsed.fragment:
            m_gid = re.search(r"gid=(\d+)", parsed.fragment)
            if m_gid: gid = m_gid.group(1)
        if gid is None:
            gid = parse_qs(parsed.query).get("gid", [None])[0]
        if m:
            doc_id = m.group(1)
            base = f"https://docs.google.com/spreadsheets/d/{doc_id}/export"
            csv_url = f"{base}?format=csv" + (f"&gid={gid}" if gid else "")
            xlsx_url = f"{base}?format=xlsx" + (f"&gid={gid}" if gid else "")
            return csv_url, xlsx_url
    return url, url

def brl(value: Decimal) -> str:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    int_part, frac_part = f"{value:.2f}".split(".")
    # separar milhares com '.' e decimais com ','
    int_part_with_sep = ""
    while len(int_part) > 3:
        int_part_with_sep = "." + int_part[-3:] + int_part_with_sep
        int_part = int_part[:-3]
    int_part_with_sep = int_part + int_part_with_sep
    return f"R$ {int_part_with_sep},{frac_part}"

def parse_price(v):
    if pd.isna(v): return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(".", "").replace(",", ".")
    s = re.sub(r"[^0-9\.\-]", "", s)
    if s in ("", "."): return None
    try: return float(s)
    except: return None

def try_header_scan(reader_func):
    raw = reader_func(header=None)
    for i in range(min(20, len(raw))):
        row = raw.iloc[i].fillna("").astype(str).str.strip().str.upper().tolist()
        if "MODELO" in row and ("CARTÃO" in row or "CARTAO" in row):
            headers = raw.iloc[i].tolist()
            df = raw.iloc[i+1:].copy()
            df.columns = headers
            return df
    return None

def load_sheet_exact(sheet_url: str):
    # lê CSV primeiro (mais robusto), depois XLSX
    csv_u, xlsx_u = to_gsheet_export(sheet_url.strip())
    df = None
    errors = []
    for candidate, reader in [(csv_u, pd.read_csv), (xlsx_u, pd.read_excel), (sheet_url.strip(), pd.read_csv)]:
        if not candidate: continue
        try:
            df = reader(candidate)
            break
        except Exception as e:
            errors.append(str(e))
            df = None
    if df is None:
        raise ValueError("Falha ao ler a planilha online. Verifique o compartilhamento.\n" + "\n".join(errors[-2:]))

    # tentar detectar cabeçalho se necessário
    cols_upper = [str(c).strip().upper() for c in df.columns]
    if not ("MODELO" in cols_upper and (("CARTÃO" in cols_upper) or ("CARTAO" in cols_upper))):
        scanned = try_header_scan(lambda **kw: pd.read_csv(csv_u, **kw))
        if scanned is not None:
            df = scanned

    # normalizar nomes
    rename_map = {}
    for c in df.columns:
        u = str(c).strip().upper()
        if u == "MODELO":
            rename_map[c] = "Produto"
        if u in ("CARTÃO","CARTAO"):
            rename_map[c] = "PrecoCartao"
        if u in ("A VISTA","À VISTA","AVISTA"):
            rename_map[c] = "AvistaSheet"
    df = df.rename(columns=rename_map)

    # fallback final
    if "Produto" not in df.columns or "PrecoCartao" not in df.columns:
        prod_col = None; cart_col = None
        for c in df.columns:
            u = str(c).upper()
            if (prod_col is None) and ("MODELO" in u): prod_col = c
            if (cart_col is None) and ("CART" in u): cart_col = c
        if prod_col and cart_col:
            df = df.rename(columns={prod_col: "Produto", cart_col: "PrecoCartao"})
        else:
            raise ValueError("Não encontrei MODELO (Produto) e CARTÃO (Preço cartão).")

    # converter e filtrar
    df["PrecoCartaoNum"] = df["PrecoCartao"].apply(parse_price)
    df = df.dropna(subset=["PrecoCartaoNum"])
    df = df[df["Produto"].astype(str).str.strip().str.upper().ne("MODELO")]
    df = df[df["Produto"].astype(str).str.strip().str.upper().ne("CÓDIGO")]
    df = df[df["Produto"].astype(str).str.strip().str.len() > 0]

    rows = [{"produto": str(r["Produto"]).strip(), "preco_cartao": float(r["PrecoCartaoNum"])} for _, r in df.iterrows()]
    return rows

@app.route("/", methods=["GET", "POST"])
def home():
    desconto_param = request.args.get("desconto", "")
    try:
        desconto_default = float(desconto_param.replace(",", ".")) if desconto_param else DEFAULT_DESCONTO
    except:
        desconto_default = DEFAULT_DESCONTO

    rows = []
    if request.method == "POST":
        action = request.form.get("action")
        if action == "carregar":
            desconto_padrao = request.form.get("desconto_padrao", str(desconto_default)).strip()
            try:
                desconto_default = float(desconto_padrao.replace(",", "."))
            except:
                pass
            try:
                rows = load_sheet_exact(DEFAULT_SHEET_URL)
                if not rows:
                    flash("Nenhum produto encontrado. Verifique a planilha.", "error")
            except Exception as e:
                flash(str(e), "error")
            return render_template("index.html", sheet_url=DEFAULT_SHEET_URL, desconto_padrao=desconto_default, rows=rows)

        elif action == "calcular":
            desconto_default = float(request.form.get("desconto", desconto_default))
            data = json.loads(request.form.get("item_json", "{}"))
            produto = str(data.get("produto", "Produto"))
            preco_cartao = Decimal(str(data.get("preco_cartao", "0")))
            frete = Decimal(request.form.get("frete", "0").replace(",", "."))

            desconto = Decimal(str(desconto_default)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_cartao = (preco_cartao + frete).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            parcela_10x = (total_cartao / Decimal("10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            avista = (preco_cartao * (Decimal("100") - desconto) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            promo_pix = (avista + frete).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            lines = [
                "*VALOR JÁ INCLUSO O FRETE *",
                f"*{produto.upper()} *",
                f"{brl(total_cartao)}",
                f"até 10x de {brl(parcela_10x)} sem juros",
                "",
                "ou",
                "",
                f"PROMOÇÃO: {brl(promo_pix)} no pix já com {desconto}% de desconto **"
            ]
            msg = "\n".join(lines)

            try:
                rows = load_sheet_exact(DEFAULT_SHEET_URL)
            except Exception:
                rows = []

            return render_template("index.html",
                                   sheet_url=DEFAULT_SHEET_URL,
                                   desconto_padrao=float(desconto),
                                   rows=rows,
                                   generated_text=msg,
                                   frete=float(frete))

    # GET
    return render_template("index.html", sheet_url=DEFAULT_SHEET_URL, desconto_padrao=desconto_default, rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
