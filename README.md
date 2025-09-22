# ApoioV (versão completa + UF → Frete)

Este projeto replica a UI principal do ApoioV (tema escuro, lista de produtos, cálculo de preços) e adiciona o seletor de UF que preenche o **Frete (R$)** automaticamente a partir da guia **FRETE**.

## Como usar
1. Crie a venv e instale dependências:
   ```bash
   py -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copie `.env.example` para `.env` e preencha:
   - `PROD_SHEET_ID` e `PROD_GID` **ou** `PROD_CSV_URL` (planilha de produtos)
   - (opcional) ajuste `%` de desconto padrão e porta
3. Rode:
   ```bash
   py app.py
   ```
   Acesse `http://127.0.0.1:5001`

## Planilha de produtos
- Espera ao menos colunas para **modelo** e **cartao** (nomes flexíveis: modelo/produto/nome; cartao/preço/valor).
- Pode incluir `imagem`, mas não é obrigatória.

## Planilha FRETE
- Já configurada para a guia informada; ajuste em `.env` se necessário.
