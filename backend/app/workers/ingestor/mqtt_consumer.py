from __future__ import annotations
import json
from typing import Callable, Dict, Any

import paho.mqtt.client as mqtt

from .config import MqttConfig

class MqttConsumer:
    def __init__(self, cfg: MqttConfig, on_payload: Callable[[str, Dict[str, Any]], None]):
        self._cfg = cfg
        self._on_payload = on_payload

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def start_forever(self):
        print(f"[MQTT] connecting {self._cfg.host}:{self._cfg.port} ...")
        self._client.connect(self._cfg.host, self._cfg.port, 60)
        self._client.loop_forever()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"[MQTT] Connected: {reason_code}")
        client.subscribe(self._cfg.topic_filter, qos=self._cfg.qos)
        print(f"[MQTT] Subscribed: {self._cfg.topic_filter} qos={self._cfg.qos}")

    def _on_disconnect(self, client, userdata, reason_code, properties):
        print(f"[MQTT] Disconnected: {reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            print(f"[ERR][MQTT] JSON inválido topic={msg.topic} err={e}")
            return

        self._on_payload(msg.topic, payload)
