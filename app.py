
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re

st.set_page_config(page_title="Perfil de Escolas — Brincando com…", layout="wide")

# ========= Config =========
DATAFILE = Path("adocao_se_edb.xlsx")

EXPECTED_COLS = [
    "PROTHEUS","NOME ESCOLA","GESTOR","UF","REGIÃO","Confessional","pedra",
    "ADOTA FIE?","ADOTA BRASIL","ADOTA D+A","ADOTA LITERATURA","ADOTA SISTEMA","ADOTA MATERIAL PROPRIO",
    "tipo_adocao","alunado_total","faixa_alunos","mensalidade","adocao_edb",
    "potencial_mercado","precificação","faixa_renda",
    "adota did edb - prot","adota lit - prot","adota apo edb - prot","adota s.e. edb - prot",
    "adota edb?","sow de s.e. edb - considerando total adocao do mercado","adota se edb"
]

ORDER_MENSAL = [
    "até 399", "400 a 799", "800 a 1.399", "1.400 a 2.199", "2.200 a 3.499"
]
ORDER_FAIXA_ALUNOS = [
    "0 a 50","51 a 100","101 a 150","151 a 200","201 a 250","251 a 300",
    "301 a 350","351 a 400","401 a 500","500+"
]
ORDER_REGIAO = ["Norte","Nordeste","Centro-Oeste","Sudeste","Sul"]

# ========= Utils =========
def strip_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    df.rename(columns={"precificacao":"precificação"}, inplace=True, errors="ignore")
    return df

def ensure_expected(df: pd.DataFrame) -> pd.DataFrame:
    for c in EXPECTED_COLS:
        if c not in df.columns:
            df[c] = pd.NA
    return df

def as_int_safe(x):
    try:
        if pd.isna(x): return pd.NA
        return int(float(str(x).replace(",", ".").strip()))
    except Exception:
        return pd.NA

def _br_to_float(num_str: str) -> float:
    """Converte número PT-BR (p.ex. '1.400', '2.199,50') em float."""
    s = num_str.replace(".", "").replace(",", ".")
    return float(s)

def bucket_mensalidade(val) -> str | pd._libs.missing.NAType:
    """
    Coloca a mensalidade em faixas canônicas, aceitando:
    - texto com faixa ('1.400 a 2.199', 'até 399')
    - valores monetários ('R$ 1.850,00')
    - números simples ('1800')
    """
    if pd.isna(val):
        return pd.NA
    s = str(val).strip().lower()

    # casos explícitos 'até 399'
    if "até" in s and "399" in s:
        return "até 399"

    # captura números no formato PT-BR (1.400 / 2.199,50 / 1800)
    matches = re.findall(r"\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+", s)
    nums = []
    for m in matches:
        try:
            nums.append(_br_to_float(m))
        except Exception:
            continue

    val_ref = None
    if len(nums) >= 2:
        # se for faixa 'x a y', usa a média para decidir a classe
        val_ref = (nums[0] + nums[1]) / 2.0
    elif len(nums) == 1:
        val_ref = nums[0]

    # Se não conseguimos extrair número, tenta padrões de faixa por texto:
    if val_ref is None:
        if "400" in s and "799" in s: return "400 a 799"
        if "800" in s and ("1.399" in s or "1399" in s): return "800 a 1.399"
        if ("1.400" in s or "1400" in s) and ("2.199" in s or "2199" in s): return "1.400 a 2.199"
        if ("2.200" in s or "2200" in s) and ("3.499" in s or "3499" in s): return "2.200 a 3.499"

        return pd.NA

    # aplica os limites das faixas
    if val_ref <= 399:
        return "até 399"
    if 400 <= val_ref <= 799:
        return "400 a 799"
    if 800 <= val_ref <= 1399:
        return "800 a 1.399"
    if 1400 <= val_ref <= 2199:
        return "1.400 a 2.199"
    if 2200 <= val_ref <= 3499:
        return "2.200 a 3.499"
    return "3.500+"

def to_money(x):
    if pd.isna(x): return np.nan
    s = str(x).replace("R$", "").replace(" ", "")
    s = s.replace(".", "").replace(",", ".")
    s = re.sub(r"[^\d\.\-]", "", s)
    try:
        return float(s) if s else np.nan
    except Exception:
        return np.nan

@st.cache_data(show_spinner=False)
def load_data(uploaded_file=None):
    if uploaded_file is not None:
        return pd.read_excel(uploaded_file, engine="openpyxl")
    if DATAFILE.exists():
        return pd.read_excel(DATAFILE, engine="openpyxl")
    return pd.DataFrame()

def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = strip_cols(df.copy())
    df = ensure_expected(df)

    # tipagem / normalizações principais
    df["alunado_total"] = df["alunado_total"].map(as_int_safe)
    df["precificação"] = df["precificação"].map(to_money)
    df["potencial_mercado"] = df["potencial_mercado"].map(to_money)

    # regiões e faixas
    df["REGIÃO"] = pd.Categorical(df["REGIÃO"].astype(str).str.strip(), categories=ORDER_REGIAO, ordered=True)
    df["faixa_alunos"] = pd.Categorical(df["faixa_alunos"].astype(str).str.strip(), categories=ORDER_FAIXA_ALUNOS, ordered=True)

    # mensalidade → bucketing robusto
    df["mensalidade"] = df["mensalidade"].apply(bucket_mensalidade)
    df["mensalidade"] = pd.Categorical(df["mensalidade"], categories=ORDER_MENSAL, ordered=True)

    # flag Brincando
    def flag_brincando(row):
        prot = str(row.get("adota s.e. edb - prot", "")).upper()
        ad_sis = str(row.get("ADOTA SISTEMA", "")).strip().lower()
        ad_se = str(row.get("adota se edb", "")).strip().lower()
        return ("BRINCANDO" in prot) or (ad_sis == "sim") or (ad_se == "sim")
    df["adota_brincando"] = df.apply(flag_brincando, axis=1)

    # confessional/pedra
    df["Confessional"] = df["Confessional"].astype(str).str.strip().replace(
        {"Si":"Sim","Nao":"Não","nao":"Não","NA":"S/I"})
    df["pedra"] = df["pedra"].astype(str).str.strip()

    return df

# ========= UI =========
with st.sidebar:
    st.header("⚙️ Configurações")
    up = st.file_uploader("(Opcional) Carregue outra base XLSX", type=["xlsx"])

    raw = load_data(up)
    if raw.empty:
        st.error("Base não encontrada. Confirme que 'adocao_se_edb.xlsx' está na raiz do repositório ou faça upload.")
        st.stop()

    df = clean(raw)

    # Filtros
    regs = [r for r in ORDER_REGIAO if r in df["REGIÃO"].dropna().unique()]
    sel_reg = st.multiselect("Região", regs, default=regs)

    ufs = sorted(df["UF"].dropna().unique().tolist())
    sel_uf = st.multiselect("UF", ufs)

    confs = sorted(df["Confessional"].dropna().unique().tolist())
    sel_conf = st.multiselect("Confessional", confs)

    faixas_al = [c for c in ORDER_FAIXA_ALUNOS if c in df["faixa_alunos"].dropna().unique()]
    sel_fa = st.multiselect("Faixa de alunos", faixas_al, default=faixas_al)

    faixas_m = [c for c in ORDER_MENSAL if c in df["mensalidade"].dropna().unique()]
    sel_mens = st.multiselect("Mensalidade (faixas)", faixas_m, default=faixas_m)


# aplica filtros
flt = df.copy()
if sel_reg:
    flt = flt[flt["REGIÃO"].isin(sel_reg)]
if sel_uf:
    flt = flt[flt["UF"].isin(sel_uf)]
if sel_conf:
    flt = flt[flt["Confessional"].isin(sel_conf)]
if sel_fa:
    flt = flt[flt["faixa_alunos"].isin(sel_fa)]
if sel_mens:
    flt = flt[flt["mensalidade"].isin(sel_mens)]


# ========= KPIs =========
st.title("📚 Perfil de Escolas — Brincando com…")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Escolas (filtro)", f"{len(flt):,}".replace(",", "."))
with col2:
    med_alunos = flt["alunado_total"].dropna()
    st.metric("Mediana de alunos", f"{int(med_alunos.median()) if not med_alunos.empty else 0:,}".replace(",", "."))
with col3:
    mens_moda = flt["mensalidade"].astype(str).mode().iloc[0] if not flt.empty else "-"
    st.metric("Moda da mensalidade", mens_moda)
with col4:
    pot = flt["precificação"].dropna().sum()
    st.metric("Potencial (soma R$)", f"R$ {pot:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

# ========= Visualizações =========
# 1) Distribuição por Região
st.subheader("Distribuição de escolas por Região")
reg_ct = (flt.groupby("REGIÃO", as_index=False)["NOME ESCOLA"].count()
          .rename(columns={"NOME ESCOLA":"Escolas"}))
st.bar_chart(reg_ct.set_index("REGIÃO")["Escolas"])

# 2) Adoção do Brincando por faixa de mensalidade
st.subheader("Adoção do Brincando por faixa de mensalidade")
if not flt.empty:
    ado = (flt.groupby(["mensalidade","adota_brincando"], as_index=False)["NOME ESCOLA"].count()
           .rename(columns={"NOME ESCOLA":"Escolas"}))
    ado["mensalidade_str"] = ado["mensalidade"].astype(str)
    chart_ado = alt.Chart(ado).mark_bar().encode(
        x=alt.X("mensalidade_str:N", sort=ORDER_MENSAL, title="Mensalidade"),
        y=alt.Y("Escolas:Q"),
        color=alt.Color("adota_brincando:N", title="Adota Brincando"),
        tooltip=["mensalidade_str","adota_brincando","Escolas"]
    )
    st.altair_chart(chart_ado, use_container_width=True)
else:
    st.info("Sem dados para adoção por faixa de mensalidade no filtro atual.")

# 3) Faixa de alunos por Região (empilhado %)
st.subheader("Faixa de alunos por Região (participação %)")
fa = (flt.dropna(subset=["faixa_alunos","REGIÃO"])
        .groupby(["REGIÃO","faixa_alunos"], as_index=False)["NOME ESCOLA"].count()
        .rename(columns={"NOME ESCOLA":"Escolas"}))
if not fa.empty:
    fa["faixa_alunos_str"] = fa["faixa_alunos"].astype(str)
    stack = alt.Chart(fa).mark_bar().encode(
        x=alt.X("REGIÃO:N", sort=ORDER_REGIAO),
        y=alt.Y("Escolas:Q", stack="normalize", title="% de escolas"),
        color=alt.Color("faixa_alunos_str:N", title="Faixa de alunos"),
        tooltip=["REGIÃO","faixa_alunos_str","Escolas"]
    )
    st.altair_chart(stack, use_container_width=True)
else:
    st.info("Sem dados para faixa de alunos na seleção.")

# 4) Heatmap — Padrões de adoção por Região
st.subheader("Heatmap — Padrões de adoção por Região")
flags_cols = ["ADOTA FIE?","ADOTA BRASIL","ADOTA D+A","ADOTA LITERATURA","ADOTA SISTEMA","ADOTA MATERIAL PROPRIO"]
for c in flags_cols:
    if c not in flt.columns:
        flt[c] = pd.NA
hm = (flt.melt(id_vars=["REGIÃO"], value_vars=flags_cols, var_name="Adoção", value_name="Valor")
         .assign(Valor=lambda d: d["Valor"].astype(str).str.strip().str.lower().isin(["sim","1","true","verdadeiro"]))
         .groupby(["REGIÃO","Adoção"], as_index=False)["Valor"].mean())
if not hm.empty:
    hm["% Escolas"] = (hm["Valor"]*100).round(1)
    heat = alt.Chart(hm).mark_rect().encode(
        x=alt.X("Adoção:N", title="Tipo de Adoção"),
        y=alt.Y("REGIÃO:N", sort=ORDER_REGIAO, title="Região"),
        color=alt.Color("% Escolas:Q"),
        tooltip=["REGIÃO","Adoção","% Escolas"]
    ).properties(height=240)
    st.altair_chart(heat, use_container_width=True)
else:
    st.info("Sem dados para montar o heatmap de adoções.")

# 5) NOVA VISUALIZAÇÃO (substitui a SOW):
# 5) NOVA VISUALIZAÇÃO (substitui a SOW):
#    Heatmap de taxa de adoção do Brincando por Faixa de alunos × Mensalidade
st.subheader("Taxa de adoção do Brincando — Faixa de alunos × Mensalidade")

base = flt.dropna(subset=["faixa_alunos", "mensalidade"]).copy()
if not base.empty:
    # garante booleano para somar adotantes
    base["adota_brincando"] = base["adota_brincando"].astype(bool)

    # observed=True evita combinações categoriais inexistentes (corrige o ValueError)
    grp = (
        base.groupby(["faixa_alunos", "mensalidade"], observed=True)
            .agg(
                escolas=("NOME ESCOLA", "count"),
                adotantes=("adota_brincando", "sum")
            )
            .reset_index()
    )

    grp["taxa_%"] = (grp["adotantes"] / grp["escolas"] * 100).round(1)
    grp["faixa_alunos_str"] = grp["faixa_alunos"].astype(str)
    grp["mensalidade_str"] = grp["mensalidade"].astype(str)

    heat2 = alt.Chart(grp).mark_rect().encode(
        x=alt.X("mensalidade_str:N", sort=ORDER_MENSAL, title="Mensalidade"),
        y=alt.Y("faixa_alunos_str:N", sort=ORDER_FAIXA_ALUNOS, title="Faixa de alunos"),
        color=alt.Color("taxa_%:Q", title="Taxa de adoção (%)"),
        tooltip=["faixa_alunos_str", "mensalidade_str", "escolas", "adotantes", "taxa_%"]
    ).properties(height=280)

    st.altair_chart(heat2, use_container_width=True)
else:
    st.info("Sem dados suficientes para calcular a taxa de adoção por faixa de alunos × mensalidade.")


# 6) Tabela detalhada + download
st.subheader("Detalhe das escolas (após filtros)")
cols_show = [
    "PROTHEUS","NOME ESCOLA","UF","REGIÃO","Confessional","pedra",
    "alunado_total","faixa_alunos","mensalidade","faixa_renda",
    "adota_brincando","precificação","potencial_mercado",
    "adota s.e. edb - prot","ADOTA SISTEMA","adota se edb"
]
present = [c for c in cols_show if c in flt.columns]
st.dataframe(flt[present].sort_values(["REGIÃO","UF","NOME ESCOLA"]), use_container_width=True)

st.download_button(
    "⬇️ Baixar (CSV) — filtro aplicado",
    flt.to_csv(index=False).encode("utf-8-sig"),
    "perfil_escolas_filtrado.csv",
    mime="text/csv"
)
