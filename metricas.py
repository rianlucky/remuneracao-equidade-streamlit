"""Cálculo dos indicadores do painel Equidade Salarial — sem Streamlit, para testar e validar.

Entrada: core.v_equidade_base (Neon), uma linha por atribuição, pessoa pseudonimizada.
Objetivo (briefing de 28/09/2026): cruzar a demografia com o salário — setores mais
desbalanceados ou concentrados, diferença salarial por sexo (no mesmo cargo), por raça/cor e por
tempo de casa — e os indicadores reportados para RI e Sustentabilidade.

Convenções:
  - Quadro numa data: admitido até a data e sem desligamento (ou desligado depois), uma linha por
    pessoa (a atribuição mais recente). Mesma regra dos painéis Turnover e Dados Demográficos.
  - Salário = salário-base mensal da atribuição (a base não tem variável nem benefícios).
  - População: todos os ativos (decisão de 28/09/2026); o filtro de vínculo permite tirar estagiários,
    PJ etc. na tela.
  - Gap = (salário dos homens − salário das mulheres) ÷ salário dos homens. Positivo = mulheres
    ganham menos. Calculado pela média e pela mediana.
  - Razão para RI = maior remuneração ÷ remuneração das demais pessoas, pela média (pedido de
    RI e Sustentabilidade) e pela mediana (padrão GRI 2-21).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

NAO_INFORMADO = "Não informado"
FAIXAS_TEMPO_CASA = [
    (365, "Até 1 ano"), (730, "1 a 2 anos"), (1095, "2 a 3 anos"), (1826, "3 a 5 anos"), (3652, "5 a 10 anos"),
]
ORDEM_TEMPO_CASA = ["Até 1 ano", "1 a 2 anos", "2 a 3 anos", "3 a 5 anos", "5 a 10 anos", "+ 10 anos"]
ORDEM_RACA = ["Branca", "Parda", "Preta", "Amarela", "Não Informada"]
ORDEM_NIVEL = ["Operacional", "Pilotos", "Staff", "Supervisor/Advogado/Engenheiro", "Coordenador/Especialista",
               "Coordenador de Obras", "Gerente de Vendas", "Gerente", "Gerente Executivo de Obras", "Gerente Executivo",
               "Gerente Executivo Estadual de Obras", "Diretor de Obras", "Diretor", "Conselheiro"]
# Liderança = de coordenação para cima, sem o Conselho (decisão de 30/09/2026: o conselho não faz a
# gestão do dia a dia; a diretoria entra)
NIVEIS_LIDERANCA = {"Coordenador/Especialista", "Coordenador de Obras", "Gerente de Vendas", "Gerente",
                    "Gerente Executivo de Obras", "Gerente Executivo", "Gerente Executivo Estadual de Obras",
                    "Diretor de Obras", "Diretor"}
# População padrão dos indicadores de remuneração = empregados (decisão de 30/09/2026, padrão GRI 2-21):
# sem conselheiros, estagiários e PJ. Diretores estatutários entram.
VINCULOS_FORA_EMPREGADOS = {"Estagiário", "PJ"}


def empregados(q: pd.DataFrame) -> pd.DataFrame:
    return q[(q["nivel"] != "Conselheiro") & ~q["vinculo"].isin(VINCULOS_FORA_EMPREGADOS)]
NEGRAS = {"Preta", "Parda"}


def faixa_tempo_casa(dias) -> str | None:
    if dias is None or pd.isna(dias):
        return None
    for limite, nome in FAIXAS_TEMPO_CASA:
        if dias < limite:
            return nome
    return "+ 10 anos"


def preparar(base: pd.DataFrame) -> pd.DataFrame:
    df = base.copy()
    for c in ("data_referencia", "data_admissao", "data_desligamento"):
        df[c] = pd.to_datetime(df[c]).dt.date
    for c in ("salario", "idade_ref"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("diretoria", "area", "nome_centro_custo", "familia_cargo", "cargo", "nivel", "vinculo", "sexo", "geracao"):
        df[c] = df[c].fillna(NAO_INFORMADO)
    df["raca_cor"] = df["raca_cor"].fillna("Não Informada")
    return df


def data_referencia(df: pd.DataFrame) -> date:
    return max(df["data_referencia"].dropna())


def quadro_em(df: pd.DataFrame, d: date) -> pd.DataFrame:
    """Uma linha por pessoa ativa em `d` (atribuição mais recente), com tempo de casa na data."""
    ativo = (df["data_admissao"] <= d) & (df["data_desligamento"].isna() | (df["data_desligamento"] > d))
    q = df[ativo].sort_values(["pessoa", "data_admissao"], ascending=[True, False]).drop_duplicates("pessoa").copy()
    q["tempo_casa_dias"] = [(d - x).days for x in q["data_admissao"]]
    q["faixa_tempo_casa"] = q["tempo_casa_dias"].map(faixa_tempo_casa)
    q["lideranca"] = q["nivel"].isin(NIVEIS_LIDERANCA)
    q["negra"] = q["raca_cor"].isin(NEGRAS)
    return q


# ----------------------------------------------------------------------------- blocos

def gap(h: pd.Series, m: pd.Series, estatistica: str = "media") -> float | None:
    """(homens − mulheres) ÷ homens. None se faltar um dos dois grupos."""
    h, m = h.dropna(), m.dropna()
    if h.empty or m.empty:
        return None
    vh, vm = (h.mean(), m.mean()) if estatistica == "media" else (h.median(), m.median())
    return float((vh - vm) / vh) if vh else None


def _gaps(q: pd.DataFrame) -> tuple[float | None, float | None]:
    h, m = q.loc[q["sexo"] == "Masculino", "salario"], q.loc[q["sexo"] == "Feminino", "salario"]
    return gap(h, m, "media"), gap(h, m, "mediana")


def razao_maior_remuneracao(q: pd.DataFrame) -> dict:
    """Maior remuneração ÷ média e ÷ mediana das demais pessoas (GRI 2-21 usa a mediana)."""
    s = q["salario"].dropna().sort_values(ascending=False)
    if len(s) < 2:
        return {"razao_media": None, "razao_mediana": None}
    maior, demais = float(s.iloc[0]), s.iloc[1:]
    return {"razao_media": maior / float(demais.mean()), "razao_mediana": maior / float(demais.median())}


def visao_geral(q: pd.DataFrame) -> dict:
    gm, gmd = _gaps(q)
    lid = q[q["lideranca"]]
    return {
        "headcount": len(q), "massa": float(q["salario"].sum()),
        "media": float(q["salario"].mean()) if len(q) else None,
        "mediana": float(q["salario"].median()) if len(q) else None,
        "gap_media": gm, "gap_mediana": gmd,
        **razao_maior_remuneracao(q),
        "pct_mulheres": float((q["sexo"] == "Feminino").mean()) if len(q) else None,
        "pct_mulheres_lideranca": float((lid["sexo"] == "Feminino").mean()) if len(lid) else None,
        "pct_negras": float(q["negra"].mean()) if len(q) else None,
        "pct_negras_lideranca": float(lid["negra"].mean()) if len(lid) else None,
    }


def por_sexo(q: pd.DataFrame, dimensao: str, ordem: list[str] | None = None) -> pd.DataFrame:
    """Para cada valor da dimensão: pessoas e salário médio/mediano de homens e mulheres + gaps."""
    linhas = []
    for valor, g in q.groupby(dimensao):
        h, m = g.loc[g["sexo"] == "Masculino", "salario"], g.loc[g["sexo"] == "Feminino", "salario"]
        linhas.append({dimensao: valor, "pessoas": len(g), "homens": len(h), "mulheres": len(m),
                       "media_homens": h.mean() if len(h) else None, "media_mulheres": m.mean() if len(m) else None,
                       "mediana_homens": h.median() if len(h) else None, "mediana_mulheres": m.median() if len(m) else None,
                       "gap_media": gap(h, m, "media"), "gap_mediana": gap(h, m, "mediana")})
    t = pd.DataFrame(linhas)
    if ordem is not None and len(t):
        t = t.set_index(dimensao).reindex([o for o in ordem if o in set(t[dimensao])] +
                                          sorted(set(t[dimensao]) - set(ordem))).reset_index()
    return t


def gap_ajustado_por_cargo(q: pd.DataFrame) -> dict:
    """Gap comparando só pessoas no mesmo cargo: média dos gaps dos cargos que têm homens e
    mulheres, ponderada pelo número de pessoas do cargo."""
    t = por_sexo(q, "cargo")
    t = t[(t["homens"] > 0) & (t["mulheres"] > 0)] if len(t) else t
    if t.empty:
        return {"gap_ajustado": None, "cargos_comparaveis": 0, "pessoas_comparaveis": 0}
    return {"gap_ajustado": float((t["gap_media"] * t["pessoas"]).sum() / t["pessoas"].sum()),
            "cargos_comparaveis": len(t), "pessoas_comparaveis": int(t["pessoas"].sum())}


def por_raca(q: pd.DataFrame) -> pd.DataFrame:
    """Salário médio e mediano por raça/cor e a diferença para o grupo Branca."""
    g = q.groupby("raca_cor")["salario"]
    t = pd.DataFrame({"pessoas": g.size(), "media": g.mean(), "mediana": g.median()})
    t = t.reindex([r for r in ORDEM_RACA if r in t.index]).reset_index()
    ref = t.loc[t["raca_cor"] == "Branca", "media"]
    t["dif_branca"] = (t["media"] - float(ref.iloc[0])) / float(ref.iloc[0]) if len(ref) else None
    t["participacao"] = t["pessoas"] / t["pessoas"].sum() if len(t) else None
    return t


def quartis_por_sexo(q: pd.DataFrame) -> pd.DataFrame:
    """Participação de mulheres e homens em cada quartil salarial (1º = 25% que ganham menos)."""
    if len(q) < 4:
        return pd.DataFrame(columns=["quartil", "sexo", "pessoas", "pct"])
    ordem = q.sort_values("salario").reset_index(drop=True)
    ordem["quartil"] = pd.qcut(ordem.index, 4, labels=["1º quartil (menores)", "2º quartil", "3º quartil", "4º quartil (maiores)"])
    t = ordem.groupby(["quartil", "sexo"], observed=True).size().rename("pessoas").reset_index()
    t["pct"] = t["pessoas"] / t.groupby("quartil", observed=True)["pessoas"].transform("sum")
    return t


def concentracao_massa(q: pd.DataFrame) -> dict:
    """Quanto da massa salarial fica com os 10% e os 1% que mais ganham."""
    s = q["salario"].dropna().sort_values(ascending=False)
    if s.empty:
        return {"top10": None, "top1": None}
    tot = s.sum()
    return {"top10": float(s.iloc[:max(1, round(len(s) * .10))].sum() / tot),
            "top1": float(s.iloc[:max(1, round(len(s) * .01))].sum() / tot)}


def setores(q: pd.DataFrame, nivel: str = "area") -> pd.DataFrame:
    """Desbalanceamento e concentração por área (ou diretoria):
       - % mulheres / % pessoas negras e a distância para o quadro todo (em pontos percentuais)
       - gap de gênero dentro do setor
       - fatia da massa salarial ÷ fatia do headcount (> 1 = o setor concentra mais salário do que gente)"""
    if q.empty:
        return pd.DataFrame()
    pm, pn = (q["sexo"] == "Feminino").mean(), q["negra"].mean()
    massa, hc = q["salario"].sum(), len(q)
    linhas = []
    for (dire, valor), g in q.groupby(["diretoria", nivel] if nivel != "diretoria" else ["diretoria", "diretoria"]):
        h, m = g.loc[g["sexo"] == "Masculino", "salario"], g.loc[g["sexo"] == "Feminino", "salario"]
        linhas.append({"diretoria": dire, "setor": valor, "pessoas": len(g),
                       "pct_mulheres": (g["sexo"] == "Feminino").mean(), "pct_negras": g["negra"].mean(),
                       "salario_medio": g["salario"].mean(), "gap_media": gap(h, m, "media"),
                       "fatia_massa": g["salario"].sum() / massa, "fatia_headcount": len(g) / hc})
    t = pd.DataFrame(linhas)
    t["dist_mulheres_pp"] = (t["pct_mulheres"] - pm) * 100
    t["dist_negras_pp"] = (t["pct_negras"] - pn) * 100
    t["concentracao"] = t["fatia_massa"] / t["fatia_headcount"]
    return t.sort_values("pessoas", ascending=False)


def por_tempo_casa(q: pd.DataFrame) -> pd.DataFrame:
    return por_sexo(q, "faixa_tempo_casa", ORDEM_TEMPO_CASA)
