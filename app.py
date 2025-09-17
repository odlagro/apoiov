# app.py (v10 - foto on select + frete zero badge)
import os, re, json
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from urllib.parse import urlparse, parse_qs
import pandas as pd
import requests

from flask import Flask, render_template, request, flash, Response

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
            # Prefer XLSX first for FOTO column (it preserves IMAGE formulas)
            xlsx_url = f"{base}?format=xlsx" + (f"&gid={gid}" if gid else "")
            csv_url  = f"{base}?format=csv"  + (f"&gid={gid}" if gid else "")
            return csv_url, xlsx_url
    return url, url

def brl(value: Decimal) -> str:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    int_part, frac_part = f"{value:.2f}".split(".")
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

def _extract_image_url(cell_val: str):
    if not cell_val: 
        return None
    s = str(cell_val).strip()
    if s == "" or s.lower() == "nan":
        return None
    m = re.search(r'(?i)\bimage\s*\(\s*"([^"]+)"', s)
    if m:
        return m.group(1)
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None

def _read_df(csv_u, xlsx_u):
    # Prefer XLSX then CSV; if XLSX fails, fall back to CSV
    errors = []
    for candidate, reader in [(xlsx_u, pd.read_excel), (csv_u, pd.read_csv)]:
        if not candidate: continue
        try:
            df = reader(candidate)
            return df, errors
        except Exception as e:
            errors.append(str(e))
    return None, errors

def load_sheet_exact(sheet_url: str):
    csv_u, xlsx_u = to_gsheet_export(sheet_url.strip())
    df, errs = _read_df(csv_u, xlsx_u)
    if df is None:
        raise ValueError("Falha ao ler a planilha online. Verifique o compartilhamento.\n" + "\n".join(errs[-2:]))

    # tentar detectar cabeçalho se necessário (para CSV; XLSX normalmente vem ok)
    cols_upper = [str(c).strip().upper() for c in df.columns]
    if not ("MODELO" in cols_upper and (("CARTÃO" in cols_upper) or ("CARTAO" in cols_upper))):
        scanned = try_header_scan(lambda **kw: pd.read_csv(csv_u, **kw))
        if scanned is not None:
            df = scanned

    # normalizar nomes, incluindo FOTO
    rename_map = {}
    for c in df.columns:
        u = str(c).strip().upper()
        if u == "MODELO":
            rename_map[c] = "Produto"
        if u in ("CARTÃO","CARTAO"):
            rename_map[c] = "PrecoCartao"
        if u in ("A VISTA","À VISTA","AVISTA"):
            rename_map[c] = "AvistaSheet"
        if u == "FOTO":
            rename_map[c] = "Foto"
    df = df.rename(columns=rename_map)

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

    # foto
    has_foto = "Foto" in df.columns
    rows = []
    for _, r in df.iterrows():
        foto_url = _extract_image_url(r["Foto"]) if has_foto else None
        rows.append({
            "produto": str(r["Produto"]).strip(),
            "preco_cartao": float(r["PrecoCartaoNum"]),
            "foto": foto_url
        })
    return rows

@app.route("/photo")
def photo():
    url = request.args.get("u", "").strip()
    if not url:
        return Response("missing url", status=400)
    try:
        r = requests.get(url, timeout=10)
        content_type = r.headers.get("Content-Type", "image/jpeg")
        return Response(r.content, mimetype=content_type)
    except Exception as e:
        return Response("error fetching image", status=502)

def parse_decimal_or_zero(s: str) -> Decimal:
    try:
        if s is None: 
            return Decimal("0")
        s = str(s).strip().replace(".", "").replace(",", ".")
        if s == "" or s == ".":
            return Decimal("0")
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")

@app.route("/", methods=["GET", "POST"])
def home():
    desconto_param = request.args.get("desconto", "")
    try:
        desconto_default = float(desconto_param.replace(",", ".")) if desconto_param else DEFAULT_DESCONTO
    except:
        desconto_default = DEFAULT_DESCONTO

    rows = []
    selected_foto = None
    frete_zero_flag = False

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
            # primeira foto padrão
            selected_foto = rows[0].get("foto") if rows else None
            return render_template("index.html", sheet_url=DEFAULT_SHEET_URL, desconto_padrao=desconto_default, rows=rows, selected_foto=selected_foto, frete_zero_flag=frete_zero_flag)

        elif action == "calcular":
            desconto_default = float(request.form.get("desconto", desconto_default))
            data = json.loads(request.form.get("item_json", "{}"))
            produto = str(data.get("produto", "Produto"))
            preco_cartao = Decimal(str(data.get("preco_cartao", "0")))
            selected_foto = data.get("foto") or None
            frete = parse_decimal_or_zero(request.form.get("frete", "0"))

            frete_zero_flag = (frete == Decimal("0"))

            desconto = Decimal(str(desconto_default)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_cartao = (preco_cartao + frete).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            parcela_10x = (total_cartao / Decimal("10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            avista = (preco_cartao * (Decimal("100") - desconto) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            promo_pix = (avista + frete).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            desconto_str = f"{desconto:.2f}"
            lines = [
                "*VALOR JÁ INCLUSO O FRETE*",
                f"*{produto.upper()}*",
                f"{brl(total_cartao)}",
                f"até 10x de {brl(parcela_10x)} sem juros",
                "",
                "ou",
                "",
                f"*PROMOÇÃO: {brl(promo_pix)} no pix já com {desconto_str}% de desconto*"
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
                                   frete=0.0,  # reset field display
                                   selected_foto=selected_foto,
                                   frete_zero_flag=frete_zero_flag)

    # GET (carregar produtos automaticamente + foto do primeiro)
    try:
        rows = load_sheet_exact(DEFAULT_SHEET_URL)
    except Exception as e:
        flash(str(e), "error")
        rows = []
    selected_foto = rows[0].get("foto") if rows else None

    return render_template("index.html", sheet_url=DEFAULT_SHEET_URL, desconto_padrao=desconto_default, rows=rows, selected_foto=selected_foto, frete_zero_flag=frete_zero_flag)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
