"""Local microphone recording and faster-whisper transcription."""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path
from typing import Callable, Optional

from bridge_protocol import BASE_DIR


StatusCallback = Callable[[str], None]
_MODELS: dict[tuple[str, str, str, str], object] = {}
_VIRTUAL_DEVICE_HINTS = (
    "virtual",
    "stereo mix",
    "cable output",
    "voicemeeter",
    "映射器",
    "立体声混音",
)


def _notify(callback: Optional[StatusCallback], message: str) -> None:
    if callback:
        callback(message)


def choose_input_device(sd, preferred_name: str = "") -> Optional[int]:
    devices = sd.query_devices()
    preferred = preferred_name.casefold().strip()

    def usable(index: int) -> bool:
        device = devices[index]
        return int(device.get("max_input_channels", 0)) > 0

    if preferred:
        for index, device in enumerate(devices):
            if usable(index) and preferred in str(device.get("name", "")).casefold():
                return index

    try:
        default_index = int(sd.default.device[0])
        if default_index >= 0 and usable(default_index):
            return default_index
    except (TypeError, ValueError, IndexError):
        pass

    for index, device in enumerate(devices):
        name = str(device.get("name", "")).casefold()
        if usable(index) and not any(hint in name for hint in _VIRTUAL_DEVICE_HINTS):
            return index
    return None


def _write_wav(path: Path, samples, sample_rate: int) -> None:
    import numpy as np

    pcm = np.clip(samples.reshape(-1), -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def _language_code(value: str) -> Optional[str]:
    value = value.strip().replace("_", "-")
    if not value or value.casefold() == "auto":
        return None
    return value.split("-", 1)[0].casefold()


def transcribe_once(config: dict, status: Optional[StatusCallback] = None) -> str:
    """Record one clip and transcribe it entirely on the local machine."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("缺少 sounddevice，请先安装 requirements.txt") from exc

    seconds = max(1.0, min(30.0, float(config.get("voice_record_seconds", 5))))
    sample_rate = int(config.get("voice_sample_rate", 16000))
    device = choose_input_device(sd, str(config.get("voice_input_device", "")))
    if device is None:
        raise RuntimeError("没有找到可用的麦克风输入设备")

    device_name = str(sd.query_devices(device).get("name", device))
    _notify(status, f"正在录音（{seconds:g} 秒，{device_name}）…")
    samples = sd.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=device,
    )
    sd.wait()

    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(prefix="game-buddy-", suffix=".wav", delete=False) as temp:
            temp_path = Path(temp.name)
        _write_wav(temp_path, samples, sample_rate)

        _notify(status, "正在本地识别…")
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("缺少 faster-whisper，请先安装 requirements.txt") from exc

        model_name = str(config.get("voice_model", "base"))
        device_name = str(config.get("voice_compute_device", "cpu"))
        compute_type = str(config.get("voice_compute_type", "int8"))
        configured_root = str(config.get("voice_model_download_root", "models")).strip()
        download_root = Path(configured_root or "models")
        if not download_root.is_absolute():
            download_root = BASE_DIR / download_root
        model_cache_dir = download_root / model_name.replace("/", "--").replace("\\", "--")
        model_cache_dir.mkdir(parents=True, exist_ok=True)
        key = (model_name, device_name, compute_type, str(model_cache_dir.resolve()))
        model = _MODELS.get(key)
        if model is None:
            model = WhisperModel(
                model_name,
                device=device_name,
                compute_type=compute_type,
                download_root=str(model_cache_dir),
            )
            _MODELS[key] = model

        segments, _ = model.transcribe(
            str(temp_path),
            language=_language_code(str(config.get("voice_language", "zh-CN"))),
            vad_filter=True,
            beam_size=5,
        )
        text = "".join(segment.text for segment in segments).strip()
        if not text:
            raise RuntimeError("没有识别到清晰语音，请靠近麦克风再试一次")
        _notify(status, "语音已转成文字，可修改后发送")
        return text
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
