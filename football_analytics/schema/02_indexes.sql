-- =============================================================================
-- ÍNDICES Y CONSTRAINTS DE RENDIMIENTO
-- Estrategia de indexación para alta carga de tracking (>1M filas/partido)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- TRACKING JUGADORES — tabla de mayor volumen
-- ---------------------------------------------------------------------------

-- Búsqueda por sesión + frame (query más frecuente del pipeline)
CREATE INDEX idx_tracking_sesion_frame
    ON tracking_jugadores (sesion_id, frame_numero);

-- Búsqueda por jugador a través del tiempo
CREATE INDEX idx_tracking_jugador_tiempo
    ON tracking_jugadores (jugador_id, timestamp_seg)
    WHERE jugador_id IS NOT NULL;

-- Búsqueda por track_id dentro de una sesión (reconexión de tracks)
CREATE INDEX idx_tracking_track_sesion
    ON tracking_jugadores (sesion_id, track_id);

-- Análisis espacial: queries por zona
CREATE INDEX idx_tracking_zona
    ON tracking_jugadores (zona_id, sesion_id)
    WHERE zona_id IS NOT NULL;

-- Búsqueda por posición en cancha (útil para análisis de proximidad)
CREATE INDEX idx_tracking_coordenadas
    ON tracking_jugadores USING BRIN (x_campo, y_campo);  -- BRIN óptimo para datos ordenados

-- Filtros de calidad
CREATE INDEX idx_tracking_interpolado
    ON tracking_jugadores (sesion_id, interpolado)
    WHERE interpolado = FALSE;

-- ---------------------------------------------------------------------------
-- TRACKING BALÓN
-- ---------------------------------------------------------------------------

CREATE INDEX idx_balon_sesion_frame
    ON tracking_balon (sesion_id, frame_numero);

CREATE INDEX idx_balon_zona
    ON tracking_balon (zona_id, sesion_id)
    WHERE zona_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- EVENTOS — búsquedas analíticas frecuentes
-- ---------------------------------------------------------------------------

CREATE INDEX idx_eventos_partido
    ON eventos (partido_id, tipo_evento_id);

CREATE INDEX idx_eventos_jugador
    ON eventos (jugador_id, tipo_evento_id)
    WHERE jugador_id IS NOT NULL;

CREATE INDEX idx_eventos_sesion_frame
    ON eventos (sesion_id, frame_inicio);

CREATE INDEX idx_eventos_tipo
    ON eventos (tipo_evento_id, exitoso);

CREATE INDEX idx_eventos_zona
    ON eventos (zona_origen_id)
    WHERE zona_origen_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- FEATURES ML — acceso masivo para entrenamiento
-- ---------------------------------------------------------------------------

CREATE INDEX idx_features_sesion
    ON features_ml (sesion_id, frame_numero);

CREATE INDEX idx_features_jugador
    ON features_ml (jugador_id, sesion_id)
    WHERE jugador_id IS NOT NULL;

CREATE INDEX idx_features_evento
    ON features_ml (evento_siguiente)
    WHERE evento_siguiente IS NOT NULL;

-- ---------------------------------------------------------------------------
-- PREDICCIONES ML
-- ---------------------------------------------------------------------------

CREATE INDEX idx_predicciones_modelo_sesion
    ON predicciones_ml (modelo_id, sesion_id);

CREATE INDEX idx_predicciones_confianza
    ON predicciones_ml (confianza DESC)
    WHERE confianza > 0.7;

-- ---------------------------------------------------------------------------
-- PARTIDOS Y VIDEOS
-- ---------------------------------------------------------------------------

CREATE INDEX idx_partidos_temporada
    ON partidos (temporada_id, fecha_partido DESC);

CREATE INDEX idx_partidos_equipos
    ON partidos (equipo_local_id, equipo_visitante_id);

CREATE INDEX idx_videos_partido
    ON videos (partido_id, procesado);

CREATE INDEX idx_sesiones_video
    ON sesiones_analisis (video_id, estado);

-- ---------------------------------------------------------------------------
-- ÍNDICES GIN/JSONB para búsqueda dentro de columnas JSONB
-- ---------------------------------------------------------------------------

CREATE INDEX idx_sesiones_metadata_gin
    ON sesiones_analisis USING GIN (metadata_json);

CREATE INDEX idx_camaras_homografia_gin
    ON camaras USING GIN (homografia_json);

CREATE INDEX idx_modelos_metricas_gin
    ON modelos_ml USING GIN (metricas_eval_json);

-- ---------------------------------------------------------------------------
-- CONSTRAINT ADICIONALES (unicidad funcional)
-- ---------------------------------------------------------------------------

-- Un jugador no puede tener dos posiciones en el mismo frame de una sesión
CREATE UNIQUE INDEX uq_tracking_sesion_jugador_frame
    ON tracking_jugadores (sesion_id, jugador_id, frame_numero)
    WHERE jugador_id IS NOT NULL;

-- Un solo balón por frame en cada sesión
CREATE UNIQUE INDEX uq_balon_sesion_frame
    ON tracking_balon (sesion_id, frame_numero);

-- Evitar duplicados de métricas por sesión/jugador
CREATE UNIQUE INDEX uq_metricas_sesion_jugador
    ON metricas_jugador_partido (sesion_id, jugador_id);

-- ---------------------------------------------------------------------------
-- ESTADÍSTICAS PERSONALIZADAS para el query planner
-- ---------------------------------------------------------------------------

-- Correlación entre zona y velocidad (para estimaciones de cardinalidad)
CREATE STATISTICS stats_tracking_zona_velocidad
    ON zona_id, velocidad_kmh
    FROM tracking_jugadores;

CREATE STATISTICS stats_eventos_tipo_zona
    ON tipo_evento_id, zona_origen_id
    FROM eventos;
