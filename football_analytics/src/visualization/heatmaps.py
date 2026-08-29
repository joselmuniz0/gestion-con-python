"""
Visualización táctica: heatmaps, trayectorias, análisis espacial.
Produce figuras de Matplotlib/Seaborn y datos para Streamlit.
"""

from __future__ import annotations

from typing import Sequence

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

# Dimensiones FIFA
LARGO = 105.0
ANCHO = 68.0


def _dibujar_cancha(ax: plt.Axes, color_cesped: str = "#1a7a1a") -> None:
    """Dibuja una cancha de fútbol estándar sobre el Axes dado."""
    ax.set_facecolor(color_cesped)
    ax.set_xlim(0, LARGO)
    ax.set_ylim(0, ANCHO)
    ax.set_aspect("equal")
    ax.axis("off")

    line_kw = dict(color="white", linewidth=1.5, zorder=2)

    # Borde
    ax.plot([0, LARGO, LARGO, 0, 0], [0, 0, ANCHO, ANCHO, 0], **line_kw)
    # Línea media
    ax.axvline(LARGO / 2, **line_kw)
    # Círculo central
    circulo = plt.Circle((LARGO / 2, ANCHO / 2), 9.15, fill=False, **line_kw)
    ax.add_patch(circulo)
    ax.plot(LARGO / 2, ANCHO / 2, "o", color="white", markersize=3, zorder=3)

    for x_arco, signo in [(0, 1), (LARGO, -1)]:
        # Área grande
        ax.plot(
            [x_arco, x_arco + signo * 16.5, x_arco + signo * 16.5, x_arco],
            [13.84, 13.84, 54.16, 54.16],
            **line_kw,
        )
        # Área chica
        ax.plot(
            [x_arco, x_arco + signo * 5.5, x_arco + signo * 5.5, x_arco],
            [24.84, 24.84, 43.16, 43.16],
            **line_kw,
        )
        # Arco
        ax.plot(
            [x_arco, x_arco + signo * 0.15, x_arco + signo * 0.15, x_arco],
            [30.34, 30.34, 37.66, 37.66],
            color="white", linewidth=3, zorder=3,
        )
        # Punto de penalti
        ax.plot(x_arco + signo * 11, ANCHO / 2, "o", color="white", markersize=3, zorder=3)
        # Semicírculo
        theta = np.linspace(-np.pi / 3, np.pi / 3, 50)
        sc_x = x_arco + signo * 11 + 9.15 * np.cos(theta) * (-signo)
        sc_y = ANCHO / 2 + 9.15 * np.sin(theta)
        ax.plot(sc_x, sc_y, **line_kw)


def heatmap_posicional(
    df: pd.DataFrame,
    titulo: str = "Heatmap Posicional",
    resolucion: float = 2.5,
    cmap_nombre: str = "heat_futbol",
    alpha: float = 0.75,
    jugador_id: int | None = None,
) -> Figure:
    """
    Genera un heatmap de densidad posicional sobre la cancha.
    df debe tener columnas x_campo, y_campo.
    resolucion: tamaño de celda en metros.
    """
    if jugador_id is not None:
        df = df[df["jugador_id"] == jugador_id]

    bins_x = int(LARGO / resolucion)
    bins_y = int(ANCHO / resolucion)

    heatmap, xedges, yedges = np.histogram2d(
        df["x_campo"].clip(0, LARGO),
        df["y_campo"].clip(0, ANCHO),
        bins=[bins_x, bins_y],
        range=[[0, LARGO], [0, ANCHO]],
    )
    # Suavizado gaussiano
    from scipy.ndimage import gaussian_filter  # type: ignore
    heatmap = gaussian_filter(heatmap.T, sigma=1.5)

    # Colormap personalizado: verde → amarillo → rojo
    colores = ["#1a7a1a", "#ffff00", "#ff8800", "#ff0000", "#8b0000"]
    cmap = LinearSegmentedColormap.from_list(cmap_nombre, colores, N=256)

    fig, ax = plt.subplots(figsize=(13, 8.5))
    _dibujar_cancha(ax)

    im = ax.imshow(
        heatmap,
        extent=[0, LARGO, 0, ANCHO],
        origin="lower",
        cmap=cmap,
        alpha=alpha,
        aspect="equal",
        zorder=1,
        vmin=0,
        vmax=np.percentile(heatmap[heatmap > 0], 95) if heatmap.max() > 0 else 1,
    )
    plt.colorbar(im, ax=ax, label="Densidad de presencia", fraction=0.02, pad=0.02)
    ax.set_title(titulo, fontsize=14, fontweight="bold", color="black", pad=10)
    fig.tight_layout()
    return fig


def trazar_trayectoria(
    df: pd.DataFrame,
    titulo: str = "Trayectoria",
    colorear_por: str = "velocidad_kmh",
    alpha: float = 0.8,
) -> Figure:
    """
    Dibuja la trayectoria del jugador coloreada por velocidad (o cualquier variable continua).
    """
    df = df.sort_values("frame_numero").copy()
    x = df["x_campo"].values
    y = df["y_campo"].values
    v = df[colorear_por].values if colorear_por in df.columns else np.zeros(len(df))

    fig, ax = plt.subplots(figsize=(13, 8.5))
    _dibujar_cancha(ax)

    # Dibuja segmentos coloreados por velocidad
    puntos = np.array([x, y]).T.reshape(-1, 1, 2)
    segmentos = np.concatenate([puntos[:-1], puntos[1:]], axis=1)

    from matplotlib.collections import LineCollection
    norm = plt.Normalize(0, 30)
    colores_linea = plt.cm.RdYlGn_r(norm(v[:-1]))
    lc = LineCollection(segmentos, colors=colores_linea, linewidth=2, alpha=alpha, zorder=3)
    ax.add_collection(lc)

    # Inicio y fin
    ax.plot(x[0], y[0], "go", markersize=8, zorder=4, label="Inicio")
    ax.plot(x[-1], y[-1], "rs", markersize=8, zorder=4, label="Fin")
    ax.legend(loc="upper right", fontsize=9)

    sm = plt.cm.ScalarMappable(cmap="RdYlGn_r", norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, label="Velocidad (km/h)", fraction=0.02, pad=0.02)
    ax.set_title(titulo, fontsize=14, fontweight="bold", pad=10)
    fig.tight_layout()
    return fig


def grafico_perfil_fisico(metricas: dict, nombre: str = "Jugador") -> Figure:
    """
    Radar/spider chart con el perfil físico del jugador:
    velocidad máxima, sprints, distancia, achiques, cobertura.
    """
    categorias = [
        "Vel. Máx\n(km/h)", "Sprints", "Distancia\n(km)",
        "Achiques", "Cobertura\nlateral (m)", "Acel.\nAlta Int.",
    ]
    valores_raw = [
        metricas.get("velocidad_max_kmh", 0),
        metricas.get("sprints_total", 0),
        metricas.get("distancia_total_m", 0) / 1000,
        metricas.get("achiques_realizados", 0),
        metricas.get("cobertura_lateral_m", 0),
        metricas.get("aceleraciones_alta_int", 0),
    ]
    # Normalizar respecto a benchmarks de referencia de porteros
    benchmarks = [35.0, 20.0, 7.0, 15.0, 40.0, 30.0]
    valores_norm = [min(1.0, v / b) if b > 0 else 0.0 for v, b in zip(valores_raw, benchmarks)]
    valores_norm += valores_norm[:1]  # cerrar el polígono

    N = len(categorias)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categorias, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_yticklabels([])

    ax.plot(angles, valores_norm, "o-", linewidth=2, color="#e74c3c")
    ax.fill(angles, valores_norm, alpha=0.25, color="#e74c3c")

    # Anotaciones con valores reales
    for angle, valor_r, valor_n, cat in zip(angles[:-1], valores_raw, valores_norm[:-1], categorias):
        ax.annotate(
            f"{valor_r:.1f}",
            xy=(angle, valor_n),
            xytext=(angle, valor_n + 0.08),
            fontsize=8, ha="center", color="#2c3e50",
        )

    ax.set_title(f"Perfil Físico — {nombre}", fontsize=13, fontweight="bold", pad=20)
    fig.tight_layout()
    return fig


def mapa_achiques(df: pd.DataFrame, titulo: str = "Mapa de Achiques") -> Figure:
    """
    Muestra los puntos donde el arquero realizó achiques (salidas rápidas fuera del área).
    Colorear por velocidad al momento del achique.
    """
    achiques_df = df[
        (df["x_campo"] > 16.5) & (df["velocidad_kmh"] > 15.0)
    ].copy()

    fig, ax = plt.subplots(figsize=(13, 8.5))
    _dibujar_cancha(ax)

    if achiques_df.empty:
        ax.text(
            LARGO / 2, ANCHO / 2, "Sin achiques detectados",
            ha="center", va="center", fontsize=14, color="white",
        )
    else:
        scatter = ax.scatter(
            achiques_df["x_campo"],
            achiques_df["y_campo"],
            c=achiques_df["velocidad_kmh"],
            cmap="YlOrRd",
            s=80,
            alpha=0.7,
            zorder=4,
            edgecolors="white",
            linewidths=0.5,
        )
        plt.colorbar(scatter, ax=ax, label="Velocidad (km/h)", fraction=0.02, pad=0.02)

        # Línea del área grande para referencia
        ax.axvline(16.5, color="yellow", linewidth=2, linestyle="--", alpha=0.8, zorder=3)
        ax.text(17, 2, "Límite área grande", color="yellow", fontsize=9)

    ax.set_title(f"{titulo} (n={len(achiques_df)})", fontsize=14, fontweight="bold", pad=10)
    fig.tight_layout()
    return fig


def grafico_velocidad_tiempo(
    df: pd.DataFrame,
    fps: float = 25.0,
    titulo: str = "Perfil de Velocidad",
) -> Figure:
    """Serie temporal de velocidad con bandas de intensidad."""
    df = df.sort_values("frame_numero").copy()
    tiempo = df["frame_numero"] / fps / 60  # minutos

    fig, ax = plt.subplots(figsize=(15, 5))

    # Bandas de intensidad
    ax.axhspan(0, UMBRAL_SPRINT := 25.0, alpha=0.05, color="blue")
    ax.axhspan(UMBRAL_SPRINT, 40, alpha=0.05, color="red")
    ax.axhline(25.0, color="red", linestyle="--", linewidth=1, alpha=0.6, label="Sprint (25 km/h)")
    ax.axhline(19.8, color="orange", linestyle="--", linewidth=1, alpha=0.6, label="Alta int. (19.8 km/h)")

    ax.plot(tiempo, df["velocidad_kmh"].fillna(0), color="#2980b9", linewidth=0.8, alpha=0.9)
    ax.fill_between(tiempo, df["velocidad_kmh"].fillna(0), alpha=0.3, color="#2980b9")

    ax.set_xlabel("Tiempo (min)", fontsize=11)
    ax.set_ylabel("Velocidad (km/h)", fontsize=11)
    ax.set_title(titulo, fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig
