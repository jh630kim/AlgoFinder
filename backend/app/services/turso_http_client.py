"""
Turso(libSQL) HTTP API 경량 클라이언트 (turso_http_client.py).

로컬(Windows) 환경은 `sqlalchemy-libsql`/`libsql-experimental` 휠이 없어 드라이버로는
Turso에 붙지 못한다. 가상매매(prop) 기록을 로컬 `app.db` 와 Turso 사이에서 동기화할 때만,
이 모듈이 Turso의 HTTP API(`/v2/pipeline`)로 직접 SQL을 실행한다. (`requests` 만 사용)
"""

import json
from datetime import datetime

import requests

from backend.app.core.config import settings

# 동기화 대상 계좌 유형(투자제안)
_ACCT = "prop"
# libSQL HTTP 파이프라인 타임아웃(초)
_TIMEOUT = 15


class TursoHttpClient:
    """Turso HTTP API로 paper_* 3테이블을 읽고 전체 교체하는 클라이언트."""

    def __init__(self, paper_db_url: str = None) -> None:
        """`PAPER_DATABASE_URL`(sqlite+libsql://host/?authToken=..)에서 호스트·토큰을 뽑아낸다.

        :param paper_db_url: 미지정 시 settings.PAPER_DATABASE_URL 사용
        """
        raw = paper_db_url if paper_db_url is not None else settings.PAPER_DATABASE_URL
        self._endpoint = ""
        self._token = ""
        if raw:
            self._parse(raw)

    def _parse(self, raw: str) -> None:
        """접속 문자열에서 `https://<host>/v2/pipeline` 엔드포인트와 JWT 토큰을 추출한다."""
        from sqlalchemy import make_url

        url = make_url(raw)
        host = url.host or ""
        query = dict(url.query)
        self._token = query.get("authToken") or query.get("auth_token") or ""
        if host:
            self._endpoint = f"https://{host}/v2/pipeline"

    @property
    def configured(self) -> bool:
        """엔드포인트와 토큰이 모두 준비됐는지 여부."""
        return bool(self._endpoint and self._token)

    # ── HTTP 파이프라인 ────────────────────────────────────────
    @staticmethod
    def _arg(value):
        """파이썬 값을 libSQL 파라미터 표현으로 변환한다."""
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "integer", "value": str(int(value))}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        return {"type": "text", "value": str(value)}

    @staticmethod
    def _cell(cell):
        """libSQL 결과 셀을 파이썬 값으로 되돌린다(정수 value는 문자열로 옴)."""
        t = cell.get("type")
        v = cell.get("value")
        if t == "null":
            return None
        if t == "integer":
            return int(v)
        if t == "float":
            return float(v)
        return v

    def _pipeline(self, statements: list) -> list:
        """[{"sql":.., "args":[..]}] 를 한 연결에서 순차 실행하고 결과 목록을 돌려준다."""
        reqs = [
            {"type": "execute", "stmt": {"sql": s["sql"], "args": [self._arg(a) for a in s.get("args", [])]}}
            for s in statements
        ]
        reqs.append({"type": "close"})
        resp = requests.post(
            self._endpoint,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            data=json.dumps({"requests": reqs}),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        for r in results:
            if r.get("type") == "error":
                raise RuntimeError(f"Turso: {r.get('error', {}).get('message', 'unknown error')}")
        return results

    @staticmethod
    def _rows(result: dict) -> list:
        """execute 결과를 [{col: value}, ...] 형태로 변환한다."""
        res = result.get("response", {}).get("result", {})
        cols = [c["name"] for c in res.get("cols", [])]
        out = []
        for row in res.get("rows", []):
            out.append({cols[i]: TursoHttpClient._cell(cell) for i, cell in enumerate(row)})
        return out

    # ── prop 계좌 읽기/전체 교체 ───────────────────────────────
    def fetch_account(self) -> dict:
        """Turso의 prop 계좌·보유·체결을 export_account 와 동일한 형태로 반환한다."""
        stmts = [
            {"sql": "SELECT account_type, initial_balance, cash_balance, total_asset_value, updated_at "
                    "FROM paper_portfolios WHERE account_type = ? LIMIT 1", "args": [_ACCT]},
            {"sql": "SELECT account_type, stock_code, stock_name, buy_date, buy_price, quantity, "
                    "total_amount, created_at FROM paper_positions WHERE account_type = ? ORDER BY id", "args": [_ACCT]},
            {"sql": "SELECT account_type, trade_date, trade_type, stock_code, stock_name, price, quantity, "
                    "total_amount, realized_pnl, created_at FROM paper_trade_histories "
                    "WHERE account_type = ? ORDER BY id", "args": [_ACCT]},
        ]
        r = self._pipeline(stmts)
        pf_rows = self._rows(r[0])
        return {
            "portfolio": pf_rows[0] if pf_rows else {"account_type": _ACCT, "initial_balance": 10000000.0,
                                                     "cash_balance": 10000000.0, "total_asset_value": 10000000.0},
            "positions": self._rows(r[1]),
            "trade_history": self._rows(r[2]),
        }

    def overwrite_account(self, data: dict) -> dict:
        """Turso의 prop 3테이블을 비우고 data로 재구성한다(BEGIN/COMMIT 원자적)."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pf = data.get("portfolio", {}) or {}
        init = float(pf.get("initial_balance", 10000000.0))
        stmts = [
            {"sql": "BEGIN"},
            {"sql": "DELETE FROM paper_positions WHERE account_type = ?", "args": [_ACCT]},
            {"sql": "DELETE FROM paper_trade_histories WHERE account_type = ?", "args": [_ACCT]},
            {"sql": "DELETE FROM paper_portfolios WHERE account_type = ?", "args": [_ACCT]},
            {"sql": "INSERT INTO paper_portfolios (account_type, initial_balance, cash_balance, "
                    "total_asset_value, updated_at) VALUES (?, ?, ?, ?, ?)",
             "args": [_ACCT, init, float(pf.get("cash_balance", init)),
                      float(pf.get("total_asset_value", pf.get("cash_balance", init))), now]},
        ]
        for row in data.get("positions", []) or []:
            qty = int(row["quantity"])
            price = float(row["buy_price"])
            stmts.append({
                "sql": "INSERT INTO paper_positions (account_type, stock_code, stock_name, buy_date, "
                       "buy_price, quantity, total_amount, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                "args": [_ACCT, str(row["stock_code"]), str(row.get("stock_name") or row["stock_code"]),
                         str(row.get("buy_date", "")), price, qty,
                         float(row.get("total_amount", price * qty)), now],
            })
        for row in data.get("trade_history", []) or []:
            stmts.append({
                "sql": "INSERT INTO paper_trade_histories (account_type, trade_date, trade_type, stock_code, "
                       "stock_name, price, quantity, total_amount, realized_pnl, created_at) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                "args": [_ACCT, str(row.get("trade_date", "")), str(row.get("trade_type", "")),
                         str(row.get("stock_code", "")), str(row.get("stock_name", "")),
                         float(row.get("price", 0) or 0), int(row.get("quantity", 0) or 0),
                         float(row.get("total_amount", 0) or 0), float(row.get("realized_pnl", 0) or 0), now],
            })
        stmts.append({"sql": "COMMIT"})
        self._pipeline(stmts)
        return {
            "portfolios": 1,
            "positions": len(data.get("positions", []) or []),
            "trade_history": len(data.get("trade_history", []) or []),
        }
