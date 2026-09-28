"""Painel Equidade Salarial — remuneração x diversidade (Pacaembu Construtora).

Substitui o dashboard "Remuneração & Equidade Salarial" do Databricks, refeito do zero a partir do
objetivo: cruzar os dados demográficos com os salários (setores desbalanceados ou concentrados,
diferença salarial por sexo, raça/cor e tempo de casa) e calcular os indicadores reportados para
RI e Sustentabilidade. Fonte: uma view própria no Neon, com um usuário de banco só de leitura.
Cálculos em metricas.py. Padrão visual e de barra lateral: skill padrao-painel-streamlit.

    streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
import streamlit as st

import auth
import metricas as m
import painel_padrao as pp

ASSETS = Path(__file__).resolve().parent / "assets"
AZUL, AMARELO, VERMELHO, VERDE = "#064D66", "#FAB900", "#F02727", "#22C55E"
CINZA, CINZA_ESCURO, BORDA = "#6B7280", "#1F2937", "#CBD8DE"
CORES_SEXO = {"Masculino": AZUL, "Feminino": AMARELO, m.NAO_INFORMADO: CINZA}
CORES_RACA = {"Branca": "#A8C5D0", "Parda": "#4A8FA8", "Preta": AZUL, "Amarela": AMARELO, "Não Informada": VERMELHO}
SEM_DADOS = "Sem pessoas no filtro selecionado."
EST_TXT = {"Média": "médio", "Mediana": "mediano"}
SEM_COMPARACAO = "O filtro não tem homens e mulheres ao mesmo tempo para comparar."
VISOES = ["Visão geral e RI", "Gênero", "Raça/cor", "Tempo de casa", "Setores"]
EIXO_REAIS = "'R$ ' + replace(format(datum.value, ',.0f'), ',', '.')"

st.set_page_config(page_title="Equidade Salarial · Pacaembu Construtora", page_icon=str(ASSETS / "icone-equidade.png"), layout="wide")

st.html(f"""<style>
.kpi {{ background:#fff; border:1px solid {BORDA}; border-radius:10px; overflow:hidden; height:100%; }}
.kpi-topo {{ background:{AZUL}; color:#fff; font-weight:700; font-size:.74rem; letter-spacing:.04em; padding:.45rem .85rem; }}
.kpi-valor {{ color:{CINZA_ESCURO}; font-size:1.75rem; font-weight:700; text-align:center; padding:.65rem 0 .1rem; }}
.kpi-delta {{ text-align:center; font-size:.78rem; font-weight:600; min-height:1.2rem; padding:0 .5rem .55rem; color:{CINZA}; }}
.kpi-base {{ height:7px; background:{AMARELO}; }}
.secao {{ color:{AZUL}; font-weight:700; font-size:1.05rem; border-bottom:3px solid {AMARELO};
          display:inline-block; padding-bottom:.15rem; margin:.6rem 0 .2rem; }}
.titulo-graf {{ color:{CINZA_ESCURO}; font-weight:600; font-size:.92rem; margin-bottom:-.4rem; }}
.nota {{ color:{CINZA}; font-size:.8rem; line-height:1.35; }}
</style>""")

# login antes de qualquer dado (mesma tabela acesso.app_users dos outros painéis) + matriz de acessos
auth.exigir_login()
auth.exigir_acesso_ao_painel("equidade")


# ----------------------------------------------------------------------------- dados e formatos

@st.cache_data(ttl=600, show_spinner="Carregando dados…")
def carregar() -> tuple[pd.DataFrame, datetime | None]:
    with psycopg2.connect(st.secrets["neon"]["database_url"], connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM core.v_equidade_base")
        base = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        cur.execute("SELECT max(concluido_em) FROM ops.v_ultima_carga WHERE schema_nome = 'core' AND tabela = 'fato_funcionario'")
        carga = cur.fetchone()[0]
    return m.preparar(base), carga


def _vazio(v) -> bool:
    return v is None or pd.isna(v)


def _int(v) -> str:
    return "—" if _vazio(v) else f"{int(v):,}".replace(",", ".")


def _reais(v, casas=0) -> str:
    return "—" if _vazio(v) else "R$ " + f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _reais_curto(v) -> str:
    if _vazio(v):
        return ""
    return f"R$ {v / 1000:.1f} mil".replace(".", ",") if v >= 1000 else _reais(v)


def _pct(v, casas=1) -> str:
    return "—" if _vazio(v) else f"{v * 100:.{casas}f}%".replace(".", ",")


def _vezes(v) -> str:
    return "—" if _vazio(v) else f"{v:.1f}x".replace(".", ",")


def _gap_txt(v) -> str:
    return "sem comparação" if _vazio(v) else f"gap {_pct(v)}"


def kpi(rotulo: str, valor: str, nota: str = "", cor_nota: str = CINZA) -> None:
    st.html(f"""<div class="kpi"><div class="kpi-topo">{rotulo}</div><div class="kpi-valor">{valor}</div>
    <div class="kpi-delta" style="color:{cor_nota}">{nota}</div><div class="kpi-base"></div></div>""")


def _cor_gap(v) -> str:
    """Vermelho quando as mulheres ganham 5% ou mais a menos; azul quando ganham 5% ou mais a mais."""
    return CINZA if _vazio(v) or abs(v) < .05 else (VERMELHO if v > 0 else AZUL)


def secao(titulo: str) -> None:
    st.html(f'<div class="secao">{titulo}</div>')


def _cor_entre(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def _estilo_gap(v) -> str:
    """Escala divergente: vermelho = mulheres ganham menos; azul = ganham mais (satura em 30%)."""
    if _vazio(v):
        return ""
    return f"background-color:{_cor_entre('#FFFFFF', '#F7A8A8' if v > 0 else '#A8C5D0', abs(v) / .30)}"


# ----------------------------------------------------------------------------- gráficos

def _cores_sexo(sexos) -> dict:
    dominio = [s for s in ("Masculino", "Feminino") if s in set(sexos)]
    return {"domain": dominio, "range": [CORES_SEXO[s] for s in dominio]}


def barras_hm_horizontais(t: pd.DataFrame, dim: str, est: str) -> dict:
    """Homens x mulheres por categoria (barras lado a lado), gap no rótulo da categoria."""
    campo = "media" if est == "Média" else "mediana"
    linhas = []
    for _, r in t.iterrows():
        rotulo = f"{r[dim]}|{_gap_txt(r[f'gap_{campo}'])} · {_int(r['pessoas'])} pessoas"
        for sexo, sufixo in (("Masculino", "homens"), ("Feminino", "mulheres")):
            v = r[f"{campo}_{sufixo}"]
            if not _vazio(v):
                linhas.append({"categoria": rotulo, "sexo": sexo, "valor": float(v), "txt": _reais_curto(v), "n": int(r[sufixo])})
    ordem = list(dict.fromkeys(x["categoria"] for x in linhas))
    y = {"field": "categoria", "type": "nominal", "sort": ordem,
         "axis": {"labelExpr": "split(datum.label, '|')", "labelLimit": 260, "labelPadding": 6}}
    x = {"field": "valor", "type": "quantitative", "axis": {"labelExpr": EIXO_REAIS, "grid": True, "tickCount": 5}}
    return {"data": {"values": linhas}, "layer": [
        {"mark": {"type": "bar", "cornerRadiusEnd": 3, "height": {"band": .42}},
         "encoding": {"y": y, "yOffset": {"field": "sexo", "sort": ["Masculino", "Feminino"]}, "x": x,
                      "color": {"field": "sexo", "scale": _cores_sexo(["Masculino", "Feminino"]), "legend": {"orient": "top"}},
                      "tooltip": [{"field": "categoria", "title": "Categoria"}, {"field": "sexo", "title": "Sexo"},
                                  {"field": "txt", "title": f"Salário {EST_TXT[est]}"}, {"field": "n", "title": "Pessoas"}]}},
        {"mark": {"type": "text", "align": "left", "dx": 4, "fontSize": 10, "color": CINZA_ESCURO},
         "encoding": {"y": y, "yOffset": {"field": "sexo", "sort": ["Masculino", "Feminino"]}, "x": x, "text": {"field": "txt"}}},
    ], "padding": {"right": 40}}


def barras_hm_verticais(t: pd.DataFrame, dim: str, est: str) -> dict:
    campo = "media" if est == "Média" else "mediana"
    linhas = []
    for _, r in t.iterrows():
        rotulo = f"{r[dim]}|{_gap_txt(r[f'gap_{campo}'])}|{_int(r['pessoas'])} pessoas"
        for sexo, sufixo in (("Masculino", "homens"), ("Feminino", "mulheres")):
            v = r[f"{campo}_{sufixo}"]
            if not _vazio(v):
                linhas.append({"categoria": rotulo, "sexo": sexo, "valor": float(v), "txt": _reais_curto(v), "n": int(r[sufixo])})
    ordem = list(dict.fromkeys(x["categoria"] for x in linhas))
    x = {"field": "categoria", "type": "nominal", "sort": ordem,
         "axis": {"labelAngle": 0, "labelExpr": "split(datum.label, '|')", "labelLimit": 200, "labelPadding": 6}}
    y = {"field": "valor", "type": "quantitative", "axis": {"labelExpr": EIXO_REAIS, "grid": True, "tickCount": 5}}
    off = {"field": "sexo", "sort": ["Masculino", "Feminino"]}
    return {"data": {"values": linhas}, "layer": [
        {"mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
         "encoding": {"x": x, "xOffset": off, "y": y,
                      "color": {"field": "sexo", "scale": _cores_sexo(["Masculino", "Feminino"]), "legend": {"orient": "top"}},
                      "tooltip": [{"field": "sexo", "title": "Sexo"}, {"field": "txt", "title": f"Salário {EST_TXT[est]}"},
                                  {"field": "n", "title": "Pessoas"}]}},
        {"mark": {"type": "text", "dy": -7, "fontSize": 10, "color": CINZA_ESCURO},
         "encoding": {"x": x, "xOffset": off, "y": y, "text": {"field": "txt"}}},
    ], "padding": {"top": 14}}


def quartis(t: pd.DataFrame) -> dict:
    d = t[t["sexo"].isin(["Masculino", "Feminino"])].assign(txt=lambda x: [_pct(p, 0) for p in x["pct"]],
                                                                cor_txt=lambda x: ["#FFFFFF" if s_ == "Masculino" else AZUL for s_ in x["sexo"]])
    y = {"field": "quartil", "type": "nominal", "sort": list(dict.fromkeys(t["quartil"].astype(str))), "axis": {"labelLimit": 180}}
    ordem = {"field": "sexo", "sort": "descending"}
    return {"data": {"values": d.assign(quartil=d["quartil"].astype(str)).to_dict("records")}, "layer": [
        {"mark": {"type": "bar"},
         "encoding": {"y": y, "x": {"field": "pct", "type": "quantitative", "stack": "normalize", "axis": {"format": ".0%", "grid": True}},
                      "color": {"field": "sexo", "scale": _cores_sexo(["Masculino", "Feminino"]), "legend": {"orient": "top"}},
                      "order": ordem,
                      "tooltip": [{"field": "quartil", "title": "Quartil"}, {"field": "sexo", "title": "Sexo"},
                                  {"field": "pessoas", "title": "Pessoas"}, {"field": "pct", "title": "%", "format": ".1%"}]}},
        {"mark": {"type": "text", "fontSize": 11, "fontWeight": 700},
         "encoding": {"y": y, "x": {"field": "pct", "type": "quantitative", "stack": "normalize", "bandPosition": .5},
                      "order": ordem, "text": {"field": "txt"},
                      "color": {"field": "cor_txt", "type": "nominal", "scale": None}}},
    ]}


def barras_raca(t: pd.DataFrame) -> dict:
    linhas = []
    for _, r in t.iterrows():
        dif = "referência" if r["raca_cor"] == "Branca" else ("" if _vazio(r["dif_branca"]) else f"{'+' if r['dif_branca'] > 0 else ''}{_pct(r['dif_branca'])}")
        rotulo = f"{r['raca_cor']}|{dif}|{_int(r['pessoas'])} pessoas"
        for est in ("Média", "Mediana"):
            v = r["media" if est == "Média" else "mediana"]
            linhas.append({"categoria": rotulo, "estatistica": est, "valor": float(v), "txt": _reais_curto(v)})
    x = {"field": "categoria", "type": "nominal", "sort": list(dict.fromkeys(x["categoria"] for x in linhas)),
         "axis": {"labelAngle": 0, "labelExpr": "split(datum.label, '|')", "labelPadding": 6, "labelOverlap": False, "labelLimit": 140}}
    y = {"field": "valor", "type": "quantitative", "axis": {"labelExpr": EIXO_REAIS, "grid": True, "tickCount": 5}}
    off = {"field": "estatistica", "sort": ["Média", "Mediana"]}
    return {"data": {"values": linhas}, "layer": [
        {"mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
         "encoding": {"x": x, "xOffset": off, "y": y,
                      "color": {"field": "estatistica", "scale": {"domain": ["Média", "Mediana"], "range": [AZUL, AMARELO]}, "legend": {"orient": "top"}},
                      "tooltip": [{"field": "estatistica", "title": "Estatística"}, {"field": "txt", "title": "Salário"}]}},
        {"mark": {"type": "text", "dy": -7, "fontSize": 10, "color": CINZA_ESCURO},
         "encoding": {"x": x, "xOffset": off, "y": y, "text": {"field": "txt"}}},
    ], "padding": {"top": 14}}


def composicao_por_nivel(q: pd.DataFrame, coluna: str, cores: dict) -> dict:
    """Participação (100%) de cada grupo dentro de cada nível — mostra onde cada grupo se concentra."""
    t = q.groupby(["nivel", coluna]).size().rename("pessoas").reset_index()
    t["pct"] = t["pessoas"] / t.groupby("nivel")["pessoas"].transform("sum")
    tot = q.groupby("nivel").size()
    t["nivel_txt"] = [f"{n} ({_int(tot[n])})" for n in t["nivel"]]
    ordem_n = [f"{n} ({_int(tot[n])})" for n in m.ORDEM_NIVEL if n in tot.index] + \
              [f"{n} ({_int(tot[n])})" for n in sorted(set(tot.index) - set(m.ORDEM_NIVEL))]
    dominio = [c for c in cores if c in set(t[coluna])]
    t["ordem"] = t[coluna].map({c: i for i, c in enumerate(dominio)})
    t["txt"] = [_pct(p, 0) if p >= .08 else "" for p in t["pct"]]
    t["cor_txt"] = ["#FFFFFF" if cores[c] in (AZUL, "#4A8FA8", VERMELHO) else CINZA_ESCURO for c in t[coluna]]
    y = {"field": "nivel_txt", "type": "nominal", "sort": ordem_n, "axis": {"labelLimit": 240, "labelOverlap": False}}
    xq = {"field": "pct", "type": "quantitative", "stack": "normalize"}
    return {"data": {"values": t.to_dict("records")}, "layer": [
        {"mark": {"type": "bar"},
         "encoding": {"y": y, "x": {**xq, "axis": {"format": ".0%", "grid": True}}, "order": {"field": "ordem"},
                      "color": {"field": coluna, "scale": {"domain": dominio, "range": [cores[c] for c in dominio]}, "legend": {"orient": "top"}},
                      "tooltip": [{"field": "nivel", "title": "Nível"}, {"field": coluna, "title": "Grupo"},
                                  {"field": "pessoas", "title": "Pessoas"}, {"field": "pct", "title": "%", "format": ".1%"}]}},
        {"mark": {"type": "text", "fontSize": 10, "fontWeight": 600},
         "encoding": {"y": y, "x": {**xq, "bandPosition": .5}, "order": {"field": "ordem"}, "text": {"field": "txt"},
                      "color": {"field": "cor_txt", "type": "nominal", "scale": None}}},
    ]}


def dispersao_setores(s: pd.DataFrame, pct_ref: float) -> dict:
    """% de mulheres (x) contra o gap de gênero (y); bolha = pessoas. Linhas: média da empresa e gap zero."""
    d = s.dropna(subset=["gap_media"]).assign(
        pm_txt=lambda x: [_pct(v) for v in x["pct_mulheres"]], gap_txt=lambda x: [_pct(v) for v in x["gap_media"]],
        sal_txt=lambda x: [_reais(v) for v in x["salario_medio"]])
    return {"layer": [
        {"data": {"values": [{"x": pct_ref}]}, "mark": {"type": "rule", "strokeDash": [4, 4], "color": CINZA},
         "encoding": {"x": {"field": "x", "type": "quantitative"}}},
        {"data": {"values": [{"y": 0}]}, "mark": {"type": "rule", "color": BORDA}, "encoding": {"y": {"field": "y", "type": "quantitative"}}},
        {"data": {"values": d.to_dict("records")}, "mark": {"type": "circle", "opacity": .75, "stroke": "#fff", "strokeWidth": 1},
         "encoding": {"x": {"field": "pct_mulheres", "type": "quantitative", "scale": {"domain": [0, 1]},
                            "axis": {"format": ".0%", "grid": True, "title": "% de mulheres no setor"}},
                      "y": {"field": "gap_media", "type": "quantitative", "scale": {"domain": [-1, 1], "clamp": True},
                            "axis": {"format": ".0%", "grid": True, "title": "Gap salarial (média)"}},
                      "size": {"field": "pessoas", "type": "quantitative", "scale": {"range": [40, 900]}, "legend": None},
                      "color": {"condition": {"test": "datum.gap_media >= 0.05", "value": VERMELHO},
                                "value": AZUL},
                      "tooltip": [{"field": "setor", "title": "Setor"}, {"field": "diretoria", "title": "Diretoria"},
                                  {"field": "pessoas", "title": "Pessoas"}, {"field": "pm_txt", "title": "% mulheres"},
                                  {"field": "gap_txt", "title": "Gap (média)"}, {"field": "sal_txt", "title": "Salário médio"}]}},
    ]}


def dispersao_concentracao(s: pd.DataFrame) -> dict:
    """Fatia do headcount (x) contra fatia da massa salarial (y). Acima da diagonal = concentra salário."""
    teto = float(max(s["fatia_headcount"].max(), s["fatia_massa"].max())) * 1.05 if len(s) else 1
    d = s.assign(hc_txt=lambda x: [_pct(v) for v in x["fatia_headcount"]], ms_txt=lambda x: [_pct(v) for v in x["fatia_massa"]],
                 conc_txt=lambda x: [_vezes(v) for v in x["concentracao"]])
    eixo = lambda t: {"format": ".0%", "grid": True, "title": t}  # noqa: E731
    return {"layer": [
        {"data": {"values": [{"a": 0}, {"a": teto}]}, "mark": {"type": "line", "strokeDash": [4, 4], "color": CINZA},
         "encoding": {"x": {"field": "a", "type": "quantitative"}, "y": {"field": "a", "type": "quantitative"}}},
        {"data": {"values": d.to_dict("records")}, "mark": {"type": "circle", "size": 120, "opacity": .8, "stroke": "#fff"},
         "encoding": {"x": {"field": "fatia_headcount", "type": "quantitative", "scale": {"domain": [0, teto]}, "axis": eixo("Fatia do headcount")},
                      "y": {"field": "fatia_massa", "type": "quantitative", "scale": {"domain": [0, teto]}, "axis": eixo("Fatia da massa salarial")},
                      "color": {"condition": {"test": "datum.concentracao >= 1.5", "value": VERMELHO}, "value": AZUL},
                      "tooltip": [{"field": "setor", "title": "Setor"}, {"field": "pessoas", "title": "Pessoas"},
                                  {"field": "hc_txt", "title": "Fatia do headcount"}, {"field": "ms_txt", "title": "Fatia da massa"},
                                  {"field": "conc_txt", "title": "Concentração"}]}},
    ]}


# ----------------------------------------------------------------------------- página

try:
    df, carga = carregar()
except Exception as exc:  # noqa: BLE001
    st.error("Não consegui ler a base do Neon. Confira o bloco [neon] em .streamlit/secrets.toml.", icon=":material/error:")
    st.caption(type(exc).__name__)
    st.stop()

ref = m.data_referencia(df)
pp.logo(ASSETS / "icone-equidade.png", "Equidade Salarial")

opcoes = lambda c: sorted(df[c].dropna().unique())  # noqa: E731
with pp.barra_lateral(fonte="Neon + Databricks", atualizado_em=carga):
    visao = st.radio("Visão", VISOES, label_visibility="collapsed")
    est = st.segmented_control("Estatística", ["Média", "Mediana"], default="Média",
                               help="Vale para os gráficos de gênero, raça/cor e tempo de casa.") or "Média"
    st.markdown("**Filtros**")
    sel = {
        "diretoria": st.multiselect("Diretoria", opcoes("diretoria"), placeholder="Todas"),
        "area": st.multiselect("Área", opcoes("area"), placeholder="Todas"),
        "nome_centro_custo": st.multiselect("Centro de custo", opcoes("nome_centro_custo"), placeholder="Todos"),
        "familia_cargo": st.multiselect("Família de cargo", opcoes("familia_cargo"), placeholder="Todas"),
        "nivel": st.multiselect("Nível", [n for n in m.ORDEM_NIVEL if n in set(df["nivel"])] +
                                sorted(set(df["nivel"]) - set(m.ORDEM_NIVEL)), placeholder="Todos"),
        "vinculo": st.multiselect("Vínculo", opcoes("vinculo"), placeholder="Todos",
                                  help="Classificação do colaborador (CLT por experiência, estagiário, prazo determinado, diretor, PJ…)."),
        "sexo": st.multiselect("Sexo", opcoes("sexo"), placeholder="Todos"),
        "raca_cor": st.multiselect("Raça/cor", [r for r in m.ORDEM_RACA if r in set(df["raca_cor"])], placeholder="Todas"),
    }

st.title(visao if visao != "Visão geral e RI" else "Equidade Salarial", anchor=False)
st.caption(f"Quadro ativo em {ref:%d/%m/%Y} · salário-base mensal · gap = (homens − mulheres) ÷ homens; positivo = mulheres ganham menos")

base = df
for col, vals in sel.items():
    if vals:
        base = base[base[col].isin(vals)]
q = m.quadro_em(base, ref)

if q.empty:
    st.info(SEM_DADOS, icon=":material/info:")
    st.stop()

v = m.visao_geral(q)

# ============================================================================= visão geral e RI
if visao == "Visão geral e RI":
    c = st.columns(4)
    with c[0]: kpi("HEADCOUNT", _int(v["headcount"]), f"{_pct(v['pct_mulheres'])} mulheres · {_pct(v['pct_negras'])} pretas e pardas")
    with c[1]: kpi("MASSA SALARIAL MENSAL", _reais(v["massa"]), "Soma dos salários-base")
    with c[2]: kpi("SALÁRIO MÉDIO", _reais(v["media"]), "Média do quadro")
    with c[3]: kpi("SALÁRIO MEDIANO", _reais(v["mediana"]), "Metade ganha até este valor")

    secao("Indicadores para RI e Sustentabilidade")
    ajuste = m.gap_ajustado_por_cargo(q)
    c = st.columns(4)
    with c[0]: kpi("MAIOR REMUNERAÇÃO ÷ MÉDIA", _vezes(v["razao_media"]), "vs média das demais pessoas")
    with c[1]: kpi("MAIOR REMUNERAÇÃO ÷ MEDIANA", _vezes(v["razao_mediana"]), "vs mediana das demais (GRI 2-21)")
    with c[2]: kpi("GAP DE GÊNERO · MÉDIA", _pct(v["gap_media"]), f"pela mediana: {_pct(v['gap_mediana'])}", _cor_gap(v["gap_media"]))
    with c[3]: kpi("GAP NO MESMO CARGO", _pct(ajuste["gap_ajustado"]),
                   f"{_int(ajuste['cargos_comparaveis'])} cargos com homens e mulheres · {_int(ajuste['pessoas_comparaveis'])} pessoas",
                   _cor_gap(ajuste["gap_ajustado"]))
    c = st.columns(4)
    conc = m.concentracao_massa(q)
    with c[0]: kpi("MULHERES NA LIDERANÇA", _pct(v["pct_mulheres_lideranca"]), f"no quadro: {_pct(v['pct_mulheres'])}")
    with c[1]: kpi("PRETAS E PARDAS NA LIDERANÇA", _pct(v["pct_negras_lideranca"]), f"no quadro: {_pct(v['pct_negras'])}")
    with c[2]: kpi("MASSA COM OS 10% MAIS BEM PAGOS", _pct(conc["top10"]), f"com o 1% mais bem pago: {_pct(conc['top1'])}")
    with c[3]:
        r = m.por_raca(q)
        rp = r.loc[r["raca_cor"].isin(["Preta", "Parda"])]
        br = r.loc[r["raca_cor"] == "Branca", "media"]
        media_negras = q.loc[q["negra"], "salario"].mean()
        dif = (media_negras - float(br.iloc[0])) / float(br.iloc[0]) if len(br) and len(rp) else None
        kpi("PRETAS E PARDAS VS BRANCAS", _pct(dif), "diferença no salário médio", _cor_gap(-dif if dif is not None else None))

    g1, g2 = st.columns([6, 5])
    with g1:
        pp.grafico("Mulheres e homens em cada quartil salarial", quartis(m.quartis_por_sexo(q)), 250, SEM_DADOS)
        st.html('<div class="nota">Quartis: o quadro ordenado do menor para o maior salário e dividido em 4 partes iguais. '
                'Numa empresa equilibrada, a participação das mulheres é parecida nos 4.</div>')
    with g2:
        st.html('<div class="titulo-graf">Como calculamos</div>')
        st.html(f"""<div class="nota" style="margin-top:.9rem">
        <b>Maior remuneração ÷ média (ou mediana) das demais</b>: o maior salário-base do filtro dividido pela
        média (ou mediana) de todas as outras pessoas. O GRI 2-21 pede a razão pela mediana.<br><br>
        <b>Gap de gênero</b>: (salário dos homens − salário das mulheres) ÷ salário dos homens, pela média e pela
        mediana. <b>No mesmo cargo</b>: o gap calculado dentro de cada cargo que tem homens e mulheres, ponderado
        pelo número de pessoas — tira o efeito de homens e mulheres estarem em cargos diferentes.<br><br>
        <b>Liderança</b>: níveis de coordenação para cima (inclui diretoria e conselho).<br>
        <b>Base</b>: salário-base mensal do cadastro, sem variável e sem benefícios; todos os ativos em {ref:%d/%m/%Y}
        (use o filtro Vínculo para tirar estagiários, PJ ou conselho).</div>""")

    reporte = pd.DataFrame([
        ("Headcount", _int(v["headcount"])),
        ("Maior remuneração ÷ média das demais", _vezes(v["razao_media"])),
        ("Maior remuneração ÷ mediana das demais (GRI 2-21)", _vezes(v["razao_mediana"])),
        ("Gap de gênero pela média", _pct(v["gap_media"])),
        ("Gap de gênero pela mediana", _pct(v["gap_mediana"])),
        ("Gap de gênero no mesmo cargo", _pct(ajuste["gap_ajustado"])),
        ("% mulheres no quadro", _pct(v["pct_mulheres"])),
        ("% mulheres na liderança", _pct(v["pct_mulheres_lideranca"])),
        ("% pretas e pardas no quadro", _pct(v["pct_negras"])),
        ("% pretas e pardas na liderança", _pct(v["pct_negras_lideranca"])),
        ("Salário médio de pretas e pardas vs brancas", _pct(dif)),
    ], columns=["Indicador", "Valor"])
    with st.expander("Tabela para o reporte (RI e Sustentabilidade)", icon=":material/table_view:"):
        st.dataframe(reporte, hide_index=True, width="stretch")
        st.download_button("Baixar CSV", reporte.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           f"equidade_salarial_{ref:%Y%m%d}.csv", "text/csv", icon=":material/download:")

# ============================================================================= gênero
elif visao == "Gênero":
    ajuste = m.gap_ajustado_por_cargo(q)
    c = st.columns(4)
    with c[0]: kpi("GAP PELA MÉDIA", _pct(v["gap_media"]), "quadro todo", _cor_gap(v["gap_media"]))
    with c[1]: kpi("GAP PELA MEDIANA", _pct(v["gap_mediana"]), "quadro todo", _cor_gap(v["gap_mediana"]))
    with c[2]: kpi("GAP NO MESMO CARGO", _pct(ajuste["gap_ajustado"]), f"{_int(ajuste['cargos_comparaveis'])} cargos comparáveis",
                   _cor_gap(ajuste["gap_ajustado"]))
    with c[3]: kpi("MULHERES NA LIDERANÇA", _pct(v["pct_mulheres_lideranca"]), f"no quadro: {_pct(v['pct_mulheres'])}")
    st.html('<div class="nota">A diferença entre o gap do quadro todo e o gap no mesmo cargo mostra quanto vem de '
            'homens e mulheres ocuparem cargos diferentes (segregação) e quanto vem de salários diferentes para o mesmo cargo.</div>')

    niv = m.por_sexo(q, "nivel", m.ORDEM_NIVEL)
    g1, g2 = st.columns([7, 5])
    with g1:
        pp.grafico(f"Salário {EST_TXT[est]} por nível: homens x mulheres", barras_hm_horizontais(niv, "nivel", est),
                   max(260, 46 * len(niv)), SEM_DADOS)
    with g2:
        pp.grafico("Mulheres e homens em cada nível", composicao_por_nivel(q[q["sexo"].isin(["Masculino", "Feminino"])], "sexo",
                                                                          {"Masculino": AZUL, "Feminino": AMARELO}),
                   max(260, 46 * len(niv)), SEM_DADOS)

    secao("Mesmo cargo, homens x mulheres")
    cargos = m.por_sexo(q, "cargo")
    cargos = cargos[(cargos["homens"] > 0) & (cargos["mulheres"] > 0)].copy()
    if cargos.empty:
        st.info(SEM_COMPARACAO, icon=":material/info:")
    else:
        campo = "media" if est == "Média" else "mediana"
        cargos = cargos.assign(abs_gap=cargos[f"gap_{campo}"].abs()).sort_values(["abs_gap", "pessoas"], ascending=False)
        tab = cargos[["cargo", "homens", "mulheres", f"{campo}_homens", f"{campo}_mulheres", f"gap_{campo}"]]
        tab.columns = ["Cargo", "Homens", "Mulheres", f"{est} homens", f"{est} mulheres", "Gap"]
        st.dataframe(tab.style.format({f"{est} homens": _reais, f"{est} mulheres": _reais, "Gap": _pct})
                     .map(_estilo_gap, subset=["Gap"]), hide_index=True, width="stretch", height=420)
        st.caption(f"{_int(len(cargos))} cargos com homens e mulheres, ordenados pelo tamanho do gap. "
                   "Vermelho = mulheres ganham menos; azul = ganham mais. Cargos com 1 ou 2 pessoas de um dos sexos oscilam muito.")

# ============================================================================= raça/cor
elif visao == "Raça/cor":
    r = m.por_raca(q)
    br = r.loc[r["raca_cor"] == "Branca", "media"]
    media_negras = q.loc[q["negra"], "salario"].mean()
    dif = (media_negras - float(br.iloc[0])) / float(br.iloc[0]) if len(br) and q["negra"].any() else None
    c = st.columns(4)
    with c[0]: kpi("PRETAS E PARDAS NO QUADRO", _pct(v["pct_negras"]), f"{_int(q['negra'].sum())} pessoas")
    with c[1]: kpi("PRETAS E PARDAS NA LIDERANÇA", _pct(v["pct_negras_lideranca"]), "coordenação para cima")
    with c[2]: kpi("SALÁRIO MÉDIO VS BRANCAS", _pct(dif), "pretas e pardas", _cor_gap(-dif if dif is not None else None))
    with c[3]:
        nao = r.loc[r["raca_cor"] == "Não Informada", "pessoas"]
        kpi("RAÇA/COR NÃO INFORMADA", _int(nao.iloc[0] if len(nao) else 0), "pessoas sem declaração no cadastro")

    g1, g2 = st.columns([6, 6])
    with g1:
        pp.grafico("Salário médio e mediano por raça/cor (e diferença da média para Branca)", barras_raca(r), max(340, 30 * q["nivel"].nunique()), SEM_DADOS)
    with g2:
        pp.grafico("Raça/cor em cada nível", composicao_por_nivel(q, "raca_cor", CORES_RACA), max(340, 30 * q["nivel"].nunique()), SEM_DADOS)

    secao(f"Salário {EST_TXT[est]} por nível e raça/cor")
    campo = "mean" if est == "Média" else "median"
    piv = q.pivot_table(index="nivel", columns="raca_cor", values="salario", aggfunc=campo)
    n = q.pivot_table(index="nivel", columns="raca_cor", values="salario", aggfunc="size")
    piv = piv.reindex([x for x in m.ORDEM_NIVEL if x in piv.index] + sorted(set(piv.index) - set(m.ORDEM_NIVEL)))
    piv = piv[[c for c in m.ORDEM_RACA if c in piv.columns]]
    n = n.reindex(index=piv.index, columns=piv.columns)
    exib = piv.copy().astype(object)
    for i in piv.index:
        for c_ in piv.columns:
            exib.loc[i, c_] = "" if pd.isna(piv.loc[i, c_]) else f"{_reais(piv.loc[i, c_])} ({_int(n.loc[i, c_])})"

    cores = pd.DataFrame("", index=piv.index, columns=piv.columns)
    if "Branca" in piv.columns:
        for c_ in piv.columns.drop("Branca"):
            cores[c_] = [_estilo_gap((b - x) / b) if not (_vazio(b) or _vazio(x)) else "" for b, x in zip(piv["Branca"], piv[c_])]
    st.dataframe(exib.rename_axis("Nível").style.apply(lambda _: cores, axis=None), width="stretch", height=38 + 35 * len(exib))
    st.caption("Entre parênteses, o número de pessoas. Cor = diferença para o grupo Branca no mesmo nível "
               "(vermelho = ganha menos; azul = ganha mais).")

# ============================================================================= tempo de casa
elif visao == "Tempo de casa":
    tc = m.por_tempo_casa(q)
    c = st.columns(4)
    medias = q.groupby("faixa_tempo_casa")["salario"].agg("mean" if est == "Média" else "median")
    with c[0]: kpi("TEMPO DE CASA MÉDIO", f"{q['tempo_casa_dias'].mean() / 365.25:.1f} anos".replace(".", ","), "quadro filtrado")
    with c[1]: kpi("ATÉ 1 ANO DE CASA", _reais(medias.get("Até 1 ano")), f"salário {EST_TXT[est]}")
    with c[2]: kpi("3 A 5 ANOS", _reais(medias.get("3 a 5 anos")), f"salário {EST_TXT[est]}")
    with c[3]: kpi("+ 10 ANOS", _reais(medias.get("+ 10 anos")), f"salário {EST_TXT[est]}")
    pp.grafico(f"Salário {EST_TXT[est]} por tempo de casa: homens x mulheres", barras_hm_verticais(tc, "faixa_tempo_casa", est), 380, SEM_DADOS)
    st.html('<div class="nota">Tempo de casa na data do quadro. O salário por faixa mistura cargos diferentes: '
            'combine com o filtro Nível ou Família de cargo para comparar pessoas parecidas.</div>')

# ============================================================================= setores
else:
    with st.container(horizontal=True, vertical_alignment="center"):
        secao("Setores mais desbalanceados ou concentrados")
        nivel_setor = st.segmented_control("Agrupar por", ["Área", "Diretoria"], default="Área", label_visibility="collapsed") or "Área"
    s = m.setores(q, "area" if nivel_setor == "Área" else "diretoria")
    g1, g2 = st.columns(2)
    with g1:
        if s["gap_media"].notna().any():
            pp.grafico("% de mulheres x gap salarial de gênero", dispersao_setores(s, v["pct_mulheres"]), 360, SEM_COMPARACAO)
        else:
            st.html('<div class="titulo-graf">% de mulheres x gap salarial de gênero</div>')
            st.info(SEM_COMPARACAO, icon=":material/info:")
        st.html('<div class="nota">Cada bolha é um setor (tamanho = pessoas). Linha tracejada = % de mulheres da empresa. '
                'Vermelho = mulheres ganham 5% ou mais a menos no setor. Setores só com um sexo ficam fora; gaps além de ±100% (setores muito pequenos) ficam na borda.</div>')
    with g2:
        pp.grafico("Fatia do headcount x fatia da massa salarial", dispersao_concentracao(s), 360, SEM_DADOS)
        st.html('<div class="nota">Acima da diagonal, o setor fica com mais salário do que gente. '
                'Vermelho = concentração de 1,5x ou mais (fatia da massa ÷ fatia do headcount).</div>')

    tab = s[["diretoria", "setor", "pessoas", "pct_mulheres", "dist_mulheres_pp", "pct_negras", "dist_negras_pp",
             "salario_medio", "gap_media", "fatia_massa", "concentracao"]].copy()
    if nivel_setor == "Diretoria":
        tab = tab.drop(columns="setor")
    tab = tab.rename(columns={"diretoria": "Diretoria", "setor": "Área", "pessoas": "Pessoas", "pct_mulheres": "% mulheres",
                              "dist_mulheres_pp": "Δ mulheres (pp)", "pct_negras": "% pretas e pardas",
                              "dist_negras_pp": "Δ pretas e pardas (pp)", "salario_medio": "Salário médio", "gap_media": "Gap (média)",
                              "fatia_massa": "Fatia da massa", "concentracao": "Concentração"})
    pp_fmt = lambda x: "—" if _vazio(x) else f"{'+' if x > 0 else ''}{x:.1f}".replace(".", ",")  # noqa: E731

    def _estilo_pp(x):
        return "" if _vazio(x) else f"background-color:{_cor_entre('#FFFFFF', '#FDE7A3', abs(x) / 30)}"

    def _estilo_conc(x):
        return "" if _vazio(x) or x < 1 else f"background-color:{_cor_entre('#FFFFFF', '#F7A8A8', (x - 1) / 2)}"

    st.dataframe(tab.style.format({"% mulheres": _pct, "% pretas e pardas": _pct, "Δ mulheres (pp)": pp_fmt, "Δ pretas e pardas (pp)": pp_fmt,
                                   "Salário médio": _reais, "Gap (média)": _pct, "Fatia da massa": _pct, "Concentração": _vezes})
                 .map(_estilo_gap, subset=["Gap (média)"]).map(_estilo_pp, subset=["Δ mulheres (pp)", "Δ pretas e pardas (pp)"])
                 .map(_estilo_conc, subset=["Concentração"]),
                 hide_index=True, width="stretch", height=460)
    st.caption(f"Δ = distância, em pontos percentuais, para a empresa ({_pct(v['pct_mulheres'])} mulheres, "
               f"{_pct(v['pct_negras'])} pretas e pardas) — amarelo mais forte = mais desbalanceado. "
               "Concentração = fatia da massa ÷ fatia do headcount. Clique no título da coluna para ordenar.")
