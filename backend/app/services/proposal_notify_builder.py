"""
투자제안 추천/매도 시그널을 디스코드 메시지 텍스트로 조립하는 서비스 모듈 (proposal_notify_builder.py).

매수 추천은 종목코드 기준으로 병합(전략별 확률 누적)하고, 매도 시그널은 보유 종목의
기준일 매도 신호를 한 줄씩 포맷한다. 순수 문자열 연산만 담당한다(외부 I/O 없음).
"""

from typing import List, Dict, Any, Tuple


class ProposalNotifyBuilder:
    """추천 목록·매도 시그널을 디스코드 발송용 코드블록 텍스트로 만드는 서비스 클래스."""

    def build(
        self, target_date_disp: str, eval_date_disp: str,
        buy_rows: List[Dict[str, Any]], sell_signals: List[Dict[str, Any]]
    ) -> Tuple[str, int, int]:
        """디스코드 메시지 본문과 (매수 종목수, 매도 종목수)를 반환합니다.

        :param target_date_disp: 표시용 기준일 'YYYY-MM-DD'
        :param eval_date_disp: 표시용 평가일 'YYYY-MM-DD'
        :param buy_rows: get_recommendations() data [{code,name,strategy,prob_up,close_price}, ...]
        :param sell_signals: build_portfolio_view() sell_signals
                             [{code,name,quantity,buy_price,current_price,badges,reason}, ...]
        :return: (message, buy_count, sell_count). 매수·매도 모두 0개면 '추천 없음' 블록을 담는다.
        """
        merged = self._merge_buys(buy_rows)
        blocks: List[str] = []
        if merged:
            blocks.append(self._buy_block(target_date_disp, eval_date_disp, merged))
        if sell_signals:
            blocks.append(self._sell_block(target_date_disp, sell_signals))
        if not blocks:
            blocks.append(self._empty_block(target_date_disp))
        return "\n".join(blocks), len(merged), len(sell_signals)

    def _merge_buys(self, buy_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """종목코드 기준 병합: 전략별 (전략키, 확률) 누적 → 최고 확률 내림차순 정렬."""
        by_code: Dict[str, Dict[str, Any]] = {}
        for r in buy_rows:
            entry = by_code.setdefault(r["code"], {
                "code": r["code"],
                "name": r.get("name") or r["code"],
                "close_price": int(r.get("close_price", 0) or 0),
                "strats": [],
            })
            entry["strats"].append((r["strategy"], float(r.get("prob_up", 0.0) or 0.0)))
        items = list(by_code.values())
        for entry in items:
            entry["strats"].sort(key=lambda t: t[1], reverse=True)
            entry["max_prob"] = entry["strats"][0][1] if entry["strats"] else 0.0
        items.sort(key=lambda e: e["max_prob"], reverse=True)
        return items

    def _buy_block(self, td: str, ed: str, items: List[Dict[str, Any]]) -> str:
        """매수 추천 코드블록 문자열을 만듭니다."""
        lines = [f"📈 매수 추천  |  기준일: {td} (평가일: {ed})", ""]
        for i, e in enumerate(items, 1):
            algos = ", ".join(f"{k}({p:.1f}%)" for k, p in e["strats"])
            lines.append(f"{i:>2} | ({e['code']}){e['name']} | {e['close_price']:,}원 | {algos}")
        lines.append(f"총 {len(items)}개 종목")
        return "```\n" + "\n".join(lines) + "\n```"

    def _sell_block(self, td: str, sigs: List[Dict[str, Any]]) -> str:
        """매도 추천 코드블록 문자열을 만듭니다."""
        lines = [f"🔻 매도 추천  |  기준일: {td}", ""]
        for i, s in enumerate(sigs, 1):
            buy = float(s.get("buy_price") or 0)
            cur = int(s.get("current_price") or 0)
            chg = ((cur - buy) / buy * 100.0) if buy else 0.0
            reason = s.get("reason") or " / ".join(s.get("badges", []))
            lines.append(
                f"{i:>2} | ({s['code']}){s.get('name', s['code'])} | "
                f"{s.get('quantity', 0)}주 | {cur:,}원 ({chg:+.1f}%) | {reason}"
            )
        lines.append(f"총 {len(sigs)}개 종목")
        return "```\n" + "\n".join(lines) + "\n```"

    def _empty_block(self, td: str) -> str:
        """매수·매도 모두 없을 때의 안내 코드블록을 만듭니다."""
        return "```\n" + f"📭 추천 없음  |  기준일: {td}\n\n매수/매도 추천 종목이 없습니다" + "\n```"
