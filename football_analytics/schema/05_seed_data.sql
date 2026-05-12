-- =============================================================================
-- DATOS SEMILLA — Valores de referencia necesarios para operar el sistema
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Zonas estándar de cancha (modelo 5×3 = 15 zonas)
-- Cancha FIFA: 105m largo × 68m ancho
-- Origen: (0,0) = esquina inferior izquierda (arco equipo local)
-- ---------------------------------------------------------------------------

INSERT INTO zonas_cancha (nombre, codigo, descripcion, tipo, vertices_json, equipo_referencia) VALUES
-- TERCIO DEFENSIVO (x: 0-35m)
('Área Chica',           'AC',  'Área pequeña del equipo defensivo',      'area_chica',   '[[0,24.84],[0,43.16],[5.5,43.16],[5.5,24.84]]',                    'local'),
('Área Grande',          'AG',  'Área de penalti del equipo defensivo',   'area_grande',  '[[0,13.84],[0,54.16],[16.5,54.16],[16.5,13.84]]',                  'local'),
('Zona Defensiva Izq',   'DI',  'Tercio defensivo banda izquierda',       'banda',        '[[0,0],[35,0],[35,22.67],[0,22.67]]',                               'local'),
('Zona Defensiva Cent',  'DC',  'Tercio defensivo centro',                'central',      '[[0,22.67],[35,22.67],[35,45.33],[0,45.33]]',                       'local'),
('Zona Defensiva Der',   'DD',  'Tercio defensivo banda derecha',         'banda',        '[[0,45.33],[35,45.33],[35,68],[0,68]]',                             'local'),
-- TERCIO MEDIO (x: 35-70m)
('Mediocampo Izq',       'MI',  'Tercio medio banda izquierda',           'mediofield',   '[[35,0],[70,0],[70,22.67],[35,22.67]]',                             'neutro'),
('Mediocampo Centro',    'MC',  'Tercio medio central',                   'mediofield',   '[[35,22.67],[70,22.67],[70,45.33],[35,45.33]]',                     'neutro'),
('Mediocampo Der',       'MD',  'Tercio medio banda derecha',             'mediofield',   '[[35,45.33],[70,45.33],[70,68],[35,68]]',                           'neutro'),
-- TERCIO OFENSIVO (x: 70-105m)
('Zona Ofensiva Izq',    'OI',  'Tercio ofensivo banda izquierda',        'banda',        '[[70,0],[105,0],[105,22.67],[70,22.67]]',                           'visitante'),
('Zona Ofensiva Cent',   'OC',  'Tercio ofensivo central',                'central',      '[[70,22.67],[105,22.67],[105,45.33],[70,45.33]]',                   'visitante'),
('Zona Ofensiva Der',    'OD',  'Tercio ofensivo banda derecha',          'banda',        '[[70,45.33],[105,45.33],[105,68],[70,68]]',                         'visitante'),
('Área Grande Rival',    'AGR', 'Área de penalti rival',                  'area_grande',  '[[88.5,13.84],[88.5,54.16],[105,54.16],[105,13.84]]',               'visitante'),
('Área Chica Rival',     'ACR', 'Área pequeña rival',                     'area_chica',   '[[99.5,24.84],[99.5,43.16],[105,43.16],[105,24.84]]',               'visitante'),
-- Zonas especiales
('Canal Central',        'CC',  'Pasillo central a lo largo del campo',   'central',      '[[0,22.67],[105,22.67],[105,45.33],[0,45.33]]',                     'neutro'),
('Semicírculo Área',     'SA',  'Zona semicírculo exterior del área',     'custom',       '[[16.5,20],[16.5,48],[30,48],[30,20]]',                             'local');

-- ---------------------------------------------------------------------------
-- Tipos de eventos estándar
-- ---------------------------------------------------------------------------

INSERT INTO tipos_evento (nombre, categoria, descripcion, automatizable) VALUES
-- Portería
('atajada',                 'porteria',  'El arquero detiene el balón',                          TRUE),
('despeje',                 'porteria',  'El arquero aleja el balón con puño o pie',              TRUE),
('achique',                 'porteria',  'El arquero sale de su área a interceptar',              TRUE),
('salida_area',             'porteria',  'El arquero sale del área grande',                       TRUE),
('gol_recibido',            'porteria',  'El arquero recibe un gol',                              TRUE),
('penalti_detenido',        'porteria',  'El arquero detiene un penalti',                         FALSE),
('mala_salida',             'porteria',  'El arquero sale mal y no llega al balón',               FALSE),
-- Remates
('remate_al_arco',          'remate',    'Remate entre los tres palos',                           TRUE),
('remate_fuera',            'remate',    'Remate que va fuera',                                   TRUE),
('remate_bloqueado',        'remate',    'Remate bloqueado por defensor',                         TRUE),
-- Gol
('gol',                     'gol',       'Balón entra al arco',                                   TRUE),
-- Pases
('pase_corto',              'pase',      'Pase de hasta 10 metros',                               FALSE),
('pase_largo',              'pase',      'Pase de más de 25 metros',                              FALSE),
('centro',                  'pase',      'Pase cruzado al área rival',                            FALSE),
-- Defensa
('despeje_defensivo',       'defensa',   'Despeje de un defensor',                                TRUE),
('interceptacion',          'defensa',   'Robo de balón en trayectoria',                          TRUE),
('entrada_defensiva',       'defensa',   'Tackle/entrada al rival',                               FALSE),
-- Tácticos
('presion_alta',            'tactica',   'Equipo aplica pressing alto',                           FALSE),
('linea_alta',              'tactica',   'Equipo mantiene línea defensiva alta',                  FALSE),
('transicion_rapida',       'tactica',   'Transición rápida ataque-defensa',                      FALSE),
-- Balón parado
('corner',                  'balon_parado', 'Saque de esquina',                                   TRUE),
('tiro_libre',              'balon_parado', 'Tiro libre directo o indirecto',                     FALSE),
('penalti',                 'balon_parado', 'Tiro desde el punto de penalti',                     FALSE),
('saque_arco',              'balon_parado', 'Saque de arco del portero',                          TRUE);

-- ---------------------------------------------------------------------------
-- Configuraciones del sistema
-- ---------------------------------------------------------------------------

INSERT INTO configuraciones (clave, valor, tipo, descripcion) VALUES
('cancha_largo_m',          '105',     'float',   'Largo estándar de la cancha en metros'),
('cancha_ancho_m',          '68',      'float',   'Ancho estándar de la cancha en metros'),
('arco_ancho_m',            '7.32',    'float',   'Ancho del arco en metros'),
('arco_alto_m',             '2.44',    'float',   'Alto del arco en metros'),
('area_grande_largo_m',     '16.5',    'float',   'Distancia del arco al borde del área'),
('area_grande_ancho_m',     '40.32',   'float',   'Ancho del área grande'),
('area_chica_largo_m',      '5.5',     'float',   'Distancia del arco al borde del área chica'),
('velocidad_sprint_kmh',    '25',      'float',   'Umbral de velocidad para sprint (km/h)'),
('velocidad_alta_int_kmh',  '19.8',    'float',   'Umbral alta intensidad (km/h)'),
('radio_presion_m',         '5',       'float',   'Radio en metros para cálculo de presión'),
('fps_default_analisis',    '25',      'float',   'FPS por defecto para subsampling de análisis'),
('modelo_deteccion_default','yolov8n', 'string',  'Modelo YOLO por defecto para detección'),
('confianza_min_default',   '0.45',    'float',   'Confianza mínima de detección por defecto'),
('max_distancia_reasignacion','50',    'float',   'Máxima distancia en px para reasignar track'),
('interpolar_gaps_max',     '10',      'integer', 'Máximo de frames a interpolar en gaps de tracking');
