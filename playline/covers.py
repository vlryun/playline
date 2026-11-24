# [AI 보조 도구: Claude Code (Claude Opus 5.5), 작업: '음원 파일에 들어 있는 커버 이미지 읽기·축소']
"""곡 커버 이미지.

MP3·WAV 파일의 태그(ID3 APIC 등)에 이미 들어 있는 커버 이미지를 꺼내 작은 썸네일로 만든다.
커버가 없는 곡은 화면에서 디스크 그림으로 대신 보여 준다. 인터넷에서 앨범 이미지를 찾아오지 않는다.
"""

from __future__ import annotations

import base64
import io

THUMB_PX = 160


def extract_cover(data: bytes) -> bytes | None:
    """음원 바이트에서 첫 번째 커버 이미지를 꺼낸다. 없거나 읽을 수 없으면 None."""
    try:
        import mutagen
        m = mutagen.File(io.BytesIO(data))
    except Exception:
        return None
    if m is None or not getattr(m, "tags", None):
        return None
    tags = m.tags
    try:
        if hasattr(tags, "getall"):                      # ID3 (MP3, WAV)
            pics = tags.getall("APIC")
            if pics:
                front = [p for p in pics if getattr(p, "type", None) == 3]
                return (front or pics)[0].data
        pics = getattr(m, "pictures", None)               # FLAC 등
        if pics:
            return pics[0].data
    except Exception:
        return None
    return None


def thumbnail(img: bytes | None, size: int = THUMB_PX) -> bytes | None:
    """정사각형으로 가운데를 잘라 JPEG 썸네일로 줄인다. 이미지가 아니면 None."""
    if not img:
        return None
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(img))
        im = im.convert("RGB")
        w, h = im.size
        side = min(w, h)
        im = im.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
        im = im.resize((size, size), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def data_uri(jpeg: bytes | None) -> str | None:
    if not jpeg:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def cover_uri_from_audio(data: bytes) -> str | None:
    return data_uri(thumbnail(extract_cover(data)))
