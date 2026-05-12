-- =============================================================================
-- QUERIES ANALÍTICAS DE REFERENCIA
-- Casos de uso reales para analistas tácticos y científicos de datos
-- =============================================================================

-- ===========================================================================
-- 1. ANÁLISIS DE ACHIQUES DEL ARQUERO
-- ¿Cuántas veces el arquero salió a cortar y hasta dónde llegó?
-- ===========================================================================

WITH achiques AS (
    SELECT
        tj.jugador_id,
        tj.sesion_id,
        -- Detectar frames donde arquero está fuera del área chica (>5.5m del arco)
        tj.frame_numero,
        tj.x_campo,
        tj.y_campo,
        tj.distancia_arco_propio,
        tj.velocidad_kmh,
        -- Identificar inicio de salida: velocidad > 8 km/h y distancia > 5.5m
        LAG(tj.distancia_arco_propio, 1) OVER w AS dist_prev,
        LEAD(tj.distancia_arco_propio, 1) OVER w AS dist_next
    FROM tracking_jugadores tj
    JOIN jugadores j ON j.id = tj.jugador_id
    WHERE j.posicion = 'portero'
      AND tj.sesion_id = :sesion_id
      AND tj.interpolado = FALSE
    WINDOW w AS (PARTITION BY tj.jugador_id, tj.sesion_id ORDER BY tj.frame_numero)
),
salidas AS (
    SELECT *
    FROM achiques
    WHERE velocidad_kmh > 8
      AND distancia_arco_propio > 5.5
      AND dist_prev < distancia_arco_propio  -- alejándose del arco
)
SELECT
    j.nombre || ' ' || j.apellido AS arquero,
    COUNT(*)                       AS frames_en_achique,
    MAX(s.distancia_arco_propio)   AS distancia_max_salida_m,
    AVG(s.distancia_arco_propio)   AS distancia_media_salida_m,
    AVG(s.velocidad_kmh)           AS velocidad_media_achique,
    MAX(s.velocidad_kmh)           AS velocidad_max_achique
FROM salidas s
JOIN jugadores j ON j.id = s.jugador_id
GROUP BY j.nombre, j.apellido;


-- ===========================================================================
-- 2. HEATMAP POSICIONAL DEL ARQUERO (cuadrícula 5x5 metros)
-- Para visualización en Matplotlib/Seaborn
-- ===========================================================================

SELECT
    FLOOR(tj.x_campo / 5) * 5      AS celda_x,
    FLOOR(tj.y_campo / 5) * 5      AS celda_y,
    COUNT(*)                        AS frecuencia,
    AVG(tj.velocidad_kmh)           AS velocidad_media,
    AVG(tj.presion_rival)           AS presion_media,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS pct_tiempo
FROM tracking_jugadores tj
JOIN jugadores j ON j.id = tj.jugador_id
WHERE j.posicion = 'portero'
  AND tj.sesion_id = :sesion_id
  AND tj.interpolado = FALSE
GROUP BY celda_x, celda_y
ORDER BY frecuencia DESC;


-- ===========================================================================
-- 3. PERFIL FÍSICO DEL ARQUERO — ZONAS DE VELOCIDAD (FIFA estándar)
-- ===========================================================================

SELECT
    j.nombre || ' ' || j.apellido AS arquero,
    -- Clasificación por zonas de intensidad FIFA
    SUM(CASE WHEN tj.velocidad_kmh < 6.0   THEN 1 ELSE 0 END) AS frames_parado,
    SUM(CASE WHEN tj.velocidad_kmh BETWEEN  6.0 AND 11.0 THEN 1 ELSE 0 END) AS frames_trote,
    SUM(CASE WHEN tj.velocidad_kmh BETWEEN 11.0 AND 14.4 THEN 1 ELSE 0 END) AS frames_carrera_baja,
    SUM(CASE WHEN tj.velocidad_kmh BETWEEN 14.4 AND 19.8 THEN 1 ELSE 0 END) AS frames_media_intensidad,
    SUM(CASE WHEN tj.velocidad_kmh BETWEEN 19.8 AND 25.0 THEN 1 ELSE 0 END) AS frames_alta_intensidad,
    SUM(CASE WHEN tj.velocidad_kmh > 25.0               THEN 1 ELSE 0 END) AS frames_sprint,
    -- Distancias aproximadas (frames × (1/fps) × velocidad_ms)
    ROUND(SUM(tj.velocidad_ms * (1.0 / v.fps))::NUMERIC, 1) AS distancia_total_m,
    MAX(tj.velocidad_kmh) AS velocidad_maxima,
    COUNT(*) AS total_frames_analizados
FROM tracking_jugadores tj
JOIN jugadores j          ON j.id = tj.jugador_id
JOIN sesiones_analisis sa ON sa.id = tj.sesion_id
JOIN videos v             ON v.id = sa.video_id
WHERE j.posicion = 'portero'
  AND tj.sesion_id = :sesion_id
  AND tj.interpolado = FALSE
  AND tj.velocidad_kmh IS NOT NULL
GROUP BY j.nombre, j.apellido;


-- ===========================================================================
-- 4. ANÁLISIS DE TIEMPO DE REACCIÓN DEL ARQUERO ANTE REMATES
-- ¿Cuánto tarda el arquero en moverse después de un remate?
-- ===========================================================================

WITH remates AS (
    SELECT
        ev.id         AS evento_id,
        ev.sesion_id,
        ev.jugador_secundario_id AS arquero_id,  -- el portero que recibe el remate
        ev.frame_inicio,
        ev.timestamp_inicio_seg,
        ev.x_campo    AS x_remate,
        ev.y_campo    AS y_remate
    FROM eventos ev
    JOIN tipos_evento te ON te.id = ev.tipo_evento_id
    WHERE te.nombre = 'remate'
      AND ev.sesion_id = :sesion_id
),
movimiento_post_remate AS (
    SELECT
        r.evento_id,
        r.arquero_id,
        r.timestamp_inicio_seg AS t_remate,
        tj.timestamp_seg       AS t_movimiento,
        tj.velocidad_kmh,
        tj.x_campo,
        tj.y_campo,
        (tj.timestamp_seg - r.timestamp_inicio_seg) AS delta_t_seg,
        ROW_NUMBER() OVER (
            PARTITION BY r.evento_id
            ORDER BY tj.frame_numero
        ) AS rn
    FROM remates r
    JOIN tracking_jugadores tj
        ON tj.jugador_id = r.arquero_id
        AND tj.sesion_id = r.sesion_id
        AND tj.frame_numero > r.frame_inicio
        AND tj.frame_numero <= r.frame_inicio + 30  -- ventana 1 segundo a 30fps
        AND tj.velocidad_kmh > 3  -- primer frame con movimiento detectable
)
SELECT
    mpr.evento_id,
    j.nombre || ' ' || j.apellido AS arquero,
    mpr.t_remate,
    MIN(mpr.delta_t_seg)          AS tiempo_reaccion_seg,
    MIN(mpr.velocidad_kmh)        AS velocidad_inicial_reaccion
FROM movimiento_post_remate mpr
JOIN jugadores j ON j.id = mpr.arquero_id
GROUP BY mpr.evento_id, j.nombre, j.apellido, mpr.t_remate
ORDER BY mpr.t_remate;


-- ===========================================================================
-- 5. ANÁLISIS DE COBERTURA DE ÁNGULO — posicionamiento del arquero
-- ¿Está el arquero bien posicionado respecto a la línea de tiro?
-- ===========================================================================

WITH posicion_arquero AS (
    SELECT
        tj.frame_numero,
        tj.timestamp_seg,
        tj.x_campo AS arq_x,
        tj.y_campo AS arq_y,
        -- Arco propio: postes en (0, 30.34) y (0, 37.66) — coordenadas FIFA
        -- Centro del arco propio local = (0, 34)
        ABS(tj.y_campo - 34.0)       AS desviacion_lateral_m,
        tj.distancia_arco_propio     AS profundidad_m,
        -- Balón
        tb.x_campo AS bal_x,
        tb.y_campo AS bal_y,
        -- Ángulo de cobertura (bisectriz ideal arquero-balon)
        DEGREES(ATAN2(ABS(tj.y_campo - tb.y_campo), ABS(tj.x_campo - tb.x_campo)))
                                     AS angulo_posicionamiento_deg
    FROM tracking_jugadores tj
    JOIN tracking_balon tb
        ON tb.sesion_id = tj.sesion_id
        AND tb.frame_numero = tj.frame_numero
    JOIN jugadores j ON j.id = tj.jugador_id
    WHERE j.posicion = 'portero'
      AND tj.sesion_id = :sesion_id
      AND tj.interpolado = FALSE
      AND tb.en_juego = TRUE
)
SELECT
    ROUND(AVG(desviacion_lateral_m), 2)       AS desviacion_lateral_media_m,
    ROUND(AVG(profundidad_m), 2)               AS profundidad_media_m,
    ROUND(AVG(angulo_posicionamiento_deg), 2)  AS angulo_medio_deg,
    ROUND(STDDEV(desviacion_lateral_m), 2)     AS consistencia_lateral,
    -- Porcentaje de tiempo bien posicionado (desviación < 2m)
    SUM(CASE WHEN desviacion_lateral_m < 2.0 THEN 1 ELSE 0 END) * 100.0
        / COUNT(*)                             AS pct_bien_posicionado
FROM posicion_arquero;


-- ===========================================================================
-- 6. COMPARATIVA MULTI-PARTIDO — evolución de métricas del arquero
-- ===========================================================================

SELECT
    p.fecha_partido,
    eq_local.nombre || ' vs ' || eq_vis.nombre   AS partido,
    mjp.velocidad_max_kmh,
    mjp.distancia_total_m                         / 1000.0 AS km_totales,
    mjp.achiques_realizados,
    mjp.salidas_area_grande,
    mjp.cobertura_lateral_m,
    mjp.posicion_media_x,
    -- Tendencia con ventana deslizante (últimos 5 partidos)
    AVG(mjp.velocidad_max_kmh)
        OVER (PARTITION BY mjp.jugador_id ORDER BY p.fecha_partido
              ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS vel_max_media_5p,
    AVG(mjp.achiques_realizados)
        OVER (PARTITION BY mjp.jugador_id ORDER BY p.fecha_partido
              ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS achiques_media_5p
FROM metricas_jugador_partido mjp
JOIN partidos p       ON p.id = mjp.partido_id
JOIN jugadores j      ON j.id = mjp.jugador_id
JOIN equipos eq_local ON eq_local.id = p.equipo_local_id
JOIN equipos eq_vis   ON eq_vis.id = p.equipo_visitante_id
WHERE j.posicion = 'portero'
  AND mjp.jugador_id = :jugador_id
ORDER BY p.fecha_partido;


-- ===========================================================================
-- 7. PRESIÓN RIVAL Y COMPORTAMIENTO DEL ARQUERO BAJO PRESIÓN
-- ===========================================================================

SELECT
    zc.nombre                         AS zona,
    ROUND(AVG(tj.presion_rival), 3)   AS presion_media,
    ROUND(AVG(tj.velocidad_kmh), 2)   AS velocidad_bajo_presion,
    ROUND(AVG(tj.aceleracion), 4)     AS aceleracion_bajo_presion,
    COUNT(*)                           AS frames_con_presion,
    -- Eventos en esta zona bajo presión
    COUNT(DISTINCT ev.id)              AS eventos_bajo_presion
FROM tracking_jugadores tj
LEFT JOIN zonas_cancha zc  ON zc.id = tj.zona_id
LEFT JOIN eventos ev
    ON ev.sesion_id = tj.sesion_id
    AND ev.frame_inicio = tj.frame_numero
    AND ev.jugador_id = tj.jugador_id
JOIN jugadores j ON j.id = tj.jugador_id
WHERE j.posicion = 'portero'
  AND tj.sesion_id = :sesion_id
  AND tj.presion_rival > 0.5  -- alta presión
  AND tj.interpolado = FALSE
GROUP BY zc.nombre
ORDER BY presion_media DESC;


-- ===========================================================================
-- 8. EXTRACCIÓN DE FEATURES PARA ENTRENAMIENTO ML
-- Dataset para modelo de predicción de achiques
-- ===========================================================================

SELECT
    fml.sesion_id,
    fml.jugador_id,
    fml.frame_numero,
    -- Features
    fml.velocidad_ms,
    fml.aceleracion,
    fml.jerk,
    fml.direccion_deg,
    fml.cambio_direccion_deg,
    fml.x_normalizado,
    fml.y_normalizado,
    fml.distancia_arco_propio,
    fml.distancia_balon,
    fml.distancia_rival_1,
    fml.presion_rival,
    fml.rivales_en_5m,
    fml.angulo_arco,
    fml.velocidad_media_5s,
    fml.distancia_5s,
    -- Target: ¿habrá un achique en los próximos 2 segundos?
    CASE WHEN fml.evento_siguiente = 'achique'
         AND fml.tiempo_hasta_evento_s <= 2.0
         THEN 1 ELSE 0 END AS target_achique
FROM features_ml fml
JOIN jugadores j ON j.id = fml.jugador_id
WHERE j.posicion = 'portero'
  AND fml.velocidad_ms IS NOT NULL
  AND fml.aceleracion IS NOT NULL
ORDER BY fml.sesion_id, fml.frame_numero;


-- ===========================================================================
-- 9. REPORTE AUTOMÁTICO DE PARTIDO — resumen ejecutivo
-- ===========================================================================

SELECT
    'RESUMEN DE PARTIDO' AS seccion,
    eq_local.nombre      AS equipo_local,
    eq_vis.nombre        AS equipo_visitante,
    p.goles_local,
    p.goles_visitante,
    p.fecha_partido,
    -- Estadísticas de tracking
    COUNT(DISTINCT tj.jugador_id)                 AS jugadores_con_tracking,
    COUNT(DISTINCT ev.id)                         AS total_eventos,
    SUM(CASE WHEN te.categoria = 'remate' THEN 1 ELSE 0 END) AS remates_totales,
    SUM(CASE WHEN te.categoria = 'porteria' THEN 1 ELSE 0 END) AS acciones_portero,
    -- Distancia media por jugador
    ROUND(AVG(mjp.distancia_total_m) / 1000.0, 2) AS distancia_media_km
FROM partidos p
JOIN equipos eq_local ON eq_local.id = p.equipo_local_id
JOIN equipos eq_vis   ON eq_vis.id = p.equipo_visitante_id
JOIN videos vi        ON vi.partido_id = p.id
JOIN sesiones_analisis sa ON sa.video_id = vi.id AND sa.estado = 'completada'
LEFT JOIN tracking_jugadores tj ON tj.sesion_id = sa.id AND tj.interpolado = FALSE
LEFT JOIN eventos ev  ON ev.sesion_id = sa.id
LEFT JOIN tipos_evento te ON te.id = ev.tipo_evento_id
LEFT JOIN metricas_jugador_partido mjp ON mjp.sesion_id = sa.id
WHERE p.id = :partido_id
GROUP BY eq_local.nombre, eq_vis.nombre, p.goles_local,
         p.goles_visitante, p.fecha_partido;
