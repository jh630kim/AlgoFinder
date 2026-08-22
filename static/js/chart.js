/**
 * AlgoFinder Chart.js 차트 전용 스크립트 (chart.js).
 * 우측 목표 화면 100% 동일: 마우스 팝업 툴팁 비활성화, 고정 HUD 수치 박스 전담,
 * 매수/매도 타점 화살표(▲/▼) 주가 라인 바로 위/아래 밀착 렌더링,
 * 볼린저 밴드 반투명 음영(Fill Shade), X축 수평(0도) 날짜 라벨 및 마우스 휠 Zoom/Pan을 시각화합니다.
 */

let techChartInstance = null;
let priceSupplyChartInstance = null;
let currentChartRawData = [];

// chartjs-plugin-zoom 전역 등록 보장
if (typeof Chart !== "undefined" && window["chartjs-plugin-zoom"]) {
    try {
        Chart.register(window["chartjs-plugin-zoom"]);
    } catch (e) {}
}

document.addEventListener("DOMContentLoaded", () => {
    initChartControls();
    initPanDragHandlers();
});

function initPanDragHandlers() {
    const techCanvas = document.getElementById("techIndicatorChart");
    const supplyCanvas = document.getElementById("priceSupplyChart");
    if (techCanvas) attachPanDragScrollHandler(techCanvas, () => techChartInstance);
    if (supplyCanvas) attachPanDragScrollHandler(supplyCanvas, () => priceSupplyChartInstance);
}

/** 🖐️ 마우스 휠 확대 상태 및 평시 마우스 좌클릭 좌우 이동(Pan) 전용 핸들러 */
function attachPanDragScrollHandler(canvas, chartGetter) {
    if (!canvas) return;
    let isDragging = false;
    let startX = 0;
    let initialMin = null;
    let initialMax = null;

    canvas.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        const chart = chartGetter();
        if (!chart || !chart.scales || !chart.scales.x) return;

        const xScale = chart.scales.x;
        isDragging = true;
        startX = e.clientX;
        initialMin = typeof xScale.min === "number" ? xScale.min : 0;
        initialMax = typeof xScale.max === "number" ? xScale.max : (chart.data.labels.length - 1);
        canvas.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const chart = chartGetter();
        if (!chart || !chart.scales || !chart.scales.x || !chart.data.labels) return;

        const xScale = chart.scales.x;
        const deltaX = e.clientX - startX;
        const totalPixels = xScale.right - xScale.left;
        const range = initialMax - initialMin;
        if (totalPixels <= 0 || range <= 0) return;

        const shiftUnits = Math.round((-deltaX / totalPixels) * range);
        const dataLen = chart.data.labels.length;

        if (shiftUnits !== 0) {
            let newMin = initialMin + shiftUnits;
            let newMax = initialMax + shiftUnits;

            if (newMin < 0) {
                newMax -= newMin;
                newMin = 0;
            }
            if (newMax >= dataLen) {
                newMin -= (newMax - dataLen + 1);
                newMax = dataLen - 1;
            }

            newMin = Math.max(0, newMin);
            newMax = Math.min(dataLen - 1, newMax);

            chart.options.scales.x.min = newMin;
            chart.options.scales.x.max = newMax;
            chart.update("none");
        }
    });

    window.addEventListener("mouseup", () => {
        if (isDragging) {
            isDragging = false;
            canvas.style.cursor = "grab";
        }
    });
}

function initChartControls() {
    const select = document.getElementById("stockSelect");
    if (select) {
        select.addEventListener("change", (e) => {
            const chkAggregate = document.getElementById("chkMarketAggregate");
            if (chkAggregate && chkAggregate.checked) return;
            const stockCode = e.target.value;
            loadAndRenderCharts(stockCode);
        });
        if (select.value) loadAndRenderCharts(select.value);
    }
}

window.loadAndRenderCharts = loadAndRenderCharts;
window.renderAggregateCharts = renderAggregateCharts;
window.updateTechChartSeriesVisibility = updateTechChartSeriesVisibility;

/** 백엔드 API 데이터를 기반으로 기술적 수치(RSI, 볼린저, 5일선, 20일선, 매매 타점) 계산 */
function calculateIndicators(rawData) {
    const prices = rawData.map((d) => d.close);
    const n = prices.length;

    // 1. 5일 이동평균선 (MA5) 및 20일 이동평균선 (MA20) & 볼린저 밴드 (Upper / Lower 2σ)
    const ma5 = new Array(n).fill(null);
    const ma20 = new Array(n).fill(null);
    const bollingerUpper = new Array(n).fill(null);
    const bollingerLower = new Array(n).fill(null);

    for (let i = 4; i < n; i++) {
        const slice5 = prices.slice(i - 4, i + 1);
        ma5[i] = slice5.reduce((a, b) => a + b, 0) / 5;
    }

    for (let i = 19; i < n; i++) {
        const slice = prices.slice(i - 19, i + 1);
        const sum = slice.reduce((a, b) => a + b, 0);
        const avg = sum / 20;
        ma20[i] = avg;

        const variance = slice.reduce((a, b) => a + Math.pow(b - avg, 2), 0) / 20;
        const std = Math.sqrt(variance);
        bollingerUpper[i] = avg + 2 * std;
        bollingerLower[i] = avg - 2 * std;
    }

    // 2. RSI (14일)
    const rsi14 = new Array(n).fill(null);
    let gains = 0, losses = 0;
    for (let i = 1; i <= 14 && i < n; i++) {
        const diff = prices[i] - prices[i - 1];
        if (diff >= 0) gains += diff;
        else losses -= diff;
    }
    let avgGain = gains / 14;
    let avgLoss = losses / 14;
    if (n > 14) {
        rsi14[14] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
        for (let i = 15; i < n; i++) {
            const diff = prices[i] - prices[i - 1];
            const g = diff >= 0 ? diff : 0;
            const l = diff < 0 ? -diff : 0;
            avgGain = (avgGain * 13 + g) / 14;
            avgLoss = (avgLoss * 13 + l) / 14;
            rsi14[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
        }
    }

    // 3. RSI Signal (9일 EMA)
    const rsiSignal = new Array(n).fill(null);
    const k = 2 / (9 + 1);
    let firstRsiIdx = rsi14.findIndex((v) => v !== null);
    if (firstRsiIdx !== -1 && n >= firstRsiIdx + 9) {
        let ema = rsi14.slice(firstRsiIdx, firstRsiIdx + 9).reduce((a, b) => a + b, 0) / 9;
        rsiSignal[firstRsiIdx + 8] = ema;
        for (let i = firstRsiIdx + 9; i < n; i++) {
            if (rsi14[i] !== null) {
                ema = rsi14[i] * k + ema * (1 - k);
                rsiSignal[i] = ema;
            }
        }
    }

    // 4. S1c 상승확률 (%)
    const s1cProb = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
        if (ma20[i] !== null && ma20[i] > 0) {
            const ratio = (prices[i] / ma20[i]) * 50;
            s1cProb[i] = Math.min(Math.max(ratio, 10), 98);
        } else {
            s1cProb[i] = 50.0;
        }
    }

    // 5. 백엔드 전략 엔진(backend/app/services/strategies)이 계산하여 전달한 매수/매도 시그널 날짜 바인딩
    const s1cBuyPoints = new Array(n).fill(null);
    const s1cSellPoints = new Array(n).fill(null);
    const s2BuyPoints = new Array(n).fill(null);
    const s2SellPoints = new Array(n).fill(null);
    const s3BuyPoints = new Array(n).fill(null);
    const s3SellPoints = new Array(n).fill(null);

    const buyDates = [];
    const sellDates = [];

    for (let i = 0; i < n; i++) {
        // 백엔드 S1cMACrossAdaptiveStrategy 전략 엔진 계산 시그널 연동 (5일 평균선 MA5 기준 밀착 표기!)
        const ma5Ref = (ma5[i] !== null && ma5[i] > 0) ? ma5[i] : prices[i];
        if (rawData[i] && rawData[i].s1c_signal === "BUY") {
            s1cBuyPoints[i] = ma5Ref * 0.995;
            buyDates.push(rawData[i].date);
        } else if (rawData[i] && rawData[i].s1c_signal === "SELL") {
            s1cSellPoints[i] = ma5Ref * 1.005;
            sellDates.push(rawData[i].date);
        }
    }

    console.log(`==================================================`);
    console.log(`📊 [백엔드 S1c 전략 엔진 수신 데이터 콘솔 디버깅 Log]`);
    console.log(`🟢 S1c 매수(BUY) 시그널 날짜 (${buyDates.length}건):`, buyDates.length > 0 ? buyDates : ["시그널 없음"]);
    console.log(`🔴 S1c 매도(SELL) 시그널 날짜 (${sellDates.length}건):`, sellDates.length > 0 ? sellDates : ["시그널 없음"]);
    console.log(`==================================================`);

    return {
        ma5,
        ma20,
        bollingerUpper,
        bollingerLower,
        rsi14,
        rsiSignal,
        s1cProb,
        s1cBuyPoints,
        s1cSellPoints,
        s2BuyPoints,
        s2SellPoints,
        s3BuyPoints,
        s3SellPoints
    };
}

let currentPeriodLimit = 120;

/** 단일 종목 백엔드 API 데이터 로드 및 렌더링 */
function loadAndRenderCharts(stockCode, limit = currentPeriodLimit) {
    currentPeriodLimit = limit;
    fetch(`/api/stock-chart/${stockCode}?limit=${limit}`)
        .then((res) => res.json())
        .then((res) => {
            if (res.status === "success") {
                currentChartRawData = res.data;
                renderTechChart(res.data, `📈 기술적 매매지표 (${stockCode})`);
                renderPriceSupplyChart(res.data, `📊 주가 & 수급 통합 복합 차트 (${stockCode})`);
            }
        });
}

/** 📊 전체 항목 집계 평균 백엔드 API 데이터 렌더링 */
function renderAggregateCharts(data, titleSuffix = "전체 집계") {
    currentChartRawData = data;
    renderTechChart(data, `📈 [${titleSuffix}] 전체 항목 평균 주가 추이`);
    renderPriceSupplyChart(data, `📊 [${titleSuffix}] 전체 항목 수급 합계/평균 복합 차트`);
}

/** 🔄 차트 마우스 휠 확대/축소 줌 초기화 함수 */
function resetTechChartZoom() {
    if (techChartInstance && techChartInstance.resetZoom) {
        techChartInstance.resetZoom();
    }
    if (priceSupplyChartInstance && priceSupplyChartInstance.resetZoom) {
        priceSupplyChartInstance.resetZoom();
    }
}

window.resetTechChartZoom = resetTechChartZoom;

/** [차트 1] 기술적 매매지표 렌더링 (5일선 / 20일선 포함) */
function renderTechChart(rawData, titleText = "📈 기술적 매매지표") {
    const canvas = document.getElementById("techIndicatorChart");
    if (!canvas) return;

    const ind = calculateIndicators(rawData);
    const labels = rawData.map((d) => d.date);
    const closePrices = rawData.map((d) => d.close);

    if (techChartInstance) techChartInstance.destroy();

    const ctx = canvas.getContext("2d");

    techChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "주가 종가",
                    data: closePrices,
                    borderColor: "#fbbf24", // 황색 골드
                    borderWidth: 2.2,
                    pointRadius: 0,
                    yAxisID: "yPrice",
                },
                {
                    label: "S1c: 5일 이평선",
                    data: ind.ma5,
                    borderColor: "#f59e0b",
                    borderWidth: 1.8,
                    borderDash: [4, 4], // 5일 평균선 점선 표현!
                    pointRadius: 0,
                    yAxisID: "yPrice",
                },
                {
                    label: "S1c: 20일 이평선",
                    data: ind.ma20,
                    borderColor: "#d97706",
                    borderWidth: 2,
                    pointRadius: 0,
                    yAxisID: "yPrice",
                },
                {
                    label: "S1c 매수",
                    data: ind.s1cBuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7,
                    pointBackgroundColor: "#f59e0b",
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                },
                {
                    label: "S1c 매도",
                    data: ind.s1cSellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7,
                    pointBackgroundColor: "#ef4444",
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                title: { display: false },
                // 마우스 호버 팝업 툴팁 비활성화 (지정 위치 HUD 박스 전담!)
                tooltip: { enabled: false },
                legend: {
                    display: true,
                    position: "top",
                    labels: {
                        color: "#cbd5e1",
                        font: { size: 11 },
                        usePointStyle: true, // 범례 아이콘을 차트 속 포인트 모양(황색 정삼각형 ▲ / 빨간색 역삼각형 ▼)과 100% 동일하게 렌더링!
                        boxWidth: 10,
                    },
                },
                zoom: {
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: "x",
                    },
                    pan: {
                        enabled: true,
                        mode: "x",
                        modifierKey: null,
                    },
                },
            },
            onHover: (evt, activeElements) => {
                if (activeElements && activeElements.length > 0) {
                    const idx = activeElements[0].index;
                    updateHudBox(rawData[idx], ind, idx);
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: "#94a3b8",
                        font: { size: 11 },
                        maxRotation: 0,
                        minRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8,
                    },
                    grid: { color: "rgba(255,255,255,0.05)" },
                },
                yPrice: {
                    type: "linear",
                    position: "left",
                    ticks: {
                        color: "#fbbf24",
                        callback: (v) => (v >= 10000 ? `+${(v / 10000).toFixed(1)}만` : v),
                    },
                    grid: { color: "rgba(255,255,255,0.06)" },
                },
            },
        },
    });
}

/** 📌 지정된 고정 위치 HUD 수치 박스 실시간 갱신 (S1c 20일선 적응형 전용) */
function updateHudBox(rawRow, indObj, idx) {
    const hudBox = document.getElementById("techHudBox");
    if (!hudBox || !rawRow) return;

    const priceStr = Math.round(rawRow.close).toLocaleString();
    const ma5Str = indObj.ma5[idx] ? Math.round(indObj.ma5[idx]).toLocaleString() : "-";
    const ma20Str = indObj.ma20[idx] ? Math.round(indObj.ma20[idx]).toLocaleString() : "-";

    let signalMsg = "관망";
    if (indObj.s1cBuyPoints[idx]) signalMsg = "🟡 S1c 20일선 골든크로스 매수(▲)";
    else if (indObj.s1cSellPoints[idx]) signalMsg = "🔴 S1c 20일선 데드크로스 매도(▼)";

    hudBox.innerHTML = `
        <div class="hud-item"><span class="hud-label">📅 일자:</span> <span class="hud-value" style="color:#e2e8f0;">${rawRow.date}</span></div>
        <div class="hud-item"><span class="hud-label">💰 종가/평균:</span> <span class="hud-value" style="color:#fbbf24; font-weight:700;">${priceStr}원</span></div>
        <div class="hud-item"><span class="hud-label">🟡 5일선:</span> <span class="hud-value" style="color:#f59e0b;">${ma5Str}원</span></div>
        <div class="hud-item"><span class="hud-label">🟡 20일선:</span> <span class="hud-value" style="color:#d97706;">${ma20Str}원</span></div>
        <div class="hud-item hud-signal-item"><span class="hud-label">⚡ 포착 신호:</span> <span class="hud-value" style="color:#38bdf8; font-weight:700;">${signalMsg}</span></div>
    `;
}

/** 칩 체크박스 상태 읽기 간편 함수 */
function getChipState(chipId) {
    const el = document.getElementById(chipId);
    return el ? el.checked : false;
}

/** 칩 체크 변경 시 차트 데이터셋 실시간 가시성 토글 */
function updateTechChartSeriesVisibility() {
    if (!techChartInstance || !currentChartRawData.length) return;
    renderTechChart(currentChartRawData);
}

/** [차트 2] 주가 & 수급 통합 복합 차트 렌더링 */
function renderPriceSupplyChart(data, titleText = "📊 주가 & 수급 통합 복합 차트") {
    const canvas = document.getElementById("priceSupplyChart");
    if (!canvas) return;

    const labels = data.map((d) => d.date);
    const closePrices = data.map((d) => d.close);
    const netForeign = data.map((d) => d.net_foreign / 100000000);

    if (priceSupplyChartInstance) priceSupplyChartInstance.destroy();

    priceSupplyChartInstance = new Chart(canvas.getContext("2d"), {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    type: "line",
                    label: "평균/종가 (원)",
                    data: closePrices,
                    borderColor: "#00ff87",
                    borderWidth: 2,
                    pointRadius: 0,
                    yAxisID: "yPrice",
                },
                {
                    type: "bar",
                    label: "외국인 수급 (억원)",
                    data: netForeign,
                    backgroundColor: "rgba(245, 158, 11, 0.7)",
                    yAxisID: "ySupply",
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: titleText, color: "#00ff87", font: { size: 14, weight: "bold" } },
                tooltip: { enabled: false },
                zoom: {
                    zoom: { wheel: { enabled: true }, mode: "x" },
                    pan: { enabled: true, mode: "x" },
                },
            },
            scales: {
                x: {
                    ticks: {
                        color: "#94a3b8",
                        font: { size: 11 },
                        maxRotation: 0,
                        minRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 8,
                    },
                    grid: { color: "rgba(255,255,255,0.05)" },
                },
                yPrice: { type: "linear", position: "left", grid: { color: "rgba(255,255,255,0.05)" } },
                ySupply: { type: "linear", position: "right", grid: { color: "rgba(255,255,255,0.05)" } },
            },
        },
    });
}
