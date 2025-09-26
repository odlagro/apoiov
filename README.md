
# ApoioV v8c (robusto + compatibilidade JS)
- Backend tenta: sheet name -> gid do link -> varredura 0..20 (CSV).
- Frontend sem optional chaining (compatível com browsers antigos).
- Ajuste tudo em /settings (sem editar código).

## Rodar
python -m venv .venv
./.venv/Scripts/activate
python -m pip install -r requirements.txt
python app.py

Abra: http://127.0.0.1:5001/settings → configure (Produtos=ORDENHADEIRAS, Frete=FRETE, linha título=4, colunas C/E/D/F/G/I etc.)
Depois: http://127.0.0.1:5001/
