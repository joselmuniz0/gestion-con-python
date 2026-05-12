-- =============================================================================
-- VISTAS ANALÍTICAS PROFESIONALES
-- Capas de abstracción sobre el modelo físico para analistas y BI
-- =============================================================================

-- ---------------------------------------------------------------------------
-- VISTA: Resumen de posición por frame (desnormalizado para herramientas BI)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_tracking_completo AS
SELECT
    tj.id,
    tj.frame_numero,
    tj.timestamp_seg,
    tj.x_campo,
    tj.y_campo,
    tj.velocidad_kmh,
    tj.aceleracion,
    tj.direccion_deg,
    tj.presion_rival,
    tj.distancia_arco_propio,
    tj.distancia_balon,
    tj.interpolado,
    tj.ocluido,
    -- Jugador
    j.nombre || ' ' || j.apellido AS jugador_nombre,
    j.posicion                    AS posicion,
    -- Equipo
    e.nombre                      AS equipo_nombre,
    -- Zona
    zc.nombre                     AS zona_nombre,
    zc.codigo                     AS zona_codigo,
    -- Sesión / Video
    sa.video_id,
    v.nombre_archivo              AS video_nombre,
    v.fps,
    -- Partido
    p.id                          AS partido_id,
    p.fecha_partido,
    eq_local.nombre               AS equipo_local,
    eq_vis.nombre                 AS equipo_visitante
FROM tracking_jugadores tj
LEFT JOIN jugadores j        ON j.id = tj.jugador_id
LEFT JOIN equipos e          ON e.id = tj.equipo_id
LEFT JOIN zonas_cancha zc    ON zc.id = tj.zona_id
JOIN  sesiones_analisis sa   ON sa.id = tj.sesion_id
JOIN  videos v               ON v.id = sa.video_id
LEFT JOIN partidos p         ON p.id = v.partido_id
LEFT JOIN equipos eq_local   ON eq_local.id = p.equipo_local_id
LEFT JOIN equipos eq_vis     ON eq_vis.id = p.equipo_visitante_id;

-- ---------------------------------------------------------------------------
-- VISTA: Heatmap de densidad por zona (agrupado)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_heatmap_zona AS
SELECT
    tj.sesion_id,
    tj.jugador_id,
    j.nombre || ' ' || j.apellido AS jugador_nombre,
    j.posicion,
    tj.zona_id,
    zc.nombre                     AS zona_nombre,
    zc.codigo                     AS zona_codigo,
    COUNT(*)                      AS frames_en_zona,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY tj.sesion_id, tj.jugador_id)
                                  AS pct_tiempo_en_zona,
    AVG(tj.velocidad_kmh)         AS velocidad_media_kmh,
    MAX(tj.velocidad_kmh)         AS velocidad_max_kmh,
    AVG(tj.presion_rival)         AS presion_media
FROM tracking_jugadores tj
LEFT JOIN jugadores j     ON j.id = tj.jugador_id
LEFT JOIN zonas_cancha zc ON zc.id = tj.zona_id
WHERE tj.interpolado = FALSE
GROUP BY tj.sesion_id, tj.jugador_id, j.nombre, j.apellido, j.posicion,
         tj.zona_id, zc.nombre, zc.codigo;

-- ---------------------------------------------------------------------------
-- VISTA: Métricas físicas de arquero por partido
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_metricas_arquero AS
SELECT
    mjp.partido_id,
    mjp.jugador_id,
    j.nombre || ' ' || j.apellido            AS arquero_nombre,
    e.nombre                                  AS equipo,
    p.fecha_partido,
    eq_local.nombre || ' vs ' || eq_vis.nombre AS partido,
    mjp.distancia_total_m                     / 1000.0 AS distancia_total_km,
    mjp.velocidad_max_kmh,
    mjp.velocidad_media_kmh,
    mjp.sprints_total,
    mjp.aceleraciones_alta_int,
    mjp.achiques_realizados,
    mjp.distancia_achique_media_m,
    mjp.salidas_area_grande,
    mjp.salidas_area_chica,
    ROUND(mjp.tiempo_en_area_chica_seg / 60.0, 1)  AS minutos_area_chica,
    ROUND(mjp.tiempo_en_area_grande_seg / 60.0, 1) AS minutos_area_grande,
    mjp.posicion_media_x,
    mjp.posicion_media_y,
    mjp.cobertura_lateral_m
FROM metricas_jugador_partido mjp
JOIN jugadores j         ON j.id = mjp.jugador_id
JOIN equipos e           ON e.id = (
    SELECT equipo_id FROM jugadores WHERE id = mjp.jugador_id LIMIT 1
)
JOIN partidos p          ON p.id = mjp.partido_id
JOIN equipos eq_local    ON eq_local.id = p.equipo_local_id
JOIN equipos eq_vis      ON eq_vis.id = p.equipo_visitante_id
WHERE j.posicion = 'portero';

-- ---------------------------------------------------------------------------
-- VISTA: Timeline de eventos de un partido
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_timeline_eventos AS
SELECT
    ev.id,
    ev.partido_id,
    ev.minuto_partido,
    ev.segundo_partido,
    ev.minuto_partido || ':' || LPAD(ev.segundo_partido::TEXT, 2, '0') AS tiempo_partido,
    te.nombre                           AS tipo_evento,
    te.categoria,
    j.nombre || ' ' || j.apellido       AS jugador,
    j2.nombre || ' ' || j2.apellido     AS jugador_secundario,
    eq.nombre                           AS equipo,
    ev.exitoso,
    ev.bajo_presion,
    zo.nombre                           AS zona_origen,
    zd.nombre                           AS zona_destino,
    ev.x_campo,
    ev.y_campo,
    ev.fuente,
    ev.revisado_humano
FROM eventos ev
JOIN tipos_evento te    ON te.id = ev.tipo_evento_id
LEFT JOIN jugadores j   ON j.id = ev.jugador_id
LEFT JOIN jugadores j2  ON j2.id = ev.jugador_secundario_id
LEFT JOIN equipos eq    ON eq.id = ev.equipo_id
LEFT JOIN zonas_cancha zo ON zo.id = ev.zona_origen_id
LEFT JOIN zonas_cancha zd ON zd.id = ev.zona_destino_id
ORDER BY ev.timestamp_inicio_seg;

-- ---------------------------------------------------------------------------
-- VISTA: Estadísticas de rendimiento de modelos ML
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_rendimiento_modelos AS
SELECT
    m.id,
    m.nombre,
    m.version,
    m.tipo,
    m.arquitectura,
    COUNT(p.id)                                       AS total_predicciones,
    AVG(p.confianza)                                  AS confianza_media,
    SUM(CASE WHEN p.correcto THEN 1 ELSE 0 END) * 100.0
        / NULLIF(COUNT(CASE WHEN p.correcto IS NOT NULL THEN 1 END), 0)
                                                      AS accuracy_pct,
    m.metricas_eval_json,
    m.activo
FROM modelos_ml m
LEFT JOIN predicciones_ml p ON p.modelo_id = m.id
GROUP BY m.id, m.nombre, m.version, m.tipo, m.arquitectura,
         m.metricas_eval_json, m.activo;

-- ---------------------------------------------------------------------------
-- VISTA MATERIALIZADA: Posición media por zona (para dashboards, se refresca periódicamente)
-- ---------------------------------------------------------------------------

CREATE MATERIALIZED VIEW mv_posicion_media_partido AS
SELECT
    sa.id           AS sesion_id,
    v.partido_id,
    tj.jugador_id,
    j.nombre || ' ' || j.apellido AS jugador_nombre,
    j.posicion,
    eq.nombre       AS equipo,
    -- Centroide de posición
    AVG(tj.x_campo) AS centroide_x,
    AVG(tj.y_campo) AS centroide_y,
    STDDEV(tj.x_campo) AS dispersion_x,
    STDDEV(tj.y_campo) AS dispersion_y,
    -- Profundidad (distancia al arco propio media)
    AVG(tj.distancia_arco_propio) AS distancia_arco_media,
    MIN(tj.distancia_arco_propio) AS distancia_arco_min,
    MAX(tj.distancia_arco_propio) AS distancia_arco_max,
    COUNT(*) AS total_frames
FROM tracking_jugadores tj
JOIN sesiones_analisis sa ON sa.id = tj.sesion_id
JOIN videos v             ON v.id = sa.video_id
LEFT JOIN jugadores j     ON j.id = tj.jugador_id
LEFT JOIN equipos eq      ON eq.id = tj.equipo_id
WHERE tj.interpolado = FALSE AND tj.jugador_id IS NOT NULL
GROUP BY sa.id, v.partido_id, tj.jugador_id, j.nombre, j.apellido, j.posicion, eq.nombre
WITH DATA;

CREATE UNIQUE INDEX ON mv_posicion_media_partido (sesion_id, jugador_id);

-- Refrescar con: REFRESH MATERIALIZED VIEW CONCURRENTLY mv_posicion_media_partido;
