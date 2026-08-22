/**
 * AlgoFinder 사이드바 자동 로딩 스크립트 (load_sidebar.js).
 * AI 코딩규칙 (AI 코딩규칙.txt): 사이드바 너비 220px 고정, PC 모드 2분할 레이아웃 적용.
 */

document.addEventListener("DOMContentLoaded", () => {
    renderSidebarNav();
});

function renderSidebarNav() {
    const sidebar = document.getElementById("sidebarNav");
    if (!sidebar) return;

    const currentPath = window.location.pathname;

    const navItems = [
        { path: "/", label: "📊 메인 대시보드" },
        { path: "/backtest", label: "🧪 백테스트" },
        { path: "/recommendation", label: "📈 모의투자" },
        { path: "/proposal", label: "💡 투자제안" },
        { path: "/proposal-mobile", label: "💡 투자제안(모)" },
    ];

    let navHtml = `
        <div class="sidebar-logo">
            <span style="font-size: 1.4rem;">📈</span>
            <span style="font-weight: 700; font-size: 1.1rem; background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">AlgoFinder</span>
        </div>
        <nav class="sidebar-menu" style="margin-top: 24px; display: flex; flex-direction: column; gap: 8px;">
    `;

    navItems.forEach((item) => {
        const isActive = currentPath === item.path || (item.path !== "/" && currentPath.startsWith(item.path));
        const activeClass = isActive ? "sidebar-item active" : "sidebar-item";
        navHtml += `
            <a href="${item.path}" class="${activeClass}" style="
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 10px 14px;
                color: ${isActive ? "#ffffff" : "#94a3b8"};
                background: ${isActive ? "linear-gradient(135deg, #0284c7, #0369a1)" : "transparent"};
                border-radius: 8px;
                text-decoration: none;
                font-size: 0.9rem;
                font-weight: ${isActive ? "600" : "400"};
                transition: all 0.2s ease;
            ">
                ${item.label}
            </a>
        `;
    });

    navHtml += `</nav>`;
    sidebar.innerHTML = navHtml;
}
