/* Clipador · interface (sem build). Rotas: #/nova, #/fila, #/resultados/<pasta>, #/biblioteca */
"use strict";

const OPCOES_FORM = ["cortes", "dmin", "dmax", "modo", "facecam", "credito", "plataforma", "visao", "chat",
  "reprisar_ia", "sem_ia", "candidatos", "candidatos_visuais", "cenas", "whisper", "idioma", "modelo",
  "hashtags_extras"];
const OPCOES_PRESET = OPCOES_FORM.filter((k) => k !== "reprisar_ia");

const S = {
  rota: "nova", foto: null, config: null, videos: null, video: null, sel: 0, filaSel: null,
  form: { fontes: [], canal: "", opcoes: {} }, infos: {}, estimativa: null, avancado: false,
  print: { t: null, erro: "", carregando: false, url: "", fonte: "" },
};

// ------------------------------------------------------------ utilidades
const $ = (sel, raiz = document) => raiz.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function fmt(seg) {
  seg = Math.max(0, Math.floor(seg || 0));
  const h = Math.floor(seg / 3600), m = Math.floor((seg % 3600) / 60), s = seg % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
function durCurta(seg) {
  if (!seg) return "";
  const h = Math.floor(seg / 3600), m = Math.round((seg % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}` : `${m} min`;
}
function dur(seg) { return seg < 60 ? `${Math.round(seg)}s` : fmt(seg); }
function k(n) {
  n = n || 0;
  if (n < 1000) return String(Math.round(n));
  if (n < 1e6) return (n / 1000).toFixed(1).replace(".", ",") + "k";
  return (n / 1e6).toFixed(2).replace(".", ",") + "M";
}
const virgula = (n, casas = 1) => Number(n || 0).toFixed(casas).replace(".", ",");
const notaTxt = (n) => (n == null ? "…" : Number.isInteger(n) ? virgula(n, 1) : virgula(n, 1));
const corNota = (n) => (n == null ? "" : n >= 8 ? "verde" : n >= 6 ? "amarelo" : "rosa");
function guardar(chave, valor) { try { localStorage.setItem(chave, JSON.stringify(valor)); } catch (e) { /* sem armazenamento */ } }
function ler(chave, padrao) { try { const v = localStorage.getItem(chave); return v ? JSON.parse(v) : padrao; } catch (e) { return padrao; } }

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, {
    method: opcoes.method || (opcoes.body ? "POST" : "GET"),
    headers: opcoes.body ? { "Content-Type": "application/json" } : {},
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined,
  });
  let dados = null;
  try { dados = await r.json(); } catch (e) { /* sem corpo */ }
  if (!r.ok) throw new Error((dados && dados.erro) || `erro ${r.status}`);
  return dados;
}

let avisoTimer = null;
// Dialogo de confirmacao no visual do app (substitui o confirm() nativo). Devolve Promise<boolean>.
// itens: [{nome, etapa, rodando}] numa lista; perigo: botao rosa, icone de alerta e foco no "nao".
const ICONE_ALERTA = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 21h20L12 3z"/><path d="M12 10v5"/><path d="M12 18h.01"/></svg>`;
const ICONE_DESLIGAR = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/></svg>`;
const ICONE_SALVAR = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`;
function confirmar({ titulo, texto = "", itens = [], nota = "", sim = "Confirmar", nao = "Cancelar", perigo = false, icone = null, classe = "" }) {
  document.querySelectorAll(".dialogo-fundo").forEach((d) => d.remove());
  return new Promise((resolver) => {
    const fundo = document.createElement("div");
    fundo.className = "dialogo-fundo " + classe;
    fundo.innerHTML = `<div class="dialogo${perigo ? " perigo" : ""}" role="alertdialog" aria-modal="true" aria-labelledby="dialogo-titulo">
      <div class="dialogo-topo"><div class="dialogo-icone">${icone || (perigo ? ICONE_ALERTA : ICONE_DESLIGAR)}</div>
        <div><h2 id="dialogo-titulo">${esc(titulo)}</h2>${texto ? `<p>${esc(texto)}</p>` : ""}</div></div>
      ${itens.length ? `<div class="dialogo-itens">${itens.map((it) => `<div class="dialogo-item${it.rodando ? " rodando" : ""}">
        <span class="ponto"></span><span class="nome" title="${esc(it.nome)}">${esc(it.nome)}</span><span class="etapa">${esc(it.etapa || "")}</span></div>`).join("")}</div>` : ""}
      ${nota ? `<div class="dialogo-nota">${esc(nota)}</div>` : ""}
      <div class="dialogo-acoes"><button class="botao" data-r="0">${esc(nao)}</button>
        <button class="botao ${perigo ? "primario" : "claro"}" data-r="1">${esc(sim)}</button></div></div>`;
    const fim = (v) => { document.removeEventListener("keydown", tecla, true); fundo.remove(); resolver(v); };
    const tecla = (e) => { if (e.key === "Escape") { e.preventDefault(); fim(false); } };
    fundo.addEventListener("click", (e) => { if (e.target === fundo) fim(false); });
    fundo.querySelectorAll("button").forEach((b) => (b.onclick = () => fim(b.dataset.r === "1")));
    document.addEventListener("keydown", tecla, true);
    document.body.appendChild(fundo);
    fundo.querySelector(`[data-r="${perigo ? 0 : 1}"]`).focus();
  });
}

// O que esta rodando ou na fila, no formato dos itens do confirmar().
function itensEmAndamento() {
  const itens = (S.foto && S.foto.itens) || [];
  const linhas = [];
  for (const it of itens.filter((i) => i.status === "rodando")) {
    const etapa = [...(it.etapas || [])].reverse().find((e) => e.status === "rodando");
    const barra = barraPrincipal(it);
    const pct = barra && barra.total ? ` ${Math.floor((100 * barra.feito) / barra.total)}%` : "";
    linhas.push({ nome: it.titulo || it.fonte, etapa: etapa ? etapa.titulo.toLowerCase() + pct : "rodando", rodando: true });
  }
  const fila = itens.filter((i) => i.status === "fila");
  if (fila.length) linhas.push({ nome: fila.length === 1 ? (fila[0].titulo || fila[0].fonte) : `${fila.length} vídeos`, etapa: "na fila" });
  return linhas;
}

function avisar(msg, erro = false) {
  const el = $("#aviso");
  el.textContent = msg;
  el.className = "aviso-flutuante" + (erro ? " erro" : "");
  el.hidden = false;
  clearTimeout(avisoTimer);
  avisoTimer = setTimeout(() => (el.hidden = true), erro ? 7000 : 3500);
}

async function copiar(texto, botao) {
  try { await navigator.clipboard.writeText(texto); } catch (e) {
    const t = document.createElement("textarea");
    t.value = texto; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove();
  }
  if (botao) {
    const antes = botao.innerHTML;
    botao.classList.add("copiado"); botao.textContent = "Copiado";
    setTimeout(() => { botao.classList.remove("copiado"); botao.innerHTML = antes; }, 1500);
  }
}

const NOMES_ETAPA = {
  "Video": ["Vídeo", "Baixando e lendo o vídeo"],
  "Transcricao": ["Transcrição", "Transcrevendo o áudio"],
  "Sinais": ["Sinais", "Procurando picos de áudio e movimento"],
  "1a passada: candidatos pela fala": ["1ª passada", "Candidatos pela fala"],
  "2a passada: a IA olha a tela": ["2ª passada", "A IA olha a tela"],
  "Escolha pela fala": ["Escolha", "A IA escolhe pela fala"],
  "Escolha pelos picos de audio": ["Escolha", "Escolha pelos picos de áudio"],
  "Render": ["Render", "Renderizando os cortes"],
};
const nomeEtapa = (t, longo = false) => (NOMES_ETAPA[t] || [t, t])[longo ? 1 : 0];

const SVG = {
  play: '<svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 1.5l7 4.5-7 4.5z" fill="#fff"/></svg>',
  twitch: '<svg width="11" height="12" viewBox="0 0 11 12"><path d="M1 0L0 2v8h3v2h2l2-2h2l2-2V0zm9 7l-2 2H6L4 11V9H2V1h8zM7 3h1v3H7zM5 3h1v3H5z" fill="#fff"/></svg>',
  youtube: '<svg width="10" height="10" viewBox="0 0 10 10"><path d="M3 2l5 3-5 3z" fill="#fff"/></svg>',
  arquivo: '<svg width="10" height="12" viewBox="0 0 10 12"><path d="M1 0h5l3 3v9H1z" fill="none" stroke="#fff" stroke-width="1.2"/></svg>',
  link: '<svg width="12" height="12" viewBox="0 0 12 12"><path d="M5 7l2-2M4 5L2.5 6.5a2 2 0 003 3L7 8M8 7l1.5-1.5a2 2 0 00-3-3L5 4" fill="none" stroke="#fff" stroke-width="1.2"/></svg>',
  copiar: '<svg width="12" height="12" viewBox="0 0 12 12"><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" stroke="#fff" fill="none"/><path d="M8 2H2.5a1 1 0 00-1 1V8" stroke="#fff" fill="none"/></svg>',
};
function plataformaDe(fonte, info) {
  if (info && info.local) return "arquivo";
  const f = (fonte || "").toLowerCase();
  if (f.includes("twitch.tv")) return "twitch";
  if (f.includes("youtu")) return "youtube";
  if (/^[a-z]:\\|^\\\\|^\//i.test(fonte)) return "arquivo";
  return "link";
}
const selo = (p) => `<div class="selo ${p}">${SVG[p] || SVG.link}</div>`;

// ------------------------------------------------------------ barra lateral e SSE
function marcarMenu() {
  document.querySelectorAll(".menu a").forEach((a) => a.classList.toggle("ativo", a.dataset.rota === S.rota));
}
function atualizarLateral() {
  const itens = (S.foto && S.foto.itens) || [];
  const pend = itens.filter((i) => i.status === "fila" || i.status === "rodando").length;
  $("#contador-fila").textContent = pend ? String(pend) : "";
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0);
  const dias = Math.round((new Date(2026, 10, 19) - hoje) / 864e5);
  $("#dias-gta").textContent = dias > 1 ? `${dias} DIAS` : dias === 1 ? "1 DIA" : dias === 0 ? "HOJE" : "SAIU!";
}
function atualizarStatusClaude(conectado = true) {
  const el = $("#status-claude");
  const c = S.config || S.config0;
  const m = c && c.maquina;
  const modelo = (c && c.resolvido && c.resolvido.modelo || "").replace(/^claude-/, "");
  if (!conectado) { el.className = "status-claude ruim"; el.lastElementChild.textContent = "servidor desligado · reconectando…"; return; }
  if (!m) return;
  el.className = "status-claude " + (m.claude ? "ok" : "ruim");
  el.lastElementChild.textContent = m.claude ? `Claude pronto · ${modelo}` : "Claude não encontrado no PATH";
  el.title = m.claude ? "O claude (Claude Code) está no PATH" : "Instale o Claude Code e faça login para usar a IA";
}

let fonteEventos = null;
function conectarEventos() {
  fonteEventos = new EventSource("/api/eventos");
  fonteEventos.onmessage = (e) => {
    const antes = S.foto;
    S.foto = JSON.parse(e.data);
    atualizarStatusClaude(true);
    atualizarLateral();
    if (S.rota === "fila") desenharFila();
    // um video acabou de terminar: a biblioteca mudou
    const terminou = (S.foto.itens || []).some((i) => i.status === "ok" &&
      !((antes && antes.itens) || []).some((a) => a.id === i.id && a.status === "ok"));
    if (terminou) { S.videos = null; if (S.rota === "biblioteca") desenharBiblioteca(); }
  };
  fonteEventos.onerror = () => atualizarStatusClaude(false);
}

// ------------------------------------------------------------ roteamento
function rotear() {
  const partes = (location.hash || "#/nova").slice(2).split("/");
  S.rota = partes[0] || "nova";
  marcarMenu();
  const tela = $("#tela");
  tela.scrollTop = 0;
  if (S.rota === "fila") desenharFila();
  else if (S.rota === "resultados") abrirResultados(decodeURIComponent(partes.slice(1).join("/") || ""));
  else if (S.rota === "biblioteca") desenharBiblioteca();
  else { S.rota = "nova"; marcarMenu(); desenharNova(); }
}

// ============================================================ NOVA EXECUCAO
async function carregarConfig(canal) {
  S.config = await api("/api/config" + (canal ? `?canal=${encodeURIComponent(canal)}` : ""));
  if (S.config.erro) avisar(S.config.erro, true);
  const r = S.config.resolvido || S.config.presets.campos_padrao;
  S.form.opcoes = {};
  for (const c of OPCOES_FORM) S.form.opcoes[c] = r[c];
  S.form.opcoes.reprisar_ia = false;
  atualizarStatusClaude(true);
}

function salvarRascunho() { guardar("clipador.rascunho", { fontes: S.form.fontes, canal: S.form.canal, opcoes: S.form.opcoes }); }

async function desenharNova() {
  if (!S.config) {
    const r = ler("clipador.rascunho", null);
    try {
      await carregarConfig(r && r.canal);
      if (r) { S.form.fontes = r.fontes || []; S.form.canal = r.canal || ""; Object.assign(S.form.opcoes, r.opcoes || {}); }
    } catch (e) {
      try { await carregarConfig(""); } catch (e2) { avisar(e2.message, true); return; }
    }
    S.form.fontes.forEach((f) => lerInfo(f));
  }
  if (S.rota !== "nova") return;
  const n = S.form.fontes.length;
  $("#tela").innerHTML = `
  <div class="tela">
    <div class="cabecalho">
      <div><div class="sobre">Nova execução</div><h1 class="titulo-tela">O que vamos cortar hoje?</h1></div>
      <div class="acoes">
        <button class="botao" id="salvar-preset">Salvar como preset</button>
        <button class="botao primario" id="gerar" ${n ? "" : "disabled"}>${SVG.play}Gerar cortes · ${n} ${n === 1 ? "vídeo" : "vídeos"}</button>
      </div>
    </div>
    <div class="colunas">
      <div class="col-esq">
        <div class="secao">
          <div class="secao-topo"><div class="rotulo-secao">Vídeos</div>
            <div class="fraco" style="font-size:13px">Cole links (um por linha) ou <button class="link" id="escolher">escolha arquivos</button></div></div>
          <div class="caixa fontes" id="fontes"></div>
        </div>
        <div class="secao">
          <div class="rotulo-secao">Preset de canal</div>
          <div class="chips" id="presets"></div>
        </div>
        <div class="secao" id="opcoes"></div>
      </div>
      <div class="col-dir">
        <div class="secao" id="facecam"></div>
        <div class="previa" id="previa"></div>
      </div>
    </div>
  </div>`;
  desenharFontes(); desenharPresets(); desenharOpcoes(); desenharFacecam(); desenharPrevia();
  $("#gerar").onclick = gerar;
  $("#salvar-preset").onclick = salvarPreset;
  $("#escolher").onclick = escolherArquivos;
  atualizarEstimativa();
}

function desenharFontes() {
  const el = $("#fontes"); if (!el) return;
  const linhas = S.form.fontes.map((f, i) => {
    const info = S.infos[f];
    let meta = "lendo…", cls = "meta";
    if (info && info.erro) { meta = info.erro; cls += " erro"; }
    else if (info) meta = [info.canal || (info.local ? "arquivo local" : ""), durCurta(info.duracao)].filter(Boolean).join(" · ");
    return `<div class="fonte-linha"><div class="num">${String(i + 1).padStart(2, "0")}</div>${selo(plataformaDe(f, info))}
      <div class="texto" title="${esc(f)}">${esc(f.replace(/^https?:\/\/(www\.)?/, ""))}</div>
      <div class="${cls}" title="${esc(info && info.titulo || "")}">${esc(meta)}</div>
      <button class="tirar" data-i="${i}" title="Tirar da lista">×</button></div>`;
  }).join("");
  el.innerHTML = linhas + `<div class="fonte-linha entrada"><div class="num">${String(S.form.fontes.length + 1).padStart(2, "0")}</div>
    <input id="novo-link" placeholder="Cole outro link ou o caminho de um arquivo .mp4 e tecle Enter" autocomplete="off" spellcheck="false"></div>`;
  el.querySelectorAll(".tirar").forEach((b) => (b.onclick = () => {
    S.form.fontes.splice(+b.dataset.i, 1); depoisDeMudarFontes();
  }));
  const inp = $("#novo-link");
  inp.onkeydown = (e) => { if (e.key === "Enter") { adicionarFontes(inp.value); } };
  inp.onpaste = (e) => {
    const txt = (e.clipboardData || window.clipboardData).getData("text");
    if (txt.includes("\n")) { e.preventDefault(); adicionarFontes(txt); }
  };
}

function adicionarFontes(texto) {
  const novas = String(texto).split(/\r?\n/).map((s) => s.trim().replace(/^"|"$/g, "")).filter((s) => s && !s.startsWith("#"));
  let n = 0;
  for (const f of novas) if (!S.form.fontes.includes(f)) { S.form.fontes.push(f); lerInfo(f); n++; }
  depoisDeMudarFontes();
  const inp = $("#novo-link"); if (inp) inp.focus();
  return n;
}

function depoisDeMudarFontes() {
  salvarRascunho(); desenharFontes();
  const n = S.form.fontes.length, g = $("#gerar");
  if (g) { g.disabled = !n; g.innerHTML = `${SVG.play}Gerar cortes · ${n} ${n === 1 ? "vídeo" : "vídeos"}`; }
  if (S.print.fonte !== S.form.fontes[0]) { S.print = { t: null, erro: "", carregando: false, url: "", fonte: "" }; }
  desenharFacecam(); desenharPrevia(); atualizarEstimativa();
}

async function lerInfo(fonte) {
  if (S.infos[fonte] && !S.infos[fonte].erro) return;
  delete S.infos[fonte];
  try { S.infos[fonte] = await api("/api/info", { body: { fonte } }); }
  catch (e) { S.infos[fonte] = { erro: e.message }; }
  if (S.rota === "nova") { desenharFontes(); desenharFacecam(); desenharPrevia(); atualizarEstimativa(); }
}

async function escolherArquivos() {
  try {
    const r = await api("/api/escolher-arquivos", { body: {} });
    if (r.arquivos.length) adicionarFontes(r.arquivos.join("\n"));
  } catch (e) { avisar(e.message, true); }
}

function desenharPresets() {
  const el = $("#presets"); if (!el) return;
  const canais = Object.keys((S.config && S.config.presets.canais) || {});
  const rotulo = (nome) => {
    const c = S.config.presets.canais[nome] || {};
    return c.dmin && c.dmax && (c.dmin > 60 || c.dmax > 60) ? `${nome} · ${c.dmin}–${c.dmax}s` : nome;
  };
  el.innerHTML = `<button class="chip ${S.form.canal ? "" : "ativo"}" data-c="">padrão</button>` +
    canais.map((c) => `<button class="chip ${S.form.canal === c ? "ativo" : ""}" data-c="${esc(c)}">${esc(rotulo(c))}</button>`).join("") +
    `<button class="chip novo" id="novo-preset">+ novo</button>`;
  el.querySelectorAll(".chip[data-c]").forEach((b) => (b.onclick = async () => {
    S.form.canal = b.dataset.c;
    try { await carregarConfig(S.form.canal); } catch (e) { avisar(e.message, true); return; }
    salvarRascunho(); desenharPresets(); desenharOpcoes(); desenharFacecam(); desenharPrevia(); atualizarEstimativa();
  }));
  $("#novo-preset").onclick = () => salvarPreset(true);
}

function opcao(o) { return S.form.opcoes[o]; }
function mudar(o, v) { S.form.opcoes[o] = v; salvarRascunho(); atualizarEstimativa(); }

function desenharOpcoes() {
  const el = $("#opcoes"); if (!el) return;
  const O = S.form.opcoes;
  const info = S.infos[S.form.fontes[0]] || {};
  const plat = O.plataforma || (info.local ? "" : plataformaDe(S.form.fontes[0] || "", info));
  const chave = (o, t, d) => `<div class="opcao"><div><div class="t">${t}</div><div class="d">${d}</div></div>
    <button class="chave ${O[o] ? "ligada" : ""}" data-chave="${o}" aria-pressed="${!!O[o]}"></button></div>`;
  el.innerHTML = `
    <div class="secao-topo"><div class="rotulo-secao">Opções</div>
      <button class="avancado-botao" id="avancado">${S.avancado ? "Avançado ▴" : "Avançado ▾"}</button></div>
    <div class="cartoes">
      <div class="cartao"><div class="nome">Cortes por vídeo</div><div class="linha">
        <input class="numero" type="number" min="1" max="30" id="o-cortes" value="${O.cortes}">
        <div class="sub">de ${Math.max(O.candidatos, O.cortes)} candidatos</div></div></div>
      <div class="cartao"><div class="nome">Duração</div><div class="linha">
        <input class="numero" type="number" min="1" id="o-dmin" value="${O.dmin}"><span class="traco">–</span>
        <input class="numero" type="number" min="1" id="o-dmax" value="${O.dmax}"><div class="sub">segundos</div></div></div>
      <div class="cartao"><div class="nome">Crédito</div><div class="credito-campo">
        ${["twitch", "youtube"].includes(plat) ? selo(plat) : ""}
        <input id="o-credito" value="${esc(O.credito || "")}" placeholder="${esc(info.canal ? (plat === "twitch" ? "twitch.tv/" : "@") + info.canal : "automático pelo link")}"></div></div>
    </div>
    <div class="segmentado" id="modos">${["blur", "crop", "facecam"].map((m) =>
      `<button data-m="${m}" class="${O.modo === m ? "ativo" : ""}">${m[0].toUpperCase() + m.slice(1)}</button>`).join("")}</div>
    <div class="lista-opcoes">
      ${chave("visao", "2ª passada: a IA olha a tela", "Mais precisa, gasta mais cota do plano")}
      ${chave("chat", "Chat da live como sinal", "Twitch precisa do TwitchDownloaderCLI")}
      ${chave("reprisar_ia", "Reprisar IA", "Reusa as respostas salvas, sem gastar cota")}
    </div>
    ${S.avancado ? `<div class="lista-opcoes">
      ${chave("sem_ia", "Sem IA", "Corta nos picos de áudio, sem chamar o Claude")}
      ${chave("cenas", "Movimento na tela", "Sinal local e grátis; gera candidatos visuais")}
      <div class="opcao"><div><div class="t">Candidatos da 1ª passada</div><div class="d">Trechos que a IA pré-seleciona pela fala</div></div><input type="number" min="1" data-num="candidatos" value="${O.candidatos}"></div>
      <div class="opcao"><div><div class="t">Candidatos visuais</div><div class="d">Picos de movimento sem fala (0 desliga)</div></div><input type="number" min="0" data-num="candidatos_visuais" value="${O.candidatos_visuais}"></div>
      <div class="opcao"><div><div class="t">Whisper</div><div class="d">Modelo da transcrição</div></div><select data-txt="whisper">${["small", "medium", "large-v3"].map((w) => `<option ${O.whisper === w ? "selected" : ""}>${w}</option>`).join("")}</select></div>
      <div class="opcao"><div><div class="t">Idioma</div><div class="d">Vazio = detectar</div></div><input type="text" data-txt="idioma" value="${esc(O.idioma || "")}"></div>
      <div class="opcao"><div><div class="t">Modelo do Claude</div><div class="d">Usado pelo Claude Code</div></div><input type="text" data-txt="modelo" value="${esc(O.modelo || "")}"></div>
      <div class="opcao"><div><div class="t">Ícone do crédito</div><div class="d">Só precisa em arquivo local</div></div><select data-txt="plataforma"><option value="" ${!O.plataforma ? "selected" : ""}>pelo link</option><option ${O.plataforma === "twitch" ? "selected" : ""}>twitch</option><option ${O.plataforma === "youtube" ? "selected" : ""}>youtube</option></select></div>
      <div class="opcao"><div><div class="t">Hashtags extras</div><div class="d">Separadas por espaço</div></div><input type="text" data-tags value="${esc((O.hashtags_extras || []).join(" "))}"></div>
    </div>` : ""}`;
  $("#avancado").onclick = () => { S.avancado = !S.avancado; desenharOpcoes(); };
  for (const o of ["cortes", "dmin", "dmax"]) $("#o-" + o).onchange = (e) => { mudar(o, parseInt(e.target.value, 10) || 1); desenharOpcoes(); };
  $("#o-credito").onchange = (e) => { mudar("credito", e.target.value.trim()); desenharPrevia(); };
  el.querySelectorAll("#modos button").forEach((b) => (b.onclick = () => { mudar("modo", b.dataset.m); desenharOpcoes(); desenharFacecam(); desenharPrevia(); }));
  el.querySelectorAll("[data-chave]").forEach((b) => (b.onclick = () => { mudar(b.dataset.chave, !opcao(b.dataset.chave)); desenharOpcoes(); }));
  el.querySelectorAll("[data-num]").forEach((i) => (i.onchange = () => mudar(i.dataset.num, parseInt(i.value, 10) || 0)));
  el.querySelectorAll("[data-txt]").forEach((i) => (i.onchange = () => mudar(i.dataset.txt, i.value.trim())));
  el.querySelectorAll("[data-tags]").forEach((i) => (i.onchange = () => mudar("hashtags_extras", i.value.split(/\s+/).filter(Boolean))));
}

// ------------------------------------------------------------ facecam
function segundoPadrao() {
  const info = S.infos[S.form.fontes[0]] || {};
  return info.duracao ? Math.floor(info.duracao * 0.25) : 60;
}

function desenharFacecam() {
  const el = $("#facecam"); if (!el) return;
  const fonte = S.form.fontes[0];
  const ativo = S.form.opcoes.modo === "facecam";
  if (S.print.t == null) S.print.t = segundoPadrao();
  const url = fonte ? `/api/print?fonte=${encodeURIComponent(fonte)}&t=${S.print.t}` : "";
  let corpo;
  if (!fonte) corpo = `<div class="vazio-print">Adicione um vídeo para tirar um print e marcar a câmera do streamer.</div>`;
  else if (S.print.erro && S.print.url === url) corpo = `<div class="vazio-print">Não consegui tirar o print: ${esc(S.print.erro)}</div>`;
  else corpo = `<img id="print-img" src="${url}" alt=""><div class="sombra"></div><div id="selecao"></div>
    ${S.print.url !== url ? '<div class="vazio-print" id="print-carregando">tirando o print…</div>' : ""}`;
  const canal = S.form.canal;
  el.innerHTML = `
    <div class="secao-topo"><div class="rotulo-secao">Região da facecam</div>
      <div class="fraco" style="font-size:13px">${fonte ? `print em ${fmt(S.print.t)} · <button class="link" id="outro-print">outro print</button>` : ""}</div></div>
    <div class="print ${ativo && fonte ? "" : "desligado"}" id="print" style="${ativo ? "" : "opacity:.55"}">${corpo}</div>
    <div class="dica-linha"><div class="dica">${ativo
      ? "Arraste para desenhar o retângulo sobre a câmera do streamer. Os números são preenchidos sozinhos."
      : "Escolha o layout <b>Facecam</b> para marcar a câmera do streamer."}</div>
      ${ativo && S.form.opcoes.facecam && canal ? `<button class="botao pequeno" id="facecam-preset">Salvar no preset ${esc(canal)}</button>` : ""}</div>`;
  const img = $("#print-img");
  if (img) {
    img.onload = () => { S.print.url = url; S.print.erro = ""; const c = $("#print-carregando"); if (c) c.remove(); desenharPrevia(); };
    img.onerror = async () => {
      let msg = "erro";
      try { const r = await fetch(url); msg = (await r.json()).erro || msg; } catch (e) { /* nada */ }
      S.print = { ...S.print, erro: msg, url, fonte }; desenharFacecam();
    };
  }
  S.print.fonte = fonte;
  const outro = $("#outro-print");
  if (outro) outro.onclick = () => {
    const info = S.infos[fonte] || {};
    const total = info.duracao || 3600;
    S.print.t = Math.floor(total * (0.1 + Math.random() * 0.8));
    desenharFacecam();
  };
  const salvar = $("#facecam-preset");
  if (salvar) salvar.onclick = async () => {
    try {
      await api(`/api/canais/${encodeURIComponent(canal)}`, { method: "PUT", body: { valores: { modo: "facecam", facecam: S.form.opcoes.facecam } } });
      S.config.presets = (await api("/api/config")).presets;
      avisar(`Facecam salva no preset ${canal}.`);
    } catch (e) { avisar(e.message, true); }
  };
  desenharSelecao();
  if (ativo && fonte) ligarDesenho();
}

function areaImagem() {
  // retangulo (em px do .print) onde a imagem aparece de verdade (object-fit: contain)
  const caixa = $("#print"), img = $("#print-img");
  const W = caixa.clientWidth, H = caixa.clientHeight;
  const iw = (img && img.naturalWidth) || 16, ih = (img && img.naturalHeight) || 9;
  const esc_ = Math.min(W / iw, H / ih), w = iw * esc_, h = ih * esc_;
  return { x: (W - w) / 2, y: (H - h) / 2, w, h };
}

function desenharSelecao() {
  const el = $("#selecao"); if (!el) return;
  const fc = S.form.opcoes.facecam;
  if (!fc || S.form.opcoes.modo !== "facecam") { el.className = ""; el.innerHTML = ""; el.removeAttribute("style"); return; }
  const a = areaImagem();
  const [x, y, w, h] = fc;
  el.className = "selecao" + (x + w > 0.62 ? " a-esquerda" : "");
  el.style.cssText = `left:${a.x + x * a.w}px;top:${a.y + y * a.h}px;width:${w * a.w}px;height:${h * a.h}px`;
  el.innerHTML = `<i></i><i></i><i></i><i></i><div class="valores">${[x, y].map((v) => virgula(v, 2)).join(" · ")} · ${virgula(w, 2)} × ${virgula(h, 2)}</div>`;
}

function ligarDesenho() {
  const caixa = $("#print");
  let inicio = null;
  const ponto = (e) => {
    const r = caixa.getBoundingClientRect(), a = areaImagem();
    return [Math.min(1, Math.max(0, (e.clientX - r.left - a.x) / a.w)), Math.min(1, Math.max(0, (e.clientY - r.top - a.y) / a.h))];
  };
  caixa.onmousedown = (e) => { if (S.print.url) { e.preventDefault(); inicio = ponto(e); } };
  const mover = (e) => {
    if (!inicio) return;
    const p = ponto(e);
    const x = Math.min(inicio[0], p[0]), y = Math.min(inicio[1], p[1]);
    const w = Math.abs(p[0] - inicio[0]), h = Math.abs(p[1] - inicio[1]);
    S.form.opcoes.facecam = [x, y, w, h].map((v) => Math.round(v * 1000) / 1000);
    desenharSelecao();
  };
  const soltar = () => {
    if (!inicio) return;
    inicio = null;
    const fc = S.form.opcoes.facecam;
    if (fc && (fc[2] < 0.02 || fc[3] < 0.02)) S.form.opcoes.facecam = null;
    salvarRascunho(); desenharFacecam(); desenharPrevia();
  };
  caixa.onmousemove = mover;
  window.onmousemove = mover;
  window.onmouseup = soltar;
}

// ------------------------------------------------------------ previa e estimativa
function desenharPrevia() {
  const el = $("#previa"); if (!el) return;
  const O = S.form.opcoes, fonte = S.form.fontes[0], info = S.infos[fonte] || {};
  const img = S.print.url ? `url('${S.print.url}')` : "linear-gradient(180deg,#E0587A 0%,#3B2A5C 50%,#1B1B2A 100%)";
  let tela = "";
  const H = 199, W = 112;
  if (O.modo === "facecam" && O.facecam && S.print.url) {
    const [x, y, w, h] = O.facecam;
    const topo = Math.round(H / 3);
    // a regiao da facecam (fracao do quadro 16:9) escalada para cobrir 112 x topo
    const esc_ = Math.max(W / (w * 16), topo / (h * 9));
    const bw = 16 * esc_, bh = 9 * esc_;
    const fx = -(x * bw) - ((w * bw) - W) / 2, fy = -(y * bh) - ((h * bh) - topo) / 2;
    const gh = H - topo, gesc = gh / 9, gw = 16 * gesc;
    tela = `<div class="parte" style="top:0;height:${topo}px;background-image:${img};background-size:${bw}px ${bh}px;background-position:${fx}px ${fy}px"></div>
      <div class="parte" style="top:${topo}px;height:${gh}px;background-image:${img};background-size:${gw}px ${gh}px;background-position:${-(gw - W) / 2}px 0"></div>`;
  } else if (O.modo === "crop") {
    tela = `<div class="parte" style="top:0;height:${H}px;background-image:${img};background-size:cover;background-position:center"></div>`;
  } else {
    tela = `<div class="borrado" style="background-image:${img}"></div>
      <div class="parte" style="top:${(H - 63) / 2}px;height:63px;background-image:${img};background-size:cover;background-position:center"></div>`;
  }
  const plat = O.plataforma || plataformaDe(fonte || "", info);
  const cred =O.credito ? O.credito.replace(/^@/, plat === "twitch" ? "twitch.tv/" : "@") : info.canal ? (plat === "twitch" ? "twitch.tv/" : "@") + info.canal : "";
  const titTop = O.modo === "facecam" ? Math.round(H / 3) + 8 : 24;
  const est = S.estimativa;
  let chamadas = "…";
  if (est) chamadas = est.reprise ? "0 (reprise)" : O.sem_ia ? "0 (sem IA)" : `~${est.total}${est.aproximado ? "+" : ""}`;
  const totalDur = S.form.fontes.reduce((s, f) => s + ((S.infos[f] || {}).duracao || 0), 0);
  const m = (S.config && S.config.maquina) || {};
  el.innerHTML = `
    <div class="celular">${tela}
      <div class="titulo-mini" style="top:${titTop}px">Título do <span class="rosa">corte</span> aqui</div>
      ${cred ? `<div class="credito-mini">${esc(cred)}</div>` : ""}</div>
    <div class="resumo-antes">
      <div class="rotulo-secao">Antes de começar</div>
      <div class="par"><div>Vídeos na fila</div><div>${S.form.fontes.length}${totalDur ? ` · ${durCurta(totalDur)} no total` : ""}</div></div>
      <div class="par" title="${est ? esc(est.por_video.map((v, i) => `vídeo ${i + 1}: ${v.primeira} na 1ª passada + até ${v.segunda} na 2ª`).join("\n")) : ""}"><div>Chamadas ao Claude</div><div class="mono ciano">${chamadas}</div></div>
      <div class="par"><div>Whisper</div><div>${esc(O.whisper || "")}${m.gpu === true ? " · GPU" : m.gpu === false ? " · CPU" : ""}</div></div>
      <div class="par"><div>Saída</div><div class="mono" style="font-size:12px" title="${esc(S.config && S.config.saida || "")}">${esc(((S.config && S.config.saida) || "saida").split(/[\\/]/).slice(-1)[0])}/</div></div>
    </div>`;
}

let estTimer = null;
function atualizarEstimativa() {
  clearTimeout(estTimer);
  estTimer = setTimeout(async () => {
    try {
      S.estimativa = await api("/api/estimativa", { body: { fontes: S.form.fontes, canal: S.form.canal, opcoes: opcoesParaEnviar(OPCOES_FORM) } });
    } catch (e) { S.estimativa = null; }
    desenharPrevia();
  }, 150);
}

function opcoesParaEnviar(campos) {
  const o = {};
  for (const c of campos) {
    let v = S.form.opcoes[c];
    if ((c === "credito" || c === "plataforma") && !v) v = null;
    if (c === "facecam" && !(Array.isArray(v) && v.length === 4)) v = null;
    o[c] = v;
  }
  return o;
}

async function gerar() {
  const b = $("#gerar"); b.disabled = true;
  try {
    const opcoes = opcoesParaEnviar(OPCOES_FORM);
    if (opcoes.modo === "facecam" && !opcoes.facecam) throw new Error("Marque a região da facecam no print (ou escolha Blur/Crop).");
    await api("/api/executar", { body: { fontes: S.form.fontes, canal: S.form.canal, opcoes } });
    S.form.fontes = []; salvarRascunho();
    location.hash = "#/fila";
  } catch (e) { avisar(e.message, true); b.disabled = false; }
}

async function salvarPreset(novo = false) {
  let nome = S.form.canal;
  if (novo === true || !nome) {
    nome = (prompt("Nome do preset (ex.: o canal do streamer, sem espaços):", "") || "").trim();
    if (!nome) return;
  } else if (!(await confirmar({ titulo: `Salvar o preset "${nome}"?`, texto: "As opções atuais vão ser gravadas no config.toml.",
    sim: "Salvar", icone: ICONE_SALVAR }))) return;
  const valores = opcoesParaEnviar(OPCOES_PRESET);
  try {
    await api(`/api/canais/${encodeURIComponent(nome)}`, { method: "PUT", body: { valores } });
    S.form.canal = nome;
    await carregarConfig(nome);
    salvarRascunho(); desenharPresets(); desenharOpcoes(); desenharFacecam(); desenharPrevia();
    avisar(`Preset "${nome}" salvo no config.toml.`);
  } catch (e) { avisar(e.message, true); }
}

// ============================================================ FILA / PROCESSANDO
const ROTULO_STATUS = { fila: "NA FILA", rodando: "RODANDO", ok: "PRONTO", falhou: "FALHOU · LOTE SEGUE", cancelado: "CANCELADO" };

function decorrido(it, agora) {
  if (!it.inicio) return "";
  return fmt((it.fim || agora) - it.inicio);
}

function desenharFila() {
  if (S.rota !== "fila") return;
  const foto = S.foto;
  if (!foto) { $("#tela").innerHTML = `<div class="tela"><div class="fraco">Conectando…</div></div>`; return; }
  const itens = foto.itens || [];
  if (!itens.length) {
    $("#tela").innerHTML = `<div class="tela"><div class="vazio"><h2>Nada na fila</h2>
      <div>Cole os links em Nova execução e clique em Gerar cortes. Fechar a janela pelo X desliga tudo (o Clipador pergunta antes).</div>
      <a class="botao primario" href="#/nova">${SVG.play}Nova execução</a></div></div>`;
    return;
  }
  const rodando = itens.find((i) => i.status === "rodando");
  let sel = itens.find((i) => i.id === S.filaSel) || rodando || itens.find((i) => i.status === "fila") || itens[itens.length - 1];
  const ativos = itens.filter((i) => i.status === "fila" || i.status === "rodando").length;
  const lista = itens.map((it) => {
    const etapa = it.etapas.length ? `${it.etapas.length}/${it.etapas_previstas.length}` : "";
    const frac = it.status === "rodando" ? progressoItem(it) : 0;
    let topo = ROTULO_STATUS[it.status];
    if (it.status === "rodando" && etapa) topo += ` · ${etapa}`;
    if (it.status === "ok") topo += ` · ${it.cortes} cortes`;
    return `<button class="item-fila ${it.id === sel.id ? "sel" : ""} ${it.status === "falhou" ? "falhou" : ""}" data-id="${it.id}">
      <div class="topo"><span class="st-${it.status}">${topo}</span><span>${decorrido(it, foto.agora)}</span></div>
      <div class="nome ${it.status === "rodando" ? "forte" : ""}">${esc(it.titulo || it.fonte)}</div>
      ${it.status === "rodando" ? `<div class="trilho"><div style="width:${Math.round(frac * 100)}%"></div></div>` : ""}
      ${it.status === "falhou" ? `<div class="erro">${esc(it.erro)} Rodar de novo reaproveita o cache.</div>` : ""}</button>`;
  }).join("");
  $("#tela").innerHTML = `<div class="fila-layout">
    <div class="fila-lista"><div class="rotulo-secao">Fila · ${itens.length} ${itens.length === 1 ? "vídeo" : "vídeos"}</div>${lista}
      ${itens.some((i) => ["ok", "falhou", "cancelado"].includes(i.status)) ? `<button class="link" id="limpar" style="padding:0 8px;text-align:left">limpar concluídos</button>` : ""}</div>
    <div class="execucao" id="execucao">${painelExecucao(sel, itens, foto, ativos)}</div></div>`;
  document.querySelectorAll(".item-fila").forEach((b) => (b.onclick = () => { S.filaSel = +b.dataset.id; desenharFila(); }));
  const lim = $("#limpar"); if (lim) lim.onclick = async () => { S.filaSel = null; await api("/api/limpar", { body: {} }); };
  const parar = $("#parar");
  if (parar) parar.onclick = async () => {
    if (!(await confirmar({ titulo: "Parar tudo?", texto: "O vídeo que está rodando para agora e a fila é cancelada.",
      itens: itensEmAndamento(), nota: "O que já foi feito fica em cache e é reaproveitado.", sim: "Parar", nao: "Continuar", perigo: true }))) return;
    try { await api("/api/parar", { body: {} }); } catch (e) { avisar(e.message, true); }
  };
}

function barraPrincipal(it) {
  const barras = Object.values(it.barras || {});
  return barras.length ? barras[barras.length - 1] : null;
}
function progressoItem(it) {
  const prev = it.etapas_previstas.length || 1;
  const feitas = it.etapas.filter((e) => e.status === "ok").length;
  const b = barraPrincipal(it);
  const parcial = b && b.total ? Math.min(1, b.feito / b.total) : 0;
  return Math.min(1, (feitas + parcial) / prev);
}

function painelExecucao(it, itens, foto, ativos) {
  const pos = itens.indexOf(it) + 1;
  const info = S.infos[it.fonte] || {};
  const dura = it.duracao || info.duracao;
  const cab = `<div class="cabecalho"><div>
      <div class="sobre">Vídeo ${pos} de ${itens.length} · ${esc(it.fonte.replace(/^https?:\/\/(www\.)?/, ""))}${dura ? " · " + durCurta(dura) : ""}</div>
      <h1 class="titulo-video">${esc(it.titulo || info.titulo || it.fonte)}</h1></div>
    <div class="acoes">${ativos ? `<button class="botao" id="parar">Parar lote</button>` : ""}
      ${it.status === "ok" && it.pasta_cortes ? `<a class="botao primario" href="#/resultados/${encodeURIComponent(pastaDe(it.pasta_cortes))}">Ver os ${it.cortes} cortes</a>` : ""}</div></div>`;
  // etapas
  const etapas = it.etapas_previstas.map((nome, i) => {
    const e = it.etapas[i];
    let cls = "futura", barra = "", tempo = "";
    if (e) {
      cls = e.status;
      if (e.status === "rodando") {
        const b = barraPrincipal(it);
        barra = `<div style="width:${b && b.total ? Math.round(100 * Math.min(1, b.feito / b.total)) : 8}%"></div>`;
      }
      if (e.tempo != null) tempo = ` <span class="mono">${dur(e.tempo)}</span>`;
    }
    return `<div class="etapa ${cls}"><div class="barra">${barra}</div><div class="nome">${i + 1} ${nomeEtapa(e ? e.titulo : nome)}${tempo}</div></div>`;
  }).join("");
  // painel da etapa atual
  const atual = it.etapas.find((e) => e.status === "rodando");
  const b = barraPrincipal(it);
  let grande = "", desc = "", pct = null;
  if (b && b.total) {
    pct = Math.min(1, b.feito / b.total);
    if (b.unidade === "tempo") { grande = `${fmt(b.feito)}<span>/${fmt(b.total)}</span>`; }
    else if (b.unidade === "bytes") { grande = `${Math.round(b.feito / 1e6)}<span>/${Math.round(b.total / 1e6)} MB</span>`; }
    else { grande = `${Math.round(b.feito)}<span>/${Math.round(b.total)}</span>`; }
    desc = b.descricao + (it.tokens.rodando ? ` · ${it.tokens.rodando} rodando` : "");
  }
  const ultimo = (it.registro || []).slice(-1)[0];
  let painel;
  if (it.status === "rodando") {
    const titulo = atual ? nomeEtapa(atual.titulo, true) : "Preparando";
    const tempoEtapa = atual ? fmt(foto.agora - atual.inicio) : "";
    painel = `<div class="painel-etapa"><div class="topo"><div class="t">${esc(titulo)}</div><div class="mono fraco" style="font-size:12px">${tempoEtapa}</div></div>
      ${grande ? `<div class="grande"><div class="n">${grande}</div><div class="d">${esc(desc)}</div></div>`
               : `<div class="grande"><div class="d" style="font-size:15px">${esc(ultimo ? ultimo.texto : "começando…")}</div></div>`}
      <div class="progresso ${pct == null ? "indeterminado" : ""}"><div style="width:${Math.round((pct || 0) * 100)}%"></div></div></div>`;
  } else if (it.status === "fila") {
    painel = `<div class="painel-etapa"><div class="topo"><div class="t">Na fila</div></div><div class="grande"><div class="d" style="font-size:15px">Começa quando o vídeo anterior terminar.</div></div></div>`;
  } else if (it.status === "ok") {
    const r = it.resumo || {};
    painel = `<div class="painel-etapa"><div class="topo"><div class="t">Pronto</div><div class="mono fraco" style="font-size:12px">${r.tempo_total ? fmt(r.tempo_total) : decorrido(it, foto.agora)}</div></div>
      <div class="grande"><div class="n">${it.cortes}</div><div class="d">cortes prontos em ${esc(pastaDe(it.pasta_cortes))}/cortes</div></div></div>`;
  } else {
    painel = `<div class="painel-etapa"><div class="topo"><div class="t">${it.status === "falhou" ? "Falhou" : "Cancelado"}</div></div>
      <div class="caixa-erro">${esc(it.erro || "Cancelado pelo usuário. O que já foi feito ficou em cache.")}</div></div>`;
  }
  const t = it.tokens || {};
  const tokens = `<div class="painel-tokens"><div class="cab"><i class="${t.rodando ? "pisca" : ""}"></i>Claude ${it.status === "rodando" ? "ao vivo" : ""}</div>
    <div class="nums"><div><div class="r">entrada</div><div class="v">${k(t.entrada)}</div></div><div><div class="r">saída</div><div class="v">${k(t.saida)}</div></div></div>
    <div class="rodape">${t.chamadas || 0} chamadas · ${t.falhas || 0} falhas · ${it.opcoes.reprisar_ia ? "reprise (sem cota)" : "cota do plano"}</div></div>`;
  // candidatos da 2a passada
  let cand = "";
  if ((it.candidatos || []).length) {
    const linhas = it.candidatos.map((c) => {
      const mudou = Math.abs(c.inicio - c.inicio_antes) > 0.5 || Math.abs(c.fim - c.fim_antes) > 0.5;
      const obs = !c.avaliado ? `<span class="rosa">falhou (sem imagem)</span>` : c.falta_contexto ? `<span class="amarelo">Falta contexto antes da janela</span>` : esc(c.titulo);
      return `<div class="lin"><div class="c1">${fmt(c.inicio_antes)} → ${fmt(c.fim_antes)}</div>
        <div class="c2">${notaTxt(c.nota_antes).replace(",0", "")} → <b class="${corNota(c.nota)}">${c.nota == null ? "…" : notaTxt(c.nota).replace(",0", "")}</b></div>
        <div class="c3 ${mudou ? "ciano" : "apagado"}">${mudou ? `${fmt(c.inicio)} → ${fmt(c.fim)}` : "igual"}</div><div class="c4">${obs}</div></div>`;
    }).join("");
    cand = `<div class="tabela"><div class="cab"><div class="c1">Candidato</div><div class="c2">Nota</div><div class="c3">Limites corrigidos</div><div class="c4">Título / observação</div></div>${linhas}</div>`;
  }
  const reg = (it.registro || []).slice(-8).map((m) => `<div class="${m.nivel}">${esc(m.texto)}</div>`).join("");
  return cab + `<div class="etapas">${etapas}</div><div class="paineis">${painel}${tokens}</div>${cand}
    ${reg ? `<div class="secao"><div class="rotulo-mini">Registro</div><div class="registro">${reg}</div></div>` : ""}`;
}

function pastaDe(caminhoCortes) {
  const partes = String(caminhoCortes || "").split(/[\\/]/).filter(Boolean);
  return partes[partes.length - 1] === "cortes" ? partes[partes.length - 2] : partes[partes.length - 1];
}

// ============================================================ RESULTADOS
async function abrirResultados(pasta) {
  $("#tela").innerHTML = `<div class="tela"><div class="fraco">Carregando…</div></div>`;
  try {
    if (!pasta) {
      S.videos = (await api("/api/videos")).videos;
      if (!S.videos.length) {
        $("#tela").innerHTML = `<div class="tela"><div class="vazio"><h2>Nenhum corte ainda</h2><div>Os vídeos processados aparecem aqui.</div>
          <a class="botao primario" href="#/nova">${SVG.play}Nova execução</a></div></div>`;
        return;
      }
      location.replace(`#/resultados/${encodeURIComponent(S.videos[0].pasta)}`);
      return;
    }
    const v = await api(`/api/videos/${encodeURIComponent(pasta)}`);
    if (!S.video || S.video.pasta !== v.pasta) S.sel = 0;
    S.video = v;
  } catch (e) {
    $("#tela").innerHTML = `<div class="tela"><div class="caixa-erro">${esc(e.message)}</div></div>`;
    return;
  }
  desenharResultados();
}

function desenharResultados() {
  const v = S.video; if (!v || S.rota !== "resultados") return;
  const posts = v.posts;
  const item = ((S.foto && S.foto.itens) || []).filter((i) => i.status === "ok" && pastaDe(i.pasta_cortes) === v.pasta).slice(-1)[0];
  const r = item && item.resumo;
  const postados = posts.filter((p) => p.postado_em).length;
  const meta = [];
  if (r) meta.push(`tempo total <b>${fmt(r.tempo_total)}</b>`);
  if (r && r.uso && r.uso.chamadas) meta.push(`Claude <span class="mono ciano">${k(r.uso.entrada)} / ${k(r.uso.saida)}</span> tokens`);
  if (item) meta.push(`layout <b>${esc(item.opcoes.modo)}</b>`);
  meta.push(`postados <b>${postados} de ${posts.length}</b>`);
  const src = (p) => `/midia/${encodeURIComponent(v.pasta)}/${encodeURIComponent(p.arquivo)}`;
  const grade = posts.map((p, i) => `<button class="corte ${i === S.sel ? "sel" : ""}" data-i="${i}">
      <div class="miniatura">${p.existe ? `<video src="${src(p)}#t=1" preload="metadata" muted playsinline></video>` : `<div class="vazio-print" style="position:absolute;inset:0">arquivo não encontrado</div>`}
        <div class="etiqueta esq ${corNota(p.nota)}">${notaTxt(p.nota)}</div><div class="etiqueta dir">${fmt(p.duracao)}</div>
        ${p.postado_em ? `<div class="etiqueta postado">postado</div>` : ""}</div>
      <div><div class="t">${esc(p.titulo || p.arquivo)}</div><div class="s">${String(i + 1).padStart(2, "0")} · ${fmt(p.inicio)} → ${fmt(p.fim)}</div></div></button>`).join("");
  $("#tela").innerHTML = `<div class="resultados-layout">
    <div class="galeria">
      <div class="cabecalho" style="flex-direction:column;align-items:stretch;gap:14px">
        <div class="migalha"><a href="#/biblioteca">Biblioteca</a><span class="apagado">/</span><b>${esc(v.titulo)}</b></div>
        <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:16px">
          <h1 class="titulo-tela" style="font-size:30px;line-height:36px">${posts.length} ${posts.length === 1 ? "corte pronto" : "cortes prontos"}</h1>
          <button class="botao" id="abrir-pasta" style="font-size:13px;padding:10px 14px">Abrir pasta</button></div>
        <div class="meta-linha">${meta.map((m) => `<div>${m}</div>`).join("")}</div>
      </div>
      <div class="grade">${grade}</div>
    </div>
    <div class="detalhe" id="detalhe"></div></div>`;
  document.querySelectorAll(".corte").forEach((b) => (b.onclick = () => {
    S.sel = +b.dataset.i;
    document.querySelectorAll(".corte").forEach((x) => x.classList.toggle("sel", x === b));
    desenharDetalhe();
  }));
  document.querySelectorAll(".corte video").forEach((vid) => {
    const card = vid.closest(".corte");
    card.onmouseenter = () => { vid.currentTime = 1; vid.play().catch(() => {}); };
    card.onmouseleave = () => { vid.pause(); };
  });
  $("#abrir-pasta").onclick = () => api(`/api/videos/${encodeURIComponent(v.pasta)}/abrir`, { body: {} }).catch((e) => avisar(e.message, true));
  desenharDetalhe();
}

function desenharDetalhe() {
  const v = S.video, p = v.posts[S.sel]; const el = $("#detalhe");
  if (!p) { el.innerHTML = ""; return; }
  const src = `/midia/${encodeURIComponent(v.pasta)}/${encodeURIComponent(p.arquivo)}`;
  const data = p.postado_em ? new Date(p.postado_em).toLocaleDateString("pt-BR") : "";
  el.innerHTML = `
    <div class="detalhe-topo">
      <div class="player">${p.existe ? `<video src="${src}" controls preload="metadata" playsinline></video>` : ""}</div>
      <div class="detalhe-info">
        <div class="mono fraco" style="font-size:12px">${esc(p.arquivo)}</div>
        <div class="nota-grande"><b class="${corNota(p.nota)}">${notaTxt(p.nota)}</b><span>/10</span></div>
        <div class="tt">${esc(p.titulo || "")}</div>
        <div class="mono ciano" style="font-size:12px">${fmt(p.inicio)} → ${fmt(p.fim)} · ${Math.round(p.duracao)}s</div>
      </div>
    </div>
    ${p.motivo ? `<div class="secao" style="gap:8px"><div class="rotulo-mini">Por que a IA escolheu</div><div class="motivo">${esc(p.motivo)}</div></div>` : ""}
    <div class="bloco"><div class="cab"><div class="rotulo-mini">Legenda do post</div>
      <button class="botao pequeno copiar" id="copiar-legenda">${SVG.copiar}Copiar</button></div>
      <div class="texto-post">${esc(p.legenda_post || "")}</div></div>
    <div class="bloco"><div class="cab"><div class="rotulo-mini">Hashtags</div>
      <button class="botao pequeno" id="copiar-tags">Copiar</button></div>
      <div class="tags">${(p.hashtags || []).map((t) => `<span>${esc(t)}</span>`).join("")}</div></div>
    <div class="acoes-corte">
      ${p.postado_em
        ? `<button class="botao marcado" id="postado" title="Clique para desmarcar">✓ Postado em ${data}</button>`
        : `<button class="botao claro" id="postado">Marcar como postado</button>`}
      <button class="botao" id="mostrar">Mostrar arquivo</button></div>`;
  $("#copiar-legenda").onclick = (e) => copiar(p.legenda_post || "", e.currentTarget);
  $("#copiar-tags").onclick = (e) => copiar((p.hashtags || []).join(" "), e.currentTarget);
  $("#mostrar").onclick = () => api(`/api/videos/${encodeURIComponent(v.pasta)}/abrir`, { body: { arquivo: p.arquivo } }).catch((e) => avisar(e.message, true));
  $("#postado").onclick = async () => {
    try {
      const r = await api(`/api/videos/${encodeURIComponent(v.pasta)}/postado`, { body: { arquivo: p.arquivo, postado: !p.postado_em } });
      p.postado_em = r.postado_em; S.videos = null;
      desenharResultados();
    } catch (e) { avisar(e.message, true); }
  };
}

// ============================================================ BIBLIOTECA
async function desenharBiblioteca() {
  if (!S.videos) {
    $("#tela").innerHTML = `<div class="tela"><div class="fraco">Carregando…</div></div>`;
    try { S.videos = (await api("/api/videos")).videos; } catch (e) { avisar(e.message, true); return; }
  }
  if (S.rota !== "biblioteca") return;
  const vs = S.videos;
  const linhas = vs.map((v) => `<a class="video-linha" href="#/resultados/${encodeURIComponent(v.pasta)}">
      <div class="mini">${v.primeiro ? `<video src="/midia/${encodeURIComponent(v.pasta)}/${encodeURIComponent(v.primeiro)}#t=1" preload="metadata" muted></video>` : ""}</div>
      <div class="info"><div class="t">${esc(v.titulo)}</div><div class="s">${esc(v.pasta)} · ${new Date(v.atualizado * 1000).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</div></div>
      <div class="num"><b class="${corNota(v.melhor_nota)}">${notaTxt(v.melhor_nota)}</b><span>melhor nota</span></div>
      <div class="num"><b>${v.cortes}</b><span>cortes</span></div>
      <div class="num"><b class="${v.postados ? "ciano" : ""}">${v.postados}/${v.cortes}</b><span>postados</span></div></a>`).join("");
  $("#tela").innerHTML = `<div class="tela">
    <div class="cabecalho"><div><div class="sobre">Biblioteca</div><h1 class="titulo-tela">Vídeos processados</h1></div>
      <div class="acoes"><button class="botao" id="recarregar">Atualizar</button></div></div>
    ${vs.length ? `<div class="lista-videos">${linhas}</div>` : `<div class="vazio"><h2>Nada por aqui ainda</h2><div>Os vídeos cortados (pastas em saida/) aparecem aqui.</div></div>`}</div>`;
  $("#recarregar").onclick = () => { S.videos = null; desenharBiblioteca(); };
}

// ============================================================ inicio
$("#desligar").onclick = async () => {
  const itens = itensEmAndamento();
  if (!(await confirmar(itens.length
    ? { titulo: "Desligar com vídeo em andamento?", texto: "Desligar o servidor para tudo isto agora:", itens,
        nota: "O que já foi feito fica em cache e é reaproveitado.", sim: "Desligar", nao: "Continuar", perigo: true }
    : { titulo: "Desligar o servidor?", texto: "Para abrir de novo, use o Clipador.exe ou clipador-ui.", sim: "Desligar" }))) return;
  S.desligado = true;
  try { await api("/api/desligar", { body: {} }); } catch (e) { /* ja caiu */ }
  if (fonteEventos) fonteEventos.close();
  document.body.innerHTML = `<main class="tela" style="justify-content:center;align-items:center;text-align:center;width:100%">
    <h1 class="titulo-tela">Servidor desligado</h1><div class="fraco">Para abrir de novo, rode <span class="mono">clipador-ui</span>. Pode fechar esta janela.</div></main>`;
};
// Fechar a janela pelo X (pywebview): o Python cancela o fechamento e chama isto. Confirmando, ele
// desliga o servidor e fecha a janela (window.pywebview.api.fechar). Devolve true na hora, sem esperar.
window.clipadorPedirFechar = () => {
  const fechar = () => window.pywebview.api.fechar();
  if (S.desligado) { fechar(); return true; }
  if (document.querySelector(".dialogo-fundo.fechar")) return true;
  const itens = itensEmAndamento();
  confirmar(itens.length
    ? { titulo: "Fechar o Clipador?", texto: "Ainda tem coisa em andamento. Fechar desliga o servidor e para tudo isto:", itens,
        nota: "O que já foi baixado e transcrito fica em cache e é reaproveitado.", sim: "Fechar e parar", nao: "Continuar", perigo: true, classe: "fechar" }
    : { titulo: "Fechar o Clipador?", texto: "O servidor também é desligado.", sim: "Fechar", nao: "Cancelar", classe: "fechar" })
    .then((ok) => {
      if (!ok) return;
      document.body.innerHTML = `<main class="tela" style="justify-content:center;align-items:center;width:100%"><div class="fraco">Desligando…</div></main>`;
      fechar();
    });
  return true;
};
window.addEventListener("hashchange", rotear);
window.addEventListener("resize", () => { if (S.rota === "nova") desenharSelecao(); });
atualizarLateral();
conectarEventos();
api("/api/config").then((c) => { S.config0 = c; atualizarStatusClaude(true); }).catch(() => {});
rotear();
