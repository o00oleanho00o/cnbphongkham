# ported from: src/video/chon-format-video.ts
"""ONE source of truth for how yt-dlp picks the video format. Used on BOTH paths: reading metadata
(``nguon_yt_dlp``) and downloading the file itself (``tai_video_vao_ram``).

WHY IT MUST BE SHARED: the two paths are two SEPARATE yt-dlp calls. The metadata path reads the
``url``/``width``/``height`` of the CHOSEN format and declares them to Zalo to build the play surface; the
download path (when yt-dlp must download from the original URL itself) CHOOSES AGAIN. If the two selectors
drift apart the bot declares the size of one format but sends the bytes of another: exactly the thing that
CRASHED the Zalo app on phones. So the selector is a CORRECTNESS constraint, not just DRY.

---

``CHON_FORMAT``: prefer an already-muxed mp4 stream (picture+sound), NOT the ``download`` variant:

* ``[format_id!=download]``: yt-dlp tags the TikTok format named ``download`` with
  ``format_note: "watermarked"`` (measured). Drop it while a clean choice remains. The second branch
  ``b[ext=mp4]`` still lets it through if it is the ONLY mp4: better a watermark than nothing sendable.
* There is NO merge branch ``bv*+ba``: merging needs ffmpeg, and the image deliberately does not install
  ffmpeg (running ffmpeg on a stranger's content is what this design avoids). ``b``/``best`` only takes a
  stream that ALREADY has both picture and sound.

``CHON_SORT``: prefer h264 over h265/av1 so old phones can play it.

WHY ``-S vcodec:h264`` and NOT ``[vcodec^=avc]`` like the old version: the old one filtered by the string
prefix ``avc``, but today's yt-dlp reports TikTok's h264 as ``vcodec="h264"``, NOT ``"avc1.*"``. So ``^=avc``
matched EMPTY, silently fell to ``b[ext=mp4]`` and took the highest resolution = h265: exactly the codec to
avoid, a SILENT failure (measured deterministically through ``--load-info-json``, see
``test_chon_format_video``). ``-S vcodec:h264`` goes through yt-dlp's INTERNAL codec normaliser: it groups
``avc1.*``/``h264``/``H264`` in one bucket, case-insensitive, so it is immune to relabelling, and since it
only SORTS and does not FILTER there is no "silent empty match" door left. With only h265, ``-f`` still
takes h265 (soft fallback, not empty).

``-S`` (``--format-sort``) is a stable yt-dlp feature of many years; the ``vcodec:<codec>`` syntax is
documented and unchanged.

No forced deviation.
"""

from __future__ import annotations

CHON_FORMAT = "b[ext=mp4][format_id!=download]/b[ext=mp4]/b"
"""``-f`` selector: pre-muxed mp4, avoiding the watermarked version while a clean choice remains."""

CHON_SORT = "vcodec:h264"
"""``-S`` sort: prefer h264 for old phones (uses yt-dlp's codec normalisation)."""


def args_chon_format() -> list[str]:
    """yt-dlp arguments choosing the format: SHARED by the metadata path and the download path."""
    return ["-f", CHON_FORMAT, "-S", CHON_SORT]
