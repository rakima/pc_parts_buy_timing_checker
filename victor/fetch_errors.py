from __future__ import annotations

import socket
import urllib.error


class FetchFailure(RuntimeError):
    code = "unknown"


class ConnectionFailure(FetchFailure):
    code = "connection"


class TimeoutFailure(FetchFailure):
    code = "timeout"


class ProductUnavailableFailure(FetchFailure):
    code = "unavailable"


class ParseFailure(FetchFailure):
    code = "parse"


def classify_fetch_error(exc: Exception, target: str) -> FetchFailure:
    if isinstance(exc, FetchFailure):
        return exc
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return TimeoutFailure(f"{target}がタイムアウトしました")
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in (404, 410):
            return ProductUnavailableFailure(f"{target}は販売終了または削除されています")
        return ConnectionFailure(f"{target}を取得できませんでした（HTTP {exc.code}）")
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return TimeoutFailure(f"{target}がタイムアウトしました")
        return ConnectionFailure(f"{target}へ接続できませんでした")
    return ParseFailure(f"{target}の構造を解析できませんでした")
