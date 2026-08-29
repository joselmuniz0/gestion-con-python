-- =============================================================================
-- FOOTBALL ANALYTICS PLATFORM — SCHEMA RELACIONAL PROFESIONAL
-- Motor: PostgreSQL 15+  (compatible SQLite con ajustes menores)
-- Versión: 2.0
-- =============================================================================
-- Convenciones:
--   • snake_case para tablas y columnas
--   • PK siempre SERIAL / BIGSERIAL (auto-increment)
--   • Timestamps en UTC con timezone
--   • CHECK constraints para enumeraciones cortas
--   • NUMERIC(precision,scale) para métricas físicas críticas
-- =============================================================================

-- ---------------------------------------------------------------------------
-- BLOQUE 1: ENTIDADES ORGANIZATIVAS
-- Describe el contexto institucional: competición, temporada, equipo, jugador
-- ---------------------------------------------------------------------------

CREATE TABLE competiciones (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(120) NOT NULL,
    tipo            VARCHAR(40)  NOT NULL CHECK (tipo IN ('liga','copa','torneo','amistoso','entrenamiento')),
    pais            VARCHAR(60),
    nivel           SMALLINT     CHECK (nivel BETWEEN 1 AND 10),  -- 1 = primera división
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE competiciones IS 'Liga / Copa / Torneo al que pertenecen los partidos';

CREATE TABLE temporadas (
    id              SERIAL PRIMARY KEY,
    competicion_id  INT          NOT NULL REFERENCES competiciones(id) ON DELETE RESTRICT,
    anio_inicio     SMALLINT     NOT NULL,
    anio_fin        SMALLINT     NOT NULL,
    descripcion     VARCHAR(40),   -- e.g. "2024/2025"
    CHECK (anio_fin >= anio_inicio)
);

CREATE TABLE equipos (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(120) NOT NULL,
    nombre_corto    VARCHAR(20),
    pais            VARCHAR(60),
    ciudad          VARCHAR(80),
    estadio         VARCHAR(120),
    color_principal VARCHAR(7),    -- Hex #RRGGBB
    color_secundario VARCHAR(7),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE jugadores (
    id              SERIAL PRIMARY KEY,
    equipo_id       INT          REFERENCES equipos(id) ON DELETE SET NULL,
    nombre          VARCHAR(120) NOT NULL,
    apellido        VARCHAR(120) NOT NULL,
    fecha_nacimiento DATE,
    nacionalidad    VARCHAR(60),
    posicion        VARCHAR(30)  NOT NULL CHECK (posicion IN
                    ('portero','defensa_central','lateral_derecho','lateral_izquierdo',
                     'mediocentro_defensivo','mediocentro','mediapunta',
                     'extremo_derecho','extremo_izquierdo','delantero_centro','segundo_delantero')),
    numero_camiseta SMALLINT,
    altura_cm       SMALLINT,
    pie_dominante   CHAR(1)      CHECK (pie_dominante IN ('D','I','A')),  -- Derecho/Izquierdo/Ambos
    activo          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- BLOQUE 2: PARTIDOS Y VIDEOS
-- ---------------------------------------------------------------------------

CREATE TABLE partidos (
    id              SERIAL PRIMARY KEY,
    temporada_id    INT          NOT NULL REFERENCES temporadas(id),
    equipo_local_id INT          NOT NULL REFERENCES equipos(id),
    equipo_visitante_id INT      NOT NULL REFERENCES equipos(id),
    fecha_partido   TIMESTAMPTZ  NOT NULL,
    estadio         VARCHAR(120),
    jornada         SMALLINT,
    goles_local     SMALLINT     CHECK (goles_local >= 0),
    goles_visitante SMALLINT     CHECK (goles_visitante >= 0),
    estado          VARCHAR(20)  NOT NULL DEFAULT 'programado'
                    CHECK (estado IN ('programado','en_curso','finalizado','cancelado','suspendido')),
    condiciones_clima VARCHAR(50),
    temperatura_c   NUMERIC(4,1),
    notas           TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CHECK (equipo_local_id <> equipo_visitante_id)
);

CREATE TABLE videos (
    id              SERIAL PRIMARY KEY,
    partido_id      INT          REFERENCES partidos(id) ON DELETE CASCADE,
    nombre_archivo  VARCHAR(255) NOT NULL,
    ruta_storage    VARCHAR(512) NOT NULL,  -- path local o URI S3/GCS
    tipo            VARCHAR(30)  NOT NULL CHECK (tipo IN
                    ('partido_completo','primera_parte','segunda_parte','tiempo_extra',
                     'entrenamiento','clip','highlight','raw')),
    duracion_seg    NUMERIC(8,2),
    fps             NUMERIC(6,2) NOT NULL,
    resolucion_w    SMALLINT,
    resolucion_h    SMALLINT,
    codec           VARCHAR(20),
    tamanio_bytes   BIGINT,
    hash_md5        CHAR(32),    -- integridad del archivo
    procesado       BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE camaras (
    id              SERIAL PRIMARY KEY,
    video_id        INT          NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    tipo            VARCHAR(30)  NOT NULL CHECK (tipo IN
                    ('broadcast','tactivision','dron','gol_norte','gol_sur','lateral_1','lateral_2','ptz')),
    posicion_descripcion VARCHAR(120),
    -- Parámetros intrínsecos de calibración (para homografía)
    focal_length_px NUMERIC(10,4),
    cx              NUMERIC(10,4),  -- centro óptico x
    cy              NUMERIC(10,4),  -- centro óptico y
    distorsion_k1   NUMERIC(10,6),
    distorsion_k2   NUMERIC(10,6),
    -- Matriz de homografía (serializada como JSON array 3x3)
    homografia_json JSONB,
    calibrado       BOOLEAN      NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------------
-- BLOQUE 3: SESIONES DE ANÁLISIS
-- Permite versionar análisis del mismo video con distintos modelos/configs
-- ---------------------------------------------------------------------------

CREATE TABLE sesiones_analisis (
    id              SERIAL PRIMARY KEY,
    video_id        INT          NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    analista        VARCHAR(120),
    modelo_deteccion VARCHAR(80) NOT NULL DEFAULT 'yolov8n',
    version_modelo  VARCHAR(20),
    confianza_min   NUMERIC(4,3) NOT NULL DEFAULT 0.45,
    iou_threshold   NUMERIC(4,3) NOT NULL DEFAULT 0.45,
    fps_procesado   NUMERIC(6,2),  -- puede ser sub-muestreo del video original
    estado          VARCHAR(20)  NOT NULL DEFAULT 'iniciada'
                    CHECK (estado IN ('iniciada','procesando','completada','error')),
    error_mensaje   TEXT,
    frames_totales  INT,
    frames_procesados INT,
    inicio          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    fin             TIMESTAMPTZ,
    metadata_json   JSONB        -- parámetros extra / configuración extendida
);

-- ---------------------------------------------------------------------------
-- BLOQUE 4: ZONAS DE CANCHA
-- Modelo espacial para análisis táctico y heatmaps
-- ---------------------------------------------------------------------------

CREATE TABLE zonas_cancha (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(60)  NOT NULL,
    codigo          VARCHAR(10)  UNIQUE NOT NULL,  -- e.g. 'ARP' = Área rival portería
    descripcion     VARCHAR(200),
    tipo            VARCHAR(30)  NOT NULL CHECK (tipo IN
                    ('tercios','zonas_14','zonas_5x3','custom','area_grande','area_chica',
                     'mediofield','banda','central')),
    -- Polígono en coordenadas de cancha (metros, origen = esquina inferior izquierda)
    -- Formato: [[x1,y1],[x2,y2],...] — rectángulo o polígono
    vertices_json   JSONB        NOT NULL,
    equipo_referencia VARCHAR(10) CHECK (equipo_referencia IN ('local','visitante','neutro'))
);

-- Coordenadas estándar FIFA: 105m x 68m
-- Insertar zonas base al ejecutar el seed script

-- ---------------------------------------------------------------------------
-- BLOQUE 5: DATOS DE TRACKING (núcleo del sistema)
-- Alta frecuencia de escritura — tabla más grande del sistema
-- ---------------------------------------------------------------------------

CREATE TABLE tracking_jugadores (
    id              BIGSERIAL    PRIMARY KEY,
    sesion_id       INT          NOT NULL REFERENCES sesiones_analisis(id) ON DELETE CASCADE,
    jugador_id      INT          REFERENCES jugadores(id) ON DELETE SET NULL,
    equipo_id       INT          REFERENCES equipos(id) ON DELETE SET NULL,
    -- Identificador de track del algoritmo (puede cambiar si tracker pierde al jugador)
    track_id        INT          NOT NULL,
    frame_numero    INT          NOT NULL,
    timestamp_seg   NUMERIC(10,4) NOT NULL,  -- segundos desde inicio del video

    -- Coordenadas en imagen (píxeles)
    bbox_x          NUMERIC(8,2),
    bbox_y          NUMERIC(8,2),
    bbox_w          NUMERIC(8,2),
    bbox_h          NUMERIC(8,2),
    confianza_det   NUMERIC(5,4),

    -- Coordenadas en cancha (metros) — post-homografía
    x_campo         NUMERIC(7,3) NOT NULL,  -- 0..105
    y_campo         NUMERIC(7,3) NOT NULL,  -- 0..68
    z_campo         NUMERIC(6,3),           -- altura estimada (futuro)

    -- Cinemática
    velocidad_ms    NUMERIC(6,3),           -- m/s
    velocidad_kmh   NUMERIC(6,2),           -- km/h
    aceleracion     NUMERIC(7,4),           -- m/s²
    direccion_deg   NUMERIC(6,2),           -- 0-360° (Norte=0, horario)
    velocidad_angular NUMERIC(8,4),         -- rad/s

    -- Orientación corporal (estimada por pose o flujo óptico)
    orientacion_cuerpo_deg NUMERIC(6,2),
    mirada_estimada_deg    NUMERIC(6,2),

    -- Contexto espacial
    zona_id         INT          REFERENCES zonas_cancha(id) ON DELETE SET NULL,
    distancia_arco_propio   NUMERIC(7,3),  -- metros al arco propio
    distancia_arco_rival    NUMERIC(7,3),  -- metros al arco rival
    distancia_balon         NUMERIC(7,3),  -- metros al balón
    distancia_rival_cercano NUMERIC(7,3),  -- metros al rival más próximo
    rivales_en_5m           SMALLINT,      -- cantidad de rivales en radio 5m
    presion_rival           NUMERIC(5,3),  -- índice 0-1 de presión recibida

    -- Indicadores tácticos
    en_posesion     BOOLEAN,
    linea_defensiva BOOLEAN,               -- está en línea defensiva
    fuera_juego     BOOLEAN,

    -- Calidad del dato
    interpolado     BOOLEAN      NOT NULL DEFAULT FALSE,  -- dato estimado entre detecciones
    ocluido         BOOLEAN      NOT NULL DEFAULT FALSE,
    confianza_pose  NUMERIC(4,3)
) PARTITION BY RANGE (frame_numero);

-- Crear particiones por rango de frames (cada 10.000 frames ≈ 5 min a 30fps)
-- En producción, usar particionado por sesion_id o fecha
CREATE TABLE tracking_jugadores_p0
    PARTITION OF tracking_jugadores FOR VALUES FROM (0) TO (10000);
CREATE TABLE tracking_jugadores_p1
    PARTITION OF tracking_jugadores FOR VALUES FROM (10000) TO (20000);
CREATE TABLE tracking_jugadores_p2
    PARTITION OF tracking_jugadores FOR VALUES FROM (20000) TO (30000);
CREATE TABLE tracking_jugadores_p3
    PARTITION OF tracking_jugadores FOR VALUES FROM (30000) TO (40000);
CREATE TABLE tracking_jugadores_p4
    PARTITION OF tracking_jugadores FOR VALUES FROM (40000) TO (50000);
CREATE TABLE tracking_jugadores_default
    PARTITION OF tracking_jugadores DEFAULT;

-- ---------------------------------------------------------------------------
-- BLOQUE 6: TRACKING DEL BALÓN
-- ---------------------------------------------------------------------------

CREATE TABLE tracking_balon (
    id              BIGSERIAL    PRIMARY KEY,
    sesion_id       INT          NOT NULL REFERENCES sesiones_analisis(id) ON DELETE CASCADE,
    frame_numero    INT          NOT NULL,
    timestamp_seg   NUMERIC(10,4) NOT NULL,
    x_campo         NUMERIC(7,3),
    y_campo         NUMERIC(7,3),
    z_estimada      NUMERIC(6,3),           -- altura (estimada por tamaño de bounding box)
    velocidad_ms    NUMERIC(7,3),
    direccion_deg   NUMERIC(6,2),
    confianza_det   NUMERIC(5,4),
    en_juego        BOOLEAN      NOT NULL DEFAULT TRUE,
    zona_id         INT          REFERENCES zonas_cancha(id)
) PARTITION BY RANGE (frame_numero);

CREATE TABLE tracking_balon_p0   PARTITION OF tracking_balon FOR VALUES FROM (0)     TO (10000);
CREATE TABLE tracking_balon_p1   PARTITION OF tracking_balon FOR VALUES FROM (10000) TO (20000);
CREATE TABLE tracking_balon_p2   PARTITION OF tracking_balon FOR VALUES FROM (20000) TO (30000);
CREATE TABLE tracking_balon_p3   PARTITION OF tracking_balon FOR VALUES FROM (30000) TO (40000);
CREATE TABLE tracking_balon_default PARTITION OF tracking_balon DEFAULT;

-- ---------------------------------------------------------------------------
-- BLOQUE 7: EVENTOS
-- Acciones discretas detectadas manual o automáticamente
-- ---------------------------------------------------------------------------

CREATE TABLE tipos_evento (
    id              SERIAL       PRIMARY KEY,
    nombre          VARCHAR(60)  UNIQUE NOT NULL,
    categoria       VARCHAR(40)  NOT NULL CHECK (categoria IN
                    ('gol','remate','pase','duelo','porteria','defensa',
                     'tactica','balon_parado','lesion','disciplina','otro')),
    descripcion     VARCHAR(200),
    automatizable   BOOLEAN      NOT NULL DEFAULT FALSE  -- puede detectarse por IA
);

CREATE TABLE eventos (
    id              BIGSERIAL    PRIMARY KEY,
    sesion_id       INT          NOT NULL REFERENCES sesiones_analisis(id) ON DELETE CASCADE,
    partido_id      INT          REFERENCES partidos(id) ON DELETE SET NULL,
    tipo_evento_id  INT          NOT NULL REFERENCES tipos_evento(id),
    jugador_id      INT          REFERENCES jugadores(id) ON DELETE SET NULL,
    jugador_secundario_id INT    REFERENCES jugadores(id) ON DELETE SET NULL,
    equipo_id       INT          REFERENCES equipos(id) ON DELETE SET NULL,

    frame_inicio    INT          NOT NULL,
    frame_fin       INT,
    timestamp_inicio_seg NUMERIC(10,4) NOT NULL,
    timestamp_fin_seg    NUMERIC(10,4),
    minuto_partido  SMALLINT,
    segundo_partido SMALLINT,

    x_campo         NUMERIC(7,3),
    y_campo         NUMERIC(7,3),

    -- Resultado / outcome
    exitoso         BOOLEAN,
    descripcion     VARCHAR(255),

    -- Contexto táctico
    bajo_presion    BOOLEAN,
    zona_origen_id  INT          REFERENCES zonas_cancha(id),
    zona_destino_id INT          REFERENCES zonas_cancha(id),

    -- Metadatos para ML
    confianza_deteccion NUMERIC(5,4),  -- si fue detectado automáticamente
    revisado_humano BOOLEAN      NOT NULL DEFAULT FALSE,
    fuente          VARCHAR(20)  NOT NULL DEFAULT 'manual'
                    CHECK (fuente IN ('manual','automatico','semiautomatico')),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- BLOQUE 8: MÉTRICAS AGREGADAS
-- Resultados de cálculos estadísticos — evitar recalcular en cada consulta
-- ---------------------------------------------------------------------------

CREATE TABLE metricas_jugador_partido (
    id              SERIAL       PRIMARY KEY,
    sesion_id       INT          NOT NULL REFERENCES sesiones_analisis(id) ON DELETE CASCADE,
    jugador_id      INT          NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    partido_id      INT          REFERENCES partidos(id),

    -- Distancias
    distancia_total_m       NUMERIC(8,1),
    distancia_sprint_m      NUMERIC(7,1),   -- >25 km/h
    distancia_alta_int_m    NUMERIC(7,1),   -- 19.8-25 km/h
    distancia_media_int_m   NUMERIC(7,1),   -- 14.4-19.8 km/h
    distancia_baja_int_m    NUMERIC(7,1),   -- <14.4 km/h

    -- Velocidad
    velocidad_max_kmh       NUMERIC(5,2),
    velocidad_media_kmh     NUMERIC(5,2),
    sprints_total           SMALLINT,

    -- Aceleración
    aceleracion_max         NUMERIC(6,3),
    desaceleracion_max      NUMERIC(6,3),
    aceleraciones_alta_int  SMALLINT,       -- >3 m/s²
    desaceleraciones_alta_int SMALLINT,

    -- Específicos de arquero
    achiques_realizados     SMALLINT,
    distancia_achique_media_m NUMERIC(5,2),
    salidas_area_grande     SMALLINT,
    salidas_area_chica      SMALLINT,
    tiempo_en_area_chica_seg NUMERIC(8,2),
    tiempo_en_area_grande_seg NUMERIC(8,2),
    posicion_media_x        NUMERIC(7,3),
    posicion_media_y        NUMERIC(7,3),
    cobertura_lateral_m     NUMERIC(6,2),   -- amplitud lateral cubierta

    -- Físicos generales
    tiempo_activo_seg       NUMERIC(8,2),
    frames_analizados       INT,

    calculado_en            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE metricas_equipo_partido (
    id              SERIAL       PRIMARY KEY,
    sesion_id       INT          NOT NULL REFERENCES sesiones_analisis(id) ON DELETE CASCADE,
    equipo_id       INT          NOT NULL REFERENCES equipos(id) ON DELETE CASCADE,
    partido_id      INT          REFERENCES partidos(id),

    posesion_pct    NUMERIC(5,2),
    ppda            NUMERIC(6,3),           -- Passes Allowed Per Defensive Action
    linea_defensiva_media_m NUMERIC(6,2),
    compacidad_media_m2     NUMERIC(8,2),   -- área convex hull del equipo
    profundidad_media_m     NUMERIC(6,2),
    amplitud_media_m        NUMERIC(6,2),

    calculado_en    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- BLOQUE 9: CLIPS Y ETIQUETAS
-- Sub-segmentos de video para revisión táctica y entrenamiento
-- ---------------------------------------------------------------------------

CREATE TABLE clips (
    id              SERIAL       PRIMARY KEY,
    video_id        INT          NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    nombre          VARCHAR(120) NOT NULL,
    frame_inicio    INT          NOT NULL,
    frame_fin       INT          NOT NULL,
    timestamp_inicio_seg NUMERIC(10,4) NOT NULL,
    timestamp_fin_seg    NUMERIC(10,4) NOT NULL,
    ruta_clip       VARCHAR(512),           -- path del clip exportado
    thumbnail_path  VARCHAR(512),
    descripcion     TEXT,
    revisado        BOOLEAN      NOT NULL DEFAULT FALSE,
    created_by      VARCHAR(80),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CHECK (frame_fin > frame_inicio)
);

CREATE TABLE etiquetas_tacticas (
    id              SERIAL       PRIMARY KEY,
    nombre          VARCHAR(80)  UNIQUE NOT NULL,
    categoria       VARCHAR(40)  NOT NULL CHECK (categoria IN
                    ('sistema_juego','transicion','balon_parado','pressing','defensa',
                     'ataque','porteria','set_piece','patron_movimiento','situacional')),
    descripcion     VARCHAR(300),
    color_hex       VARCHAR(7)
);

CREATE TABLE clips_etiquetas (
    clip_id         INT          NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    etiqueta_id     INT          NOT NULL REFERENCES etiquetas_tacticas(id) ON DELETE CASCADE,
    PRIMARY KEY (clip_id, etiqueta_id)
);

CREATE TABLE eventos_etiquetas (
    evento_id       BIGINT       NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
    etiqueta_id     INT          NOT NULL REFERENCES etiquetas_tacticas(id) ON DELETE CASCADE,
    PRIMARY KEY (evento_id, etiqueta_id)
);

-- ---------------------------------------------------------------------------
-- BLOQUE 10: MÓDULO MACHINE LEARNING
-- Gestión de modelos, datasets y predicciones
-- ---------------------------------------------------------------------------

CREATE TABLE modelos_ml (
    id              SERIAL       PRIMARY KEY,
    nombre          VARCHAR(120) NOT NULL,
    version         VARCHAR(20)  NOT NULL,
    tipo            VARCHAR(60)  NOT NULL CHECK (tipo IN
                    ('deteccion_objetos','tracking','clasificacion_accion',
                     'prediccion_evento','clustering_espacial','anomalia',
                     'pose_estimation','clasificacion_tactica')),
    framework       VARCHAR(40),            -- pytorch, tensorflow, sklearn, etc.
    arquitectura    VARCHAR(80),            -- yolov8, resnet50, lstm, etc.
    ruta_artefacto  VARCHAR(512),
    metricas_eval_json JSONB,               -- mAP, F1, AUC, etc.
    descripcion     TEXT,
    activo          BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE datasets_ml (
    id              SERIAL       PRIMARY KEY,
    nombre          VARCHAR(120) NOT NULL,
    descripcion     TEXT,
    tipo            VARCHAR(40)  NOT NULL CHECK (tipo IN
                    ('entrenamiento','validacion','test','produccion')),
    sesiones_incluidas INT[],               -- IDs de sesiones usadas
    partidos_incluidos INT[],
    n_samples        INT,
    n_features       INT,
    ruta_dataset    VARCHAR(512),
    version         VARCHAR(20),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE predicciones_ml (
    id              BIGSERIAL    PRIMARY KEY,
    modelo_id       INT          NOT NULL REFERENCES modelos_ml(id) ON DELETE CASCADE,
    sesion_id       INT          NOT NULL REFERENCES sesiones_analisis(id) ON DELETE CASCADE,
    frame_numero    INT,
    jugador_id      INT          REFERENCES jugadores(id),
    etiqueta_predicha VARCHAR(80) NOT NULL,
    confianza       NUMERIC(7,6) NOT NULL,
    probabilidades_json JSONB,             -- distribución completa de clases
    ground_truth    VARCHAR(80),           -- para evaluación posterior
    correcto        BOOLEAN,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE features_ml (
    id              BIGSERIAL    PRIMARY KEY,
    sesion_id       INT          NOT NULL REFERENCES sesiones_analisis(id) ON DELETE CASCADE,
    jugador_id      INT          REFERENCES jugadores(id),
    frame_numero    INT          NOT NULL,
    timestamp_seg   NUMERIC(10,4),
    -- Features cinemáticos
    velocidad_ms            NUMERIC(6,3),
    aceleracion             NUMERIC(7,4),
    jerk                    NUMERIC(8,5),   -- variación de aceleración
    direccion_deg           NUMERIC(6,2),
    cambio_direccion_deg    NUMERIC(6,2),
    velocidad_angular       NUMERIC(8,4),
    -- Features espaciales
    x_normalizado           NUMERIC(6,4),  -- 0-1
    y_normalizado           NUMERIC(6,4),
    distancia_arco_propio   NUMERIC(7,3),
    distancia_arco_rival    NUMERIC(7,3),
    distancia_balon         NUMERIC(7,3),
    distancia_rival_1       NUMERIC(7,3),
    distancia_rival_2       NUMERIC(7,3),
    angulo_arco             NUMERIC(6,3),  -- ángulo de tiro al arco
    presion_rival           NUMERIC(5,3),
    rivales_en_5m           SMALLINT,
    -- Features temporales (ventana deslizante)
    velocidad_media_5s      NUMERIC(6,3),
    distancia_5s            NUMERIC(7,3),
    zona_id                 INT,
    -- Target para supervisado
    evento_siguiente        VARCHAR(60),   -- qué evento ocurre en próximos N frames
    tiempo_hasta_evento_s   NUMERIC(8,4)
);

-- ---------------------------------------------------------------------------
-- BLOQUE 11: CONFIGURACIÓN Y AUDITORÍA
-- ---------------------------------------------------------------------------

CREATE TABLE configuraciones (
    id              SERIAL       PRIMARY KEY,
    clave           VARCHAR(100) UNIQUE NOT NULL,
    valor           TEXT         NOT NULL,
    tipo            VARCHAR(20)  NOT NULL DEFAULT 'string'
                    CHECK (tipo IN ('string','integer','float','boolean','json')),
    descripcion     VARCHAR(300),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE logs_procesamiento (
    id              BIGSERIAL    PRIMARY KEY,
    sesion_id       INT          REFERENCES sesiones_analisis(id),
    nivel           VARCHAR(10)  NOT NULL CHECK (nivel IN ('DEBUG','INFO','WARNING','ERROR','CRITICAL')),
    componente      VARCHAR(60),
    mensaje         TEXT         NOT NULL,
    datos_extra     JSONB,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
