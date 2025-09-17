# app.py (v5)
import os, io, re, json
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse, parse_qs

from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import pandas as pd

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -------- Config (pode alterar por env ou querystring) --------
DEFAULT_SHEET_URL = os.environ.get("DEFAULT_SHEET_URL", "")
DEFAULT_DESCONTO = float(os.environ.get("DEFAULT_DESCONTO", 12.0))
# --------------------------------------------------------------

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def to_gsheet_export(url: str):
    """Retorna (csv_url, xlsx_url) preservando gid."""
    if not url:
        return url, url
    try:
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
    except Exception:
        pass
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
    """Tenta detectar a linha de cabeçalhos (útil para planilha com título)"""
    raw = reader_func(header=None)
    for i in range(min(15, len(raw))):
        row = raw.iloc[i].fillna("").astype(str).str.strip().str.upper().tolist()
        if ("CÓDIGO" in row or "CODIGO" in row) and "MODELO" in row and ("A VISTA" in row or "À VISTA" in row or "AVISTA" in row) and "CARTÃO" in row or "CARTAO" in row:
            headers = raw.iloc[i].tolist()
            df = raw.iloc[i+1:].copy()
            df.columns = headers
            return df
    return None

def load_sheet_exact(sheet_url: str=None, upload_file=None):
    """Lê a planilha e retorna registros com colunas exatas: MODELO (produto), CARTÃO (preço_cartao)."""
    df = None
    if sheet_url:
        csv_u, xlsx_u = to_gsheet_export(sheet_url.strip())
        tried = []
        for candidate, reader in [(csv_u, pd.read_csv), (xlsx_u, pd.read_excel), (sheet_url.strip(), pd.read_csv)]:
            if not candidate: continue
            try:
                df = reader(candidate)
                break
            except Exception as e:
                tried.append((candidate, str(e)))
                df = None
        if df is None:
            raise ValueError("Falha ao ler a planilha online. Confirme o compartilhamento.")
    elif upload_file and upload_file.filename:
        fn = secure_filename(upload_file.filename)
        if not allowed_file(fn):
            raise ValueError("Arquivo não suportado. Envie CSV/XLSX.")
        path = os.path.join(UPLOAD_FOLDER, fn)
        upload_file.save(path)
        ext = fn.rsplit(".", 1)[1].lower()
        reader = pd.read_excel if ext in ("xlsx", "xls") else pd.read_csv
        df = reader(path)
    else:
        return []

    # Se as colunas não aparecerem, tentar escanear cabeçalho
    cols_upper = [str(c).strip().upper() for c in df.columns]
    required = ["MODELO", "CARTÃO", "CARTAO"]
    if not ("MODELO" in cols_upper and ("CARTÃO" in cols_upper or "CARTAO" in cols_upper)):
        df_scan = try_header_scan(lambda **kw: pd.read_csv(csv_u, **kw) if sheet_url else (pd.read_excel if ext in ("xlsx","xls") else pd.read_csv)(path, **kw))
        if df_scan is not None:
            df = df_scan

    # Normalizar nomes
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

    if "Produto" not in df.columns or "PrecoCartao" not in df.columns:
        # última tentativa: procurar por substring
        prod_col = None
        cart_col = None
        for c in df.columns:
            u = str(c).upper()
            if "MODELO" in u and prod_col is None: prod_col = c
            if ("CART" in u) and cart_col is None: cart_col = c
        if prod_col and cart_col:
            df = df.rename(columns={prod_col: "Produto", cart_col: "PrecoCartao"})
        else:
            raise ValueError("Não encontrei as colunas necessárias: MODELO (Produto) e CARTÃO (Preço cartão).")

    # Converter preços
    df["PrecoCartaoNum"] = df["PrecoCartao"].apply(parse_price)
    df = df.dropna(subset=["PrecoCartaoNum"])

    # Filtrar linhas vazias ou cabeçalhos repetidos
    df = df[df["Produto"].astype(str).str.strip().str.upper().ne("MODELO")]
    df = df[df["Produto"].astype(str).str.strip().str.upper().ne("CÓDIGO")]
    df = df[df["Produto"].astype(str).str.strip().str.len() > 0]

    # Montar lista
    rows = [{"produto": str(r["Produto"]).strip(),
             "preco_cartao": float(r["PrecoCartaoNum"])}
            for _, r in df.iterrows()]
    return rows

@app.route("/", methods=["GET", "POST"])
def home():
    sheet_param = request.args.get("sheet", "").strip() or DEFAULT_SHEET_URL
    desconto_param = request.args.get("desconto", "")
    try:
        desconto_default = float(desconto_param.replace(",", ".")) if desconto_param else DEFAULT_DESCONTO
    except:
        desconto_default = DEFAULT_DESCONTO

    rows = []
    if request.method == "POST":
        action = request.form.get("action")
        if action == "carregar":
            sheet_url = request.form.get("sheet_url", "").strip()
            desconto_padrao = request.form.get("desconto_padrao", str(desconto_default)).strip()
            try:
                desconto_default = float(desconto_padrao.replace(",", "."))
            except:
                pass
            try:
                rows = load_sheet_exact(sheet_url, request.files.get("file"))
                if not rows:
                    flash("Nenhum produto encontrado. Confira se a planilha tem MODELO e CARTÃO e se está pública.", "error")
            except Exception as e:
                flash(str(e), "error")
            return render_template("index.html", sheet_url=sheet_url, desconto_padrao=desconto_default, rows=rows)

        elif action == "calcular":
            desconto_default = float(request.form.get("desconto", desconto_default))
            item_json = request.form.get("item_json", "{}")
            data = json.loads(item_json)
            produto = str(data.get("produto", "Produto"))
            preco_cartao = Decimal(str(data.get("preco_cartao", "0")))
            frete = Decimal(request.form.get("frete", "0").replace(",", "."))

            # Regras:
            # Avista (padrão) = preco_cartao * (1 - desconto%)
            # 10x = (preco_cartao + frete) / 10
            # Total cartão = preco_cartao + frete
            # Promo PIX = preco_cartao * (1 - desconto%) + frete   (desconto não aplica ao frete)
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

            # Recarregar lista
            sheet_url_hidden = request.form.get("sheet_url_hidden", "")
            try:
                rows = load_sheet_exact(sheet_url_hidden)
            except Exception:
                rows = []

            return render_template("index.html",
                                   sheet_url=sheet_url_hidden,
                                   desconto_padrao=float(desconto),
                                   rows=rows,
                                   generated_text=msg,
                                   frete=float(frete))

    # GET
    return render_template("index.html", sheet_url=sheet_param, desconto_padrao=desconto_default, rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
