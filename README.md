# Equidade Salarial — remuneração x diversidade

Painel Streamlit que substitui o dashboard "Remuneração & Equidade Salarial" do Databricks,
**refeito do zero** a partir do objetivo: cruzar os dados demográficos com os salários (setores
mais desbalanceados ou concentrados; diferença salarial por sexo, raça/cor e tempo de casa) e
calcular os indicadores reportados para RI e Sustentabilidade.

Lê **só do Neon**, por uma view própria (`core.v_equidade_base`: sem nome, sem data de nascimento,
pessoa pseudonimizada), com um usuário de banco só de leitura. Com login (o mesmo dos outros
painéis) e matriz de acessos (painel `equidade`, grupo Remuneração e Orçamento de Pessoas) — é
dado sensível (salário + sexo + raça/cor), só para quem pode ver remuneração. Padrão visual da
skill `padrao-painel-streamlit`.

## Rodar

```powershell
streamlit run app.py
```

`.streamlit/secrets.toml` (fora do Git) tem `[neon]` com a conexão e `[app] email_suporte` —
ver `.streamlit/secrets.toml.example`.

## Visões (barra lateral)

| Visão | O que mostra |
|---|---|
| Visão geral e RI | Headcount, massa, salário médio e mediano; **maior remuneração ÷ média e ÷ mediana das demais**; gap de gênero (média, mediana e no mesmo cargo); mulheres e pretas/pardas na liderança; concentração da massa; mulheres por quartil salarial; tabela para o reporte (CSV) |
| Gênero | Gap por nível, composição de cada nível e tabela "mesmo cargo, homens x mulheres" |
| Raça/cor | Salário médio e mediano por raça/cor e diferença para Branca; raça/cor em cada nível; salário por nível × raça/cor |
| Tempo de casa | Salário de homens e mulheres por faixa de tempo de casa, com o gap |
| Setores | % de mulheres x gap por área (ou diretoria); fatia do headcount x fatia da massa; tabela de desbalanceamento e concentração |

Filtros (valem para todas as visões): diretoria, área, centro de custo, família de cargo, nível,
vínculo, sexo, raça/cor. **Estatística** (média/mediana) vale para os gráficos de gênero, raça/cor
e tempo de casa.

## Regras

1. **Quadro**: ativos na data da base (admitido até a data e sem desligamento), uma linha por
   pessoa — a mesma regra dos painéis Turnover e Dados Demográficos. População: **todos os ativos**;
   o filtro Vínculo tira estagiários, PJ, conselho etc.
2. **Salário** = salário-base mensal do cadastro (sem variável e sem benefícios).
3. **Gap de gênero** = (salário dos homens − salário das mulheres) ÷ salário dos homens, pela média
   e pela mediana. Positivo = mulheres ganham menos.
4. **Gap no mesmo cargo** = gap dentro de cada cargo que tem homens e mulheres, ponderado pelo
   número de pessoas do cargo.
5. **Maior remuneração ÷ demais** = maior salário-base do filtro ÷ média (ou mediana, GRI 2-21)
   de todas as outras pessoas.
6. **Liderança** = níveis de coordenação para cima, incluindo diretoria e conselho.
7. **Concentração do setor** = fatia da massa salarial ÷ fatia do headcount.
8. Sem supressão de grupos pequenos (decisão de 28/09/2026: o painel é restrito a quem pode ver
   remuneração).

## O que mudou em relação ao Databricks (de propósito)

| Ponto | Databricks | Aqui | Por quê |
|---|---|---|---|
| Desenho | réplica de widgets | refeito a partir do briefing (RI, gênero, raça/cor, tempo de casa, setores) | o dashboard antigo não respondia às perguntas |
| Massa salarial | soma das fotos diárias (~25x maior) | soma dos ativos na data | a medida original somava a mesma pessoa em cada foto |
| Diretoria / área | `rh.gold.dim_departamento_areas_diretorias` | mapeamento oficial (`core.v_funcionario_diretoria`) | a dim está desatualizada |
| "Compa-ratio" | salário ÷ média do próprio nível | retirado | não é compa-ratio (não usa referência de mercado); pode voltar com a referência Muller |
| Razão para RI | não existia | maior remuneração ÷ média e ÷ mediana das demais | pedido de RI e Sustentabilidade |

## Conferência

`_neon/validacao/validar_paineis.py` (função `painel_equidade`) roda o mesmo `metricas.py` e
compara com um cálculo independente sobre `core.fato_funcionario_ativo`. Em 28/09/2026
(referência 27/09): headcount 1.520 (régua 1.518, diferença da regra por data), massa, razões
para RI e gaps pela média e mediana ✅; sem duplicidade e sem ativos sem salário.
