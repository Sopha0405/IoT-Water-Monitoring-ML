from __future__ import annotations
import threading
import queue
import time
from typing import Optional, Tuple, Dict, Any

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import WriteOptions

from .config import InfluxConfig, BatchConfig
from .models import Telemetry

class InfluxWriter:
    """
    Consume (topic, payload_dict) desde una cola y escribe Points en Influx con batch writes.
    """
    def __init__(self, influx: InfluxConfig, batch: BatchConfig):
        self._cfg = influx
        self._batch = batch
        self._q: "queue.Queue[Tuple[str, Dict[str, Any]]]" = queue.Queue(maxsize=batch.queue_max)
        self._stop = threading.Event()

        self._client = InfluxDBClient(url=influx.url, token=influx.token, org=influx.org)
        self._write_api = self._client.write_api(
            write_options=WriteOptions(
                batch_size=batch.batch_size,
                flush_interval=batch.flush_interval_ms,
                jitter_interval=batch.jitter_interval_ms,
                retry_interval=batch.retry_interval_ms,
                max_retries=5,
                max_retry_delay=30000,
                exponential_base=2,
            )
        )

        self._thread = threading.Thread(target=self._loop, daemon=True)

    @property
    def queue(self):
        return self._q

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        time.sleep(0.5)
        try:
            self._write_api.flush()
        except Exception:
            pass
        try:
            self._client.close()
        except Exception:
            pass

    def enqueue(self, topic: str, payload: Dict[str, Any]) -> bool:
        """
        Encola sin bloquear. Si está llena, descarta el más viejo y reintenta.
        Devuelve True si se encoló.
        """
        try:
            self._q.put_nowait((topic, payload))
            return True
        except queue.Full:
            # drop oldest
            try:
                _ = self._q.get_nowait()
                self._q.task_done()
            except Exception:
                pass
            try:
                self._q.put_nowait((topic, payload))
                return True
            except queue.Full:
                return False

    def _loop(self):
        print(f"[WRITER] start batch_size={self._batch.batch_size} flush_ms={self._batch.flush_interval_ms}")
        while not self._stop.is_set():
            try:
                topic, payload = self._q.get(timeout=1)
            except queue.Empty:
                continue

            try:
                tel = Telemetry.from_message(topic, payload)
                point = tel.to_point(self._cfg.measurement)
                self._write_api.write(bucket=self._cfg.bucket, org=self._cfg.org, record=point)
            except Exception as e:
                raw = (str(payload)[:200] + "...") if payload else "None"
                print(f"[ERR][INFLUX] {e} raw={raw}")
            finally:
                self._q.task_done()

        print("[WRITER] stopped")
