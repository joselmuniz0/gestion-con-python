# Football Analytics Platform — Arquitectura Completa

## 1. Visión General del Sistema

La plataforma transforma video de fútbol crudo en inteligencia táctica accionable.  
El flujo va desde bytes de video hasta dashboards y modelos de ML, pasando por cuatro capas:

```
VIDEO CRUDO
    │
    ▼
┌─────────────────────────────────────────┐
│  CAPA 1: INGESTA Y DETECCIÓN            │
│  OpenCV + YOLO + ByteTrack              │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  CAPA 2: TRANSFORMACIÓN Y PERSISTENCIA  │
│  Homografía + PostgreSQL/SQLite          │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  CAPA 3: ANALYTICS Y FEATURES           │
│  Pandas + SciPy + cálculos tácticos     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  CAPA 4: VISUALIZACIÓN Y ML             │
│  Streamlit + Matplotlib + scikit-learn  │
└─────────────────────────────────────────┘
```

---

## 2. Modelo Entidad-Relación — Diagrama Conceptual

```
COMPETICION ──(1:N)── TEMPORADA ──(1:N)── PARTIDO
                                              │
                              (1:N)───────────┤──────────(1:N)
                              │               │               │
                           EQUIPO         PARTIDO        EQUIPO
                           (local)                      (visitante)
                              │
                           (1:N)
                              │
                           JUGADOR
                              │
                    ┌─────────┴──────────┐
                    │                    │
                 TRACKING           EVENTOS
                    │                    │
              SESION_ANALISIS       TIPO_EVENTO
                    │
              VIDEO ──(N:1)── PARTIDO
                    │
               CAMARA
```

### Relaciones clave y cardinalidades

| Relación | Cardinalidad | Justificación |
|---|---|---|
| Competicion → Temporadas | 1:N | Una liga tiene múltiples temporadas |
| Temporada → Partidos | 1:N | Una temporada tiene múltiples jornadas |
| Partido → Videos | 1:N | Un partido puede tener cámara principal + secundarias |
| Video → Sesiones | 1:N | El mismo video puede re-analizarse con distintos modelos |
| Sesion → Tracking | 1:N | Una sesión produce millones de registros de posición |
| Sesion → Eventos | 1:N | Los eventos se asocian a la sesión que los detectó |
| Jugador → Tracking | 1:N | Cada jugador tiene una trayectoria por sesión |
| TipoEvento → Eventos | 1:N | Reutilizar catálogo de tipos (normalización) |
| Eventos ↔ Etiquetas | N:M | Un evento puede tener múltiples etiquetas tácticas |

---

## 3. Modelo Relacional — Tablas y Responsabilidades

### Bloque Organizativo
| Tabla | Propósito | Registros típicos |
|---|---|---|
| `competiciones` | Catálogo de ligas/copas | ~10-50 |
| `temporadas` | Años por competición | ~100 |
| `equipos` | Catálogo de clubes | ~200 |
| `jugadores` | Plantel de jugadores | ~5.000 |

### Bloque de Contenido
| Tabla | Propósito | Registros típicos |
|---|---|---|
| `partidos` | Fixture y resultados | ~10.000 |
| `videos` | Archivos de video asociados | ~20.000 |
| `camaras` | Config de cámara + homografía | ~40.000 |
| `sesiones_analisis` | Ejecuciones del pipeline | ~20.000 |

### Bloque de Tracking (alta frecuencia)
| Tabla | Propósito | Registros típicos |
|---|---|---|
| `tracking_jugadores` | Posición de cada jugador por frame | **50-200M por temporada** |
| `tracking_balon` | Posición del balón por frame | 5-20M por temporada |
| `zonas_cancha` | Definición de zonas tácticas | ~20 |

### Bloque Analítico
| Tabla | Propósito |
|---|---|
| `eventos` | Acciones discretas del juego |
| `tipos_evento` | Catálogo de eventos (normalización) |
| `metricas_jugador_partido` | Métricas agregadas ya calculadas |
| `metricas_equipo_partido` | Compacidad, línea, posesión |
| `clips` | Fragmentos de video de interés |
| `etiquetas_tacticas` | Vocabulario táctico |

### Bloque ML
| Tabla | Propósito |
|---|---|
| `features_ml` | Features precalculadas para entrenamiento |
| `modelos_ml` | Registro de versiones de modelos |
| `datasets_ml` | Metadatos de datasets de entrenamiento |
| `predicciones_ml` | Salida de modelos para evaluación |

---

## 4. Pipeline de Videoanálisis — Paso a Paso

### Paso 1: Carga del Video
```python
video = VideoCaptura("partido_river_boca.mp4")
# FPS detectado: 25.0 | Resolución: 1920×1080 | Duración: 5400s
```
**Componentes:** `cv2.VideoCapture` — lee el archivo y expone metadatos (FPS, resolución, total de frames).

### Paso 2: Sub-muestreo de Frames
Para un análisis a 12.5 fps (paso=2) sobre un video de 90 min a 25fps:
- Total frames: 135.000 → procesados: 67.500
- Ahorro de cómputo: 50%

**Decisión de diseño:** procesar todos los frames es innecesario para cinemática. Los modelos de ML se benefician de datos a 10-25fps; el tracking tiene interpolación para los frames saltados.

### Paso 3: Detección con YOLO
```
Frame 720 → YOLOv8n → 22 personas + 1 balón detectados
Tiempo: ~15ms en GPU (RTX 3060)
```
- Clase 0 = persona (jugadores + árbitros)
- Clase 32 = sports ball
- Se conserva solo la detección de mayor confianza para el balón

**Por qué YOLO y no un modelo custom:** Velocidad de inferencia (15ms/frame), rendimiento estado del arte para detección de personas, base de pesos pre-entrenada en millones de imágenes deportivas, fácil fine-tuning con datos propios.

### Paso 4: Tracking Multi-Objeto (ByteTrack)
```
Detecciones frame t → ByteTrack → Tracks con IDs persistentes
Track 5: jugador identificado en 847 frames consecutivos
```
ByteTrack supera a SORT/DeepSORT en oclusiones parciales y es el estándar actual para tracking en deportes. Mantiene identidad del jugador incluso cuando el modelo de detección lo pierde por 1-2 segundos.

### Paso 5: Transformación de Coordenadas (Homografía)
```
(1020px, 540px) → H_3x3 → (52.3m, 34.1m) en coordenadas de cancha
```
La homografía H es una matriz 3×3 que mapea cualquier punto en la imagen al plano de la cancha. Se calibra una vez por video marcando puntos conocidos (esquinas del área, centro del campo).

**Limitación:** La homografía es exacta solo para puntos en el plano del suelo. Los pies del jugador se usan como punto de referencia (no el centro del bounding box).

### Paso 6: Cálculo de Cinemática
```
v(t) = Δposición / Δt
a(t) = Δv / Δt
θ(t) = atan2(Δy, Δx)
```
Se calcula por diferencias finitas. Se aplica suavizado (ventana de 3 frames) para eliminar ruido de detección antes de calcular aceleración.

### Paso 7: Cálculo de Contexto Espacial
Para cada frame:
- Distancia a cada arco: euclídea sobre coordenadas de cancha
- Presión rival: suma gaussiana de cercanía de rivales en radio 5m
- Zona: lookup de qué polígono contiene la posición actual

### Paso 8: Persistencia en Batch
Los datos se acumulan en listas Python y se insertan cada 500 frames con `bulk_insert_mappings`. Esto reduce el overhead de SQLAlchemy de O(N) commits a O(N/500).

### Paso 9: Cálculo de Métricas Agregadas
Al finalizar el procesamiento del video:
```python
metricas = calcular_metricas_jugador(df_tracking, jugador_id, sesion_id, fps)
# → distancia_total_m, velocidad_max, sprints, achiques, etc.
```
Se persisten en `metricas_jugador_partido` para consulta instantánea.

### Paso 10: Extracción de Features para ML
```python
extractor = FeatureExtractor(fps=25.0)
df_features = extractor.extraer(df_tracking, df_balon, df_rivales)
X, y = extractor.preparar_dataset_ml(df_features, target_col="evento_siguiente")
```

---

## 5. Arquitectura de Software — Componentes

```
┌──────────────────────────────────────────────────────────────────┐
│                        INTERFAZ DE USUARIO                        │
│                                                                    │
│   Streamlit Dashboard    │    Jupyter Notebooks    │   CLI         │
│   (análisis en tiempo    │    (exploración,         │   (pipeline  │
│    real, reportes)       │     ML, ad-hoc)           │    producción│
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│                         CAPA DE ANALYTICS                         │
│                                                                    │
│   metrics.py          │  feature_extractor.py  │  tactical.py     │
│   (KPIs físicos)      │  (features ML)         │  (patrones táct.)│
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│                         CAPA DE DATOS                             │
│                                                                    │
│   PostgreSQL 15        │   SQLAlchemy ORM       │   Pandas         │
│   (producción)         │   (abstracción DB)     │   (procesamiento)│
│   SQLite (dev/test)    │                        │                  │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│                       CAPA DE PIPELINE                            │
│                                                                    │
│   video_processor.py   │   detector.py    │   coordinate_transform│
│   (orquestador)        │   (YOLO wrapper) │   (homografía)        │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│                       INFRAESTRUCTURA                             │
│                                                                    │
│   OpenCV (I/O video)   │   CUDA/GPU (inferencia) │  Storage (video│
│   Ultralytics (YOLO)   │   ByteTrack (tracking)  │   files/S3/NFS)│
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Estrategia de Machine Learning

### 6.1 Qué almacenar vs calcular dinámicamente

| Dato | Estrategia | Justificación |
|---|---|---|
| Posición cruda (x,y) | **Almacenar** | Dato base, inmutable, costoso de re-extraer |
| Velocidad, aceleración | **Almacenar** | Requiere datos de múltiples frames, conveniente precalcularlo |
| Distancias a arco | **Almacenar** | Simple de calcular pero muy consultado |
| Features ML (jerk, presión) | **Almacenar en `features_ml`** | Costoso de calcular, reusado en múltiples entrenamientos |
| Estadísticas de partido | **Calcular + cachear** en `metricas_*` | Cambia poco, conveniente materializar |
| Predicciones de modelos | **Almacenar en `predicciones_ml`** | Permite comparar versiones de modelos offline |
| Heatmaps | **Calcular en tiempo real** | Cambia según filtros del usuario |

### 6.2 Casos de uso ML implementables

#### Clasificación de Acciones (supervisado)
- **Input:** ventana de 25 frames de features cinemáticas + espaciales
- **Output:** clase de acción (parado, trote, sprint, achique, salida)
- **Modelo:** LSTM o Transformer temporal
- **Accuracy esperado:** 85-92% según resolución de clases

#### Predicción de Eventos (supervisado, secuencial)
- **Input:** últimos N frames de tracking del arquero + posición del balón
- **Output:** probabilidad de evento en los próximos 2 segundos (achique, remate, etc.)
- **Modelo:** BiLSTM + Atención
- **Aplicación:** alertas en tiempo real para analistas

#### Clustering de Patrones de Posicionamiento (no supervisado)
- **Input:** posición media + métricas cinemáticas por acción
- **Output:** clusters de comportamiento (portero adelantado, posición defensiva, etc.)
- **Modelo:** K-Means o DBSCAN sobre features normalizadas
- **Aplicación:** perfilado automático de estilo de juego

#### Detección de Anomalías
- **Input:** features de posicionamiento durante un partido
- **Output:** frames donde el comportamiento es inusual
- **Modelo:** Autoencoder o Isolation Forest
- **Aplicación:** detección de momentos de alto riesgo no capturados por eventos

### 6.3 Optimización para entrenamiento

```python
# Consulta optimizada para extraer dataset de entrenamiento
df = pd.read_sql("""
    SELECT * FROM features_ml
    WHERE sesion_id IN (SELECT id FROM sesiones_analisis WHERE estado = 'completada')
    AND velocidad_ms IS NOT NULL
    AND evento_siguiente IS NOT NULL
""", engine, dtype_backend="numpy_nullable")

# Usar PyArrow para DataFrames grandes (3-5x más rápido que numpy)
```

**Índice crítico:** `idx_features_sesion (sesion_id, frame_numero)` — necesario para queries por ventana temporal.

---

## 7. Optimización y Escalabilidad

### 7.1 Particionado de tablas

`tracking_jugadores` se particiona por `frame_numero`. Ventajas:
- Las queries sobre un rango de tiempo solo leen 1-2 particiones
- El vacuum/mantenimiento es por partición (menor bloqueo)
- Permite archivar datos históricos eliminando particiones antiguas sin afectar índices

En producción con múltiples partidos, particionar también por `sesion_id`:
```sql
PARTITION BY LIST (sesion_id)
```

### 7.2 Índices estratégicos

Las queries más frecuentes y sus índices:

| Query | Índice usado |
|---|---|
| Heatmap de un jugador en un partido | `idx_tracking_jugador_tiempo` |
| Buscar frames con alta presión | `idx_tracking_sesion_frame` + filtro |
| Timeline de eventos | `idx_eventos_partido` |
| Extraer features por sesión | `idx_features_sesion` |

**Regla:** no crear índices compuestos con más de 3 columnas. Usar `EXPLAIN ANALYZE` para validar que los planes de ejecución los usan.

### 7.3 Vista materializada para dashboards

`mv_posicion_media_partido` pre-calcula centroides de posición. Se refresca con:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_posicion_media_partido;
```
Esto permite refrescar sin bloquear lecturas (requiere índice UNIQUE).

### 7.4 Manejo de grandes volúmenes

Un partido completo (90 min × 22 jugadores × 25fps):
- 90 × 60 × 25 × 22 = **2.97 millones de filas de tracking**
- Con 12 columnas numéricas (8 bytes c/u): ~285 MB por partido en raw

**Estrategias:**
1. **Compresión de columnas:** PostgreSQL con extensión `columnar` (Hydra) o TimescaleDB para datos de series temporales
2. **Subsampling selectivo:** guardar todos los frames pero calcular features solo en frames "interesantes" (con aceleración alta o eventos próximos)
3. **Archivado por temporada:** mover datos de temporadas pasadas a tablas comprimidas o Parquet en S3

### 7.5 Escalabilidad horizontal

Para procesar múltiples videos en paralelo:
```
Pipeline Worker 1 ──→ Video A ──→ DB
Pipeline Worker 2 ──→ Video B ──→ DB
Pipeline Worker 3 ──→ Video C ──→ DB
        │
        ▼
   Celery + Redis (cola de tareas)
```
Cada worker es un proceso Python independiente que ejecuta `PipelineVideoanálisis.procesar()`.

---

## 8. Variables de Tracking — Justificación Técnica

| Variable | Unidad | Descripción | Uso principal |
|---|---|---|---|
| `x_campo`, `y_campo` | metros | Posición en cancha (origen: arco equipo local) | Todo |
| `velocidad_ms` | m/s | Velocidad instantánea (diferencias finitas) | Perfil físico |
| `velocidad_kmh` | km/h | Velocidad en unidades deportivas | Dashboards |
| `aceleracion` | m/s² | Variación de velocidad entre frames | Explosividad |
| `direccion_deg` | grados (0-360°) | Ángulo de desplazamiento | Patrones de movimiento |
| `velocidad_angular` | rad/s | Cambio de orientación corporal | Análisis de reacción |
| `orientacion_cuerpo_deg` | grados | Hacia dónde mira el jugador (estimado por pose) | Análisis táctico |
| `distancia_arco_propio` | metros | Distancia al centro del arco propio | Posicionamiento portero |
| `distancia_arco_rival` | metros | Distancia al arco contrario | Análisis ofensivo |
| `distancia_balon` | metros | Distancia al balón | Cobertura, achiques |
| `distancia_rival_cercano` | metros | Distancia al rival más próximo | Presión, duelos |
| `rivales_en_5m` | entero | Cantidad de rivales en radio 5m | Índice de presión |
| `presion_rival` | 0-1 | Índice de presión recibida (suma gaussiana) | ML, heatmaps |
| `zona_id` | FK | Zona de cancha ocupada | Análisis por zona |
| `interpolado` | bool | True si el dato fue estimado | Calidad de dato |

---

## 9. Estructura del Proyecto

```
football_analytics/
├── schema/
│   ├── 01_tables.sql          ← Definición completa de tablas
│   ├── 02_indexes.sql         ← Índices y constraints de rendimiento
│   ├── 03_views.sql           ← Vistas analíticas y materializadas
│   ├── 04_sample_queries.sql  ← Queries de referencia para analistas
│   └── 05_seed_data.sql       ← Datos de referencia (zonas, tipos de evento)
├── src/
│   ├── pipeline/
│   │   └── video_processor.py ← Pipeline completo: ingesta→detección→tracking→DB
│   ├── features/
│   │   └── feature_extractor.py ← Features cinemáticas, espaciales y temporales
│   ├── analytics/
│   │   └── metrics.py         ← Métricas físicas y tácticas agregadas
│   ├── visualization/
│   │   ├── heatmaps.py        ← Heatmaps, trayectorias, perfiles físicos
│   │   └── dashboard.py       ← Dashboard Streamlit interactivo
│   └── db/
│       ├── models.py          ← SQLAlchemy ORM
│       └── database.py        ← Gestión de conexiones
├── docs/
│   └── ARQUITECTURA.md        ← Este documento
└── requirements.txt           ← Dependencias del proyecto
```

---

## 10. Guía de Inicio Rápido

### Instalación
```bash
cd football_analytics
pip install -r requirements.txt
```

### Configuración de base de datos
```bash
# Desarrollo (SQLite)
export DB_TYPE=sqlite
export SQLITE_PATH=football_analytics.db

# Producción (PostgreSQL)
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_USER=analytics
export DB_PASSWORD=securepassword
export DB_NAME=football_analytics

# Crear esquema (PostgreSQL)
psql -U analytics -d football_analytics -f schema/01_tables.sql
psql -U analytics -d football_analytics -f schema/02_indexes.sql
psql -U analytics -d football_analytics -f schema/03_views.sql
psql -U analytics -d football_analytics -f schema/05_seed_data.sql
```

### Procesar un video
```python
from src.db.database import init_db
from src.pipeline.video_processor import PipelineVideoanálisis

init_db(create_tables=True)  # SQLite dev

pipeline = PipelineVideoanálisis(
    ruta_video="partido.mp4",
    sesion_id=1,
    homografia=[[...], [...], [...]],  # matriz 3x3 precalibrada
    modelo_yolo="yolov8n.pt",
    confianza_min=0.45,
    paso_frames=2,  # procesar a 12.5fps
)
pipeline.procesar(callback_progreso=lambda f, t: print(f"{f}/{t}"))
```

### Lanzar dashboard
```bash
streamlit run src/visualization/dashboard.py
```
