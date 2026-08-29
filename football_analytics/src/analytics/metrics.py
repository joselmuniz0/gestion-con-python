"""
Cálculo de métricas físicas y tácticas.
Produce los registros que se almacenan en metricas_jugador_partido y metricas_equipo_partido.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# Umbrales de intensidad según estándares FIFA/GPS
UMBRAL_SPRINT_KMH = 25.0
UMBRAL_ALTA_INT_KMH = 19.8
UMBRAL_MEDIA_INT_KMH = 14.4
UMBRAL_BAJA_INT_KMH = 11.0
UMBRAL_ACELERACION_ALTA = 3.0  # m/s²


@dataclass
class MetricasJugador:
    jugador_id: int
    sesion_id: int
    partido_id: int | None = None

    # Distancias
    distancia_total_m: float = 0.0
    distancia_sprint_m: float = 0.0
    distancia_alta_int_m: float = 0.0
    distancia_media_int_m: float = 0.0
    distancia_baja_int_m: float = 0.0

    # Velocidad
    velocidad_max_kmh: float = 0.0
    velocidad_media_kmh: float = 0.0
    sprints_total: int = 0

    # Aceleración
    aceleracion_max: float = 0.0
    desaceleracion_max: float = 0.0
    aceleraciones_alta_int: int = 0
    desaceleraciones_alta_int: int = 0

    # Arquero
    achiques_realizados: int = 0
    distancia_achique_media_m: float = 0.0
    salidas_area_grande: int = 0
    salidas_area_chica: int = 0
    tiempo_en_area_chica_seg: float = 0.0
    tiempo_en_area_grande_seg: float = 0.0
    posicion_media_x: float = 0.0
    posicion_media_y: float = 0.0
    cobertura_lateral_m: float = 0.0

    frames_analizados: int = 0
    tiempo_activo_seg: float = 0.0


def calcular_metricas_jugador(
    df: pd.DataFrame,
    jugador_id: int,
    sesion_id: int,
    fps: float,
    partido_id: int | None = None,
) -> MetricasJugador:
    """
    Calcula métricas físicas de un jugador a partir del DataFrame de tracking.
    df debe tener columnas: frame_numero, x_campo, y_campo, velocidad_kmh, aceleracion
    """
    m = MetricasJugador(jugador_id=jugador_id, sesion_id=sesion_id, partido_id=partido_id)
    dt = 1.0 / fps

    if df.empty:
        return m

    df_clean = df.dropna(subset=["velocidad_kmh"]).copy()
    m.frames_analizados = len(df)
    m.tiempo_activo_seg = round(len(df) * dt, 2)

    # --- Distancias por zona de intensidad ---
    dx = df_clean["x_campo"].diff().fillna(0)
    dy = df_clean["y_campo"].diff().fillna(0)
    dist_frame = np.sqrt(dx**2 + dy**2)

    m.distancia_total_m = round(float(dist_frame.sum()), 1)
    m.distancia_sprint_m = round(
        float(dist_frame[df_clean["velocidad_kmh"] > UMBRAL_SPRINT_KMH].sum()), 1
    )
    m.distancia_alta_int_m = round(
        float(dist_frame[
            (df_clean["velocidad_kmh"] > UMBRAL_ALTA_INT_KMH)
            & (df_clean["velocidad_kmh"] <= UMBRAL_SPRINT_KMH)
        ].sum()), 1
    )
    m.distancia_media_int_m = round(
        float(dist_frame[
            (df_clean["velocidad_kmh"] > UMBRAL_MEDIA_INT_KMH)
            & (df_clean["velocidad_kmh"] <= UMBRAL_ALTA_INT_KMH)
        ].sum()), 1
    )
    m.distancia_baja_int_m = round(
        float(dist_frame[df_clean["velocidad_kmh"] <= UMBRAL_MEDIA_INT_KMH].sum()), 1
    )

    # --- Velocidad ---
    m.velocidad_max_kmh = round(float(df_clean["velocidad_kmh"].max()), 2)
    m.velocidad_media_kmh = round(float(df_clean["velocidad_kmh"].mean()), 2)

    # Conteo de sprints: eventos continuos > 25 km/h con al menos 2 frames
    en_sprint = df_clean["velocidad_kmh"] > UMBRAL_SPRINT_KMH
    m.sprints_total = int((en_sprint & ~en_sprint.shift(1, fill_value=False)).sum())

    # --- Aceleración ---
    if "aceleracion" in df_clean.columns:
        acc = df_clean["aceleracion"].dropna()
        if not acc.empty:
            m.aceleracion_max = round(float(acc.max()), 3)
            m.desaceleracion_max = round(float(acc.min()), 3)
            m.aceleraciones_alta_int = int((acc > UMBRAL_ACELERACION_ALTA).sum())
            m.desaceleraciones_alta_int = int((acc < -UMBRAL_ACELERACION_ALTA).sum())

    # --- Posición media ---
    m.posicion_media_x = round(float(df["x_campo"].mean()), 3)
    m.posicion_media_y = round(float(df["y_campo"].mean()), 3)
    m.cobertura_lateral_m = round(
        float(df["y_campo"].max() - df["y_campo"].min()), 2
    )

    # --- Métricas específicas de arquero ---
    # Área chica: x < 5.5m; Área grande: x < 16.5m
    mask_area_chica = df["x_campo"] <= 5.5
    mask_area_grande = df["x_campo"] <= 16.5

    m.tiempo_en_area_chica_seg = round(float(mask_area_chica.sum() * dt), 2)
    m.tiempo_en_area_grande_seg = round(float(mask_area_grande.sum() * dt), 2)

    # Salidas del área grande: frames donde cruza la línea de 16.5m saliendo
    fuera_area = df["x_campo"] > 16.5
    m.salidas_area_grande = int(
        (fuera_area & ~fuera_area.shift(1, fill_value=False)).sum()
    )
    fuera_chica = df["x_campo"] > 5.5
    m.salidas_area_chica = int(
        (fuera_chica & ~fuera_chica.shift(1, fill_value=False)).sum()
    )

    # Achiques: salidas rápidas (velocidad > 15 km/h) fuera del área grande
    if "velocidad_kmh" in df.columns:
        achique_mask = (df["x_campo"] > 16.5) & (df["velocidad_kmh"] > 15.0)
        m.achiques_realizados = int(
            (achique_mask & ~achique_mask.shift(1, fill_value=False)).sum()
        )
        if m.achiques_realizados > 0:
            achiques_df = df[achique_mask]
            m.distancia_achique_media_m = round(
                float(achiques_df["distancia_arco_propio"].mean())
                if "distancia_arco_propio" in df.columns else 0.0,
                2,
            )

    return m


def calcular_metricas_equipo(
    df_equipo: pd.DataFrame,
    equipo_id: int,
    sesion_id: int,
    partido_id: int | None = None,
) -> dict:
    """
    Métricas colectivas del equipo: posesión, compacidad, línea defensiva.
    df_equipo: tracking de todos los jugadores del equipo en cada frame.
    """
    if df_equipo.empty:
        return {}

    metricas = {
        "sesion_id": sesion_id,
        "equipo_id": equipo_id,
        "partido_id": partido_id,
    }

    # Línea defensiva: posición media en X del bloque defensivo
    metricas["linea_defensiva_media_m"] = round(
        float(df_equipo.groupby("frame_numero")["x_campo"].min().mean()), 2
    )

    # Profundidad y amplitud
    metricas["profundidad_media_m"] = round(
        float(
            (df_equipo.groupby("frame_numero")["x_campo"].max()
             - df_equipo.groupby("frame_numero")["x_campo"].min()).mean()
        ), 2
    )
    metricas["amplitud_media_m"] = round(
        float(
            (df_equipo.groupby("frame_numero")["y_campo"].max()
             - df_equipo.groupby("frame_numero")["y_campo"].min()).mean()
        ), 2
    )

    # Compacidad: área del convex hull del equipo por frame (promedio)
    try:
        from scipy.spatial import ConvexHull  # type: ignore

        areas = []
        for _, frame_df in df_equipo.groupby("frame_numero"):
            pts = frame_df[["x_campo", "y_campo"]].values
            if len(pts) >= 3:
                try:
                    hull = ConvexHull(pts)
                    areas.append(hull.volume)  # en 2D, .volume = área
                except Exception:
                    pass
        if areas:
            metricas["compacidad_media_m2"] = round(float(np.mean(areas)), 2)
    except ImportError:
        pass

    return metricas


def generar_reporte_arquero(
    df_tracking: pd.DataFrame,
    jugador_id: int,
    fps: float,
    nombre_arquero: str = "Arquero",
) -> str:
    """Genera un reporte textual de las métricas del arquero."""
    df_arq = df_tracking[df_tracking["jugador_id"] == jugador_id].copy()
    m = calcular_metricas_jugador(df_arq, jugador_id, -1, fps)

    lineas = [
        f"{'='*60}",
        f"  REPORTE FÍSICO-TÁCTICO — {nombre_arquero.upper()}",
        f"{'='*60}",
        "",
        "MÉTRICAS FÍSICAS",
        f"  Distancia total:        {m.distancia_total_m / 1000:.2f} km",
        f"  Distancia sprint:       {m.distancia_sprint_m:.0f} m",
        f"  Velocidad máxima:       {m.velocidad_max_kmh:.1f} km/h",
        f"  Velocidad media:        {m.velocidad_media_kmh:.1f} km/h",
        f"  Sprints (>25 km/h):     {m.sprints_total}",
        f"  Aceleraciones alta int: {m.aceleraciones_alta_int}",
        "",
        "MÉTRICAS DE PORTERÍA",
        f"  Achiques realizados:    {m.achiques_realizados}",
        f"  Distancia media achique:{m.distancia_achique_media_m:.1f} m",
        f"  Salidas área grande:    {m.salidas_area_grande}",
        f"  Salidas área chica:     {m.salidas_area_chica}",
        f"  Tiempo en área chica:   {m.tiempo_en_area_chica_seg / 60:.1f} min",
        f"  Tiempo en área grande:  {m.tiempo_en_area_grande_seg / 60:.1f} min",
        "",
        "POSICIONAMIENTO",
        f"  Posición media (x):     {m.posicion_media_x:.1f} m",
        f"  Posición media (y):     {m.posicion_media_y:.1f} m",
        f"  Cobertura lateral:      {m.cobertura_lateral_m:.1f} m",
        f"{'='*60}",
    ]
    return "\n".join(lineas)
