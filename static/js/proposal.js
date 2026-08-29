/**
 * 투자제안(proposal) / 모의투자(recommendation) 공용 화면 컨트롤러 (proposal.js).
 *
 * 계좌유형은 window.PROPOSAL_ACCOUNT 로 주입('prop'=투자제안 기본, 'rec'=모의투자).
 * - 투자제안(advice): 신호 판단일 = 기준일(D-0).
 * - 모의투자(sim): 신호 판단일 = 기준일 직전 거래일(D-1), 매매 초기값은 기준일(D-0) 종가.
 *   추가로 '다음날 조회'(btnNextDayRec)로 지수 거래일 달력 기준 다음 거래일로 이동한다.
 * S1~S5(8전략) 매수 추천 조회, 실제 체결 내역 수동 기록(매수/매도 모달), 보유 종목 매도
 * 시그널(전략 매도 / -5% 손절 / +10% 익절) 표시. 모든 연산은 백엔드가 수행하며 이 파일은
 * 렌더링과 입력 중계만 담당한다.
 */

(function () {
    "use strict";

    const ACCOUNT = window.PROPOSAL_ACCOUNT || "prop";
    // 모의투자 계좌는 D-1 신호 모드, 투자제안은 기존 D-0 모드
    const MODE = ACCOUNT === "rec" ? "sim" : "advice";
    const IS_MOBILE = !!window.PROPOSAL_MOBILE;
    let sellTargetCode = null;
    let sellMaxQty = 0;
    let proposalChart = null;
    let lastSummary = null;
    // 보조 차트 끝 날짜(YYYYMMDD): 매수추천 표는 판단 기준일(D-1), 그 외 표는 기준일(D-0)
    let chartEndSignal = null;
    let chartEndEval = null;

    const $ = (id) => document.getElementById(id);
    const won = (n) => (Math.round(Number(n) || 0)).toLocaleString() + " 원";
    const setText = (id, v) => { const el = $(id); if (el) el.textContent = v; };
    const pnlColor = (v) => (v > 0 ? "#f87171" : v < 0 ? "#38bdf8" : "#94a3b8");

    // 모의투자 전용: 마지막으로 조회한 기준일을 브라우저에 기억
    const REC_DATE_KEY = "algofinder_rec_target_date";

    function loadRememberedDate() {
        try {
            const v = localStorage.getItem(REC_DATE_KEY) || "";
            return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : "";
        } catch (e) {
            return "";
        }
    }

    function rememberTargetDate(v) {
        if (ACCOUNT !== "rec" || !/^\d{4}-\d{2}-\d{2}$/.test(v || "")) return;
        try { localStorage.setItem(REC_DATE_KEY, v); } catch (e) { /* 사생활 보호 모드 등 */ }
    }

    document.addEventListener("DOMContentLoaded", init);

    function init() {
        const dp = $("recTargetDate");
        // 모의투자는 SSR 기본값보다 '마지막 사용 기준일'을 우선 복원
        if (dp && ACCOUNT === "rec") {
            const saved = loadRememberedDate();
            if (saved) dp.value = saved;
        }
        if (dp && !dp.value) dp.value = new Date().toISOString().slice(0, 10);

        bindClick("btnFetchRec", refresh);
        bindClick("btnNextDayRec", nextDay);
        bindClick("btnNotifyRecommendations", notifyRecommendations);
        bindClick("btnExportPaper", exportPaper);
        bindClick("btnImportPaper", () => { const f = $("importPaperFile"); if (f) f.click(); });
        const impFile = $("importPaperFile");
        if (impFile) impFile.addEventListener("change", importPaperFromFile);
        bindClick("btnSyncTursoPush", () => syncTurso("push"));
        bindClick("btnSyncTursoPull", () => syncTurso("pull"));
        bindClick("btnResetPortfolio", resetPortfolio);
        bindClick("btnOpenManualBuyModal", () => openBuyModal());
        bindClick("btnCloseModal", closeBuyModal);
        bindClick("btnCancelModal", closeBuyModal);
        bindClick("btnConfirmManualBuy", confirmBuy);
        bindClick("btnCloseSellModal", closeSellModal);
        bindClick("btnCancelSellModal", closeSellModal);
        bindClick("btnConfirmManualSell", confirmSell);
        bindClick("btnCloseChartModal", closeChartModal);

        const codeInput = $("inputStockCode");
        if (codeInput) codeInput.addEventListener("blur", autofillStockInfo);

        // SSR로 주입된 코스피 20일선 배지에 초기 국면 색상 적용
        const badge = $("kospiRegimeBadge");
        if (badge) applyRegimeColor(badge, badge.dataset.regime || "");

        refresh();
    }

    function bindClick(id, fn) {
        const el = $(id);
        if (el) el.addEventListener("click", fn);
    }

    function targetDate() {
        const dp = $("recTargetDate");
        return dp && dp.value ? dp.value : new Date().toISOString().slice(0, 10);
    }

    // ── 진행 중 로딩 오버레이 ──────────────────────────────────
    let loadingTimer = null;

    function showLoading() {
        // 캐시 히트(수십 ms)로 즉시 끝나는 경우 깜빡임 방지: 200ms 뒤에만 표시
        if (loadingTimer) return;
        const btn = $("btnFetchRec");
        if (btn) btn.disabled = true;
        loadingTimer = setTimeout(() => {
            const ov = $("proposalLoadingOverlay");
            if (ov) ov.classList.add("active");
        }, 200);
    }

    function hideLoading() {
        if (loadingTimer) { clearTimeout(loadingTimer); loadingTimer = null; }
        const ov = $("proposalLoadingOverlay");
        if (ov) ov.classList.remove("active");
        const btn = $("btnFetchRec");
        if (btn) btn.disabled = false;
    }

    // 'YYYYMMDD' / 'YYYY-MM-DD' → 'YYYY-MM-DD' (그 외/빈값은 원본 반환)
    function fmtYmd(v) {
        const s = String(v || "");
        if (/^\d{8}$/.test(s)) return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
        return s;
    }

    // 실제 평가에 사용된 거래일(eval_date) 표시. 선택일과 다르면 휴장일 안내를 노출
    function renderEvalDate(evalDate, selectedDate) {
        const el = $("evalDateValue");
        const note = $("evalDateNote");
        const shown = fmtYmd(evalDate);
        if (el) el.textContent = shown || "-";
        if (note) note.style.display = (shown && shown !== selectedDate) ? "" : "none";
    }

    // 신호 판단 기준일(D-1) 표시. 모의투자 화면에만 해당 요소가 존재한다
    function renderSignalDate(sig) {
        const el = $("signalDateValue");
        if (el) el.textContent = fmtYmd(sig) || "-";
    }

    // 모의투자: 지수 거래일 달력에서 다음 거래일로 기준일을 이동한 뒤 재조회
    async function nextDay() {
        const note = $("nextDayNote");
        try {
            const r = await fetch(`/api/paper-trading/next-trading-date?date=${targetDate()}`).then((x) => x.json());
            if (r.status === "success" && r.next_date) {
                const dp = $("recTargetDate");
                if (dp) dp.value = r.next_date;
                if (note) note.style.display = "none";
                refresh();
            } else if (note) {
                note.style.display = "";
            }
        } catch (e) {
            console.error("nextDay error:", e);
        }
    }

    // 코스피 20일선 국면(up/down/flat)에 따라 배지 글자색·테두리색을 지정
    function applyRegimeColor(el, regime) {
        const map = {
            up: { color: "#22c55e", border: "rgba(34,197,94,0.45)" },
            down: { color: "#ef4444", border: "rgba(239,68,68,0.45)" },
            flat: { color: "#cbd5e1", border: "rgba(203,213,225,0.35)" },
        };
        const c = map[regime] || { color: "#cbd5e1", border: "rgba(251,191,36,0.3)" };
        el.style.color = c.color;
        el.style.borderColor = c.border;
    }

    // 포트폴리오 응답의 kospi_regime 블록을 배지에 반영
    function renderKospiRegime(kr) {
        const el = $("kospiRegimeBadge");
        if (!el || !kr) return;
        el.textContent = kr.text || "📊 코스피 20일선: -";
        el.dataset.regime = kr.regime || "";
        applyRegimeColor(el, kr.regime || "");
    }

    // ── 데이터 로드 ─────────────────────────────────────────────
    async function refresh() {
        const td = targetDate();
        rememberTargetDate(td);
        showLoading();
        try {
            const [pf, rec] = await Promise.all([
                fetch(`/api/paper-trading/portfolio?account_type=${ACCOUNT}&target_date=${td}&mode=${MODE}`).then((r) => r.json()),
                fetch(`/api/recommended-stocks?target_date=${td}&mode=${MODE}`).then((r) => r.json()),
            ]);
            // 차트 끝 날짜는 렌더(=행 버튼 배선)보다 먼저 확정해야 한다.
            // wireRowButtons가 이 값을 읽어 차트 요청에 end 파라미터로 싣기 때문.
            chartEndEval = rec.eval_date || pf.eval_date || td;
            chartEndSignal = rec.signal_date || pf.signal_date || chartEndEval;
            if (pf.status === "success") {
                renderSummary(pf.summary);
                renderHoldings(pf.positions || []);
                renderSellSignals(pf.sell_signals || []);
            }
            if (pf.status === "success") renderKospiRegime(pf.kospi_regime);
            if (rec.status === "success") renderRecommendations(rec.data || []);
            renderEvalDate(rec.eval_date || pf.eval_date, td);
            renderSignalDate(rec.signal_date || pf.signal_date);
        } catch (e) {
            console.error("proposal refresh error:", e);
        } finally {
            hideLoading();
        }
    }

    // 투자제안: 현재 기준일의 매수 추천 + 보유 매도 시그널을 디스코드로 전달
    async function notifyRecommendations() {
        if (ACCOUNT !== "prop") return;
        if (!confirm("현재 기준일의 매수·매도 추천을 디스코드로 전달할까요?")) return;
        const btn = $("btnNotifyRecommendations");
        const orig = btn ? btn.textContent : "";
        if (btn) { btn.disabled = true; btn.textContent = "전달 중…"; }
        try {
            const r = await fetch("/api/proposal/notify-recommendations", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ target_date: targetDate() }),
            }).then((x) => x.json());
            if (r.status === "success") {
                alert(`디스코드로 매수 ${r.buy_count}건 · 매도 ${r.sell_count}건을 전달했습니다.`);
            } else {
                alert(r.message || "디스코드 전달에 실패했습니다.");
            }
        } catch (e) {
            console.error("notifyRecommendations error:", e);
            alert("디스코드 전달 요청 중 오류가 발생했습니다.");
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = orig; }
        }
    }

    // ── 가상매매 JSON 내보내기 / 불러오기 ─────────────────────
    function downloadJson(obj, filename) {
        const blob = new Blob([JSON.stringify(obj, null, 1)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
    }

    function ymdStamp() {
        return new Date().toISOString().slice(0, 10).replace(/-/g, "");
    }

    async function exportPaper() {
        try {
            const data = await fetch(`/api/paper-trading/export?account_type=${ACCOUNT}`).then((r) => r.json());
            downloadJson(data, `algofinder_${ACCOUNT}_${ymdStamp()}.json`);
        } catch (e) {
            console.error("exportPaper error:", e);
            alert("내보내기에 실패했습니다.");
        }
    }

    async function importPaperFromFile(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) return;
        let payload;
        try {
            payload = JSON.parse(await file.text());
        } catch (e) {
            alert("JSON 파일을 읽을 수 없습니다.");
            return;
        }
        if (!confirm("현재 가상매매 기록을 이 파일 내용으로 완전히 교체합니다.\n교체 직전 상태는 백업 파일로 자동 저장됩니다. 계속할까요?")) return;
        try {
            payload.account_type = ACCOUNT;
            const res = await fetch("/api/paper-trading/import", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            }).then((r) => r.json());
            if (res.status === "success") {
                if (res.backup) downloadJson(res.backup, `algofinder_${ACCOUNT}_backup_${ymdStamp()}.json`);
                const im = res.imported || {};
                alert(`불러오기 완료 (보유 ${im.positions || 0}건 · 체결 ${im.trade_history || 0}건).`);
                refresh();
            } else {
                alert(res.message || "불러오기에 실패했습니다.");
            }
        } catch (e) {
            console.error("importPaper error:", e);
            alert("불러오기 요청 중 오류가 발생했습니다.");
        }
    }

    // 로컬 prop 계좌를 Turso와 한 번에 동기화(push=로컬→Turso, pull=Turso→로컬)
    async function syncTurso(direction) {
        if (ACCOUNT !== "prop") return;
        const isPush = direction === "push";
        const msg = isPush
            ? "로컬 투자제안 기록을 Turso로 완전히 교체합니다.\nTurso 직전 상태는 백업 파일로 저장됩니다. 계속할까요?"
            : "Turso 기록으로 로컬 투자제안을 완전히 교체합니다.\n로컬 직전 상태는 백업 파일로 저장됩니다. 계속할까요?";
        if (!confirm(msg)) return;
        try {
            const res = await fetch(`/api/paper-trading/sync-turso?direction=${direction}`, {
                method: "POST", headers: { "Content-Type": "application/json" },
            }).then((r) => r.json());
            if (res.status === "success") {
                if (res.backup) downloadJson(res.backup, `algofinder_prop_${direction}_backup_${ymdStamp()}.json`);
                const im = res.imported || {};
                alert(`${isPush ? "Turso로 보내기" : "Turso에서 받기"} 완료 (보유 ${im.positions || 0}건 · 체결 ${im.trade_history || 0}건).`);
                refresh();
            } else {
                alert(res.message || "Turso 동기화에 실패했습니다.");
            }
        } catch (e) {
            console.error("syncTurso error:", e);
            alert("Turso 동기화 요청 중 오류가 발생했습니다.");
        }
    }

    async function resetPortfolio() {
        if (!confirm("투자제안 자산을 1,000만원 현금 상태로 초기화하시겠습니까?")) return;
        await fetch("/api/paper-trading/reset", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ account_type: ACCOUNT, initial_balance: 10000000 }),
        });
        refresh();
    }

    // ── 렌더링 ─────────────────────────────────────────────────
    function renderSummary(s) {
        if (!s) return;
        lastSummary = s;
        setText("pfInitial", won(s.initial_balance));
        setText("pfCash", won(s.cash_balance));
        setText("pfStockValue", won(s.stock_value));
        const tp = $("pfTotalAsset");
        if (tp) {
            const sign = s.profit_pct >= 0 ? "+" : "";
            tp.innerHTML = `${won(s.total_asset)} <span style="font-size:13px;color:${pnlColor(s.profit_pct)}">(${sign}${s.profit_pct}%)</span>`;
        }
        setText("pfHoldCount", `${s.holding_count} / ${s.max_slots} 개`);
    }

    function renderHoldings(rows) {
        const box = $("holdingsBody");
        if (!box) return;
        if (!rows.length) {
            box.innerHTML = emptyRow(9, "보유 중인 종목이 없습니다. 추천 표에서 [🛒 매수]를 눌러 실제 체결 내역을 기록하세요.");
            return;
        }
        box.innerHTML = rows.map((p) => {
            const pc = pnlColor(p.profit_pct);
            const sign = p.profit_pct >= 0 ? "+" : "";
            if (IS_MOBILE) {
                return `<div class="mobile-card-item">
                    <div style="display:flex;justify-content:space-between;font-weight:800;color:#fff;margin-bottom:6px;">
                        <span>${p.stock_name} (${p.stock_code})</span><span style="color:${pc}">${sign}${p.profit_pct}%</span></div>
                    <div style="font-size:12px;color:#cbd5e1;">매수 ${won(p.buy_price)} · ${p.quantity}주 · 현재가 ${won(p.current_price)}</div>
                    <div style="font-size:12px;color:${pc};margin:4px 0 8px;">평가손익 ${sign}${(p.profit_krw).toLocaleString()}원</div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn-sell-action" data-sell='${sellData(p)}' style="flex:1;padding:9px;">🔻 매도</button>
                        <button class="btn-chart-view" data-chart='${p.stock_code}|${p.stock_name}' style="flex:1;padding:9px;">📈 차트</button></div>
                </div>`;
            }
            return `<tr>
                <td style="padding:10px;font-weight:700;color:#fff;">${p.stock_name} (${p.stock_code})</td>
                <td style="padding:10px;">${p.buy_date}</td>
                <td style="padding:10px;">${won(p.buy_price)}</td>
                <td style="padding:10px;">${p.quantity}주</td>
                <td style="padding:10px;">${won(p.total_amount)}</td>
                <td style="padding:10px;">${won(p.current_price)}</td>
                <td style="padding:10px;color:${pc};font-weight:700;">${sign}${(p.profit_krw).toLocaleString()}원 (${sign}${p.profit_pct}%)</td>
                <td style="padding:10px;"><button class="btn-sell-action" data-sell='${sellData(p)}'>🔻 매도</button></td>
                <td style="padding:10px;"><button class="btn-chart-view" data-chart='${p.stock_code}|${p.stock_name}'>📊 차트보기</button></td>
            </tr>`;
        }).join("");
        wireRowButtons(box);
    }

    function renderSellSignals(rows) {
        const box = $("sellSignalBody");
        if (!box) return;
        if (!rows.length) {
            box.innerHTML = emptyRow(6, "선택한 기준일에 매도 조건이 포착된 보유 종목이 없습니다.");
            return;
        }
        box.innerHTML = rows.map((r) => {
            if (IS_MOBILE) {
                return `<div class="mobile-card-item" style="border-color:rgba(239,68,68,0.4);">
                    <div style="font-weight:800;color:#f87171;">${r.name} (${r.code})</div>
                    <div style="font-size:12px;color:#fca5a5;margin:4px 0;">${r.badges.join(" · ")}</div>
                    <div style="font-size:12px;color:#cbd5e1;">🚨 ${r.reason}</div>
                    <div style="font-size:12px;color:#94a3b8;margin:4px 0 8px;">${r.quantity}주 · 매수 ${won(r.buy_price)} · 현재 ${won(r.current_price)}</div>
                    <button class="btn-sell-action" data-sell='${sellData({stock_code:r.code,stock_name:r.name,quantity:r.quantity,current_price:r.current_price})}' style="width:100%;padding:9px;">🔻 매도 기록</button>
                </div>`;
            }
            return `<tr style="background:rgba(239,68,68,0.10);">
                <td style="padding:10px;font-weight:700;color:#f87171;">${r.name} (${r.code})</td>
                <td style="padding:10px;">${r.quantity}주</td>
                <td style="padding:10px;">${won(r.buy_price)}</td>
                <td style="padding:10px;">${won(r.current_price)}</td>
                <td style="padding:10px;color:#f87171;font-weight:700;">${r.badges.join(", ")}</td>
                <td style="padding:10px;text-align:left;color:#fca5a5;">🚨 ${r.reason}</td>
            </tr>`;
        }).join("");
        wireRowButtons(box);
    }

    function renderRecommendations(rows) {
        const box = $("recBody");
        if (!box) return;
        if (!rows.length) {
            box.innerHTML = emptyRow(7, "선택한 기준일에 매수 신호가 포착된 종목이 없습니다.");
            return;
        }
        box.innerHTML = rows.map((r) => {
            const buyBtn = `<button class="btn-buy-action" data-buy='${r.code}|${r.name}|${r.close_price}'>🛒 매수</button>`;
            if (IS_MOBILE) {
                return `<div class="mobile-card-item">
                    <div style="display:flex;justify-content:space-between;font-weight:800;color:#fff;">
                        <span>${r.name} (${r.code})</span><span style="color:#38bdf8;">${r.prob_up}%</span></div>
                    <div style="font-size:12px;color:#fbbf24;margin:4px 0;">${r.strategy_name}</div>
                    <div style="font-size:12px;color:#cbd5e1;margin-bottom:8px;">추천가 ${won(r.close_price)} · 💡 ${r.reason}</div>
                    <div style="display:flex;gap:8px;">${buyBtn}
                        <button class="btn-chart-view" data-chart='${r.code}|${r.name}' style="flex:1;">📈 차트</button></div>
                </div>`;
            }
            return `<tr>
                <td style="padding:10px;font-weight:700;color:#fff;">${r.name} (${r.code})</td>
                <td style="padding:10px;color:#94a3b8;">${r.market || "-"}</td>
                <td style="padding:10px;font-weight:800;color:#38bdf8;">${r.prob_up}%</td>
                <td style="padding:10px;font-weight:700;color:#fff;">${won(r.close_price)}</td>
                <td style="padding:10px;color:#fbbf24;">${r.strategy_name}</td>
                <td style="padding:10px;text-align:left;color:#cbd5e1;">💡 ${r.reason}</td>
                <td style="padding:10px;display:flex;gap:6px;justify-content:center;">${buyBtn}
                    <button class="btn-chart-view" data-chart='${r.code}|${r.name}'>📊 차트보기</button></td>
            </tr>`;
        }).join("");
        wireRowButtons(box);
    }

    function emptyRow(cols, msg) {
        return IS_MOBILE
            ? `<div style="padding:18px;text-align:center;color:#64748b;font-size:13px;">${msg}</div>`
            : `<tr><td colspan="${cols}" style="padding:22px;text-align:center;color:#64748b;">${msg}</td></tr>`;
    }

    function sellData(p) {
        return JSON.stringify({ code: p.stock_code, name: p.stock_name, qty: p.quantity, price: p.current_price || 0 })
            .replace(/'/g, "&#39;");
    }

    function wireRowButtons(box) {
        box.querySelectorAll("[data-buy]").forEach((b) =>
            b.addEventListener("click", () => {
                const [code, name, price] = b.getAttribute("data-buy").split("|");
                openBuyModal({ code, name, price });
            }));
        box.querySelectorAll("[data-sell]").forEach((b) =>
            b.addEventListener("click", () => openSellModal(JSON.parse(b.getAttribute("data-sell").replace(/&#39;/g, "'")))));
        // 매수추천 표(recBody)는 판단 기준일(D-1)까지, 보유/매도신호 표는 기준일(D-0)까지
        const chartEnd = box.id === "recBody" ? chartEndSignal : chartEndEval;
        box.querySelectorAll("[data-chart]").forEach((b) =>
            b.addEventListener("click", () => {
                const [code, name] = b.getAttribute("data-chart").split("|");
                openChartModal(code, name, chartEnd);
            }));
    }

    // ── 매수 모달 ─────────────────────────────────────────────
    function openBuyModal(prefill) {
        const m = $("manualBuyModal");
        if (!m) return;
        const price = prefill ? Number(prefill.price) || 0 : 0;
        $("inputStockCode").value = prefill ? prefill.code : "";
        $("inputBuyPrice").value = prefill ? prefill.price : "";
        // 모의투자: 20% 분할 기준 수량을 자동으로 채움(편집 가능)
        $("inputBuyQty").value = (ACCOUNT === "rec" && price > 0) ? autoBuyQty(price) : "";
        $("inputBuyDate").value = targetDate();
        setText("buyStockNameHint", prefill ? prefill.name : "종목 코드를 입력해 주세요");
        ["inputBuyPrice", "inputBuyQty"].forEach((id) => {
            const el = $(id);
            if (el) el.oninput = updateBuyTotal;
        });
        updateBuyTotal();
        m.classList.add("active");
    }
    function closeBuyModal() { const m = $("manualBuyModal"); if (m) m.classList.remove("active"); }

    // 20% 분할 매수: (총자산 ÷ 최대 슬롯)과 잔여 현금 중 작은 값 ÷ 단가, 내림
    function autoBuyQty(price) {
        if (!lastSummary || price <= 0) return "";
        const perSlot = (lastSummary.total_asset || 0) / (lastSummary.max_slots || 5);
        const budget = Math.min(perSlot, lastSummary.cash_balance || 0);
        return Math.max(0, Math.floor(budget / price)) || "";
    }

    function updateBuyTotal() {
        const total = (Number($("inputBuyPrice").value) || 0) * (parseInt($("inputBuyQty").value, 10) || 0);
        setText("buyModalTotal", won(total));
    }

    async function autofillStockInfo() {
        const code = $("inputStockCode").value.trim();
        if (code.length < 6) return;
        try {
            const r = await fetch(`/api/paper-trading/stock-info?code=${code}&target_date=${targetDate()}`).then((x) => x.json());
            if (r.status === "success") {
                setText("buyStockNameHint", `${r.name} (${r.market || "-"})`);
                if (!$("inputBuyPrice").value && r.close_price) $("inputBuyPrice").value = r.close_price;
                if (ACCOUNT === "rec" && !$("inputBuyQty").value) {
                    const q = autoBuyQty(Number($("inputBuyPrice").value) || 0);
                    if (q) $("inputBuyQty").value = q;
                }
                updateBuyTotal();
            }
        } catch (e) { console.error(e); }
    }

    async function confirmBuy() {
        const body = {
            account_type: ACCOUNT,
            stock_code: $("inputStockCode").value.trim(),
            buy_price: Number($("inputBuyPrice").value),
            quantity: parseInt($("inputBuyQty").value, 10),
            buy_date: $("inputBuyDate").value,
        };
        const res = await fetch("/api/paper-trading/manual-buy", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        }).then((r) => r.json());
        if (res.status === "success") { closeBuyModal(); refresh(); }
        else alert(res.message || "매수에 실패했습니다.");
    }

    // ── 매도 모달 ─────────────────────────────────────────────
    function openSellModal(p) {
        const m = $("manualSellModal");
        if (!m) return;
        sellTargetCode = p.code;
        sellMaxQty = p.qty;
        setText("sellModalStockLabel", `${p.name} (${p.code}) · 보유 ${p.qty}주`);
        $("inputSellPrice").value = p.price || "";
        $("inputSellQty").value = p.qty;
        $("inputSellDate").value = targetDate();
        updateSellTotal();
        ["inputSellPrice", "inputSellQty"].forEach((id) => {
            const el = $(id);
            if (el) el.oninput = updateSellTotal;
        });
        m.classList.add("active");
    }
    function closeSellModal() { const m = $("manualSellModal"); if (m) m.classList.remove("active"); }

    function updateSellTotal() {
        const total = (Number($("inputSellPrice").value) || 0) * (parseInt($("inputSellQty").value, 10) || 0);
        setText("sellModalTotal", won(total));
    }

    async function confirmSell() {
        const qty = parseInt($("inputSellQty").value, 10);
        if (qty > sellMaxQty) { alert(`보유 수량(${sellMaxQty}주)을 초과할 수 없습니다.`); return; }
        const body = {
            account_type: ACCOUNT, stock_code: sellTargetCode,
            sell_price: Number($("inputSellPrice").value),
            quantity: qty, sell_date: $("inputSellDate").value,
        };
        const res = await fetch("/api/paper-trading/sell", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        }).then((r) => r.json());
        if (res.status === "success") { alert(res.message); closeSellModal(); refresh(); }
        else alert(res.message || "매도에 실패했습니다.");
    }

    // ── 차트 모달 ─────────────────────────────────────────────
    async function openChartModal(code, name, endDate) {
        const m = $("stockChartModal");
        if (!m) return;
        setText("chartModalTitle", `📈 ${name} (${code}) 최근 시세`);
        m.classList.add("active");
        try {
            const qs = endDate ? `?limit=120&end=${encodeURIComponent(endDate)}` : "?limit=120";
            const r = await fetch(`/api/stock-chart/${code}${qs}`).then((x) => x.json());
            drawChart((r.data || []));
        } catch (e) { console.error(e); }
    }
    function closeChartModal() { const m = $("stockChartModal"); if (m) m.classList.remove("active"); }

    // 거래정지 연속 구간을 [시작 index, 끝 index] 목록으로 묶음
    function suspendedSpans(rows) {
        const spans = [];
        let start = -1;
        rows.forEach((d, i) => {
            const on = !!d.is_suspended;
            if (on && start < 0) start = i;
            if (!on && start >= 0) { spans.push([start, i - 1]); start = -1; }
        });
        if (start >= 0) spans.push([start, rows.length - 1]);
        return spans;
    }

    // 거래정지 구간을 회색 반투명 밴드 + '거래정지' 라벨로 칠하는 Chart.js 플러그인
    function suspendedBandPlugin(spans) {
        return {
            id: "suspendedBand",
            beforeDatasetsDraw(chart) {
                if (!spans.length) return;
                const { ctx, chartArea: area, scales: { x } } = chart;
                ctx.save();
                spans.forEach(([s, e]) => {
                    const x1 = x.getPixelForValue(s);
                    const x2 = x.getPixelForValue(e);
                    const left = Math.min(x1, x2) - (x.getPixelForValue(1) - x.getPixelForValue(0)) / 2;
                    const right = Math.max(x1, x2) + (x.getPixelForValue(1) - x.getPixelForValue(0)) / 2;
                    ctx.fillStyle = "rgba(148, 163, 184, 0.18)";
                    ctx.fillRect(left, area.top, right - left, area.bottom - area.top);
                    ctx.fillStyle = "#94a3b8";
                    ctx.font = "700 10px sans-serif";
                    ctx.textAlign = "center";
                    ctx.fillText("거래정지", (left + right) / 2, area.top + 12);
                });
                ctx.restore();
            },
        };
    }

    function drawChart(rows) {
        const cv = $("proposalChartCanvas");
        if (!cv || !window.Chart) return;
        const labels = rows.map((d) => d.date);
        const close = rows.map((d) => d.close);
        const ma = (n) => close.map((_, i) => i < n - 1 ? null : close.slice(i - n + 1, i + 1).reduce((a, b) => a + b, 0) / n);
        if (proposalChart) proposalChart.destroy();
        proposalChart = new window.Chart(cv.getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [
                    { label: "종가", data: close, borderColor: "#38bdf8", borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
                    { label: "MA5", data: ma(5), borderColor: "#fbbf24", borderWidth: 1, pointRadius: 0 },
                    { label: "MA20", data: ma(20), borderColor: "#a855f7", borderWidth: 1, pointRadius: 0 },
                ],
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: "#cbd5e1" } } },
                scales: { x: { ticks: { color: "#64748b", maxTicksLimit: 8 } }, y: { ticks: { color: "#64748b" } } } },
            plugins: [suspendedBandPlugin(suspendedSpans(rows))],
        });
    }
})();
