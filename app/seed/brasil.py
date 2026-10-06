"""Brazil configuration seed. Real, not fictional.

Axes and poles are initial HYPOTHESES (es_hipotesis=True), versioned with
vigente_desde. The outlet list is for ingestion only: no outlet receives a
position here. Positions are estimated by the system (Phase 2).
Context lines (election dates) come from the commissioning prompt and are
marked for the country team to verify; results, candidates and the incoming
government are deliberately absent from code.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

HERE = Path(__file__).parent
START = date(2026, 10, 1)

AXES = [
    # slug, nombre, tipo, activo, orden, descripcion, poles[(slug, etiqueta)]
    ("lulismo-bolsonarismo", "Lulismo / bolsonarismo", "principal", True, 0,
     "Fratura que ordena boa parte do ecossistema desde 2018. Nomes dos polos a revisar após a eleição de 2026.",
     [("campo-lulista", "Campo lulista e aliados"), ("campo-bolsonarista", "Campo bolsonarista e aliados")]),
    ("centro-sul-norte-nordeste", "Centro-Sul / Norte-Nordeste", "territorial", True, 1,
     "A imprensa nacional se concentra no Sudeste; voto e agenda regional diferem de forma marcada.",
     [("centro-sul", "Veículos do eixo Rio–São Paulo–Sul"), ("norte-nordeste", "Veículos regionais do Norte e Nordeste")]),
    ("institucionalismo-antissistema", "Institucionalismo / antissistema", "secundario", True, 2,
     "Explica cobertura que não se encaixa no eixo 1, como decisões judiciais e regulação de plataformas.",
     [("institucionalista", "Defensores de STF, TSE e Congresso como árbitros"), ("antissistema", "Críticos dessas instituições")]),
    ("agenda-de-costumes", "Agenda de costumes", "candidato", False, 3,
     "Candidato: avaliar se acrescenta informação ao eixo 1 antes de ativar.",
     [("conservador-religioso", "Conservadorismo religioso"), ("progressista-secular", "Progressismo secular")]),
]

TRANSLATED_AXES = {
    "es": {
        "Lulismo / bolsonarismo": "Lulismo / bolsonarismo", "Centro-Sul / Norte-Nordeste": "Centro-Sur / Norte-Nordeste",
        "Institucionalismo / antissistema": "Institucionalismo / antisistema", "Agenda de costumes": "Agenda de costumbres",
        "Campo lulista e aliados": "Campo lulista y aliados", "Campo bolsonarista e aliados": "Campo bolsonarista y aliados",
        "Veículos do eixo Rio–São Paulo–Sul": "Medios del eje Río–São Paulo–Sur",
        "Veículos regionais do Norte e Nordeste": "Medios regionales del Norte y Nordeste",
        "Defensores de STF, TSE e Congresso como árbitros": "Defensores del STF, TSE y Congreso como árbitros",
        "Críticos dessas instituições": "Críticos de esas instituciones",
        "Conservadorismo religioso": "Conservadurismo religioso", "Progressismo secular": "Progresismo secular",
    },
    "en": {
        "Lulismo / bolsonarismo": "Lulismo / Bolsonarismo", "Centro-Sul / Norte-Nordeste": "Centre-South / North-Northeast",
        "Institucionalismo / antissistema": "Institutionalism / anti-system", "Agenda de costumes": "Social-values agenda",
        "Campo lulista e aliados": "Lula camp and allies", "Campo bolsonarista e aliados": "Bolsonaro camp and allies",
        "Veículos do eixo Rio–São Paulo–Sul": "Rio–São Paulo–South outlets",
        "Veículos regionais do Norte e Nordeste": "Regional outlets of the North and Northeast",
        "Defensores de STF, TSE e Congresso como árbitros": "Defenders of the STF, TSE and Congress as arbiters",
        "Críticos dessas instituições": "Critics of those institutions",
        "Conservadorismo religioso": "Religious conservatism", "Progressismo secular": "Secular progressivism",
    },
}

# Ingestion list only. tipo, alcance, region. No positions, no pole.
OUTLETS = [
    ("Folha de S.Paulo", "diario", "nacional", "SE", "https://www.folha.uol.com.br"),
    ("O Estado de S. Paulo (Estadão)", "diario", "nacional", "SE", "https://www.estadao.com.br"),
    ("O Globo", "diario", "nacional", "SE", "https://oglobo.globo.com"),
    ("g1", "digital", "nacional", "SE", "https://g1.globo.com"),
    ("UOL", "digital", "nacional", "SE", "https://www.uol.com.br"),
    ("Metrópoles", "digital", "nacional", "CO", "https://www.metropoles.com"),
    ("Poder360", "digital", "nacional", "CO", "https://www.poder360.com.br"),
    ("CNN Brasil", "tv", "nacional", "SE", "https://www.cnnbrasil.com.br"),
    ("Jovem Pan", "radio", "nacional", "SE", "https://jovempan.com.br"),
    ("Gazeta do Povo", "diario", "nacional", "S", "https://www.gazetadopovo.com.br"),
    ("Revista Oeste", "digital", "nacional", "SE", "https://revistaoeste.com"),
    ("CartaCapital", "digital", "nacional", "SE", "https://www.cartacapital.com.br"),
    ("Brasil de Fato", "digital", "nacional", "SE", "https://www.brasildefato.com.br"),
    ("Correio Braziliense", "diario", "regional", "CO", "https://www.correiobraziliense.com.br"),
    ("Jornal do Commercio", "diario", "regional", "NE", "https://jc.uol.com.br"),
    ("Diário do Nordeste", "diario", "regional", "NE", "https://diariodonordeste.verdesmares.com.br"),
    ("A Tarde", "diario", "regional", "NE", "https://atarde.com.br"),
    ("O Liberal", "diario", "regional", "N", "https://www.oliberal.com"),
    ("GZH", "digital", "regional", "S", "https://gauchazh.clicrbs.com.br"),
    ("Band (portal)", "tv", "nacional", "SE", "https://www.band.uol.com.br"),
    ("SBT News", "tv", "nacional", "SE", "https://sbtnews.sbt.com.br"),
    ("Record (R7)", "tv", "nacional", "SE", "https://noticias.r7.com"),
]
OFFICIAL = [
    ("Agência Brasil (EBC)", "agencia", "nacional", "CO", "https://agenciabrasil.ebc.com.br"),
]

# Primary sources (used as fuente_primaria; listed here for the methodology page).
PRIMARY_SOURCES = [
    "Diário Oficial da União", "Supremo Tribunal Federal (STF)", "Tribunal Superior Eleitoral (TSE)",
    "Câmara dos Deputados", "Senado Federal", "IBGE", "Banco Central do Brasil", "Tesouro Nacional",
    "Tribunal de Contas da União e tribunais de contas estaduais",
]

DATA_GAPS = [
    {"pt": "WhatsApp, YouTube e rádio sem transcrição não entram na contagem. Boa parte da informação política no Brasil circula por esses canais; a cobertura medida aqui é a de texto publicado na web.",
     "es": "WhatsApp, YouTube y la radio sin transcripción no entran en el conteo. Buena parte de la información política en Brasil circula por esos canales; la cobertura medida aquí es la del texto publicado en la web.",
     "en": "WhatsApp, YouTube and untranscribed radio are not counted. Much political information in Brazil circulates through those channels; the coverage measured here is text published on the web."},
]

CONTEXT = [
    {"texto": "Primeiro turno das eleições gerais: 4 de outubro de 2026. Segundo turno previsto: 25 de outubro de 2026.",
     "fuente": "Prompt de encomenda do projeto; a confirmar pela equipe com o calendário do TSE", "fecha": "2026-10-05",
     "verificado": False},
]

EXCLUSIONS = [
    ("Verde e amarelo combinados (bandeira; símbolo apropriado pelo campo bolsonarista)", ["#009C3B", "#FFDF00"], "emblema"),
    ("Vermelho (associado ao PT)", ["#CC0000", "#E30613"], "partidario"),
    ("Azul e amarelo partidários", ["#0047AB", "#FFD700"], "partidario"),
    ("Bandeira nacional", ["#009C3B", "#FFDF00", "#002776"], "emblema"),
    ("Brasão da República", [], "emblema"),
    ("Camisa da seleção", ["#FFDF00", "#009C3B"], "emblema"),
    ("Símbolos religiosos", [], "religioso"),
    ("Imagens do 8 de janeiro de 2023", [], "conflicto"),
    ("Imagens de outros conflitos recentes", [], "conflicto"),
]

CULTURAL_CANDIDATES = [
    ("Barro e cerâmica", "material", "candidata", "Avaliar: barro cozido pode cair perto do vermelho excluído."),
    ("Algodão cru", "material", "candidata", "Base provisória do color de marca (pardo de algodão)."),
    ("Madeira", "material", "candidata", ""),
    ("Pedra", "material", "candidata", "Tom derivado para Política (gris pedra)."),
    ("Rotulação popular (letreiros pintados à mão)", "tipografia", "candidata", "Possível raiz da tipografia de títulos; checar marca de classe/região."),
    ("Sinalização viária", "tipografia", "candidata", "Infraestrutura comum a cidade e campo."),
    ("Imprensa de jornais do interior", "tipografia", "candidata", ""),
    ("Paisagem e luz", "paisaje", "candidata", "Paridade territorial obrigatória."),
    ("Pedra portuguesa de Copacabana", "material", "solo_seccion", "Marca regional forte: só em Sociedade e cultura se passar no teste cego."),
    ("Xilogravura de cordel", "tipografia", "solo_seccion", "Marca regional forte (Nordeste): idem."),
    ("Renda de bilro", "material", "solo_seccion", "Marca regional forte: idem."),
    ("Arquitetura de Brasília", "paisaje", "solo_seccion", "Associada ao poder federal: nunca na cabeça."),
]

# Provisional theme tokens (núcleo + capa país). Marked provisional until inventory and blind test.
THEME_TOKENS = {
    "font_read": "Source Serif 4", "font_ui": "Inter",
    "font_headline": "Source Serif 4 (provisória; família de raiz brasileira pendente do inventário)",
    "brand": "#5E5546",       # pardo de algodão cru, oscuro y poco saturado (provisional)
    "brand_politica": "#5C5A55",  # derivado hacia gris piedra
    "pole_a": "#4C6A8B", "pole_b": "#7F5E7C",  # equal CIELAB L* (44) and chroma (22); blind test pending
    "accent_ui": "#1F5E8C",
    "status_scale": ["#3A3A3A", "#5C5C5C", "#8A8A8A", "#B5B5B5", "transparent"],
}
SECTIONS = [
    ("politica", "#5C5A55", False, "Instituições e documentos, sem rostos em ação", 4),
    ("justica", "#5C5A55", False, "Sedes e documentos", 4),
    ("economia", "#5E5546", False, "Locais de trabalho e mercados, paridade capital/regiões", 3),
    ("meio-ambiente", "#6A6355", True, "Território e paisagem com escala humana", 2),
    ("sociedade", "#6E6556", True, "Ofícios, espaços públicos, vida cotidiana", 1),
]


def seed_brasil(s: Session) -> m.Country:
    country = s.get(m.Country, "BR")
    if country is None:
        country = m.Country(id="BR", nombre="Brasil", idiomas=["pt", "es", "en"], zona_horaria="America/Sao_Paulo",
                            fecha_inicializacion=START, contexto=CONTEXT, data_gaps=DATA_GAPS)
        s.add(country)
        s.flush()
    if not s.scalars(select(m.Cleavage).where(m.Cleavage.country_id == "BR")).first():
        for slug, nombre, tipo, activo, orden, desc, poles in AXES:
            c = m.Cleavage(country_id="BR", slug=slug, nombre=nombre, tipo=tipo, activo=activo, orden=orden,
                           descripcion=desc, es_hipotesis=True, vigente_desde=START)
            s.add(c)
            s.flush()
            for i, (pslug, etq) in enumerate(poles):
                s.add(m.Pole(cleavage_id=c.id, slug=pslug, etiqueta=etq, orden=i))
            s.flush()
            for lang, table in TRANSLATED_AXES.items():
                _tr(s, "cleavage", c.id, "nombre", lang, table.get(nombre, nombre))
                for p in c.poles:
                    _tr(s, "pole", p.id, "etiqueta", lang, table.get(p.etiqueta, p.etiqueta))
            s.add(m.Palette(country_id="BR", cleavage_id=c.id, provisional=True, contraste_verificado=True,
                            asignacion_polo_color={poles[0][0]: THEME_TOKENS["pole_a"], poles[1][0]: THEME_TOKENS["pole_b"]}))
    if not s.scalars(select(m.Outlet).where(m.Outlet.country_id == "BR", m.Outlet.es_ficticio.is_(False))).first():
        for nombre, tipo, alcance, region, url in OUTLETS:
            s.add(m.Outlet(country_id="BR", nombre=nombre, tipo=tipo, alcance=alcance, region=region, url=url,
                           idioma="pt", activo=True, feeds=[]))
        for nombre, tipo, alcance, region, url in OFFICIAL:
            s.add(m.Outlet(country_id="BR", nombre=nombre, tipo=tipo, alcance=alcance, region=region, url=url,
                           idioma="pt", es_fuente_oficial=True, activo=True, feeds=[]))
    if not s.scalars(select(m.LoadedTerm).where(m.LoadedTerm.country_id == "BR")).first():
        for t in json.loads((HERE / "loaded_terms_br.json").read_text(encoding="utf-8")):
            s.add(m.LoadedTerm(country_id="BR", vigente_desde=START, **t))
    if not s.scalars(select(m.ExclusionList).where(m.ExclusionList.country_id == "BR")).first():
        for elemento, colores, motivo in EXCLUSIONS:
            s.add(m.ExclusionList(country_id="BR", elemento=elemento, colores=colores, motivo=motivo,
                                  confirmado=False, vigente_desde=START))
        for nombre, fam, dec, just in CULTURAL_CANDIDATES:
            s.add(m.CulturalReference(country_id="BR", nombre=nombre, familia=fam, decision=dec, justificacion=just))
    if not s.scalars(select(m.ThemeCountry).where(m.ThemeCountry.country_id == "BR")).first():
        th = m.ThemeCountry(country_id="BR", tipografia_titulares=THEME_TOKENS["font_headline"],
                            color_marca=THEME_TOKENS["brand"], textura_id=None, provisional=True,
                            direccion_foto="Luz natural, território com escala humana, paridade Norte/Nordeste/Centro-Sul.",
                            tokens=THEME_TOKENS, vigente_desde=START)
        s.add(th)
        s.flush()
        for sec, tono, tex, img, aust in SECTIONS:
            s.add(m.ThemeSection(theme_country_id=th.id, seccion=sec, tono_derivado=tono, uso_textura=tex,
                                 direccion_imagen=img, austeridad=aust))
    s.flush()
    return country


def _tr(s: Session, tipo: str, sid: int, campo: str, lang: str, texto: str, claim_ids=None,
        metodo: str = "maquina_sin_revisar", revisor: str | None = None) -> None:
    s.add(m.Translation(source_tipo=tipo, source_id=sid, campo=campo, idioma=lang, texto=texto,
                        claim_ids=claim_ids or [], metodo=metodo, revisor=revisor))
