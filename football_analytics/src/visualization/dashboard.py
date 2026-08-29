"""
Dashboard interactivo con Streamlit.
Punto de entrada: streamlit run src/visualization/dashboard.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Asegurar que el módulo raíz esté en el path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from football_analytics.src.analytics.metrics import (
    calcular_metricas_jugador,
    generar_reporte_arquero,
)
from football_analytics.src.db.database import execute_raw, init_db
from football_analytics.src.visualization.heatmaps import (
    grafico_perfil_fisico,
    grafico_velocidad_tiempo,
    heatmap_posicional,
    mapa_achiques,
    trazar_trayectoria,
)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Football Analytics Platform",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inicializar DB (SQLite en dev)
@st.cache_resource
def _init():
    init_db()

_init()

# ---------------------------------------------------------------------------
# SIDEBAR — FILTROS
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚽ Football Analytics")
    st.markdown("---")

    partidos = execute_raw("""
        SELECT p.id, eq_l.nombre || ' vs ' || eq_v.nombre || ' (' ||
               strftime('%d/%m/%Y', p.fecha_partido) || ')' AS descripcion
        FROM partidos p
        JOIN equipos eq_l ON eq_l.id = p.equipo_local_id
        JOIN equipos eq_v ON eq_v.id = p.equipo_visitante_id
        ORDER BY p.fecha_partido DESC
        LIMIT 50
    """)

    if not partidos:
        st.warning("No hay partidos cargados. Carga datos primero.")
        st.stop()

    opciones_partidos = {r["id"]: r["descripcion"] for r in partidos}
    partido_id = st.selectbox(
        "Partido",
        options=list(opciones_partidos.keys()),
        format_func=lambda x: opciones_partidos[x],
    )

    jugadores = execute_raw("""
        SELECT DISTINCT j.id,
               j.nombre || ' ' || j.apellido || ' (' || j.posicion || ')' AS nombre_completo
        FROM tracking_jugadores tj
        JOIN sesiones_analisis sa ON sa.id = tj.sesion_id
        JOIN videos v             ON v.id = sa.video_id
        JOIN jugadores j          ON j.id = tj.jugador_id
        WHERE v.partido_id = :pid AND tj.jugador_id IS NOT NULL
    """, {"pid": partido_id})

    if not jugadores:
        st.warning("No hay tracking para este partido.")
        st.stop()

    opciones_jugadores = {r["id"]: r["nombre_completo"] for r in jugadores}
    jugador_id = st.selectbox(
        "Jugador",
        options=list(opciones_jugadores.keys()),
        format_func=lambda x: opciones_jugadores[x],
    )

    vista = st.radio(
        "Vista",
        ["Heatmap", "Trayectoria", "Perfil Físico", "Achiques", "Velocidad", "Reporte"],
    )

# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def cargar_tracking(partido_id: int, jugador_id: int) -> pd.DataFrame:
    rows = execute_raw("""
        SELECT tj.frame_numero, tj.timestamp_seg,
               tj.x_campo, tj.y_campo,
               tj.velocidad_kmh, tj.velocidad_ms, tj.aceleracion,
               tj.direccion_deg, tj.presion_rival,
               tj.distancia_arco_propio, tj.distancia_balon,
               tj.rivales_en_5m, tj.interpolado,
               v.fps
        FROM tracking_jugadores tj
        JOIN sesiones_analisis sa ON sa.id = tj.sesion_id
        JOIN videos v             ON v.id = sa.video_id
        WHERE v.partido_id = :pid
          AND tj.jugador_id = :jid
          AND tj.interpolado = 0
        ORDER BY tj.frame_numero
    """, {"pid": partido_id, "jid": jugador_id})
    return pd.DataFrame(rows)

df = cargar_tracking(partido_id, jugador_id)
nombre_jugador = opciones_jugadores[jugador_id]
fps = float(df["fps"].iloc[0]) if not df.empty and "fps" in df.columns else 25.0

# ---------------------------------------------------------------------------
# KPIs RÁPIDOS
# ---------------------------------------------------------------------------

st.title(f"Dashboard — {nombre_jugador}")

if not df.empty:
    m = calcular_metricas_jugador(df.assign(jugador_id=jugador_id), jugador_id, -1, fps)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Distancia total", f"{m.distancia_total_m / 1000:.2f} km")
    col2.metric("Vel. máxima", f"{m.velocidad_max_kmh:.1f} km/h")
    col3.metric("Sprints", str(m.sprints_total))
    col4.metric("Achiques", str(m.achiques_realizados))
    col5.metric("Frames analizados", f"{m.frames_analizados:,}")

    st.markdown("---")

# ---------------------------------------------------------------------------
# VISTAS
# ---------------------------------------------------------------------------

if df.empty:
    st.error("No hay datos de tracking para este jugador y partido.")
else:
    if vista == "Heatmap":
        fig = heatmap_posicional(
            df.assign(jugador_id=jugador_id),
            titulo=f"Heatmap — {nombre_jugador}",
        )
        st.pyplot(fig, use_container_width=True)

    elif vista == "Trayectoria":
        fig = trazar_trayectoria(
            df.assign(jugador_id=jugador_id),
            titulo=f"Trayectoria — {nombre_jugador}",
        )
        st.pyplot(fig, use_container_width=True)

    elif vista == "Perfil Físico":
        metricas_dict = {
            "velocidad_max_kmh": m.velocidad_max_kmh,
            "sprints_total": m.sprints_total,
            "distancia_total_m": m.distancia_total_m,
            "achiques_realizados": m.achiques_realizados,
            "cobertura_lateral_m": m.cobertura_lateral_m,
            "aceleraciones_alta_int": m.aceleraciones_alta_int,
        }
        fig = grafico_perfil_fisico(metricas_dict, nombre=nombre_jugador)
        st.pyplot(fig, use_container_width=False)

    elif vista == "Achiques":
        fig = mapa_achiques(
            df.assign(jugador_id=jugador_id),
            titulo=f"Mapa de Achiques — {nombre_jugador}",
        )
        st.pyplot(fig, use_container_width=True)

    elif vista == "Velocidad":
        fig = grafico_velocidad_tiempo(
            df,
            fps=fps,
            titulo=f"Perfil de Velocidad — {nombre_jugador}",
        )
        st.pyplot(fig, use_container_width=True)

    elif vista == "Reporte":
        reporte = generar_reporte_arquero(
            df.assign(jugador_id=jugador_id),
            jugador_id=jugador_id,
            fps=fps,
            nombre_arquero=nombre_jugador,
        )
        st.code(reporte, language=None)

    # Tabla de datos crudos (expandible)
    with st.expander("Ver datos de tracking"):
        st.dataframe(df.head(500), use_container_width=True)
