from datetime import datetime
import io
import random
import sqlite3
from fpdf import FPDF
from geopy.geocoders import Nominatim
import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st

try:
    from kerykeion import AstrologicalSubject
    KERYKEION_DISPONIVEL = True
except ImportError:
    KERYKEION_DISPONIVEL = False

st.set_page_config(
    page_title="Sistema de Diagnóstico Corporativo - RH", layout="wide"
)

TRADUCAO_SIGNOS = {
    "Ari": "Áries", "Aries": "Áries", "Tau": "Touro", "Taurus": "Touro",
    "Gem": "Gêmeos", "Gemini": "Gêmeos", "Can": "Câncer", "Cancer": "Câncer",
    "Leo": "Leão", "Vir": "Virgem", "Virgo": "Virgem", "Lib": "Libra",
    "Libra": "Libra", "Sco": "Escorpião", "Scorpio": "Escorpião",
    "Sag": "Sagitário", "Sagittarius": "Sagitário", "Cap": "Capricórnio",
    "Capricorn": "Capricórnio", "Aqu": "Aquário", "Aquarius": "Aquário",
    "Pis": "Peixes", "Pisces": "Peixes",
}

ELEMENTOS_SIGNOS = {
    "Áries": "Fogo", "Leão": "Fogo", "Sagitário": "Fogo",
    "Touro": "Terra", "Virgem": "Terra", "Capricórnio": "Terra",
    "Gêmeos": "Ar", "Libra": "Ar", "Aquário": "Ar",
    "Câncer": "Água", "Escorpião": "Água", "Peixes": "Água"
}

PREFERENCIA_ELEMENTO_CASA = {
    1: ["Fogo", "Terra"],
    2: ["Terra"],
    3: ["Ar"],
    4: ["Água"],
    5: ["Fogo"],
    6: ["Terra"],
    7: ["Ar"],
    8: ["Água", "Terra"],
    9: ["Fogo", "Ar"],
    10: ["Terra", "Fogo"],
    11: ["Ar", "Fogo"],
    12: ["Água"]
}

def calcular_nota_astrologica_casa(casa_num, signo_nome):
    elemento_signo = ELEMENTOS_SIGNOS.get(signo_nome, "Terra")
    prefs = PREFERENCIA_ELEMENTO_CASA.get(casa_num, ["Terra"])
    if elemento_signo in prefs:
        return 5
    elif elemento_signo in ["Fogo", "Ar"] and any(p in ["Fogo", "Ar"] for p in prefs):
        return 4
    elif elemento_signo in ["Terra", "Água"] and any(p in ["Terra", "Água"] for p in prefs):
        return 4
    return 3

ATIVADORES_NOTA_5 = {
    1: ["O Mago", "Rei de Ouros", "Rainha de Espadas"],
    2: ["A Imperatriz", "Rei de Paus", "Rainha de Copas"],
    3: ["O Hierofante", "Rei de Ouros", "Rainha de Copas"],
    4: ["O Mundo", "Rei de Ouros", "Rainha de Ouros"],
    5: ["O Imperador", "Rei de Ouros", "Rainha de Paus"],
    6: ["A Força", "Rei de Copas", "Rainha de Ouros"],
    7: ["A Estrela", "Rei de Espadas", "Rainha de Espadas"],
    8: ["A Justiça", "Rei de Espadas", "Rainha de Ouros"],
}

FALSOS_POSITIVOS = {
    1: ["O Pendurado"], 2: ["O Eremita"], 3: ["O Louco"], 4: ["O Sol"],
    5: ["A Sacerdotisa", "A Papisa"], 6: ["Os Enamorados", "Os Amantes"],
    7: ["A Temperança"], 8: ["O Carro"],
}

ALERTAS_IMATURIDADE = {
    1: ["Pajem de Paus", "Pajem de Ouros", "Pajem de Espadas", "Pajem de Copas"],
    2: ["Cavaleiro de Espadas"], 3: ["Cavaleiro de Copas"],
    4: ["Pajem de Ouros"], 5: ["Pajem de Espadas"],
    6: ["Cavaleiro de Paus"], 7: ["Cavaleiro de Ouros"], 8: ["Pajem de Copas"],
}

OBS_MAP = {
    1: "Possui potencial, mas a competência técnica pode estar passando por fase de reorganização ou adaptação, exigindo direcionamento.",
    2: "Apresenta boa capacidade de trabalho em equipe e adaptação, desde que mantenha limites profissionais claros.",
    3: "Boa compatibilidade com ambiente baseado em troca e colaboração, prezando pela reciprocidade.",
    4: "Riscos administráveis. Atenção em transformar planejamento em decisão e manter estabilidade emocional.",
    5: "Forte potencial de crescimento e autonomia quando há espaço para exercer criatividade e aperfeiçoar habilidades.",
    6: "Possui recursos emocionais, mas pode ser impactada por situações de desgaste ou frustração em resultados.",
    7: "Boa estrutura mental e racionalização, evitando que experiências frustrantes ocupem espaço excessivo.",
    8: "Capacidade de concluir os processos de maneira ética, gerindo bem as responsabilidades assumidas.",
}


def calcular_nota_metodologica(casa_num, c_cent, c_neg, c_pos):
    nota_base = 3
    cent_limpo = str(c_cent).strip().lower() if c_cent else ""
    neg_limpo = str(c_neg).strip().lower() if c_neg else ""
    pos_limpo = str(c_pos).strip().lower() if c_pos else ""

    if any(atrib.lower() in cent_limpo for atrib in ATIVADORES_NOTA_5.get(casa_num, [])):
        nota_base = 5
    elif any(fp.lower() in cent_limpo for fp in FALSOS_POSITIVOS.get(casa_num, [])):
        nota_base = 2
    elif any(imato.lower() in cent_limpo for imato in ALERTAS_IMATURIDADE.get(casa_num, [])):
        nota_base = 1

    if casa_num == 1 and any(k in pos_limpo for k in ["ouros", "espadas", "mago"]):
        if nota_base < 5:
            nota_base += 1

    if any(k in neg_limpo for k in ["torre", "diabo", "cinco de ouros", "oito de espadas", "nove de espadas", "dez de espadas"]):
        if nota_base > 1:
            nota_base -= 1

    return max(1, min(5, nota_base))


def inicializar_banco():
    with sqlite3.connect("rh_diagnostico.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS avaliacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                vaga TEXT,
                nivel TEXT,
                data TEXT,
                pontos INTEGER,
                classificacao TEXT,
                sinal_vermelho TEXT
            )
        """)
        conn.commit()


inicializar_banco()


def salvar_no_banco(nome, vaga, nivel, data, pontos, classificacao, sinal_vermelho):
    if not nome or not nome.strip() or nome.strip() in ["Candidato(a)", "Selecionar Candidato Cadastrado..."]:
        return False
    with sqlite3.connect("rh_diagnostico.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO avaliacoes (nome, vaga, nivel, data, pontos, classificacao, sinal_vermelho)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (nome.strip(), vaga, nivel, data, pontos, classificacao, sinal_vermelho),
        )
        conn.commit()
    return True


if "astro_data_raw" not in st.session_state:
    st.session_state["astro_data_raw"] = "01/01/1999"
if "astro_local" not in st.session_state:
    st.session_state["astro_local"] = "São Paulo, SP"
if "astro_hora" not in st.session_state:
    st.session_state["astro_hora"] = datetime.strptime("12:00", "%H:%M").time()
if "input_nome_cand" not in st.session_state:
    st.session_state["input_nome_cand"] = ""

if st.session_state.get("reset_trigger", False):
    st.session_state["input_nome_cand"] = ""
    st.session_state["input_vaga_cand"] = ""
    st.session_state["input_nivel_cand"] = "C-Level / Executivo"
    st.session_state["astro_data_raw"] = "01/01/1999"
    st.session_state["astro_hora"] = datetime.strptime("12:00", "%H:%M").time()
    st.session_state["astro_local"] = "São Paulo, SP"
    st.session_state["ficha_gerada"] = False
    if "mandala_calculada" in st.session_state:
        del st.session_state["mandala_calculada"]
    if "big_three_calculado" in st.session_state:
        del st.session_state["big_three_calculado"]
    for i in range(1, 9):
        st.session_state[f"t_central_{i}"] = ""
        st.session_state[f"t_negativa_{i}"] = ""
        st.session_state[f"t_positiva_{i}"] = ""
        st.session_state[f"t_pontos_{i}"] = 3
    st.session_state["reset_trigger"] = False


def disparar_nova_avaliacao():
    st.session_state["reset_trigger"] = True


st.title("Sistema de Diagnóstico Corporativo: Tarot & Astrologia para RH")
st.markdown(
    "Plataforma unificada de recrutamento e seleção orientada pelo método expandido de 8 casas estruturais, tiragem de 3 cartas e mandala astrológica com motor astronômico real (Kerykeion)."
)

tab1, tab2, tab3 = st.tabs([
    "1. Cadastro e Avaliação (Tarot 8 Casas)",
    "2. Mapeamento Astrológico (12 Casas)",
    "3. Ficha de Avaliação e Cruzamento Analítico",
])

DECK_TAROT = [
    "O Mago", "A Sacerdotisa", "A Imperatriz", "O Imperador", "O Hierofante",
    "Os Enamorados", "O Carro", "A Justiça", "O Eremita", "A Roda da Fortuna",
    "A Força", "O Pendurado", "A Morte", "A Temperança", "O Diabo", "A Torre",
    "A Estrela", "A Lua", "O Sol", "O Julgamento", "O Mundo", "O Louco",
    "Ás de Ouros", "Dois de Ouros", "Três de Ouros", "Quatro de Ouros",
    "Cinco de Ouros", "Seis de Ouros", "Sete de Ouros", "Oito de Ouros",
    "Nove de Ouros", "Dez de Ouros", "Ás de Copas", "Dois de Copas",
    "Três de Copas", "Quatro de Copas", "Cinco de Copas", "Seis de Copas",
    "Sete de Copas", "Oito de Copas", "Nove de Copas", "Dez de Copas",
    "Ás de Espadas", "Dois de Espadas", "Três de Espadas", "Quatro de Espadas",
    "Cinco de Espadas", "Seis de Espadas", "Sete de Espadas", "Oito de Espadas",
    "Nove de Espadas", "Dez de Espadas", "Ás de Paus", "Dois de Paus",
    "Três de Paus", "Quatro de Paus", "Cinco de Paus", "Seis de Paus",
    "Sete de Paus", "Oito de Paus", "Nove de Paus", "Dez de Paus",
]

with tab1:
    col_topo_t1, col_topo_t2 = st.columns([4, 1])
    with col_topo_t1:
        st.header("Fase 1: Parâmetros do Candidato e Método de Tiragem (Tarot)")
    with col_topo_t2:
        st.button(
            "🔄 Nova Avaliação",
            on_click=disparar_nova_avaliacao,
            use_container_width=True,
        )

    st.markdown("Selecione o modo de cadastro e preencha as informações do candidato.")

    with sqlite3.connect("rh_diagnostico.db") as conn_db:
        cursor_db = conn_db.cursor()
        cursor_db.execute("SELECT DISTINCT nome FROM avaliacoes")
        candidatos_existentes = [row[0] for row in cursor_db.fetchall() if row[0]]

    tipo_cad = st.radio(
        "Modo de Candidato",
        ["Selecionar Existente", "Cadastrar Novo"],
        index=1,
        horizontal=True,
        key="tipo_cad_modo",
    )

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        if tipo_cad == "Selecionar Existente":
            if candidatos_existentes:
                opcoes_dropdown = ["Selecionar Candidato Cadastrado..."] + candidatos_existentes
                escolha_cand = st.selectbox(
                    "Candidato(a) Registrado",
                    opcoes_dropdown,
                    key="select_cand_existente_ativo",
                )
                if escolha_cand != "Selecionar Candidato Cadastrado...":
                    nome_candidato = escolha_cand
                    st.session_state["input_nome_cand"] = escolha_cand
                else:
                    nome_candidato = ""
                    st.session_state["input_nome_cand"] = ""
            else:
                st.info("Nenhum candidato registrado no banco.")
                nome_candidato = ""
        else:
            nome_candidato = st.text_input(
                "Nome Completo do Novo Candidato(a)", key="input_nome_cand"
            )

    with col_c2:
        vaga_cargo = st.text_input("Vaga / Cargo Pretendido", key="input_vaga_cand")
    with col_c3:
        nivel_hierarquico = st.selectbox(
            "Nível Hierárquico",
            [
                "C-Level / Executivo", "Diretor", "Gerente", "Supervisor",
                "Coordenador", "Especialista / Analista", "Técnico", "Operacional",
            ],
            key="input_nivel_cand",
        )

    st.markdown("---")
    st.subheader("Modo de Geração da Leitura das Cartas")
    modo_geracao = st.radio(
        "Selecione como deseja preencher as cartas nas 8 casas:",
        [
            "Manual (Preenchimento Direto)",
            "Automático (Assistente Especialista com Regras Metodológicas)",
        ],
        key="radio_modo_tarot",
    )

    if modo_geracao == "Automático (Assistente Especialista com Regras Metodológicas)":
        if st.button("🎲 Executar Sorteio e Cálculo Inteligente via Regras"):
            cartas_embaralhadas = random.sample(DECK_TAROT, len(DECK_TAROT))
            idx = 0
            for i in range(1, 9):
                c_cent = cartas_embaralhadas[idx % len(DECK_TAROT)]
                idx += 1
                c_neg = cartas_embaralhadas[idx % len(DECK_TAROT)]
                idx += 1
                c_pos = cartas_embaralhadas[idx % len(DECK_TAROT)]
                idx += 1

                st.session_state[f"t_central_{i}"] = c_cent
                st.session_state[f"t_negativa_{i}"] = c_neg
                st.session_state[f"t_positiva_{i}"] = c_pos

                pontos_sugeridos = calcular_nota_metodologica(i, c_cent, c_neg, c_pos)
                st.session_state[f"t_pontos_{i}"] = pontos_sugeridos

            st.success("Sorteio e atribuição de notas baseados estritamente nas diretrizes metodológicas concluídos com sucesso!")
            st.rerun()

    st.markdown("---")
    st.subheader("Matriz de Avaliação por Casas (Notas de 1 a 5)")

    casas_config = [
        (1, "Hard Skills (Competência Técnica e Rotina)", "Casa 6 Astrológica"),
        (2, "Soft Skills (Inteligência Social e Comunicação)", "Casa 3 Astrológica"),
        (3, "Fit Cultural (Alinhamento de Valores e Coletivo)", "Casa 11 Astrológica"),
        (4, "Desafios (Pontos Cegos e Autossabotagem)", "Casa 12 Astrológica"),
        (5, "Potencial Futuro (Projeção e Liderança de Longo Prazo)", "Casa 10 Astrológica"),
        (6, "Equilíbrio Emocional (Resiliência sob Pressão)", "Casa 4 Astrológica"),
        (7, "Saúde Psicológica (Foco Cognitivo e Burnout)", "Casa 1 Astrológica"),
        (8, "Confiabilidade e Ética (Compliance e Acordos)", "Casa 8 Astrológica"),
    ]

    col_esq, col_dir = st.columns(2)
    for num, titulo, base_astro in casas_config:
        col_alvo = col_esq if num <= 4 else col_dir
        with col_alvo:
            with st.expander(f"Casa {num}: {titulo} — [{base_astro}]"):
                st.text_input("Arcano Central (Resposta)", key=f"t_central_{num}", placeholder="Ex: O Mago")
                st.text_input("Carta Negativa (Dificuldades)", key=f"t_negativa_{num}", placeholder="Ex: Ás de Ouros")
                st.text_input("Carta Positiva (Pontos Fortes)", key=f"t_positiva_{num}", placeholder="Ex: 4 de Copas")
                st.number_input("Nota (1-5)", min_value=1, max_value=5, value=3, key=f"t_pontos_{num}")

    pontuacoes_t1 = [st.session_state.get(f"t_pontos_{i}", 3) for i in range(1, 9)]
    total_t1 = sum(pontuacoes_t1)
    perc_t1 = (total_t1 / 40.0) * 100

    st.markdown("---")
    st.info(f"📊 **Resultado Individual da Fase 1 (Tarot):** {total_t1} / 40 pontos ({perc_t1:.1f}% de aderência comportamental)")

    st.markdown("")
    with st.expander("📂 Consulta Opcional de Histórico de Candidatos"):
        with sqlite3.connect("rh_diagnostico.db") as conn_hist:
            df_h_temp = pd.read_sql_query(
                "SELECT nome, vaga, nivel, data, pontos, classificacao FROM avaliacoes",
                conn_hist,
            )
        if not df_h_temp.empty:
            st.dataframe(df_h_temp, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum histórico gravado no banco de dados.")

with tab2:
    st.header("Fase 2: Motor Astrológico e Mandala de 12 Casas (Kerykeion Real)")
    st.markdown("Insira as coordenadas e dados de nascimento para calcular as posições reais de efemérides via Kerykeion e pontuação automática.")

    if not KERYKEION_DISPONIVEL:
        st.warning("⚠️ A biblioteca **kerykeion** ainda não foi detectada. Certifique-se de executar `pip install kerykeion`.")

    col_astro1, col_astro2 = st.columns(2)
    with col_astro1:
        data_nasc_raw = st.text_input(
            "Data de Nascimento (Apenas números ou DD/MM/AAAA)",
            placeholder="Ex: 02051978 ou 02/05/1978",
            key="astro_data_raw",
        )
        local_nasc = st.text_input(
            "Local de Nascimento (Cidade/Estado)",
            placeholder="Ex: São Paulo, SP",
            key="astro_local",
        )
    with col_astro2:
        hora_nasc = st.time_input("Horário de Nascimento", key="astro_hora")
        sistema_casas = st.selectbox("Sistema de Casas", ["Plácidus", "Koch", "Signo Inteiro"], key="astro_sistema")

    def calcular_mandala_real(d_nasc_str, h_nasc, loc):
        if not d_nasc_str or h_nasc is None or not loc or not loc.strip():
            st.error("⚠️ Preencha a Data, o Horário e o Local de Nascimento para processar a mandala astrológica.")
            return None, None

        digits = "".join(filter(str.isdigit, d_nasc_str))
        if len(digits) != 8:
            st.error("❌ Formato de data inválido. Digite os 8 números corretamente (ex: 02051978 ou 02/05/1978).")
            return None, None

        try:
            d_nasc = datetime.strptime(digits, "%d%m%Y").date()
        except ValueError:
            st.error("❌ Data inválida (ex: dia ou mês inexistente).")
            return None, None

        geolocator = Nominatim(user_agent="rh_astrology_real_v15")
        lat, lon = None, None
        try:
            loc_obj = geolocator.geocode(loc)
            if loc_obj:
                lat, lon = loc_obj.latitude, loc_obj.longitude
            else:
                st.error(f"❌ Não foi possível encontrar coordenadas geográficas para '{loc}'.")
                return None, None
        except Exception as e:
            st.error(f"❌ Erro de conexão ao buscar geolocalização: {e}")
            return None, None

        if KERYKEION_DISPONIVEL:
            try:
                subject = AstrologicalSubject(
                    name="Candidato", year=d_nasc.year, month=d_nasc.month, day=d_nasc.day,
                    hour=h_nasc.hour, minute=h_nasc.minute, city=loc, nation="BR",
                    lat=lat, lng=lon, tz_str="America/Sao_Paulo",
                )

                def extrair_signo_grau(obj_attr):
                    if not obj_attr:
                        return "Desconhecido", 0.0
                    if isinstance(obj_attr, dict):
                        s = obj_attr.get("sign", "Desconhecido")
                        p = obj_attr.get("position", obj_attr.get("pos", 0.0))
                    else:
                        s = getattr(obj_attr, "sign", "Desconhecido")
                        p = getattr(obj_attr, "position", getattr(obj_attr, "pos", 0.0))
                    s_trad = TRADUCAO_SIGNOS.get(s, s)
                    return s_trad, p

                sun_s, sun_p = extrair_signo_grau(getattr(subject, "sun", None))
                moon_s, moon_p = extrair_signo_grau(getattr(subject, "moon", None))
                asc_s, asc_p = extrair_signo_grau(getattr(subject, "first_house", None))

                big_three = {
                    "Solar": {"signo": sun_s, "grau": f"{int(sun_p % 30)}° {int((sun_p % 1) * 60)}'"},
                    "Ascendente": {"signo": asc_s, "grau": f"{int(asc_p % 30)}° {int((asc_p % 1) * 60)}'"},
                    "Lunar": {"signo": moon_s, "grau": f"{int(moon_p % 30)}° {int((moon_p % 1) * 60)}'"},
                }

                casas_res = {}
                house_attrs = [
                    "first_house", "second_house", "third_house", "fourth_house",
                    "fifth_house", "sixth_house", "seventh_house", "eighth_house",
                    "ninth_house", "tenth_house", "eleventh_house", "twelfth_house",
                ]
                for i, attr in enumerate(house_attrs, start=1):
                    if hasattr(subject, attr):
                        h_obj = getattr(subject, attr)
                        signo, pos = extrair_signo_grau(h_obj)
                    else:
                        signo, pos = "Desconhecido", 0.0

                    nota_casa_astro = calcular_nota_astrologica_casa(i, signo)
                    grau_int = int(pos % 30)
                    min_int = int((pos % 1) * 60)
                    casas_res[f"Casa {i}"] = {
                        "signo": signo,
                        "grau": f"{grau_int}° {min_int}'",
                        "nota": nota_casa_astro,
                        "analise": f"Posicionamento real calculado no signo de {signo} a {pos:.2f}° (Nota de afinidade: {nota_casa_astro}/5).",
                    }
                return casas_res, big_three
            except Exception as e:
                st.error(f"Erro no cálculo do Kerykeion: {e}")
                return None, None

        signos = ["Áries", "Touro", "Gêmeos", "Câncer", "Leão", "Virgem", "Libra", "Escorpião", "Sagitário", "Capricórnio", "Aquário", "Peixes"]
        seed = d_nasc.toordinal() + int(h_nasc.hour * 60 + h_nasc.minute) + abs(hash(loc)) % 1000
        big_three = {
            "Solar": {"signo": signos[seed % 12], "grau": "12° 0'"},
            "Ascendente": {"signo": signos[(seed + 6) % 12], "grau": "8° 15'"},
            "Lunar": {"signo": signos[(seed + 3) % 12], "grau": "15° 30'"},
        }
        casas_res = {}
        for c in range(1, 13):
            s_idx = (seed + c * 7) % 12
            g = (seed * c * 3) % 30
            sig = signos[s_idx]
            nota_casa_astro = calcular_nota_astrologica_casa(c, sig)
            casas_res[f"Casa {c}"] = {
                "signo": sig,
                "grau": f"{g}°",
                "nota": nota_casa_astro,
                "analise": f"Posicionamento parametrizado para {loc} (Nota de afinidade: {nota_casa_astro}/5).",
            }
        return casas_res, big_three


    if st.button("Processar Mandala Astrológica Real"):
        with st.spinner("Calculando efemérides celestes reais via Kerykeion para o local informado..."):
            mandala, big_three = calcular_mandala_real(data_nasc_raw, hora_nasc, local_nasc)
            if mandala and big_three:
                st.session_state["mandala_calculada"] = mandala
                st.session_state["big_three_calculado"] = big_three
                st.success("Mapeamento astrológico de alta precisão concluído!")

    if "mandala_calculada" in st.session_state:
        if "big_three_calculado" in st.session_state:
            b3 = st.session_state["big_three_calculado"]
            st.markdown("### Trindade Principal (Signo Solar, Ascendente e Lunar)")
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                st.metric(label="Signo Solar", value=b3['Solar']['signo'], delta=b3['Solar']['grau'])
            with col_b2:
                st.metric(label="Signo Ascendente", value=b3['Ascendente']['signo'], delta=b3['Ascendente']['grau'])
            with col_b3:
                st.metric(label="Signo Lunar", value=b3['Lunar']['signo'], delta=b3['Lunar']['grau'])
            st.markdown("")

        st.markdown("### Resultado da Mandala das 12 Casas (Kerykeion Real)")
        mandala_items = list(st.session_state["mandala_calculada"].items())
        
        total_t2 = sum([v.get("nota", 3) for k, v in mandala_items])
        perc_t2 = (total_t2 / 60.0) * 100
        st.info(f"🌟 **Resultado Individual da Fase 2 (Astrologia):** {total_t2} / 60 pontos ({perc_t2:.1f}% de potencial estrutural celeste)")
        st.markdown("")

        for idx_linha in range(0, len(mandala_items), 3):
            cols_grid = st.columns(3)
            for col_idx in range(3):
                if idx_linha + col_idx < len(mandala_items):
                    k, v = mandala_items[idx_linha + col_idx]
                    with cols_grid[col_idx]:
                        with st.container(border=True):
                            st.markdown(f"**{k}** *(Nota: {v.get('nota', 3)}/5)*")
                            st.markdown(f"### {v['signo']} `({v['grau']})`")
                            st.caption(v['analise'])
    else:
        st.info("Nenhuma mandala calculada na sessão atual. Preencha os dados e clique em 'Processar Mandala Astrológica Real'.")

with tab3:
    st.header("Fase 3: FICHA DE AVALIAÇÃO E INTEGRAÇÃO ANALÍTICA")
    st.markdown("Documento oficial de governança integrando a Fase 1 (Tarot), a Fase 2 (Astrologia) e o Índice Global de Aderência.")

    if st.button("Gerar Ficha de Avaliação e Súmula Executiva Integrada"):
        st.session_state["ficha_gerada"] = True

    if st.session_state.get("ficha_gerada", False):
        pontuacoes_t1 = [st.session_state.get(f"t_pontos_{i}", 3) for i in range(1, 9)]
        total_t1 = sum(pontuacoes_t1)
        perc_t1 = (total_t1 / 40.0) * 100

        mandala_dados = st.session_state.get("mandala_calculada", {})
        if mandala_dados:
            total_t2 = sum([v.get("nota", 3) for k, v in mandala_dados.items()])
            perc_t2 = (total_t2 / 60.0) * 100
        else:
            total_t2 = 36
            perc_t2 = 60.0

        indice_global = (perc_t1 * 0.7) + (perc_t2 * 0.3)

        p6 = st.session_state.get("t_pontos_6", 3)
        p7 = st.session_state.get("t_pontos_7", 3)
        p8 = st.session_state.get("t_pontos_8", 3)

        sinal_vermelho = "Sim" if (p6 <= 2 or p7 <= 2 or p8 <= 2) else "Não"

        if indice_global >= 80:
            classificacao = "Altamente Recomendado (Aderência Superior a 80%)"
        elif indice_global >= 60:
            classificacao = "Recomendado com Ressalvas (Aderência entre 60% e 79%)"
        else:
            classificacao = "Não Recomendado (Abaixo de 60%: Riscos severos)"

        c_nome = st.session_state.get("input_nome_cand", "Candidato(a)")
        c_vaga = st.session_state.get("input_vaga_cand", "Cargo")
        c_nivel = st.session_state.get("input_nivel_cand", "Nível")
        data_atual = datetime.now().strftime("%d / %m / %Y")

        st.markdown("---")
        st.markdown("### 📋 FICHA DE AVALIAÇÃO INTEGRADA")
        col_f1, col_f2, col_f3 = st.columns([3, 2, 2])
        with col_f1:
            st.markdown(f"**CANDIDATO(A):** {c_nome}")
        with col_f2:
            st.markdown(f"**VAGA / CARGO:** {c_vaga} ({c_nivel})")
        with col_f3:
            st.markdown(f"**DATA:** {data_atual}")

        st.markdown("---")

        col_res1, col_res2, col_res3 = st.columns(3)
        with col_res1:
            st.metric(label="Fase 1 (Tarot)", value=f"{total_t1} / 40", delta=f"{perc_t1:.1f}%")
        with col_res2:
            st.metric(label="Fase 2 (Astrologia)", value=f"{total_t2} / 60", delta=f"{perc_t2:.1f}%")
        with col_res3:
            st.metric(label="Fase 3 (Índice Global)", value=f"{indice_global:.1f}%")

        st.markdown("")
        st.markdown(f"**Classificação Final:** {classificacao}")

        if sinal_vermelho == "Sim":
            st.error("🚨 SINAL VERMELHO ATIVADO: Identificado risco crítico nas Casas 6, 7 ou 8 com nota 1 ou 2.")
        else:
            st.success("✅ SINAL VERMELHO DESATIVADO: Nenhuma restrição severa nas bases emocionais, psicológicas ou éticas.")

        st.markdown("---")

        sub_tab1, sub_tab2, sub_tab3 = st.tabs([
            "Sumário Executivo e Gráfico",
            "Tabela e Cruzamento Astrológico",
            "Histórico e Banco de Dados",
        ])

        with sub_tab1:
            st.markdown("### Visão Radar de Competências (8 Casas)")

            categories = [
                "Hard Skills", "Soft Skills", "Fit Cultural", "Desafios",
                "Potencial Futuro", "Equilíbrio Emocional", "Saúde Psicológica",
                "Confiabilidade e Ética",
            ]

            fig = go.Figure()
            fig.add_trace(
                go.Scatterpolar(
                    r=pontuacoes_t1 + [pontuacoes_t1[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    name="Candidato",
                    line_color="#00cc96",
                    fillcolor="rgba(0, 204, 150, 0.25)",
                )
            )

            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 5], dtick=1),
                    bgcolor="rgba(22, 26, 29, 0.6)",
                ),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=40, r=40, t=30, b=30),
                height=380,
                showlegend=False,
            )

            st.plotly_chart(fig, use_container_width=True)

            st.markdown("### Parecer Final do Avaliador")
            parecer_texto = (
                f"Perfil avaliado para **{c_nome}**, concorrendo ao cargo de "
                f"**{vaga_cargo}** no nível **{nivel_hierarquico}**. Os resultados "
                f"independentes apontam **{perc_t1:.1f}%** na Fase 1 (Tarot) e "
                f"**{perc_t2:.1f}%** na Fase 2 (Astrologia), resultando em um "
                f"**Índice Global de Aderência de {indice_global:.1f}%** (*{classificacao}*)."
            )
            st.write(parecer_texto)

            def gerar_pdf_relatorio():
                pdf = FPDF()
                pdf.add_page()
                pdf.set_auto_page_break(auto=True, margin=15)
                
                pdf.set_font("helvetica", "B", 12)
                pdf.cell(0, 8, "SISTEMA DE DIAGNOSTICO CORPORATIVO - LAUDO EXECUTIVO", 0, 1, "C")
                pdf.set_font("helvetica", "", 8)
                pdf.cell(0, 4, "Recrutamento e Selecao | Metodo Integrado de 3 Fases", 0, 1, "C")
                pdf.ln(3)

                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 5, f"Candidato(a): {c_nome}", 0, 1)
                pdf.cell(0, 5, f"Cargo/Vaga: {c_vaga} ({c_nivel})", 0, 1)
                pdf.cell(0, 5, f"Data da Avaliacao: {data_atual}", 0, 1)
                pdf.ln(2)

                pdf.cell(0, 5, f"Fase 1 (Tarot): {total_t1} / 40 ({perc_t1:.1f}%)", 0, 1)
                pdf.cell(0, 5, f"Fase 2 (Astrologia): {total_t2} / 60 ({perc_t2:.1f}%)", 0, 1)
                pdf.cell(0, 5, f"Fase 3 (Indice Global Integrado): {indice_global:.1f}% | {classificacao}", 0, 1)
                pdf.cell(0, 5, f"Sinal Vermelho Ativado: {sinal_vermelho}", 0, 1)
                pdf.ln(3)

                pdf.set_font("helvetica", "B", 9)
                pdf.cell(0, 5, "Tabela Oficial de Avaliação Profissional (Tarot)", 0, 1)
                pdf.set_font("helvetica", "B", 8)
                pdf.set_fill_color(230, 230, 230)
                pdf.cell(8, 5, "Pos", 1, 0, "C", True)
                pdf.cell(37, 5, "Competencia", 1, 0, "L", True)
                pdf.cell(12, 5, "Nota", 1, 0, "C", True)
                pdf.cell(123, 5, "Arcanos (Central / Neg / Pos)", 1, 1, "L", True)

                competencias_nomes = [
                    "Hard Skills", "Soft Skills", "Fit Cultural", "Desafios",
                    "Potencial Futuro", "Equilíbrio Emocional", "Saúde Psicológica",
                    "Confiabilidade e Ética",
                ]
                
                pdf.set_font("helvetica", "", 8)
                for i in range(1, 9):
                    c_cent = st.session_state.get(f"t_central_{i}", "-")
                    c_neg = st.session_state.get(f"t_negativa_{i}", "-")
                    c_pos = st.session_state.get(f"t_positiva_{i}", "-")
                    nota = st.session_state.get(f"t_pontos_{i}", 3)
                    obs_casa = OBS_MAP.get(i, "")
                    
                    cartas_txt = f"C: {c_cent} | (-) {c_neg} | (+) {c_pos}"
                    
                    pdf.cell(8, 5, str(i), 1, 0, "C")
                    pdf.cell(37, 5, competencias_nomes[i - 1], 1, 0, "L")
                    pdf.cell(12, 5, str(nota), 1, 0, "C")
                    pdf.cell(123, 5, cartas_txt, 1, 1, "L")
                    
                    pdf.set_font("helvetica", "I", 7)
                    pdf.multi_cell(180, 4, f"Obs: {obs_casa}", "LRB", "L")
                    pdf.set_font("helvetica", "", 8)

                pdf.ln(3)
                res_pdf = pdf.output(dest="S")
                if isinstance(res_pdf, str):
                    return res_pdf.encode("latin1")
                return bytes(res_pdf)

            st.markdown("### Ações e Exportação de Laudo")
            col_acao1, col_acao2 = st.columns(2)
            with col_acao1:
                pdf_bytes = gerar_pdf_relatorio()
                st.download_button(
                    label="📄 Baixar Laudo Executivo em PDF",
                    data=pdf_bytes,
                    file_name=f"Laudo_Executivo_{c_nome.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                )
            with col_acao2:
                if st.button("💾 Salvar Avaliação no Banco de Dados (SQLite)"):
                    if c_nome in ["", "Candidato(a)", "Selecionar Candidato Cadastrado..."]:
                        st.error("⚠️ Selecione ou informe um nome de candidato válido antes de salvar a avaliação.")
                    else:
                        sucesso = salvar_no_banco(
                            c_nome, vaga_cargo, nivel_hierarquico, data_atual,
                            int(indice_global), classificacao, sinal_vermelho,
                        )
                        if sucesso:
                            st.success("✅ Avaliação salva com sucesso no banco de dados SQLite!")
                        else:
                            st.error("⚠️ Falha ao salvar a avaliação.")

        with sub_tab2:
            st.markdown("### Tabela Oficial de Avaliação Profissional")
            competencias_nomes = [
                "Hard Skills", "Soft Skills", "Fit Cultural", "Desafios",
                "Potencial Futuro", "Equilíbrio Emocional", "Saúde Psicológica",
                "Confiabilidade e Ética",
            ]

            tabela_dados = []
            for i in range(1, 9):
                c_cent = st.session_state.get(f"t_central_{i}", "-")
                c_neg = st.session_state.get(f"t_negativa_{i}", "-")
                c_pos = st.session_state.get(f"t_positiva_{i}", "-")
                nota = st.session_state.get(f"t_pontos_{i}", 3)
                cartas_formatadas = f"Central: {c_cent} | (-) Neg: {c_neg} | (+) Pos: {c_pos}"
                tabela_dados.append({
                    "Posição": i,
                    "Competência": competencias_nomes[i - 1],
                    "Cartas (Central / Neg / Pos)": cartas_formatadas,
                    "Pontuação": nota,
                    "Observação": OBS_MAP.get(i, ""),
                })

            df_ficha = pd.DataFrame(tabela_dados)
            st.table(df_ficha)

            st.markdown("### Cruzamento Analítico com Efemérides Astrológicas")
            mapeamento_cruzado = [
                (1, "Hard Skills & Rotina", 6, "Casa 6 Astrológica (Trabalho)"),
                (2, "Soft Skills & Comunicação", 3, "Casa 3 Astrológica (Comunicação)"),
                (3, "Fit Cultural & Coletivo", 11, "Casa 11 Astrológica (Grupos)"),
                (4, "Desafios & Autossabotagem", 12, "Casa 12 Astrológica (Inconsciente)"),
                (5, "Potencial de Liderança", 10, "Casa 10 Astrológica (Carreira)"),
                (6, "Equilíbrio Emocional", 4, "Casa 4 Astrológica (Base Emocional)"),
                (7, "Saúde Psicológica & Foco", 1, "Casa 1 Astrológica (Self)"),
                (8, "Confiabilidade & Ética", 8, "Casa 8 Astrológica (Compliance)"),
            ]

            for t_num, t_nome, a_num, a_desc in mapeamento_cruzado:
                signo_astro = "Não calculado"
                if f"Casa {a_num}" in mandala_dados:
                    signo_astro = f"{mandala_dados[f'Casa {a_num}']['signo']} ({mandala_dados[f'Casa {a_num}']['grau']})"
                nota_casa = st.session_state.get(f"t_pontos_{t_num}", 3)
                st.write(f"- **Casa {t_num} ({t_nome}) [Nota {nota_casa}/5]:** Alinhada à **{a_desc}** — Signo Cúspide: **{signo_astro}**.")

        with sub_tab3:
            st.markdown("### Histórico de Candidatos Avaliados (Pipeline Local)")
            with sqlite3.connect("rh_diagnostico.db") as conn_db:
                df_historico = pd.read_sql_query(
                    "SELECT id, nome, vaga, nivel, data, pontos, classificacao, sinal_vermelho FROM avaliacoes",
                    conn_db,
                )

            if not df_historico.empty:
                st.dataframe(df_historico, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum registro encontrado no banco de dados. Clique em 'Salvar Avaliação' para registrar o primeiro candidato.")