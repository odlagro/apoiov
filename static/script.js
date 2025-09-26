async function json(url){ const r=await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json(); }
const money=(n)=>Number(n||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});

// Normaliza número vindo como "1.234,56", "12,00", "12.00" ou "12"
const parseBR=(s)=>{
  if (typeof s === 'number') return s;
  s = (s ?? '').toString().replace(/[R$\s]/g,'').trim();
  if (s.includes(',')) {
    // Formato BR: vírgula é decimal -> remove milhares e troca vírgula por ponto
    s = s.replace(/\./g,'').replace(',', '.');
  }
  // Se não tem vírgula, mantemos os pontos (podem ser decimais: "12.00")
  const v = parseFloat(s);
  return isNaN(v) ? 0 : v;
};

let DATA=[];

async function loadUF(){
  const sel=document.getElementById('uf'); sel.innerHTML='<option>Selecione...</option>';
  const hint=document.getElementById('freteHint'); hint.textContent='Buscando frete...';
  try{
    const js=await json('/api/fretes');
    js.data.forEach(f=>{
      const o=document.createElement('option');
      o.value=f.uf; o.textContent=f.uf; o.dataset.valor=f.valor;
      sel.appendChild(o);
    });
    hint.textContent='Frete carregado.';
    sel.onchange=()=>{
      const opt=sel.options[sel.selectedIndex];
      document.getElementById('frete').value=(Number(opt?.dataset?.valor||0))
        .toLocaleString('pt-BR',{minimumFractionDigits:2});
    };
  }catch(e){ hint.textContent='Erro ao ler frete'; }
}

async function loadProdutos(){
  const tbody=document.getElementById('tbody'); tbody.innerHTML='<tr><td colspan="5">Carregando...</td></tr>';
  try{
    const js=await json('/api/produtos'); if(!js.ok) throw new Error(js.error||'Falha');
    DATA=js.data; tbody.innerHTML='';
    js.data.forEach((p,i)=>{
      const tr=document.createElement('tr');
      tr.innerHTML=`<td><input type="checkbox" class="pick" data-i="${i}"></td>
                    <td>${p.produto}</td>
                    <td>${money(p.cartao)}</td>
                    <td>${money(p.avista)}</td>
                    <td>${money(p.dezx)}</td>`;
      tbody.appendChild(tr);
    });
    if(!js.data.length) tbody.innerHTML='<tr><td colspan="5">Nenhum item encontrado.</td></tr>';
  }catch(e){ tbody.innerHTML='<tr><td colspan="5">Erro ao carregar produtos</td></tr>'; }
}

function buildMsg(p, frete, descInput, uf){
  // clamp 0..100
  const desc = Math.min(100, Math.max(0, Number(descInput) || 0));

  // Total com frete (sem desconto)
  const total = p.cartao + frete;
  const parcela = total / 10;

  // Promo: (cartão sem frete com desconto) + frete
  const cartaoComDesconto = p.cartao - (p.cartao * (desc / 100));
  const promo = cartaoComDesconto + frete;

  const descTxt = `${Math.round(desc)}%`;

  return `*VALOR JÁ INCLUSO O FRETE PARA ${uf||'UF'}*
*${p.produto}*
${(p.indicada||'').trim()}

${money(total)}
até 10x de ${money(parcela)} sem juros
ou
*PROMOÇÃO: ${money(promo)} no pix já com ${descTxt} de desconto*`;
}

function calc(){
  const frete=parseBR(document.getElementById('frete').value);
  let desc=parseBR(document.getElementById('desc').value);
  desc = Math.min(100, Math.max(0, Number(desc) || 0)); // clamp por segurança

  const uf=document.getElementById('uf').value;
  const picks=[...document.querySelectorAll('.pick:checked')].map(x=>Number(x.dataset.i));
  const items=picks.map(i=>DATA[i]).filter(Boolean);
  const wrap=document.getElementById('result'); wrap.innerHTML='';
  if(!items.length){ wrap.innerHTML='<div class="small">Selecione pelo menos 1 produto.</div>'; return; }
  items.forEach(p=>{
    const box=document.createElement('div'); box.className='msg';
    const img = p.imagem ? `<img src="${p.imagem}" alt="${p.produto}">` : `<div class="small">Sem imagem</div>`;
    const msg = buildMsg(p, frete, desc, uf);
    box.innerHTML = `${img}
      <div>
        <textarea>${msg}</textarea>
        <div class="actions"><button class="ghost copy">Copiar</button></div>
      </div>`;
    box.querySelector('.copy').addEventListener('click',()=>{
      const ta=box.querySelector('textarea'); ta.select(); document.execCommand('copy');
    });
    wrap.appendChild(box);
  });
}

window.addEventListener('load',()=>{
  loadUF(); loadProdutos();
  document.getElementById('reload').onclick=()=>{ loadUF(); loadProdutos(); };
  document.getElementById('calc').onclick=calc;
});
