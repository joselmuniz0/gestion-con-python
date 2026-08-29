"""
Extracción de features para machine learning.
Produce DataFrames de Pandas listos para entrenamiento de modelos supervisados/no supervisados.
"""

from __future__ import annotations

import math
import warnings
from typing import Sequence

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# CONSTANTES DE CANCHA
# ---------------------------------------------------------------------------

LARGO_CANCHA = 105.0
ANCHO_CANCHA = 68.0
ARCO_LOCAL_X = 0.0
ARCO_LOCAL_Y = 34.0    # centro del arco local
ARCO_RIVAL_X = 105.0
ARCO_RIVAL_Y = 34.0
POSTE_IZQ_Y = 30.34
POSTE_DER_Y = 37.66


# ---------------------------------------------------------------------------
# FEATURES CINEMÁTICAS
# ---------------------------------------------------------------------------

def calcular_jerk(velocidades: pd.Series, fps: float) -> pd.Series:
    """
    Jerk = derivada de la aceleración (variación de aceleración).
    Indica cambios bruscos de intensidad, útil para detectar arranques/frenadas.
    """
    dt = 1.0 / fps
    aceleracion = velocidades.diff() / dt
    return aceleracion.diff() / dt


def calcular_cambio_direccion(direcciones_deg: pd.Series) -> pd.Series:
    """
    Diferencia angular entre frames consecutivos.
    Valores altos indican cambios de dirección bruscos (giros, achiques, etc.)
    """
    diff = direcciones_deg.diff()
    # Normalizar al rango [-180, 180]
    return diff.apply(lambda d: ((d + 180) % 360) - 180 if pd.notna(d) else np.nan)


def calcular_velocidad_angular(
    orientaciones_deg: pd.Series, fps: float
) -> pd.Series:
    """Tasa de cambio de orientación corporal (rad/s)."""
    dt = 1.0 / fps
    diff_rad = orientaciones_deg.diff().apply(
        lambda d: math.radians(((d + 180) % 360) - 180) if pd.notna(d) else np.nan
    )
    return diff_rad / dt


# ---------------------------------------------------------------------------
# FEATURES ESPACIALES
# ---------------------------------------------------------------------------

def calcular_distancia_arco(x: float, y: float, arco: str = "propio") -> float:
    """Distancia euclidiana al centro del arco en metros."""
    if arco == "propio":
        return math.sqrt((x - ARCO_LOCAL_X) ** 2 + (y - ARCO_LOCAL_Y) ** 2)
    return math.sqrt((x - ARCO_RIVAL_X) ** 2 + (y - ARCO_RIVAL_Y) ** 2)


def calcular_angulo_tiro(x: float, y: float) -> float:
    """
    Ángulo subtendido desde la posición (x,y) hacia los palos del arco rival.
    Un ángulo mayor = mejor posición de tiro.
    """
    if x >= ARCO_RIVAL_X:
        return 0.0

    d_poste_izq = math.sqrt((x - ARCO_RIVAL_X) ** 2 + (y - POSTE_IZQ_Y) ** 2)
    d_poste_der = math.sqrt((x - ARCO_RIVAL_X) ** 2 + (y - POSTE_DER_Y) ** 2)
    d_interpalos = abs(POSTE_DER_Y - POSTE_IZQ_Y)

    # Fórmula del ángulo subtendido (ley del coseno)
    cos_angulo = (d_poste_izq**2 + d_poste_der**2 - d_interpalos**2) / (
        2 * d_poste_izq * d_poste_der + 1e-9
    )
    cos_angulo = max(-1.0, min(1.0, cos_angulo))
    return math.degrees(math.acos(cos_angulo))


def calcular_presion_rival(
    x_jugador: float,
    y_jugador: float,
    posiciones_rivales: list[tuple[float, float]],
    radio: float = 5.0,
) -> float:
    """
    Índice de presión rival [0,1].
    Suma gaussiana de la cercanía de rivales dentro del radio.
    """
    if not posiciones_rivales:
        return 0.0

    presion = 0.0
    for xr, yr in posiciones_rivales:
        dist = math.sqrt((x_jugador - xr) ** 2 + (y_jugador - yr) ** 2)
        if dist < radio:
            # Función gaussiana: mayor presión cuanto más cerca
            presion += math.exp(-(dist**2) / (2 * (radio / 3) ** 2))

    return min(1.0, presion)


def calcular_distancias_n_rivales(
    x: float,
    y: float,
    posiciones_rivales: list[tuple[float, float]],
    n: int = 3,
) -> list[float]:
    """Distancias a los N rivales más cercanos (ordenadas de menor a mayor)."""
    dists = sorted(
        math.sqrt((x - xr) ** 2 + (y - yr) ** 2) for xr, yr in posiciones_rivales
    )
    result = dists[:n]
    while len(result) < n:
        result.append(np.nan)
    return result


# ---------------------------------------------------------------------------
# VENTANAS TEMPORALES (sliding windows)
# ---------------------------------------------------------------------------

def features_ventana(
    serie: pd.Series,
    ventana_frames: int,
    fps: float,
    nombre: str,
) -> pd.DataFrame:
    """
    Genera estadísticas de una serie en una ventana deslizante.
    Retorna columnas: {nombre}_media, {nombre}_max, {nombre}_std
    """
    r = serie.rolling(ventana_frames, min_periods=1)
    return pd.DataFrame({
        f"{nombre}_media_{ventana_frames}f": r.mean(),
        f"{nombre}_max_{ventana_frames}f": r.max(),
        f"{nombre}_std_{ventana_frames}f": r.std(),
    })


def distancia_en_ventana(
    x: pd.Series, y: pd.Series, fps: float, ventana_seg: float
) -> pd.Series:
    """Distancia total recorrida en la ventana de tiempo definida."""
    ventana_frames = max(1, int(ventana_seg * fps))
    dx = x.diff().fillna(0)
    dy = y.diff().fillna(0)
    dist_frame = np.sqrt(dx**2 + dy**2)
    return dist_frame.rolling(ventana_frames, min_periods=1).sum()


# ---------------------------------------------------------------------------
# EXTRACTOR PRINCIPAL
# ---------------------------------------------------------------------------

class FeatureExtractor:
    """
    Transforma el DataFrame de tracking crudo en un DataFrame de features
    listo para modelos de ML.
    """

    def __init__(self, fps: float = 25.0, radio_presion: float = 5.0):
        self.fps = fps
        self.radio_presion = radio_presion

    def extraer(
        self,
        df_tracking: pd.DataFrame,
        df_balon: pd.DataFrame | None = None,
        df_rivales: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        df_tracking: columnas mínimas requeridas:
            sesion_id, jugador_id, frame_numero, timestamp_seg,
            x_campo, y_campo, velocidad_ms, aceleracion, direccion_deg
        df_balon: columnas: sesion_id, frame_numero, x_campo, y_campo
        df_rivales: columnas: sesion_id, frame_numero, jugador_id, equipo_id, x_campo, y_campo

        Retorna DataFrame con todas las features calculadas.
        """
        df = df_tracking.copy().sort_values(["jugador_id", "frame_numero"])

        # --- Features cinemáticas derivadas ---
        df["jerk"] = (
            df.groupby("jugador_id")["velocidad_ms"]
            .transform(lambda s: calcular_jerk(s, self.fps))
        )
        df["cambio_direccion_deg"] = (
            df.groupby("jugador_id")["direccion_deg"]
            .transform(calcular_cambio_direccion)
        )

        # --- Normalización posicional ---
        df["x_normalizado"] = df["x_campo"] / LARGO_CANCHA
        df["y_normalizado"] = df["y_campo"] / ANCHO_CANCHA

        # --- Distancias a arcos ---
        df["distancia_arco_propio"] = df.apply(
            lambda r: calcular_distancia_arco(r["x_campo"], r["y_campo"], "propio"), axis=1
        )
        df["distancia_arco_rival"] = df.apply(
            lambda r: calcular_distancia_arco(r["x_campo"], r["y_campo"], "rival"), axis=1
        )

        # --- Ángulo de tiro ---
        df["angulo_arco_rival"] = df.apply(
            lambda r: calcular_angulo_tiro(r["x_campo"], r["y_campo"]), axis=1
        )

        # --- Distancia al balón ---
        if df_balon is not None and not df_balon.empty:
            df = df.merge(
                df_balon[["sesion_id", "frame_numero", "x_campo", "y_campo"]]
                .rename(columns={"x_campo": "x_balon", "y_campo": "y_balon"}),
                on=["sesion_id", "frame_numero"],
                how="left",
            )
            df["distancia_balon"] = np.sqrt(
                (df["x_campo"] - df["x_balon"]) ** 2
                + (df["y_campo"] - df["y_balon"]) ** 2
            )
        else:
            df["distancia_balon"] = np.nan

        # --- Presión rival y distancias ---
        if df_rivales is not None and not df_rivales.empty:
            df = self._agregar_features_rivales(df, df_rivales)
        else:
            df["presion_rival"] = 0.0
            df["distancia_rival_1"] = np.nan
            df["distancia_rival_2"] = np.nan
            df["rivales_en_5m"] = 0

        # --- Ventanas temporales (por jugador) ---
        for col in ["velocidad_ms", "aceleracion"]:
            if col in df.columns:
                ventana_frames = int(5 * self.fps)  # ventana de 5 segundos
                grp = df.groupby("jugador_id")[col]
                df[f"{col}_media_5s"] = grp.transform(
                    lambda s: s.rolling(ventana_frames, min_periods=1).mean()
                )

        df["distancia_5s"] = df.groupby("jugador_id").apply(
            lambda g: distancia_en_ventana(g["x_campo"], g["y_campo"], self.fps, 5.0)
        ).reset_index(level=0, drop=True)

        return df

    def _agregar_features_rivales(
        self, df: pd.DataFrame, df_rivales: pd.DataFrame
    ) -> pd.DataFrame:
        """Calcula presión y distancias a rivales para cada fila."""
        resultados = []
        for (sesion, frame, jugador), grupo in df.groupby(
            ["sesion_id", "frame_numero", "jugador_id"]
        ):
            row = grupo.iloc[0]
            rivales_frame = df_rivales[
                (df_rivales["sesion_id"] == sesion)
                & (df_rivales["frame_numero"] == frame)
                & (df_rivales["jugador_id"] != jugador)
            ]
            pos_rivales = list(zip(rivales_frame["x_campo"], rivales_frame["y_campo"]))

            presion = calcular_presion_rival(
                row["x_campo"], row["y_campo"], pos_rivales, self.radio_presion
            )
            dists = calcular_distancias_n_rivales(
                row["x_campo"], row["y_campo"], pos_rivales, n=2
            )
            resultados.append({
                "sesion_id": sesion,
                "frame_numero": frame,
                "jugador_id": jugador,
                "presion_rival": presion,
                "distancia_rival_1": dists[0],
                "distancia_rival_2": dists[1],
                "rivales_en_5m": sum(
                    1 for d in dists if pd.notna(d) and d <= self.radio_presion
                ),
            })

        df_presion = pd.DataFrame(resultados)
        return df.merge(df_presion, on=["sesion_id", "frame_numero", "jugador_id"], how="left")

    def preparar_dataset_ml(
        self,
        df_features: pd.DataFrame,
        target_col: str = "evento_siguiente",
        columnas_excluir: Sequence[str] | None = None,
        dropna: bool = True,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """
        Retorna (X, y) listos para sklearn/PyTorch.
        columnas_excluir: columnas de ID o texto que no deben ser features.
        """
        excluir = set(columnas_excluir or [])
        excluir.update({
            "id", "sesion_id", "jugador_id", "frame_numero", "timestamp_seg",
            "x_balon", "y_balon", target_col,
        })

        feature_cols = [c for c in df_features.columns if c not in excluir]

        X = df_features[feature_cols]
        y = df_features[target_col] if target_col in df_features.columns else None

        if dropna:
            mask = X.notna().all(axis=1)
            if y is not None:
                mask &= y.notna()
            X = X[mask]
            if y is not None:
                y = y[mask]

        return X, y
