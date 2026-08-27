/**
 * 투자제안(proposal) 화면 컨트롤러 (proposal.js) — PC / 모바일 공용.
 *
 * 계좌유형 'prop' 고정. 기준일 종가 기준 S1~S5(8전략) 매수 추천 조회, 실제 체결 내역
 * 수동 기록(매수/매도 모달), 보유 종목 매도 시그널(전략 매도 / -5% 손절 / +10% 익절) 표시.
 * 모든 연산은 백엔드가 수행하며 이 파일은 렌더링과 입력 중계만 담당한다.
 */

(function () {
    "use strict";

    const ACCOUNT = "prop";
    const IS_MOBILE = !!window.PROPOSAL_MOBILE;
    let sellTargetCode = null;
    let sellMaxQty = 0;
    let proposalChart = null;

    const $ = (id) => document.getElementById(id);
    const won = (n) => (Math.round(Number(n) || 0)).toLocaleString() + " 원";
    const setText = (id, v) => { const el = $(id); if (el) el.textContent = v; };
    const pnlColor = (v) => (v > 0 ? "#f87171" : v < 0 ? "#38bdf8" : "#94a3b8");

    document.addEventListener("DOMContentLoaded", init);

    function init() {
        const dp = $("recTargetDate");
        if (dp && !dp.value) dp.value = new Date().toISOString().slice(0, 10);

        bindClick("btnFetchRec", refresh);
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

    // ── 데이터 로드 ─────────────────────────────────────────────
    async function refresh() {
        const td = targetDate();
        try {
            const [pf, rec] = await Promise.all([
                fetch(`/api/paper-trading/portfolio?account_type=${ACCOUNT}&target_date=${td}`).then((r) => r.json()),
                fetch(`/api/recommended-stocks?target_date=${td}`).then((r) => r.json()),
            ]);
            if (pf.status === "success") {
                renderSummary(pf.summary);
                renderHoldings(pf.positions || []);
                renderSellSignals(pf.sell_signals || []);
            }
            if (rec.status === "success") renderRecommendations(rec.data || []);
        } catch (e) {
            console.error("proposal refresh error:", e);
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
            box.innerHTML = emptyRow(7, "선택한 기준일에 매도 조건이 포착된 보유 종목이 없습니다.");
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
                <td style="padding:10px;"><button class="btn-sell-action" data-sell='${sellData({stock_code:r.code,stock_name:r.name,quantity:r.quantity,current_price:r.current_price})}'>🔻 매도</button></td>
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
        box.querySelectorAll("[data-chart]").forEach((b) =>
            b.addEventListener("click", () => {
                const [code, name] = b.getAttribute("data-chart").split("|");
                openChartModal(code, name);
            }));
    }

    // ── 매수 모달 ─────────────────────────────────────────────
    function openBuyModal(prefill) {
        const m = $("manualBuyModal");
        if (!m) return;
        $("inputStockCode").value = prefill ? prefill.code : "";
        $("inputBuyPrice").value = prefill ? prefill.price : "";
        $("inputBuyQty").value = "";
        $("inputBuyDate").value = targetDate();
        setText("buyStockNameHint", prefill ? prefill.name : "종목 코드를 입력해 주세요");
        m.classList.add("active");
    }
    function closeBuyModal() { const m = $("manualBuyModal"); if (m) m.classList.remove("active"); }

    async function autofillStockInfo() {
        const code = $("inputStockCode").value.trim();
        if (code.length < 6) return;
        try {
            const r = await fetch(`/api/paper-trading/stock-info?code=${code}&target_date=${targetDate()}`).then((x) => x.json());
            if (r.status === "success") {
                setText("buyStockNameHint", `${r.name} (${r.market || "-"})`);
                if (!$("inputBuyPrice").value && r.close_price) $("inputBuyPrice").value = r.close_price;
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
    async function openChartModal(code, name) {
        const m = $("stockChartModal");
        if (!m) return;
        setText("chartModalTitle", `📈 ${name} (${code}) 최근 시세`);
        m.classList.add("active");
        try {
            const r = await fetch(`/api/stock-chart/${code}?limit=120`).then((x) => x.json());
            drawChart((r.data || []));
        } catch (e) { console.error(e); }
    }
    function closeChartModal() { const m = $("stockChartModal"); if (m) m.classList.remove("active"); }

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
        });
    }
})();
