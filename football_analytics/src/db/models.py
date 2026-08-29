"""
SQLAlchemy ORM models — espejo del esquema relacional de football_analytics.
Usar con PostgreSQL (psycopg2) o SQLite (para desarrollo local).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime,
    Float, ForeignKey, Integer, Numeric, SmallInteger, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ENTIDADES ORGANIZATIVAS
# ---------------------------------------------------------------------------

class Competicion(Base):
    __tablename__ = "competiciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    pais: Mapped[Optional[str]] = mapped_column(String(60))
    nivel: Mapped[Optional[int]] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    temporadas: Mapped[List["Temporada"]] = relationship(back_populates="competicion")


class Temporada(Base):
    __tablename__ = "temporadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competicion_id: Mapped[int] = mapped_column(ForeignKey("competiciones.id"), nullable=False)
    anio_inicio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    anio_fin: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(40))

    competicion: Mapped["Competicion"] = relationship(back_populates="temporadas")
    partidos: Mapped[List["Partido"]] = relationship(back_populates="temporada")


class Equipo(Base):
    __tablename__ = "equipos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    nombre_corto: Mapped[Optional[str]] = mapped_column(String(20))
    pais: Mapped[Optional[str]] = mapped_column(String(60))
    ciudad: Mapped[Optional[str]] = mapped_column(String(80))
    estadio: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    jugadores: Mapped[List["Jugador"]] = relationship(back_populates="equipo")


class Jugador(Base):
    __tablename__ = "jugadores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipos.id"))
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    apellido: Mapped[str] = mapped_column(String(120), nullable=False)
    posicion: Mapped[str] = mapped_column(String(30), nullable=False)
    numero_camiseta: Mapped[Optional[int]] = mapped_column(SmallInteger)
    altura_cm: Mapped[Optional[int]] = mapped_column(SmallInteger)
    pie_dominante: Mapped[Optional[str]] = mapped_column(String(1))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    equipo: Mapped[Optional["Equipo"]] = relationship(back_populates="jugadores")
    tracking: Mapped[List["TrackingJugador"]] = relationship(back_populates="jugador")
    eventos: Mapped[List["Evento"]] = relationship(
        back_populates="jugador", foreign_keys="Evento.jugador_id"
    )


# ---------------------------------------------------------------------------
# PARTIDOS Y VIDEOS
# ---------------------------------------------------------------------------

class Partido(Base):
    __tablename__ = "partidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    temporada_id: Mapped[int] = mapped_column(ForeignKey("temporadas.id"), nullable=False)
    equipo_local_id: Mapped[int] = mapped_column(ForeignKey("equipos.id"), nullable=False)
    equipo_visitante_id: Mapped[int] = mapped_column(ForeignKey("equipos.id"), nullable=False)
    fecha_partido: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estadio: Mapped[Optional[str]] = mapped_column(String(120))
    jornada: Mapped[Optional[int]] = mapped_column(SmallInteger)
    goles_local: Mapped[Optional[int]] = mapped_column(SmallInteger)
    goles_visitante: Mapped[Optional[int]] = mapped_column(SmallInteger)
    estado: Mapped[str] = mapped_column(String(20), default="programado")
    notas: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    temporada: Mapped["Temporada"] = relationship(back_populates="partidos")
    videos: Mapped[List["Video"]] = relationship(back_populates="partido")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partido_id: Mapped[Optional[int]] = mapped_column(ForeignKey("partidos.id"))
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    ruta_storage: Mapped[str] = mapped_column(String(512), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    duracion_seg: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    fps: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    resolucion_w: Mapped[Optional[int]] = mapped_column(SmallInteger)
    resolucion_h: Mapped[Optional[int]] = mapped_column(SmallInteger)
    procesado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    partido: Mapped[Optional["Partido"]] = relationship(back_populates="videos")
    sesiones: Mapped[List["SesionAnalisis"]] = relationship(back_populates="video")


class SesionAnalisis(Base):
    __tablename__ = "sesiones_analisis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id"), nullable=False)
    analista: Mapped[Optional[str]] = mapped_column(String(120))
    modelo_deteccion: Mapped[str] = mapped_column(String(80), default="yolov8n")
    version_modelo: Mapped[Optional[str]] = mapped_column(String(20))
    confianza_min: Mapped[float] = mapped_column(Numeric(4, 3), default=0.45)
    fps_procesado: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    estado: Mapped[str] = mapped_column(String(20), default="iniciada")
    frames_totales: Mapped[Optional[int]] = mapped_column(Integer)
    frames_procesados: Mapped[Optional[int]] = mapped_column(Integer)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    fin: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB)

    video: Mapped["Video"] = relationship(back_populates="sesiones")
    tracking: Mapped[List["TrackingJugador"]] = relationship(back_populates="sesion")
    eventos: Mapped[List["Evento"]] = relationship(back_populates="sesion")


# ---------------------------------------------------------------------------
# TRACKING
# ---------------------------------------------------------------------------

class ZonaCancha(Base):
    __tablename__ = "zonas_cancha"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    codigo: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    vertices_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    equipo_referencia: Mapped[Optional[str]] = mapped_column(String(10))


class TrackingJugador(Base):
    __tablename__ = "tracking_jugadores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sesion_id: Mapped[int] = mapped_column(ForeignKey("sesiones_analisis.id"), nullable=False)
    jugador_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jugadores.id"))
    equipo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipos.id"))
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_numero: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seg: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    # Coordenadas de imagen
    bbox_x: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    bbox_y: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    bbox_w: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    bbox_h: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    confianza_det: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    # Coordenadas en cancha
    x_campo: Mapped[float] = mapped_column(Numeric(7, 3), nullable=False)
    y_campo: Mapped[float] = mapped_column(Numeric(7, 3), nullable=False)

    # Cinemática
    velocidad_ms: Mapped[Optional[float]] = mapped_column(Numeric(6, 3))
    velocidad_kmh: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    aceleracion: Mapped[Optional[float]] = mapped_column(Numeric(7, 4))
    direccion_deg: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    velocidad_angular: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    orientacion_cuerpo_deg: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))

    # Contexto espacial
    zona_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zonas_cancha.id"))
    distancia_arco_propio: Mapped[Optional[float]] = mapped_column(Numeric(7, 3))
    distancia_arco_rival: Mapped[Optional[float]] = mapped_column(Numeric(7, 3))
    distancia_balon: Mapped[Optional[float]] = mapped_column(Numeric(7, 3))
    distancia_rival_cercano: Mapped[Optional[float]] = mapped_column(Numeric(7, 3))
    rivales_en_5m: Mapped[Optional[int]] = mapped_column(SmallInteger)
    presion_rival: Mapped[Optional[float]] = mapped_column(Numeric(5, 3))

    # Indicadores
    interpolado: Mapped[bool] = mapped_column(Boolean, default=False)
    ocluido: Mapped[bool] = mapped_column(Boolean, default=False)

    sesion: Mapped["SesionAnalisis"] = relationship(back_populates="tracking")
    jugador: Mapped[Optional["Jugador"]] = relationship(back_populates="tracking")
    zona: Mapped[Optional["ZonaCancha"]] = relationship()


# ---------------------------------------------------------------------------
# EVENTOS
# ---------------------------------------------------------------------------

class TipoEvento(Base):
    __tablename__ = "tipos_evento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    categoria: Mapped[str] = mapped_column(String(40), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(200))
    automatizable: Mapped[bool] = mapped_column(Boolean, default=False)


class Evento(Base):
    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sesion_id: Mapped[int] = mapped_column(ForeignKey("sesiones_analisis.id"), nullable=False)
    partido_id: Mapped[Optional[int]] = mapped_column(ForeignKey("partidos.id"))
    tipo_evento_id: Mapped[int] = mapped_column(ForeignKey("tipos_evento.id"), nullable=False)
    jugador_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jugadores.id"))
    jugador_secundario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jugadores.id"))
    equipo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("equipos.id"))
    frame_inicio: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_fin: Mapped[Optional[int]] = mapped_column(Integer)
    timestamp_inicio_seg: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    minuto_partido: Mapped[Optional[int]] = mapped_column(SmallInteger)
    x_campo: Mapped[Optional[float]] = mapped_column(Numeric(7, 3))
    y_campo: Mapped[Optional[float]] = mapped_column(Numeric(7, 3))
    exitoso: Mapped[Optional[bool]] = mapped_column(Boolean)
    bajo_presion: Mapped[Optional[bool]] = mapped_column(Boolean)
    zona_origen_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zonas_cancha.id"))
    zona_destino_id: Mapped[Optional[int]] = mapped_column(ForeignKey("zonas_cancha.id"))
    confianza_deteccion: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    revisado_humano: Mapped[bool] = mapped_column(Boolean, default=False)
    fuente: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    sesion: Mapped["SesionAnalisis"] = relationship(back_populates="eventos")
    jugador: Mapped[Optional["Jugador"]] = relationship(
        back_populates="eventos", foreign_keys=[jugador_id]
    )
    tipo_evento: Mapped["TipoEvento"] = relationship()
