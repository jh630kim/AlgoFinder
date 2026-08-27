/**
 * AlgoFinder 메인 대시보드 4단계 연쇄 동적 필터링 및 컨트롤러 (app.js).
 * 1단계: 구분(Sector/Market) 선택 -> 2단계: 전체 업종(Industry) 동적 로드 ->
 * 3단계: 전체(xxx개) 동적 카운트 -> 4단계: 종목(Stock) 드롭다운 연동 및 시가총액 정렬.
 * 드롭다운에서 선택 시 검색창에 종목명 자동 입력 동기화 및 100% 차트 렌더링 보장.
 */

document.addEventListener("DOMContentLoaded", () => {
    initDashboardHeaderStats();
    initCascadeFilterControls();
    initStrategyChipEvents();
    initTimeframeControlEvents();
});

/** 기간 선택 버튼 (1개월, 6개월, 1년, 5년, 전체) 및 줌 초기화 바인딩 */
function initTimeframeControlEvents() {
    const timeBtns = document.querySelectorAll(".time-btn[data-period]");
    timeBtns.forEach((btn) => {
        btn.addEventListener("click", (e) => {
            timeBtns.forEach((b) => b.classList.remove("active"));
            e.target.classList.add("active");

            const periodLimit = parseInt(e.target.getAttribute("data-period"), 10) || 120;
            const selectStock = document.getElementById("stockSelect");
            if (selectStock && selectStock.value && window.loadAndRenderCharts) {
                window.loadAndRenderCharts(selectStock.value, periodLimit);
            }
        });
    });

    const btnResetZoom = document.getElementById("btnResetZoom");
    if (btnResetZoom) {
        btnResetZoom.addEventListener("click", () => {
            if (window.resetTechChartZoom) {
                window.resetTechChartZoom();
            }
        });
    }

    const btnCustomDate = document.getElementById("btnCustomDate");
    if (btnCustomDate) {
        btnCustomDate.addEventListener("click", () => {
            alert("📅 직접지정 기능: 전체 데이터 범위 내에서 날짜 기간을 자유롭게 조회합니다.");
            const selectStock = document.getElementById("stockSelect");
            if (selectStock && selectStock.value && window.loadAndRenderCharts) {
                window.loadAndRenderCharts(selectStock.value, 5000);
            }
        });
    }
}

/** 대시보드 상단 칩 정보 4종 갱신 (Null 가드 안전 처리) */
function loadHeaderStats() {
    fetch("/api/market-indices")
        .then((res) => res.json())
        .then((res) => {
            if (res.status === "success" && res.data) {
                const data = res.data;
                const elStocks = document.getElementById("statTotalStocks");
                const elRecords = document.getElementById("statTotalRecords");
                const elDate = document.getElementById("statLatestDate");
                const elSync = document.getElementById("statLastSyncTime");

                if (elStocks) elStocks.innerText = (data.total_stocks || 0).toLocaleString();
                if (elRecords) elRecords.innerText = (data.total_records || 0).toLocaleString();
                if (elDate) elDate.innerText = data.latest_date || "-";
                if (elSync) elSync.innerText = data.last_sync_time || "-";
            }
        })
        .catch((err) => console.error("Header stats fetch error:", err));
}

/** 대시보드 상단 칩 로드 및 수급 동기화 버튼 바인딩 */
function initDashboardHeaderStats() {
    loadHeaderStats();

    const btnSync = document.getElementById("btnManualSync");
    if (btnSync) {
        btnSync.addEventListener("click", () => runManualSync(btnSync));
    }
}

/** 수급 동기화 실행 + 진행바 폴링 (시뮬레이션 진행바와 동일 패턴) */
function runManualSync(btnSync) {
    const wrap = document.getElementById("syncProgressWrap");
    const bar = document.getElementById("syncProgressBar");
    const text = document.getElementById("syncProgressText");
    const origLabel = btnSync.innerHTML;
    let pollTimer = null;

    const restore = (hideDelay) => {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = null;
        btnSync.disabled = false;
        btnSync.style.opacity = "1";
        btnSync.innerHTML = origLabel;
        setTimeout(() => { if (wrap) wrap.style.display = "none"; }, hideDelay);
    };

    btnSync.disabled = true;
    btnSync.style.opacity = "0.6";
    btnSync.innerHTML = "⏳ 동기화 중...";
    if (wrap) wrap.style.display = "block";
    if (bar) bar.style.width = "5%";
    if (text) text.innerText = "동기화 준비 중...";

    const startPolling = () => {
        pollTimer = setInterval(() => {
            fetch("/api/sync-progress")
                .then((r) => r.json())
                .then((d) => {
                    if (text) text.innerText = d.message || "동기화 중...";
                    if (bar) {
                        let pct = d.total > 0 ? (d.current / d.total) * 100 : 5;
                        if (pct < 5) pct = 5;
                        bar.style.width = pct + "%";
                    }
                    if (d.status === "completed") {
                        if (bar) bar.style.width = "100%";
                        restore(2000);
                        loadHeaderStats();
                    } else if (d.status === "error") {
                        restore(3000);
                        alert(d.message || "동기화 중 오류가 발생했습니다.");
                    }
                })
                .catch((err) => console.error("Sync progress poll error:", err));
        }, 1000);
    };

    fetch("/api/sync", { method: "POST" })
        .then((r) => r.json())
        .then((res) => {
            if (res.status === "started") {
                startPolling();
            } else {
                restore(0);
                alert(res.message || "동기화를 시작할 수 없습니다.");
            }
        })
        .catch((err) => {
            restore(0);
            console.error("Sync start error:", err);
            alert("동기화 요청 중 오류가 발생했습니다.");
        });
}

/** 4단계 연쇄 제어 컨트롤러 초기화 */
function initCascadeFilterControls() {
    const marketSelect = document.getElementById("marketFilterSelect");
    const sectorSelect = document.getElementById("sectorFilterSelect");
    const stockSelect = document.getElementById("stockSelect");
    const inputKeyword = document.getElementById("keywordFilterInput");

    if (!marketSelect || !sectorSelect || !stockSelect) return;

    // 1단계: 구분 목록 백엔드 동적 로드 (내림차순 정렬 및 localStorage 기억 고정)
    fetch("/api/target-categories")
        .then((res) => res.json())
        .then((res) => {
            if (res.status === "success" && Array.isArray(res.data)) {
                marketSelect.innerHTML = '<option value="ALL">전체 타깃</option>';
                // 내림차순 정렬 (한국어/문자열 내림차순)
                const sortedCategories = res.data.sort((a, b) => b.localeCompare(a, "ko"));
                sortedCategories.forEach((cat) => {
                    const opt = document.createElement("option");
                    opt.value = cat;
                    opt.textContent = cat;
                    marketSelect.appendChild(opt);
                });

                // localStorage에 저장된 마지막 선택값 복원
                const savedCategory = localStorage.getItem("algo_last_selected_category");
                if (savedCategory && Array.from(marketSelect.options).some((opt) => opt.value === savedCategory)) {
                    marketSelect.value = savedCategory;
                }

                loadSectorFilterOptions(marketSelect.value);
            } else {
                loadSectorFilterOptions("ALL");
            }
        })
        .catch(() => {
            loadSectorFilterOptions("ALL");
        });

    // 구분 변경 시 -> localStorage 저장 & 2단계 업종 로드 및 3단계 종목 갱신
    marketSelect.addEventListener("change", (e) => {
        const categoryVal = e.target.value;
        localStorage.setItem("algo_last_selected_category", categoryVal);
        loadSectorFilterOptions(categoryVal);
    });

    // 업종 변경 시 -> 3단계 종목 갱신
    sectorSelect.addEventListener("change", () => {
        const categoryVal = marketSelect.value;
        const industryVal = sectorSelect.value;
        loadFilteredTargetStocks(categoryVal, industryVal);
    });

    // 종목 드롭박스 선택 변경 시 -> localStorage 저장 & 검색창 종목명 자동 입력 동기화 & 차트 렌더링!
    stockSelect.addEventListener("change", (e) => {
        const selectedCode = e.target.value;
        if (selectedCode) {
            localStorage.setItem("algo_last_selected_stock", selectedCode);
        }
        const selectedText = e.target.options[e.target.selectedIndex] ? e.target.options[e.target.selectedIndex].text : "";
        
        // "삼성전자 (005930)" -> pureName "삼성전자" 추출하여 검색창에 자동 입력!
        if (inputKeyword && selectedText) {
            const pureName = selectedText.split("(")[0].trim();
            inputKeyword.value = pureName;
        }

        const chk = document.getElementById("chkMarketAggregate");
        if (chk && chk.checked) {
            chk.checked = false; // 종목 선택 시 전체 집계 체크 해제
            stockSelect.disabled = false;
            if (inputKeyword) inputKeyword.disabled = false;
        }

        if (selectedCode && window.loadAndRenderCharts) {
            window.loadAndRenderCharts(selectedCode);
        }
    });

    // 검색창 입력 시 -> 종목 드롭박스 <option> 리스트 실시간 동적 필터링!
    if (inputKeyword) {
        inputKeyword.addEventListener("input", (e) => {
            const query = e.target.value.trim().toLowerCase();
            if (!query) {
                renderStockSelectOptions(allCurrentTargetStocks);
                if (allCurrentTargetStocks.length > 0 && stockSelect) {
                    const savedStock = localStorage.getItem("algo_last_selected_stock");
                    let targetStock = allCurrentTargetStocks[0];
                    if (savedStock && allCurrentTargetStocks.some((stk) => stk.code === savedStock)) {
                        targetStock = allCurrentTargetStocks.find((stk) => stk.code === savedStock);
                    }
                    stockSelect.value = targetStock.code;
                }
                return;
            }

            const filtered = allCurrentTargetStocks.filter(
                (stk) => stk.name.toLowerCase().includes(query) || stk.code.toLowerCase().includes(query)
            );

            renderStockSelectOptions(filtered);

            if (filtered.length > 0) {
                stockSelect.value = filtered[0].code;
                localStorage.setItem("algo_last_selected_stock", filtered[0].code);
                if (window.loadAndRenderCharts) {
                    window.loadAndRenderCharts(filtered[0].code);
                }
            }
        });
    }

    // 초기 실행은 백엔드 구분 로드 후 localStorage 복원값에 맞춰 연동됨
}

/** 2단계: 구분 기반 업종 옵션 백엔드 로드 */
function loadSectorFilterOptions(categoryVal) {
    const sectorSelect = document.getElementById("sectorFilterSelect");
    const lblCatInd = document.getElementById("lblSelectedCategoryIndustry");

    if (lblCatInd) {
        lblCatInd.innerHTML = `${categoryVal === "ALL" ? "전체 타깃" : categoryVal} &nbsp; 전체 업종`;
    }

    fetch(`/api/target-industries?category=${encodeURIComponent(categoryVal)}`)
        .then((res) => res.json())
        .then((res) => {
            if (res.status === "success") {
                sectorSelect.innerHTML = '<option value="ALL">전체 업종</option>';
                res.data.forEach((ind) => {
                    const opt = document.createElement("option");
                    opt.value = ind;
                    opt.textContent = ind;
                    sectorSelect.appendChild(opt);
                });
                loadFilteredTargetStocks(categoryVal, "ALL");
            }
        });
}

let allCurrentTargetStocks = [];

/** 3단계 & 4단계: 필터링된 종목 백엔드 로드 및 드롭박스 갱신 (시가총액 정렬 적용) */
function loadFilteredTargetStocks(categoryVal, industryVal) {
    const stockSelect = document.getElementById("stockSelect");
    const chkLabel = document.getElementById("chkAggregateLabel");
    const inputKeyword = document.getElementById("keywordFilterInput");
    const lblCatInd = document.getElementById("lblSelectedCategoryIndustry");

    if (lblCatInd) {
        lblCatInd.innerHTML = `${categoryVal === "ALL" ? "전체 타깃" : categoryVal} &nbsp; ${industryVal === "ALL" ? "전체 업종" : industryVal}`;
    }

    fetch(`/api/filtered-stocks?category=${encodeURIComponent(categoryVal)}&industry=${encodeURIComponent(industryVal)}`)
        .then((res) => res.json())
        .then((res) => {
            if (res.status === "success") {
                allCurrentTargetStocks = res.data || [];
                const totalCount = res.total_count || 0;
                if (chkLabel) {
                    chkLabel.innerHTML = `📊 전체 (${totalCount.toLocaleString()}개) : <input type="checkbox" id="chkMarketAggregate" style="accent-color: #38bdf8; cursor: pointer;">`;
                    bindAggregateCheckboxEvent(categoryVal, industryVal);
                }

                renderStockSelectOptions(allCurrentTargetStocks);

                // 초기 체크 상태 파악 후 비활성화 & 차트 시각화 트리거
                const chk = document.getElementById("chkMarketAggregate");

                if (chk && chk.checked) {
                    stockSelect.disabled = true;
                    if (inputKeyword) inputKeyword.disabled = true;
                    fetchAndRenderAggregateChart(categoryVal, industryVal);
                } else {
                    stockSelect.disabled = false;
                    if (inputKeyword) inputKeyword.disabled = false;
                    if (allCurrentTargetStocks.length > 0) {
                        const savedStock = localStorage.getItem("algo_last_selected_stock");
                        let targetStock = allCurrentTargetStocks[0];
                        if (savedStock && allCurrentTargetStocks.some((stk) => stk.code === savedStock)) {
                            targetStock = allCurrentTargetStocks.find((stk) => stk.code === savedStock);
                        }
                        
                        stockSelect.value = targetStock.code;
                        localStorage.setItem("algo_last_selected_stock", targetStock.code);

                        // 검색창 종목명 동기화
                        if (inputKeyword && targetStock) {
                            inputKeyword.value = targetStock.name;
                        }
                        
                        if (window.loadAndRenderCharts) {
                            window.loadAndRenderCharts(targetStock.code);
                        }
                    }
                }
            }
        });
}

/** 종목 드롭박스 옵션 동적 렌더링 함수 */
function renderStockSelectOptions(stocks) {
    const stockSelect = document.getElementById("stockSelect");
    if (!stockSelect) return;

    stockSelect.innerHTML = "";
    if (stocks.length === 0) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "검색 결과 없음";
        stockSelect.appendChild(opt);
        return;
    }

    stocks.forEach((stk) => {
        const opt = document.createElement("option");
        opt.value = stk.code;
        opt.textContent = `${stk.name} (${stk.code})`;
        stockSelect.appendChild(opt);
    });
}

/** 📊 전체 집계 체크박스 이벤트 바인딩 */
function bindAggregateCheckboxEvent(categoryVal, industryVal) {
    const chk = document.getElementById("chkMarketAggregate");
    const selectStock = document.getElementById("stockSelect");
    const inputKeyword = document.getElementById("keywordFilterInput");
    if (!chk) return;

    chk.addEventListener("change", (e) => {
        if (e.target.checked) {
            selectStock.disabled = true;
            if (inputKeyword) inputKeyword.disabled = true;
            fetchAndRenderAggregateChart(categoryVal, industryVal);
        } else {
            selectStock.disabled = false;
            if (inputKeyword) inputKeyword.disabled = false;
            if (selectStock.value && window.loadAndRenderCharts) {
                window.loadAndRenderCharts(selectStock.value);
            }
        }
    });
}

/** 📊 전체 항목 평균 집계 차트 백엔드 API 로드 및 시각화 */
function fetchAndRenderAggregateChart(categoryVal, industryVal) {
    fetch(`/api/aggregate-chart?category=${encodeURIComponent(categoryVal)}&industry=${encodeURIComponent(industryVal)}`)
        .then((res) => res.json())
        .then((res) => {
            if (res.status === "success" && window.renderAggregateCharts) {
                const suffix = categoryVal === "ALL" ? "전체 타깃" : categoryVal;
                window.renderAggregateCharts(res.data, suffix);
            }
        });
}

const STRATEGY_CHIP_IDS = [
    "chkChipS1",
    "chkChipS1aVol",
    "chkChipS1bOld",
    "chkChipS1c",
    "chkChipS2",
    "chkChipS3",
    "chkChipS4",
    "chkChipS5",
];

/** 💾 체크박스 선택 상태 localStorage 저장 */
function saveChipStates() {
    const stateObj = {};
    STRATEGY_CHIP_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            stateObj[id] = el.checked;
        }
    });
    try {
        localStorage.setItem("algofinder_chip_states", JSON.stringify(stateObj));
    } catch (e) {
        console.warn("localStorage 저장 실패:", e);
    }
}

/** 💾 체크박스 선택 상태 localStorage 복원 (기록 없으면 S1 기본형만 체크!) */
function restoreChipStates() {
    const savedStr = localStorage.getItem("algofinder_chip_states");
    if (!savedStr) {
        // 기록이 없으면: S1 기본형만 checked = true, 나머지 7개는 checked = false 기본 지정!
        STRATEGY_CHIP_IDS.forEach((id) => {
            const el = document.getElementById(id);
            if (el) {
                el.checked = (id === "chkChipS1");
            }
        });
        return;
    }

    try {
        const stateObj = JSON.parse(savedStr);
        STRATEGY_CHIP_IDS.forEach((id) => {
            const el = document.getElementById(id);
            if (el && stateObj.hasOwnProperty(id)) {
                el.checked = Boolean(stateObj[id]);
            }
        });
    } catch (e) {
        console.warn("localStorage 복원 실패:", e);
    }
}

/** 8종 기술적 지표 칩 체크박스 이벤트 및 로컬 저장소 복원 바인딩 */
function initStrategyChipEvents() {
    // 1. 저장된 선택 상태 복원 (없으면 S1 기본형만 선택)
    restoreChipStates();

    // 2. 체크박스 change 이벤트 핸들러 연동
    STRATEGY_CHIP_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("change", () => {
                saveChipStates(); // 선택 변경 시 저장
                if (window.updateTechChartSeriesVisibility) {
                    window.updateTechChartSeriesVisibility();
                }
            });
        }
    });

    const btnToggleAll = document.getElementById("btnToggleAllTechChips");
    if (btnToggleAll) {
        let allChecked = true;
        btnToggleAll.addEventListener("click", () => {
            allChecked = !allChecked;
            STRATEGY_CHIP_IDS.forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.checked = allChecked;
            });
            saveChipStates();
            if (window.updateTechChartSeriesVisibility) {
                window.updateTechChartSeriesVisibility();
            }
        });
    }
}
