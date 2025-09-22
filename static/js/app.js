// static/js/app.js
function brReal(v){ return "R$ " + (v||0).toFixed(2).replace(".", ","); }

let produtos = [];
let selecionado = null;

async function carregarUFs(){
  const sel = document.getElementById("ufSelect");
  const msg = document.getElementById("ufMsg");
  try{
    msg.textContent = "Carregando UFs...";
    const r = await fetch("/api/ufs");
    const data = await r.json();
    if(!data.ok) throw new Error("Falha");
    sel.innerHTML = '<option value="">Selecione...</option>' + data.ufs.map(u=>`<option value="${u}">${u}</option>`).join("");
    msg.textContent = "";
    sel.addEventListener("change", async (ev)=>{
      const uf = ev.target.value;
      if(!uf) return;
      try{
        msg.textContent = "Buscando frete...";
        const rr = await fetch(`/api/frete?uf=${encodeURIComponent(uf)}`);
        const dj = await rr.json();
        if(!dj.ok){ msg.textContent = dj.error || "Erro ao buscar frete."; return; }
        document.getElementById("frete").value = dj.frete.toFixed(2).replace(".", ",");
        document.getElementById("frete").dispatchEvent(new Event("input", {bubbles:true}));
        msg.textContent = `Frete ${uf} aplicado.`;
      }catch(e){ msg.textContent = "Falha de rede."; }
    });
  }catch(e){
    msg.textContent = "Não foi possível carregar UFs agora.";
  }
}

async function carregarProdutos(){
  const tb = document.querySelector("#tblProdutos tbody");
  tb.innerHTML = '<tr><td colspan="5" class="text-center text-secondary">Carregando...</td></tr>';
  const r = await fetch("/api/produtos");
  const data = await r.json();
  if(!data.ok){ tb.innerHTML = `<tr><td colspan="5" class="text-danger">${data.error||"Erro"}</td></tr>`; return; }
  produtos = data.items || [];
  if(!produtos.length){ tb.innerHTML = '<tr><td colspan="5" class="text-warning">Nenhum produto na planilha.</td></tr>'; return; }
  const descontoPadrao = parseFloat(document.getElementById("descontoPadrao").value||"0")/100;
  tb.innerHTML = produtos.map((p,idx)=>{
    const avista = p.cartao * (1 - descontoPadrao);
    const dez = p.cartao / 10;
    return `<tr>
      <td><input type="radio" name="pSel" value="${idx}"></td>
      <td>${p.modelo}</td>
      <td class="text-end">${brReal(p.cartao)}</td>
      <td class="text-end">${brReal(avista)}</td>
      <td class="text-end">${brReal(dez)}</td>
    </tr>`;
  }).join("");
  document.querySelectorAll('input[name="pSel"]').forEach(r=>{
    r.addEventListener("change", ev=>{
      const i = parseInt(ev.target.value,10);
      selecionado = produtos[i];
      recalcular();
    });
  });
}

function lerFrete(){
  const v = (document.getElementById("frete").value||"").replace("R$","").replace(" ","").replace(".","").replace(",", ".");
  const n = parseFloat(v);
  return isNaN(n)?0:n;
}

function recalcular(){
  const desc = parseFloat(document.getElementById("desconto").value||"0")/100;
  const frete = lerFrete();
  const lblSub = document.getElementById("subtotalAvista");
  const lblTot = document.getElementById("totalAvista");
  const lbl10x = document.getElementById("parcela10x");
  if(!selecionado){
    lblSub.textContent = "R$ 0,00";
    lblTot.textContent = "R$ 0,00";
    lbl10x.textContent = "R$ 0,00";
    return;
  }
  const avista = selecionado.cartao * (1 - desc);
  const total = avista + frete;
  const dez = selecionado.cartao / 10;
  lblSub.textContent = brReal(avista);
  lblTot.textContent = brReal(total);
  lbl10x.textContent = brReal(dez);
}

function gerarMensagem(){
  if(!selecionado){
    document.getElementById("mensagem").value = "Selecione um produto.";
    return;
  }
  const desc = parseFloat(document.getElementById("desconto").value||"0");
  const frete = lerFrete();
  const avista = selecionado.cartao * (1 - desc/100);
  const total = avista + frete;
  const p10 = selecionado.cartao / 10;
  const linhas = [
    `Produto: ${selecionado.modelo}`,
    `Preço no cartão: ${brReal(selecionado.cartao)}`,
    `À vista (${desc.toFixed(2)}%): ${brReal(avista)}`,
    `Frete: ${brReal(frete)}`,
    `Total à vista + frete: ${brReal(total)}`,
    `10x sem juros: ${brReal(p10)} (total ${brReal(selecionado.cartao)})`
  ];
  document.getElementById("mensagem").value = linhas.join("\n");
}

document.addEventListener("DOMContentLoaded", ()=>{
  carregarUFs();
  carregarProdutos();
  document.getElementById("btnRecarregar").addEventListener("click", carregarProdutos);
  ["desconto","frete","descontoPadrao"].forEach(id=>{
    const el = document.getElementById(id);
    el.addEventListener("input", ()=>{
      if(id==="descontoPadrao"){ carregarProdutos(); }
      else{ recalcular(); }
    });
  });
  document.getElementById("btnGerar").addEventListener("click", gerarMensagem);
});
