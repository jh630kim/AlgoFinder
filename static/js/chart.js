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

/** 🔺 스퀴즈 전용 빗금(Hatched) 삼각형 오프스크린 Canvas 포인트 생성 헬퍼 */
function createHatchedTriangleCanvas(color, isReversed = false, size = 18) {
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return "triangle";

    const p = size / 2;
    ctx.beginPath();
    if (!isReversed) {
        // 정삼각형 ▲ (위)
        ctx.moveTo(p, 1);
        ctx.lineTo(size - 1, size - 1);
        ctx.lineTo(1, size - 1);
    } else {
        // 역삼각형 ▼ (아래)
        ctx.moveTo(1, 1);
        ctx.lineTo(size - 1, 1);
        ctx.lineTo(p, size - 1);
    }
    ctx.closePath();

    // 1. 바탕색 채우기
    ctx.fillStyle = color;
    ctx.fill();

    // 2. 삼각형 클리핑 후 사선 빗금 선 그리기
    ctx.save();
    ctx.clip();
    ctx.strokeStyle = "#ffffff"; // 흰색 사선 빗금
    ctx.lineWidth = 1.8;

    for (let i = -size; i < size * 2; i += 4) {
        ctx.beginPath();
        ctx.moveTo(i, 0);
        ctx.lineTo(i + size, size);
        ctx.stroke();
    }
    ctx.restore();

    // 3. 외곽선 강조
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.2;
    ctx.stroke();

    return canvas;
}

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

    // 백엔드가 전달한 오리지널 진짜 수치(ind_ma5, ind_ma20, ind_bb_ub, ind_bb_lb, ind_rsi14, ind_rsi_signal) 우선 바인딩
    const ma5 = new Array(n).fill(null);
    const ma20 = new Array(n).fill(null);
    const bollingerUpper = new Array(n).fill(null);
    const bollingerLower = new Array(n).fill(null);
    const rsi14 = new Array(n).fill(null);
    const rsiSignal = new Array(n).fill(null);

    for (let i = 0; i < n; i++) {
        if (rawData[i]) {
            if (rawData[i].ind_ma5 !== undefined && rawData[i].ind_ma5 !== null) ma5[i] = rawData[i].ind_ma5;
            if (rawData[i].ind_ma20 !== undefined && rawData[i].ind_ma20 !== null) ma20[i] = rawData[i].ind_ma20;
            if (rawData[i].ind_bb_ub !== undefined && rawData[i].ind_bb_ub !== null) bollingerUpper[i] = rawData[i].ind_bb_ub;
            if (rawData[i].ind_bb_lb !== undefined && rawData[i].ind_bb_lb !== null) bollingerLower[i] = rawData[i].ind_bb_lb;
            if (rawData[i].ind_rsi14 !== undefined && rawData[i].ind_rsi14 !== null) rsi14[i] = rawData[i].ind_rsi14;
            if (rawData[i].ind_rsi_signal !== undefined && rawData[i].ind_rsi_signal !== null) rsiSignal[i] = rawData[i].ind_rsi_signal;
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

    // 5. 백엔드 전략 엔진(backend/app/services/strategies)이 계산하여 전달한 8종 매수/매도 시그널 날짜 바인딩
    const s1BuyPoints = new Array(n).fill(null);
    const s1SellPoints = new Array(n).fill(null);
    const s1aBuyPoints = new Array(n).fill(null);
    const s1aSellPoints = new Array(n).fill(null);
    const s1bBuyPoints = new Array(n).fill(null);
    const s1bSellPoints = new Array(n).fill(null);
    const s1cBuyPoints = new Array(n).fill(null);
    const s1cSellPoints = new Array(n).fill(null);
    const s2BuyPoints = new Array(n).fill(null);
    const s2SellPoints = new Array(n).fill(null);
    const s3BuyPoints = new Array(n).fill(null);
    const s3SellPoints = new Array(n).fill(null);
    const s3aBuyPoints = new Array(n).fill(null);
    const s3aSellPoints = new Array(n).fill(null);
    const s4BuyPoints = new Array(n).fill(null);
    const s4SellPoints = new Array(n).fill(null);
    const s4aBuyPoints = new Array(n).fill(null);
    const s4aSellPoints = new Array(n).fill(null);
    const s5BuyPoints = new Array(n).fill(null);
    const s5SellPoints = new Array(n).fill(null);

    for (let i = 0; i < n; i++) {
        const priceRef = prices[i];
        
        // 1. S1 기본형
        if (rawData[i] && rawData[i].s1_signal === "BUY") s1BuyPoints[i] = priceRef * 0.993;
        else if (rawData[i] && rawData[i].s1_signal === "SELL") s1SellPoints[i] = priceRef * 1.007;

        // 2. S1a 거래량 동반형
        if (rawData[i] && rawData[i].s1a_signal === "BUY") s1aBuyPoints[i] = priceRef * 0.994;
        else if (rawData[i] && rawData[i].s1a_signal === "SELL") s1aSellPoints[i] = priceRef * 1.006;

        // 3. S1b 수급 필터형
        if (rawData[i] && rawData[i].s1b_signal === "BUY") s1bBuyPoints[i] = priceRef * 0.9945;
        else if (rawData[i] && rawData[i].s1b_signal === "SELL") s1bSellPoints[i] = priceRef * 1.0055;

        // 4. S1c 적응형
        if (rawData[i] && rawData[i].s1c_signal === "BUY") s1cBuyPoints[i] = priceRef * 0.995;
        else if (rawData[i] && rawData[i].s1c_signal === "SELL") s1cSellPoints[i] = priceRef * 1.005;

        // 5. S2 RSI 돌파형 (RSI 9일 Signal 이평선 기준 위치)
        const rsiSigRef = (rsiSignal[i] !== null && rsiSignal[i] > 0) ? rsiSignal[i] : ((rsi14[i] !== null) ? rsi14[i] : 50);
        if (rawData[i] && rawData[i].s2_signal === "BUY") s2BuyPoints[i] = rsiSigRef - 3.5;
        else if (rawData[i] && rawData[i].s2_signal === "SELL") s2SellPoints[i] = rsiSigRef + 3.5;

        // 6. S3 볼린저 밴드 반등형 (종가 라인 밀착)
        if (rawData[i] && rawData[i].s3_signal === "BUY") s3BuyPoints[i] = priceRef * 0.991;
        else if (rawData[i] && rawData[i].s3_signal === "SELL") s3SellPoints[i] = priceRef * 1.009;

        // 6-a. S3a 볼린저 밴드 스퀴즈 돌파형 (종가 라인 밀착)
        if (rawData[i] && rawData[i].s3a_signal === "BUY") s3aBuyPoints[i] = priceRef * 0.9905;
        else if (rawData[i] && rawData[i].s3a_signal === "SELL") s3aSellPoints[i] = priceRef * 1.0095;

        // 7. S4 RSI 표준 과매도 탈출형 (진짜 14일 RSI 오렌지 실선 위아래 1:1 밀착 위치)
        const rsi14Val = (rsi14[i] !== null && rsi14[i] > 0) ? rsi14[i] : 50;
        if (rawData[i] && rawData[i].s4_signal === "BUY") s4BuyPoints[i] = rsi14Val - 3.5;
        else if (rawData[i] && rawData[i].s4_signal === "SELL") s4SellPoints[i] = rsi14Val + 3.5;

        // 7-a. S4a RSI Signal 교차형 (RSI 9일 Signal 이평선 기준 위치)
        if (rawData[i] && rawData[i].s4a_signal === "BUY") s4aBuyPoints[i] = rsiSigRef - 3.5;
        else if (rawData[i] && rawData[i].s4a_signal === "SELL") s4aSellPoints[i] = rsiSigRef + 3.5;

        // 8. S5 캔들 반전형 (종가 라인 밀착)
        if (rawData[i] && rawData[i].s5_signal === "BUY") s5BuyPoints[i] = priceRef * 0.989;
        else if (rawData[i] && rawData[i].s5_signal === "SELL") s5SellPoints[i] = priceRef * 1.011;
    }

    const volumes = rawData.map((d) => d.volume || 0);
    const volMa5 = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
        if (rawData[i] && rawData[i].ind_vol_ma5 !== undefined && rawData[i].ind_vol_ma5 !== null) {
            volMa5[i] = rawData[i].ind_vol_ma5;
        }
    }

    const volBarColors = new Array(n).fill("#ef4444");
    for (let i = 0; i < n; i++) {
        if (i > 0 && volumes[i] < volumes[i - 1]) {
            volBarColors[i] = "#3b82f6"; // 전일 대비 감소 -> 파란색
        } else {
            volBarColors[i] = "#ef4444"; // 전일 대비 증가 -> 빨간색
        }
    }

    return {
        ma5,
        ma20,
        bollingerUpper,
        bollingerLower,
        rsi14,
        rsiSignal,
        volume: volumes,
        volMa5,
        volBarColors,
        s1cProb,
        s1BuyPoints,
        s1SellPoints,
        s1aBuyPoints,
        s1aSellPoints,
        s1bBuyPoints,
        s1bSellPoints,
        s1cBuyPoints,
        s1cSellPoints,
        s2BuyPoints,
        s2SellPoints,
        s3BuyPoints,
        s3SellPoints,
        s3aBuyPoints,
        s3aSellPoints,
        s4BuyPoints,
        s4SellPoints,
        s4aBuyPoints,
        s4aSellPoints,
        s5BuyPoints,
        s5SellPoints,
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

    const isAnyS1Active = getChipState("chkChipS1") || getChipState("chkChipS1aVol") || getChipState("chkChipS1bOld") || getChipState("chkChipS1c");
    const isS2Active = getChipState("chkChipS2");
    const isS3Active = getChipState("chkChipS3");
    const isS4Active = getChipState("chkChipS4");
    const isRsiChartActive = isS2Active || isS4Active;

    techChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "수급량 (거래량)",
                    data: ind.volume,
                    type: "bar",
                    backgroundColor: ind.volBarColors,
                    borderWidth: 0,
                    barPercentage: 0.65,
                    categoryPercentage: 0.85,
                    yAxisID: "yVolume",
                    order: 10,
                    hidden: false, // 종가선처럼 항시 기본 노출!
                },
                {
                    label: "수급 5일 이평선",
                    data: ind.volMa5,
                    type: "line",
                    borderColor: "#f59e0b",
                    borderWidth: 1.5,
                    borderDash: [3, 3], // 5일 수급 이평 점선!
                    pointRadius: 0,
                    yAxisID: "yVolume",
                    order: 9,
                    hidden: false, // 종가선처럼 항시 기본 노출!
                },
                {
                    label: "주가 종가",
                    data: closePrices,
                    borderColor: "#fbbf24", // 황색 골드
                    borderWidth: 2.2,
                    pointRadius: 0,
                    yAxisID: "yPrice",
                },
                {
                    label: "5일 이평선",
                    data: ind.ma5,
                    borderColor: "#34d399", // 밝은 에메랄드/민트 점선!
                    borderWidth: 1.8,
                    borderDash: [4, 4], // 5일 평균선 점선 표현!
                    pointRadius: 0,
                    yAxisID: "yPrice",
                    hidden: !isAnyS1Active,
                },
                {
                    label: "20일 이평선",
                    data: ind.ma20,
                    borderColor: "#059669", // 딥 에메랄드 실선!
                    borderWidth: 2,
                    pointRadius: 0,
                    yAxisID: "yPrice",
                    hidden: !isAnyS1Active,
                },
                {
                    label: "14일 RSI",
                    data: ind.rsi14,
                    borderColor: "#f97316",
                    borderWidth: 2,
                    pointRadius: 0,
                    yAxisID: "yRSI",
                    hidden: !isRsiChartActive,
                },
                {
                    label: "RSI Signal(9)선",
                    data: ind.rsiSignal,
                    borderColor: "#fdba74",
                    borderWidth: 1.8,
                    borderDash: [3, 3],
                    pointRadius: 0,
                    yAxisID: "yRSI",
                    hidden: !isRsiChartActive,
                },
                {
                    label: "70% 과매수 기준선",
                    data: new Array(labels.length).fill(70),
                    borderColor: "rgba(239, 68, 68, 0.6)",
                    borderWidth: 1.2,
                    borderDash: [3, 3],
                    pointRadius: 0,
                    yAxisID: "yRSI",
                    hidden: !isRsiChartActive,
                },
                {
                    label: "30% 과매도 기준선",
                    data: new Array(labels.length).fill(30),
                    borderColor: "rgba(16, 185, 129, 0.6)",
                    borderWidth: 1.2,
                    borderDash: [3, 3],
                    pointRadius: 0,
                    yAxisID: "yRSI",
                    hidden: !isRsiChartActive,
                },
                {
                    label: "S3: 볼린저 밴드 상단",
                    data: ind.bollingerUpper,
                    borderColor: "rgba(236, 72, 153, 0.7)",
                    borderWidth: 1.5,
                    pointRadius: 0,
                    yAxisID: "yPrice",
                    hidden: !isS3Active,
                },
                {
                    label: "S3: 볼린저 밴드 하단",
                    data: ind.bollingerLower,
                    borderColor: "rgba(236, 72, 153, 0.7)",
                    borderWidth: 1.5,
                    fill: "-1",
                    backgroundColor: "rgba(236, 72, 153, 0.08)",
                    pointRadius: 0,
                    yAxisID: "yPrice",
                    hidden: !isS3Active,
                },
                {
                    label: "S1 매수",
                    data: ind.s1BuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 8,
                    pointBackgroundColor: "#10b981", // 에메랄드색
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1"),
                },
                {
                    label: "S1 매도",
                    data: ind.s1SellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 8,
                    pointBackgroundColor: "#10b981", // 에메랄드색
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1"),
                },
                {
                    label: "S1a 매수",
                    data: ind.s1aBuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7.5,
                    pointBackgroundColor: "#06b6d4", // 스카이블루 청색
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1aVol"),
                },
                {
                    label: "S1a 매도",
                    data: ind.s1aSellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7.5,
                    pointBackgroundColor: "#06b6d4", // 스카이블루 청색
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1aVol"),
                },
                {
                    label: "S1b 매수",
                    data: ind.s1bBuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7.5,
                    pointBackgroundColor: "#a855f7", // 보라/퍼플
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1bOld"),
                },
                {
                    label: "S1b 매도",
                    data: ind.s1bSellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7.5,
                    pointBackgroundColor: "#a855f7", // 보라/퍼플
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1bOld"),
                },
                {
                    label: "S1c 매수",
                    data: ind.s1cBuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7,
                    pointBackgroundColor: "#fbbf24", // 황금색
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1c"),
                },
                {
                    label: "S1c 매도",
                    data: ind.s1cSellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7,
                    pointBackgroundColor: "#fbbf24", // 황금색
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS1c"),
                },
                {
                    label: "S2 매수",
                    data: ind.s2BuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7,
                    pointBackgroundColor: "#f97316", // 오렌지
                    pointBorderColor: "#ffffff",
                    yAxisID: "yRSI",
                    hidden: !getChipState("chkChipS2"),
                },
                {
                    label: "S2 매도",
                    data: ind.s2SellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7,
                    pointBackgroundColor: "#f97316", // 오렌지
                    pointBorderColor: "#ffffff",
                    yAxisID: "yRSI",
                    hidden: !getChipState("chkChipS2"),
                },
                {
                    label: "S3 매수",
                    data: ind.s3BuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7,
                    pointBackgroundColor: "#ec4899", // 핑크 (일반 반등)
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS3"),
                },
                {
                    label: "S3 매도",
                    data: ind.s3SellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7,
                    pointBackgroundColor: "#ec4899", // 핑크 (일반 반등)
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS3"),
                },
                {
                    label: "S3a 스퀴즈 매수",
                    data: ind.s3aBuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: createHatchedTriangleCanvas("#d946ef", false, 14),
                    pointRadius: 7,
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS3"),
                },
                {
                    label: "S3a 스퀴즈 매도",
                    data: ind.s3aSellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: createHatchedTriangleCanvas("#d946ef", true, 14),
                    pointRadius: 7,
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS3"),
                },
                {
                    label: "S4 표준 매수",
                    data: ind.s4BuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7,
                    pointBackgroundColor: "#6366f1", // 인디고 블루
                    pointBorderColor: "#ffffff",
                    yAxisID: "yRSI",
                    hidden: !getChipState("chkChipS4"),
                },
                {
                    label: "S4 표준 매도",
                    data: ind.s4SellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7,
                    pointBackgroundColor: "#6366f1", // 인디고 블루
                    pointBorderColor: "#ffffff",
                    yAxisID: "yRSI",
                    hidden: !getChipState("chkChipS4"),
                },
                {
                    label: "S4a 교차 매수",
                    data: ind.s4aBuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: createHatchedTriangleCanvas("#06b6d4", false, 14), // 스카이블루 빗금 삼각형
                    pointRadius: 7,
                    yAxisID: "yRSI",
                    hidden: !getChipState("chkChipS4"),
                },
                {
                    label: "S4a 교차 매도",
                    data: ind.s4aSellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: createHatchedTriangleCanvas("#06b6d4", true, 14), // 스카이블루 빗금 역삼각형
                    pointRadius: 7,
                    yAxisID: "yRSI",
                    hidden: !getChipState("chkChipS4"),
                },
                {
                    label: "S5 매수",
                    data: ind.s5BuyPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRadius: 7,
                    pointBackgroundColor: "#84cc16", // 라임 그린
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS5"),
                },
                {
                    label: "S5 매도",
                    data: ind.s5SellPoints,
                    type: "line",
                    showLine: false,
                    pointStyle: "triangle",
                    pointRotation: 180,
                    pointRadius: 7,
                    pointBackgroundColor: "#84cc16", // 라임 그린
                    pointBorderColor: "#ffffff",
                    yAxisID: "yPrice",
                    hidden: !getChipState("chkChipS5"),
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
                        usePointStyle: true, // 사각형 박스 드로잉 완전 방지!
                        boxWidth: 16,
                        filter: (legendItem, data) => {
                            // 체크 해제(hidden == true) 항목은 범례 상단에서 완전히 숨김 제거!
                            const ds = data.datasets[legendItem.datasetIndex];
                            return ds && !ds.hidden;
                        },
                        generateLabels: (chart) => {
                            const original = Chart.defaults.plugins.legend.labels.generateLabels(chart);
                            return original.map((item) => {
                                const ds = chart.data.datasets[item.datasetIndex];
                                if (ds) {
                                    if (ds.showLine === false) {
                                        item.pointStyle = ds.pointStyle || "triangle";
                                        item.fillStyle = ds.pointBackgroundColor;
                                        item.strokeStyle = ds.pointBorderColor || ds.pointBackgroundColor;
                                        item.rotation = ds.pointRotation || 0;
                                        item.lineWidth = 1;
                                    } else {
                                        item.pointStyle = "line";
                                        item.strokeStyle = ds.borderColor;
                                        item.fillStyle = ds.borderColor;
                                        item.lineWidth = ds.borderWidth || 2;
                                        item.lineDash = ds.borderDash || [];
                                    }
                                }
                                return item;
                            });
                        },
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
                yRSI: {
                    type: "linear",
                    position: "right",
                    min: 0,
                    max: 100,
                    display: isRsiChartActive,
                    ticks: {
                        color: "#f97316",
                        callback: (v) => `${v}%`,
                    },
                    grid: { drawOnChartArea: false },
                },
                yVolume: {
                    type: "linear",
                    position: "right",
                    display: false,
                    min: 0,
                    max: Math.max(...(ind.volume || [100]).filter((v) => v !== null && !isNaN(v)), 100) * 5,
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}

/** 📌 지정된 고정 위치 HUD 수치 박스 실시간 갱신 (8종 전략 전용) */
function updateHudBox(rawRow, indObj, idx) {
    const hudBox = document.getElementById("techHudBox");
    if (!hudBox || !rawRow) return;

    const priceStr = Math.round(rawRow.close).toLocaleString();
    const ma5Str = indObj.ma5[idx] ? Math.round(indObj.ma5[idx]).toLocaleString() : "-";
    const ma20Str = indObj.ma20[idx] ? Math.round(indObj.ma20[idx]).toLocaleString() : "-";

    const signals = [];
    if (indObj.s1BuyPoints[idx]) signals.push('<span style="color:#10b981; font-weight:700;">🟢 S1 매수(▲)</span>');
    if (indObj.s1SellPoints[idx]) signals.push('<span style="color:#10b981; font-weight:700;">🔴 S1 매도(▼)</span>');
    if (indObj.s1aBuyPoints[idx]) signals.push('<span style="color:#06b6d4; font-weight:700;">🔵 S1a 매수(▲)</span>');
    if (indObj.s1aSellPoints[idx]) signals.push('<span style="color:#06b6d4; font-weight:700;">🔴 S1a 매도(▼)</span>');
    if (indObj.s1bBuyPoints[idx]) signals.push('<span style="color:#a855f7; font-weight:700;">🟣 S1b 매수(▲)</span>');
    if (indObj.s1bSellPoints[idx]) signals.push('<span style="color:#a855f7; font-weight:700;">🔴 S1b 매도(▼)</span>');
    if (indObj.s1cBuyPoints[idx]) signals.push('<span style="color:#fbbf24; font-weight:700;">🟡 S1c 매수(▲)</span>');
    if (indObj.s1cSellPoints[idx]) signals.push('<span style="color:#fbbf24; font-weight:700;">🔴 S1c 매도(▼)</span>');
    if (indObj.s2BuyPoints[idx]) signals.push('<span style="color:#f97316; font-weight:700;">🍊 S2 매수(▲)</span>');
    if (indObj.s2SellPoints[idx]) signals.push('<span style="color:#f97316; font-weight:700;">🔴 S2 매도(▼)</span>');
    if (indObj.s3BuyPoints[idx]) signals.push('<span style="color:#ec4899; font-weight:700;">🌸 S3 매수(▲)</span>');
    if (indObj.s3SellPoints[idx]) signals.push('<span style="color:#ec4899; font-weight:700;">🔴 S3 매도(▼)</span>');
    if (indObj.s3aBuyPoints[idx]) signals.push('<span style="color:#d946ef; font-weight:700;">💥 S3a 스퀴즈 매수(▲)</span>');
    if (indObj.s3aSellPoints[idx]) signals.push('<span style="color:#d946ef; font-weight:700;">🔴 S3a 스퀴즈 매도(▼)</span>');
    if (indObj.s4BuyPoints[idx]) signals.push('<span style="color:#6366f1; font-weight:700;">💙 S4 표준 매수(▲)</span>');
    if (indObj.s4SellPoints[idx]) signals.push('<span style="color:#6366f1; font-weight:700;">🔴 S4 표준 매도(▼)</span>');
    if (indObj.s4aBuyPoints[idx]) signals.push('<span style="color:#06b6d4; font-weight:700;">⚡ S4a 교차 매수(▲)</span>');
    if (indObj.s4aSellPoints[idx]) signals.push('<span style="color:#06b6d4; font-weight:700;">🔴 S4a 교차 매도(▼)</span>');
    if (indObj.s5BuyPoints[idx]) signals.push('<span style="color:#84cc16; font-weight:700;">🔥 S5 매수(▲)</span>');
    if (indObj.s5SellPoints[idx]) signals.push('<span style="color:#84cc16; font-weight:700;">🔴 S5 매도(▼)</span>');

    const signalMsg = signals.length > 0 ? signals.join(" | ") : "관망";

    hudBox.innerHTML = `
        <div class="hud-item"><span class="hud-label">📅 일자:</span> <span class="hud-value" style="color:#e2e8f0;">${rawRow.date}</span></div>
        <div class="hud-item"><span class="hud-label">💰 종가/평균:</span> <span class="hud-value" style="color:#fbbf24; font-weight:700;">${priceStr}원</span></div>
        <div class="hud-item"><span class="hud-label">🟡 5일선:</span> <span class="hud-value" style="color:#f59e0b;">${ma5Str}원</span></div>
        <div class="hud-item"><span class="hud-label">🟡 20일선:</span> <span class="hud-value" style="color:#d97706;">${ma20Str}원</span></div>
        <div class="hud-item hud-signal-item"><span class="hud-label">⚡ 포착 신호:</span> <span class="hud-value">${signalMsg}</span></div>
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
