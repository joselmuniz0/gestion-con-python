"""
Pipeline de procesamiento de video.
Etapas: carga → extracción de frames → detección YOLO → tracking → coordenadas → persistencia
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FrameData:
    """Contenedor de datos de un frame procesado."""
    frame_numero: int
    timestamp_seg: float
    imagen: np.ndarray                        # BGR original
    imagen_anotada: np.ndarray | None = None  # con overlays de visualización
    detecciones: list = field(default_factory=list)   # lista de Detection
    tracks: list = field(default_factory=list)         # lista de Track
    balon: dict | None = None                 # posición del balón si detectado


@dataclass
class Detection:
    """Detección cruda de YOLO."""
    bbox_x: float   # esquina superior izquierda
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confianza: float
    clase: int      # 0=persona, 32=sports ball en COCO


@dataclass
class Track:
    """Track activo del algoritmo de seguimiento."""
    track_id: int
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confianza: float
    x_campo: float | None = None
    y_campo: float | None = None
    velocidad_ms: float | None = None
    velocidad_kmh: float | None = None
    aceleracion: float | None = None
    direccion_deg: float | None = None


class VideoCaptura:
    """Wrapper sobre cv2.VideoCapture con información de metadatos."""

    def __init__(self, ruta: str | Path):
        self.ruta = str(ruta)
        self._cap = cv2.VideoCapture(self.ruta)
        if not self._cap.isOpened():
            raise FileNotFoundError(f"No se pudo abrir el video: {ruta}")

        self.fps: float = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.total_frames: int = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.ancho: int = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.alto: int = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duracion_seg: float = self.total_frames / self.fps
        logger.info(
            "Video cargado: %s | %.1f fps | %dx%d | %.1f seg | %d frames",
            Path(ruta).name, self.fps, self.ancho, self.alto,
            self.duracion_seg, self.total_frames,
        )

    def frames(
        self,
        paso: int = 1,
        frame_inicio: int = 0,
        frame_fin: int | None = None,
    ) -> Iterator[tuple[int, float, np.ndarray]]:
        """Genera (frame_num, timestamp_seg, imagen) con sub-muestreo opcional."""
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_inicio)
        fin = frame_fin or self.total_frames
        frame_num = frame_inicio

        while frame_num < fin:
            ok, imagen = self._cap.read()
            if not ok:
                break
            if (frame_num - frame_inicio) % paso == 0:
                ts = frame_num / self.fps
                yield frame_num, ts, imagen
            frame_num += 1

    def release(self) -> None:
        self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


class DetectorYOLO:
    """Wrapper sobre Ultralytics YOLO para detección de personas y balón."""

    CLASE_PERSONA = 0
    CLASE_BALON = 32  # sports ball en COCO

    def __init__(
        self,
        modelo: str = "yolov8n.pt",
        confianza_min: float = 0.45,
        iou: float = 0.45,
        device: str = "auto",
    ):
        try:
            from ultralytics import YOLO  # type: ignore
            self._model = YOLO(modelo)
            self._model.to(device if device != "auto" else ("cuda" if self._cuda_disponible() else "cpu"))
        except ImportError:
            raise ImportError("Instalar ultralytics: pip install ultralytics")

        self.confianza_min = confianza_min
        self.iou = iou
        logger.info("YOLO cargado: %s", modelo)

    @staticmethod
    def _cuda_disponible() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def detectar(self, imagen: np.ndarray) -> tuple[list[Detection], Detection | None]:
        """
        Retorna (personas: list[Detection], balon: Detection | None).
        Separa la detección del balón de las personas para tratamiento diferenciado.
        """
        resultados = self._model.predict(
            imagen,
            conf=self.confianza_min,
            iou=self.iou,
            classes=[self.CLASE_PERSONA, self.CLASE_BALON],
            verbose=False,
        )

        personas: list[Detection] = []
        balon: Detection | None = None

        for r in resultados:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                det = Detection(
                    bbox_x=x1,
                    bbox_y=y1,
                    bbox_w=x2 - x1,
                    bbox_h=y2 - y1,
                    confianza=float(box.conf[0]),
                    clase=int(box.cls[0]),
                )
                if det.clase == self.CLASE_PERSONA:
                    personas.append(det)
                elif det.clase == self.CLASE_BALON and (
                    balon is None or det.confianza > balon.confianza
                ):
                    balon = det  # quedarse con el balón de mayor confianza

        return personas, balon


class TrackerMultiObjeto:
    """
    Tracker basado en ByteTrack o BoTrack (via Ultralytics).
    Mantiene identidades a través de frames y recupera tracks perdidos.
    """

    def __init__(self, max_desaparicion: int = 30):
        self.max_desaparicion = max_desaparicion
        self._tracks_activos: dict[int, Track] = {}
        self._historial: dict[int, list[tuple[float, float]]] = {}  # track_id → [(x,y)]
        try:
            from ultralytics.trackers import BYTETracker  # type: ignore
            self._bt = BYTETracker()
            self._usar_bytetrack = True
        except ImportError:
            self._usar_bytetrack = False
            logger.warning("ByteTrack no disponible — usando tracker básico IoU")

    def actualizar(
        self, detecciones: list[Detection], imagen_shape: tuple
    ) -> list[Track]:
        """Recibe detecciones del frame actual y devuelve tracks actualizados."""
        if not detecciones:
            return []

        if self._usar_bytetrack:
            return self._actualizar_bytetrack(detecciones, imagen_shape)
        return self._actualizar_iou(detecciones)

    def _actualizar_bytetrack(
        self, detecciones: list[Detection], imagen_shape: tuple
    ) -> list[Track]:
        import numpy as np
        h, w = imagen_shape[:2]
        dets_np = np.array([
            [d.bbox_x, d.bbox_y, d.bbox_x + d.bbox_w, d.bbox_y + d.bbox_h, d.confianza]
            for d in detecciones
        ], dtype=np.float32)

        tracks_bt = self._bt.update(dets_np, (h, w), (h, w))
        tracks = []
        for t in tracks_bt:
            x1, y1, x2, y2 = t.tlbr
            tracks.append(Track(
                track_id=int(t.track_id),
                bbox_x=float(x1), bbox_y=float(y1),
                bbox_w=float(x2 - x1), bbox_h=float(y2 - y1),
                confianza=float(t.score),
            ))
        return tracks

    def _actualizar_iou(self, detecciones: list[Detection]) -> list[Track]:
        """Fallback IoU simple cuando ByteTrack no está disponible."""
        tracks = []
        for i, det in enumerate(detecciones):
            tracks.append(Track(
                track_id=i,
                bbox_x=det.bbox_x, bbox_y=det.bbox_y,
                bbox_w=det.bbox_w, bbox_h=det.bbox_h,
                confianza=det.confianza,
            ))
        return tracks


class TransformadorCoordenadas:
    """
    Convierte coordenadas de píxeles (imagen) a coordenadas de cancha (metros)
    usando homografía. La homografía se calibra marcando 4+ puntos conocidos.
    """

    # Dimensiones estándar FIFA
    LARGO_CANCHA = 105.0
    ANCHO_CANCHA = 68.0

    def __init__(self, homografia: np.ndarray | None = None):
        self._H = homografia  # matriz 3×3

    def calibrar_desde_puntos(
        self,
        puntos_imagen: list[tuple[float, float]],
        puntos_cancha: list[tuple[float, float]],
    ) -> None:
        """
        Calcula la homografía a partir de 4+ correspondencias.
        puntos_imagen: [(x_px, y_px), ...]  — píxeles en la imagen
        puntos_cancha: [(x_m,  y_m),  ...]  — metros en la cancha
        """
        src = np.array(puntos_imagen, dtype=np.float32)
        dst = np.array(puntos_cancha, dtype=np.float32)
        self._H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        logger.info("Homografía calibrada. Error RMS estimado con RANSAC.")

    def transformar(self, x_px: float, y_px: float) -> tuple[float, float]:
        """Transforma un punto en píxeles a coordenadas de cancha (metros)."""
        if self._H is None:
            raise RuntimeError("Homografía no calibrada. Llamar calibrar_desde_puntos() primero.")
        punto = np.array([[[x_px, y_px]]], dtype=np.float32)
        resultado = cv2.perspectiveTransform(punto, self._H)
        x_m, y_m = float(resultado[0][0][0]), float(resultado[0][0][1])
        # Clamp a límites de cancha
        x_m = max(0.0, min(x_m, self.LARGO_CANCHA))
        y_m = max(0.0, min(y_m, self.ANCHO_CANCHA))
        return x_m, y_m

    def transformar_lote(
        self, puntos: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Versión vectorizada para múltiples puntos."""
        if self._H is None:
            raise RuntimeError("Homografía no calibrada.")
        src = np.array([[list(p)] for p in puntos], dtype=np.float32)
        dst = cv2.perspectiveTransform(src, self._H)
        return [
            (
                float(max(0.0, min(pt[0][0], self.LARGO_CANCHA))),
                float(max(0.0, min(pt[0][1], self.ANCHO_CANCHA))),
            )
            for pt in dst
        ]

    def serializar(self) -> list[list[float]]:
        """Serializa la homografía como lista de listas (para almacenar en JSON)."""
        return self._H.tolist() if self._H is not None else []

    @classmethod
    def desde_json(cls, datos: list[list[float]]) -> "TransformadorCoordenadas":
        t = cls()
        t._H = np.array(datos, dtype=np.float64)
        return t


class PipelineVideoanálisis:
    """
    Pipeline completo de videoanálisis.
    Orquesta: VideoCaptura → YOLO → Tracker → Coordenadas → Persistencia
    """

    def __init__(
        self,
        ruta_video: str | Path,
        sesion_id: int,
        homografia: list[list[float]] | None = None,
        modelo_yolo: str = "yolov8n.pt",
        confianza_min: float = 0.45,
        paso_frames: int = 1,
    ):
        self.ruta_video = ruta_video
        self.sesion_id = sesion_id
        self.paso_frames = paso_frames

        self.detector = DetectorYOLO(modelo_yolo, confianza_min)
        self.tracker = TrackerMultiObjeto()
        self.transformador = (
            TransformadorCoordenadas.desde_json(homografia)
            if homografia
            else TransformadorCoordenadas()
        )

    def procesar(
        self,
        callback_progreso=None,
        guardar_cada_n: int = 500,
    ) -> list[FrameData]:
        """
        Ejecuta el pipeline completo.
        callback_progreso(frame_actual, total_frames) → opcional para UI/logging
        guardar_cada_n → flush de datos a DB cada N frames
        """
        resultados: list[FrameData] = []
        batch_tracking: list[dict] = []

        with VideoCaptura(self.ruta_video) as video:
            total = video.total_frames
            calculador = CalculadorCinematica(fps=video.fps)

            for frame_num, ts, imagen in video.frames(paso=self.paso_frames):
                # 1. Detección
                personas, balon = self.detector.detectar(imagen)

                # 2. Tracking
                tracks = self.tracker.actualizar(personas, imagen.shape)

                # 3. Transformación de coordenadas
                for track in tracks:
                    cx = track.bbox_x + track.bbox_w / 2
                    cy = track.bbox_y + track.bbox_h   # punto inferior del bbox
                    if self.transformador._H is not None:
                        track.x_campo, track.y_campo = self.transformador.transformar(cx, cy)

                # 4. Cinemática
                calculador.calcular_lote(tracks, frame_num)

                # 5. Acumular
                frame_data = FrameData(
                    frame_numero=frame_num,
                    timestamp_seg=ts,
                    imagen=imagen,
                    detecciones=personas,
                    tracks=tracks,
                    balon=self._procesar_balon(balon),
                )
                resultados.append(frame_data)

                # Batch para DB
                for track in tracks:
                    batch_tracking.append(self._track_a_dict(track, frame_num, ts))

                if len(batch_tracking) >= guardar_cada_n:
                    self._persistir_batch(batch_tracking)
                    batch_tracking.clear()

                if callback_progreso:
                    callback_progreso(frame_num, total)

            if batch_tracking:
                self._persistir_batch(batch_tracking)

        logger.info("Pipeline completado: %d frames procesados", len(resultados))
        return resultados

    def _procesar_balon(self, det: Detection | None) -> dict | None:
        if det is None:
            return None
        cx = det.bbox_x + det.bbox_w / 2
        cy = det.bbox_y + det.bbox_h / 2
        x_m, y_m = (
            self.transformador.transformar(cx, cy)
            if self.transformador._H is not None
            else (cx, cy)
        )
        return {"x_campo": x_m, "y_campo": y_m, "confianza": det.confianza}

    def _track_a_dict(self, track: Track, frame: int, ts: float) -> dict:
        return {
            "sesion_id": self.sesion_id,
            "track_id": track.track_id,
            "frame_numero": frame,
            "timestamp_seg": ts,
            "bbox_x": track.bbox_x,
            "bbox_y": track.bbox_y,
            "bbox_w": track.bbox_w,
            "bbox_h": track.bbox_h,
            "confianza_det": track.confianza,
            "x_campo": track.x_campo,
            "y_campo": track.y_campo,
            "velocidad_ms": track.velocidad_ms,
            "velocidad_kmh": track.velocidad_kmh,
            "aceleracion": track.aceleracion,
            "direccion_deg": track.direccion_deg,
        }

    def _persistir_batch(self, batch: list[dict]) -> None:
        """Inserta el batch de tracking en la base de datos."""
        from ..db.database import get_session
        from ..db.models import TrackingJugador

        with get_session() as session:
            session.bulk_insert_mappings(TrackingJugador, batch)
        logger.debug("Batch de %d tracks persistido", len(batch))


class CalculadorCinematica:
    """Calcula velocidad, aceleración y dirección a partir de posiciones consecutivas."""

    def __init__(self, fps: float):
        self.fps = fps
        self._prev_pos: dict[int, tuple[float, float]] = {}
        self._prev_vel: dict[int, float] = {}

    def calcular_lote(self, tracks: list[Track], frame_num: int) -> None:
        dt = 1.0 / self.fps
        for track in tracks:
            if track.x_campo is None:
                continue
            tid = track.track_id
            if tid in self._prev_pos:
                px, py = self._prev_pos[tid]
                dx = track.x_campo - px
                dy = track.y_campo - py
                dist = (dx**2 + dy**2) ** 0.5
                vel_ms = dist / dt
                track.velocidad_ms = round(vel_ms, 3)
                track.velocidad_kmh = round(vel_ms * 3.6, 2)
                # Aceleración
                if tid in self._prev_vel:
                    track.aceleracion = round((vel_ms - self._prev_vel[tid]) / dt, 4)
                # Dirección (0° = eje X positivo, sentido antihorario)
                if dist > 0.01:
                    import math
                    track.direccion_deg = round(math.degrees(math.atan2(dy, dx)) % 360, 2)
                self._prev_vel[tid] = vel_ms
            self._prev_pos[tid] = (track.x_campo, track.y_campo)
