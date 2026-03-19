"""公司 CDN 文件服务客户端

职责：
  - upload(file_path) → CDN URL     将本地文件上传到公司 CDN，返回公网 URL
  - download(url, dest_path)         将远程 URL 下载到本地路径

上传接口（无鉴权）：
  POST https://**/file/upload
  multipart/form-data，字段名 file
  响应：{"code": 200, "info": "**..."}

使用方式：
    from api.cdn import upload_file, download_file
    cdn_url = await upload_file("/abs/path/report.xlsx")
    await download_file("https://cdn.xxx/input.csv", "/tmp/input.csv")
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# 下载 / 上传超时（秒）
_DOWNLOAD_TIMEOUT = 120
_UPLOAD_TIMEOUT = 60


def _get_upload_url() -> str:
    """每次调用时从环境变量动态读取，确保 load_dotenv() 后能生效。"""
    url = os.environ.get("CDN_UPLOAD_URL", "").strip()
    if not url:
        raise RuntimeError(
            "CDN_UPLOAD_URL 未配置，请在 .env 或环境变量中设置该值。"
        )
    return url


async def upload_file(file_path: str | Path) -> str:
    """将本地文件上传至公司 CDN，返回 CDN 公网 URL。

    对应后端接口:
        POST CDN_UPLOAD_URL
        multipart/form-data，字段名 file（@RequestPart("file") MultipartFile file）
        响应：{"code": 200, "info": "<cdn_url>"}

    Args:
        file_path: 要上传的本地文件绝对路径。

    Returns:
        CDN 公网 URL 字符串。

    Raises:
        FileNotFoundError: 文件不存在。
        RuntimeError: CDN_UPLOAD_URL 未配置，或服务端返回非 200 code。
        httpx.HTTPStatusError: HTTP 层面非 2xx 响应。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"待上传文件不存在: {path}")

    upload_url = _get_upload_url()
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    logger.info("上传文件到 CDN: %s → %s", path.name, upload_url)

    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        with path.open("rb") as f:
            resp = await client.post(
                upload_url,
                files={"file": (path.name, f, mime_type)},
                # httpx 使用 files= 时会自动设置 Content-Type: multipart/form-data
                # 不需要手动指定，手动指定反而会丢失 boundary 导致服务端解析失败
            )

    resp.raise_for_status()

    try:
        body = resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"CDN 响应不是合法 JSON，status={resp.status_code}，body={resp.text!r}"
        ) from exc

    if body.get("code") != 200:
        raise RuntimeError(f"CDN 上传失败，服务端返回: {body}")

    cdn_url: str = body["info"]
    logger.info("CDN 上传成功: %s → %s", path.name, cdn_url)
    return cdn_url


async def download_file(url: str, dest_path: str | Path) -> None:
    """将远程 URL 的文件下载到本地路径。

    Args:
        url:       远程文件 URL。
        dest_path: 本地保存路径（含文件名）。

    Raises:
        httpx.HTTPStatusError: 下载请求返回非 2xx 状态码。
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    logger.info("下载输入文件: %s → %s", url, dest.name)

    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)

    logger.info("下载完成: %s (%d bytes)", dest.name, dest.stat().st_size)
