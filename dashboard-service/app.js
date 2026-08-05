// =============================================================================
// AI Trading Terminal — app.js
// Full 5-Stage workflow: Stage 0 → 1 → 2 → 3 → 4
//
// API calls go through /api/ which nginx proxies to backtest:8008
// This avoids hardcoded IPs and works from any browser.
// =============================================================================

// Use nginx's same-origin proxy in Docker.  When index.html is opened directly
// from disk, /api resolves to file:///api and the Analyze button cannot reach
// the service, so connect to the published backtest port instead.
const API = window.location.protocol === "file:"
    ? "http://localhost:8008"
    : "/api";

// ── Global state ─────────────────────────────────────────────────────────────
let currentSymbol  = "";
let currentMode    = "INTRADAY";
let lockedPosition = null;
let s2Data         = null;   // Stage 2 recommendation response
let s4AutoTimer    = null;

// ── In-flight guards — prevent stacked / duplicate API calls ─────────────────
let _s1Loading    = false;   // loadStage1()      — analyzing a coin
let _s4Refreshing = false;   // refreshProtection() — Stage 4 protect call

// ── Binance WebSocket – real-time live price ──────────────────────────────────
let _binanceWs         = null;   // WebSocket instance
let _binanceReconnectT = null;   // reconnect timer

/**
 * Connect to /ws_price WebSocket endpoint (backed by Binance).
 * Receives real-time price pushes for BTC, ETH, SOL, BNB, XRP and more.
 * Sub-second latency. Auto-reconnects on disconnect.
 */
function startBinanceWs() {
    const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost  = window.location.protocol === "file:"
        ? "localhost:8008"
        : window.location.host;
    const wsUrl   = `${wsProto}//${wsHost}/api/ws_price`;

    // Avoid duplicate connections
    if (_binanceWs && (_binanceWs.readyState === WebSocket.OPEN ||
                       _binanceWs.readyState === WebSocket.CONNECTING)) return;

    try {
        _binanceWs = new WebSocket(wsUrl);

        _binanceWs.onopen = () => {
            console.log("[BinanceWS] Connected →", wsUrl);
            if (_binanceReconnectT) { clearTimeout(_binanceReconnectT); _binanceReconnectT = null; }
        };

        _binanceWs.onmessage = (evt) => {
            try {
                const data = JSON.parse(evt.data);
                if (data && data.LivePrices) {
                    updateLivePriceBand(data.LivePrices);
                }
            } catch (e) { /* ignore parse errors */ }
        };

        _binanceWs.onerror = (err) => {
            console.warn("[BinanceWS] Error:", err);
        };

        _binanceWs.onclose = () => {
            console.warn("[BinanceWS] Disconnected — reconnecting in 5s");
            _binanceWs = null;
            _binanceReconnectT = setTimeout(startBinanceWs, 5000);
        };
    } catch (e) {
        console.warn("[BinanceWS] Failed to connect:", e);
        _binanceReconnectT = setTimeout(startBinanceWs, 5000);
    }
}

/**
 * Update live prices from WebSocket — called on every Kraken tick.
 * 1. Updates Stage 1 price display with flash animation.
 * 2. Updates Stage 4 Live P&L bar in real-time without a full API call.
 */
function updateLivePriceBand(prices) {
    const sym  = currentSymbol || "BTC-USD";
    const coin = prices[sym];
    if (!coin || !coin.price) return;

    const livePrice = parseFloat(coin.price);

    // ── Stage 1 price flash ───────────────────────────────────────────────
    const priceEl = document.getElementById("s1-price");
    if (priceEl) {
        const formatted = fmtPrice(livePrice);
        if (priceEl.textContent !== formatted) {
            priceEl.textContent = formatted;
            priceEl.classList.remove("ws-flash");
            void priceEl.offsetWidth;
            priceEl.classList.add("ws-flash");
        }
    }

    // ── Stage 4 real-time P&L update ─────────────────────────────────────
    // Only update if Stage 4 is visible and we have a locked position
    const s4panel = document.getElementById("panel-4");
    if (lockedPosition && s4panel && !s4panel.classList.contains("hidden")) {
        const entry     = parseFloat(lockedPosition.entry) || 0;
        const direction = (lockedPosition.direction || "LONG").toUpperCase();

        if (entry > 0) {
            // P&L % calculation
            const pnlPct = direction === "SHORT"
                ? ((entry - livePrice) / entry) * 100
                : ((livePrice - entry) / entry) * 100;
            const pnlUsd = direction === "SHORT"
                ? (entry - livePrice)
                : (livePrice - entry);

            // Update price display
            const priceS4 = document.getElementById("s4-price");
            if (priceS4) {
                priceS4.textContent = fmtPrice(livePrice);
                priceS4.classList.remove("ws-flash");
                void priceS4.offsetWidth;
                priceS4.classList.add("ws-flash");
            }

            // Update P&L value
            const pnlEl = document.getElementById("s4-pnl");
            if (pnlEl) {
                pnlEl.textContent = fmtPct(pnlPct);
                pnlEl.className   = pnlPct >= 0 ? "a-val val-up" : "a-val val-down";
            }

            // Update P&L USD sub
            const pnlUsdEl = document.getElementById("s4-pnl-usd");
            if (pnlUsdEl) {
                const sign = pnlUsd >= 0 ? "+" : "";
                pnlUsdEl.textContent = `${sign}$${Math.abs(pnlUsd).toFixed(2)}`;
                pnlUsdEl.className   = pnlUsd >= 0 ? "a-sub val-up" : "a-sub val-down";
            }

            // Update P&L bar
            const barFill  = document.getElementById("s4-pnl-bar-fill");
            const barValue = document.getElementById("s4-pnl-bar-value");
            if (barFill && barValue) {
                const clamp  = Math.min(Math.abs(pnlPct), 10);   // max 10% visual
                const width  = (clamp / 10) * 100;
                barFill.style.width      = width + "%";
                barFill.style.background = pnlPct >= 0 ? "var(--green)" : "var(--red)";
                barValue.textContent     = fmtPct(pnlPct);
                barValue.className       = "pnl-bar-value " + (pnlPct >= 0 ? "val-up" : "val-down");
            }

            // Source indicator pulse
            const srcEl = document.getElementById("s4-pnl-source");
            if (srcEl) {
                srcEl.textContent = "● live";
                srcEl.className   = "pnl-bar-source pnl-live-pulse";
            }
        }
    }
}

// Start Binance WebSocket when page loads
document.addEventListener("DOMContentLoaded", () => {
    startBinanceWs();
});

// ─────────────────────────────────────────────────────────────────────────────
// Toast notifications
// ─────────────────────────────────────────────────────────────────────────────
function showToast(msg, type = "info") {
    const c = document.getElementById("toast-container");
    if (!c) return;
    const t = document.createElement("div");
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    c.appendChild(t);
    requestAnimationFrame(() => t.classList.add("show"));
    setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 350); }, 4000);
}

// ─────────────────────────────────────────────────────────────────────────────
// Formatting helpers
// ─────────────────────────────────────────────────────────────────────────────
function N(v, fallback = "N/A") {
    // Safe null/undefined/zero display
    if (v === null || v === undefined || v === "") return fallback;
    return v;
}

function fmt(n, dec = 2) {
    const v = parseFloat(n);
    if (isNaN(v)) return "N/A";
    return v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtPrice(n) {
    const v = parseFloat(n);
    if (isNaN(v) || v === 0) return "N/A";
    if (v >= 10000) return "$" + fmt(v, 0);
    if (v >= 1000)  return "$" + fmt(v, 2);
    if (v >= 1)     return "$" + fmt(v, 4);
    return "$" + v.toFixed(6);
}

function fmtBig(n) {
    const v = parseFloat(n);
    if (isNaN(v) || v === 0) return "N/A";
    if (v >= 1e12) return "$" + (v / 1e12).toFixed(2) + "T";
    if (v >= 1e9)  return "$" + (v / 1e9).toFixed(2) + "B";
    if (v >= 1e6)  return "$" + (v / 1e6).toFixed(2) + "M";
    return "$" + v.toLocaleString();
}

function fmtPct(n) {
    const v = parseFloat(n);
    if (isNaN(v)) return "N/A";
    const sign = v >= 0 ? "+" : "";
    return sign + v.toFixed(2) + "%";
}

function fmtPnl(pct) {
    const v = parseFloat(pct);
    if (isNaN(v)) return { text: "N/A", cls: "val-dim" };
    return { text: fmtPct(v), cls: v >= 0 ? "val-up" : "val-down" };
}

// ─────────────────────────────────────────────────────────────────────────────
// DOM helpers
// ─────────────────────────────────────────────────────────────────────────────
function set(id, text, cls = "") {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = (text !== null && text !== undefined && text !== "") ? text : "N/A";
    el.classList.remove("val-up","val-down","val-neutral","val-cyan","val-dim","val-orange","val-purple");
    if (cls) el.classList.add(cls);
}

function show(id) { const e = document.getElementById(id); if (e) e.style.display = ""; }
function hide(id) { const e = document.getElementById(id); if (e) e.style.display = "none"; }

// ─────────────────────────────────────────────────────────────────────────────
// Colour helpers
// ─────────────────────────────────────────────────────────────────────────────
function riskColor(r)  { const v=parseFloat(r)||0; return v<=30?"val-up":v<=60?"val-neutral":"val-down"; }
function confColor(c)  { const v=parseFloat(c)||0; return v>=65?"val-up":v>=45?"val-neutral":"val-down"; }
function rrColor(rr)   { const v=parseFloat(rr)||0; return v>=2?"val-up":v>=1?"val-neutral":"val-down"; }

function trendColor(t) {
    if (!t) return "val-dim";
    const u = t.toUpperCase();
    if (u.includes("BULL") || u.includes("UP") || u.includes("LONG") || u.includes("BUY")) return "val-up";
    if (u.includes("BEAR") || u.includes("DOWN") || u.includes("SHORT") || u.includes("SELL")) return "val-down";
    return "val-neutral";
}

function signalColor(s) {
    if (!s) return "val-dim";
    const u = s.toUpperCase();
    if (u === "LONG" || u === "BUY" || u === "STRONG BUY") return "val-up";
    if (u === "SHORT" || u === "SELL" || u === "STRONG SELL") return "val-down";
    if (u === "WAIT") return "val-neutral";
    return "val-dim";
}

function decisionBannerClass(dec) {
    if (!dec) return "";
    const d = dec.toUpperCase();
    if (d === "LONG")     return "dec-long";
    if (d === "SHORT")    return "dec-short";
    if (d === "WAIT")     return "dec-wait";
    return "dec-notrade";
}

function actionBannerClass(action) {
    if (!action) return "";
    const a = action.toUpperCase();
    if (a.includes("EXIT NOW"))     return "action-exit";
    if (a.includes("TAKE PROFIT"))  return "action-profit";
    if (a.includes("PARTIAL EXIT")) return "action-partial";
    if (a.includes("HOLD STRONG"))  return "action-hold-strong";
    if (a.includes("HOLD"))         return "action-hold";
    if (a.includes("MOVE STOP"))    return "action-move-sl";
    if (a.includes("TRAILING"))     return "action-trail";
    return "action-hold";
}

// ─────────────────────────────────────────────────────────────────────────────
// Stage navigation
// ─────────────────────────────────────────────────────────────────────────────
const STAGE_LABELS = [
    "STAGE 0 — CRYPTO SEARCH",
    "STAGE 1 — MARKET ANALYSIS",
    "STAGE 2 — TRADE SIGNAL",
    "STAGE 3 — POSITION LOCKED",
    "STAGE 4 — REAL-TIME MONITOR",
    "ACCURACY DASHBOARD",
];

function goToStage(n) {
    // Stage 5 (Accuracy) is always accessible — no symbol required
    if (n >= 1 && n <= 4 && !currentSymbol) {
        showToast("Enter a symbol in Stage 0 first.", "warning");
        const inp = document.getElementById("s0-manual-input");
        if (inp) { inp.focus(); inp.scrollIntoView({ behavior: "smooth", block: "center" }); }
        return;
    }
    if ((n === 3 || n === 4) && !lockedPosition) {
        showToast("Lock a position in Stage 2 first.", "warning");
        return;
    }

    const maxStage = 5;
    for (let i = 0; i <= maxStage; i++) {
        const p = document.getElementById(`panel-${i}`);
        if (p) p.classList.add("hidden");
        const s = document.getElementById(`pipe-${i}`);
        if (s) s.classList.remove("active", "done");
    }
    const panel = document.getElementById(`panel-${n}`);
    if (panel) panel.classList.remove("hidden");
    for (let i = 0; i < n; i++) {
        const s = document.getElementById(`pipe-${i}`);
        if (s) s.classList.add("done");
    }
    const cur = document.getElementById(`pipe-${n}`);
    if (cur) cur.classList.add("active");
    const badge = document.getElementById("header-stage-badge");
    if (badge) badge.textContent = STAGE_LABELS[n] || `STAGE ${n}`;
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (n === 4 && lockedPosition) refreshProtection();
    if (n === 5) loadAccuracyDashboard();
}

// ─────────────────────────────────────────────────────────────────────────────
// API fetch wrapper — shows errors as toasts, returns null on failure
// ─────────────────────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
    // A short-lived gateway restart or a slow market-data request should not
    // surface as a misleading permanent "Failed to fetch" error.  Retry safe
    // GETs, while keeping POST/DELETE requests single-shot.
    const method = (options.method || "GET").toUpperCase();
    const attempts = method === "GET" ? 3 : 1;
    const timeoutMs = options.timeoutMs || 330_000;
    const fetchOptions = { ...options };
    delete fetchOptions.timeoutMs;

    for (let attempt = 1; attempt <= attempts; attempt++) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const res = await fetch(API + path, { ...fetchOptions, signal: controller.signal });
            const data = await res.json().catch(() => null);
            if (!res.ok) {
                const msg = data?.detail || data?.error || `HTTP ${res.status}`;
                showToast(`❌ API error: ${msg}`, "error");
                console.error("API error", path, res.status, data);
                return null;
            }
            return data;
        } catch (err) {
            const retryable = method === "GET" && attempt < attempts;
            if (retryable) {
                await new Promise(resolve => setTimeout(resolve, 750 * attempt));
                continue;
            }
            const message = err.name === "AbortError"
                ? "The service took too long to respond"
                : err.message;
            showToast(`❌ Network error: ${message}`, "error");
            console.error("Network error", path, err);
            return null;
        } finally {
            clearTimeout(timer);
        }
    }
    return null;
}

// =============================================================================
// STAGE 0 — Stock Selection Engine
// =============================================================================

// =============================================================================
// STAGE 0 — Crypto Search
// =============================================================================

async function runStage0() {
    // Legacy stub — no longer used. Kept to prevent reference errors.
}

// =============================================================================
// STAGE 0 — Crypto Asset List (autocomplete)
// =============================================================================

const ASSET_LIST = [
    // ── Major Caps ────────────────────────────────────────────────────────
    { sym:"BTC-USD",    name:"Bitcoin",            cat:"crypto", icon:"₿" },
    { sym:"ETH-USD",    name:"Ethereum",           cat:"crypto", icon:"Ξ" },
    { sym:"BNB-USD",    name:"BNB",                cat:"crypto", icon:"🔶" },
    { sym:"SOL-USD",    name:"Solana",             cat:"crypto", icon:"◎" },
    { sym:"XRP-USD",    name:"XRP",                cat:"crypto", icon:"✕" },
    { sym:"ADA-USD",    name:"Cardano",            cat:"crypto", icon:"₳" },
    { sym:"DOGE-USD",   name:"Dogecoin",           cat:"crypto", icon:"Ð" },
    { sym:"TRX-USD",    name:"TRON",               cat:"crypto", icon:"🔺" },
    { sym:"TON-USD",    name:"Toncoin",            cat:"crypto", icon:"💎" },
    { sym:"SHIB-USD",   name:"Shiba Inu",          cat:"crypto", icon:"🐕" },

    // ── Layer 1 / Layer 2 ─────────────────────────────────────────────────
    { sym:"AVAX-USD",   name:"Avalanche",          cat:"crypto", icon:"🔺" },
    { sym:"DOT-USD",    name:"Polkadot",           cat:"crypto", icon:"●" },
    { sym:"MATIC-USD",  name:"Polygon",            cat:"crypto", icon:"⬡" },
    { sym:"NEAR-USD",   name:"NEAR Protocol",      cat:"crypto", icon:"Ⓝ" },
    { sym:"ARB-USD",    name:"Arbitrum",           cat:"crypto", icon:"🔵" },
    { sym:"OP-USD",     name:"Optimism",           cat:"crypto", icon:"🔴" },
    { sym:"APT-USD",    name:"Aptos",              cat:"crypto", icon:"◈" },
    { sym:"ICP-USD",    name:"Internet Computer",  cat:"crypto", icon:"∞" },
    { sym:"ATOM-USD",   name:"Cosmos",             cat:"crypto", icon:"⚛" },
    { sym:"XLM-USD",    name:"Stellar",            cat:"crypto", icon:"✦" },

    // ── DeFi / Utility ────────────────────────────────────────────────────
    { sym:"LINK-USD",   name:"Chainlink",          cat:"crypto", icon:"⬡" },
    { sym:"UNI-USD",    name:"Uniswap",            cat:"crypto", icon:"🦄" },
    { sym:"LTC-USD",    name:"Litecoin",           cat:"crypto", icon:"Ł" },
    { sym:"ETC-USD",    name:"Ethereum Classic",   cat:"crypto", icon:"Ξ" },
    { sym:"FIL-USD",    name:"Filecoin",           cat:"crypto", icon:"⬡" },
    { sym:"AAVE-USD",   name:"Aave",               cat:"crypto", icon:"👻" },
    { sym:"MKR-USD",    name:"Maker",              cat:"crypto", icon:"⬡" },
    { sym:"CRV-USD",    name:"Curve DAO",          cat:"crypto", icon:"🔵" },
    { sym:"LDO-USD",    name:"Lido DAO",           cat:"crypto", icon:"🔷" },
    { sym:"SNX-USD",    name:"Synthetix",          cat:"crypto", icon:"⚡" },

    // ── Meme / AI / Others ────────────────────────────────────────────────
    { sym:"PEPE-USD",   name:"Pepe",               cat:"crypto", icon:"🐸" },
    { sym:"FLOKI-USD",  name:"Floki Inu",          cat:"crypto", icon:"🐕" },
    { sym:"WIF-USD",    name:"dogwifhat",           cat:"crypto", icon:"🎩" },
    { sym:"BONK-USD",   name:"Bonk",               cat:"crypto", icon:"🔨" },
    { sym:"FET-USD",    name:"Fetch.ai",            cat:"crypto", icon:"🤖" },
    { sym:"RENDER-USD", name:"Render",             cat:"crypto", icon:"🎨" },
    { sym:"INJ-USD",    name:"Injective",          cat:"crypto", icon:"🔮" },
    { sym:"SUI-USD",    name:"Sui",                cat:"crypto", icon:"💧" },
    { sym:"SEI-USD",    name:"Sei",                cat:"crypto", icon:"🔱" },
    { sym:"JUP-USD",    name:"Jupiter",            cat:"crypto", icon:"🪐" },
];

const POPULAR_ASSETS = ["BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","DOGE-USD","ADA-USD","AVAX-USD","MATIC-USD","ARB-USD"];

const MAX_RECENT = 6;
function getRecentSearches() {
    try { return JSON.parse(localStorage.getItem("recentSearches") || "[]"); } catch { return []; }
}
function addRecentSearch(sym) {
    try {
        let arr = getRecentSearches().filter(s => s !== sym);
        arr.unshift(sym);
        localStorage.setItem("recentSearches", JSON.stringify(arr.slice(0, MAX_RECENT)));
    } catch {}
}

// Highlight matched portion of text
function highlight(text, query) {
    if (!query) return text;
    const idx = text.toUpperCase().indexOf(query.toUpperCase());
    if (idx === -1) return text;
    return text.slice(0, idx)
        + `<mark class="dd-highlight">${text.slice(idx, idx + query.length)}</mark>`
        + text.slice(idx + query.length);
}

function catBadge(cat) {
    if (cat === "crypto") return `<span class="dd-cat dd-cat-crypto">CRYPTO</span>`;
    return "";
}

function renderDropdown(items, query, header) {
    const dd = document.getElementById("search-dropdown");
    if (!dd) return;

    if (header) {
        dd.innerHTML = `<div class="dd-section-header">${header}</div>` +
            items.map(a => buildItem(a, query)).join("") ;
    } else {
        dd.innerHTML = items.map(a => buildItem(a, query)).join("");
    }

    dd.style.display = "block";
    bindDropdownClicks();
}

function buildItem(asset, query) {
    const symHL  = highlight(asset.sym,  query);
    const nameHL = highlight(asset.name, query);
    return `<div class="dd-item" data-sym="${asset.sym}" tabindex="-1">
      <span class="dd-icon">${asset.icon}</span>
      <span class="dd-info">
        <span class="dd-sym">${symHL}</span>
        <span class="dd-name">${nameHL}</span>
      </span>
      ${catBadge(asset.cat)}
    </div>`;
}

function bindDropdownClicks() {
    document.querySelectorAll(".dd-item").forEach(item => {
        item.addEventListener("mousedown", e => {
            e.preventDefault();
            selectAsset(item.dataset.sym);
        });
    });
}

function closeDropdown() {
    const dd = document.getElementById("search-dropdown");
    if (dd) dd.style.display = "none";
}

function selectAsset(sym) {
    const inp = document.getElementById("s0-manual-input");
    if (inp) { inp.value = sym; inp.focus(); }
    closeDropdown();
    toggleClearBtn(sym);
    hideSearchError();
}

function toggleClearBtn(val) {
    const btn = document.getElementById("s0-clear-btn");
    if (btn) btn.style.display = val ? "" : "none";
}

function clearSearch() {
    const inp = document.getElementById("s0-manual-input");
    if (inp) { inp.value = ""; inp.focus(); }
    toggleClearBtn("");
    closeDropdown();
}

function initSearch() {
    const inp = document.getElementById("s0-manual-input");
    const dd  = document.getElementById("search-dropdown");
    if (!inp || !dd) return;

    inp.addEventListener("input", () => {
        const raw = inp.value;
        const val = raw.trim().toUpperCase();
        toggleClearBtn(raw);

        if (!val) {
            // Show popular + recent when empty
            showDefaultDropdown();
            return;
        }

        const matches = ASSET_LIST.filter(a =>
            a.sym.toUpperCase().includes(val) ||
            a.name.toUpperCase().includes(val)
        ).slice(0, 10);

        if (!matches.length) {
            dd.innerHTML = `<div class="dd-no-match">No matching assets found for "<strong>${raw}</strong>"</div>`;
            dd.style.display = "block";
            return;
        }

        renderDropdown(matches, val, null);
    });

    inp.addEventListener("focus", () => {
        const val = inp.value.trim();
        if (!val) showDefaultDropdown();
        else inp.dispatchEvent(new Event("input"));
    });

    inp.addEventListener("blur", () => setTimeout(closeDropdown, 180));

    // Keyboard navigation
    inp.addEventListener("keydown", e => {
        const items = [...document.querySelectorAll(".dd-item")];
        const active = document.querySelector(".dd-item.dd-active");
        const idx = items.indexOf(active);

        if (e.key === "ArrowDown") {
            e.preventDefault();
            items.forEach(i => i.classList.remove("dd-active"));
            const next = items[idx + 1] || items[0];
            next?.classList.add("dd-active");
            next?.scrollIntoView({ block: "nearest" });
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            items.forEach(i => i.classList.remove("dd-active"));
            const prev = items[idx - 1] || items[items.length - 1];
            prev?.classList.add("dd-active");
            prev?.scrollIntoView({ block: "nearest" });
        } else if (e.key === "Enter") {
            if (active) {
                e.preventDefault();
                selectAsset(active.dataset.sym);
            } else {
                manualSelectSymbol();
            }
        } else if (e.key === "Escape") {
            closeDropdown();
            inp.blur();
        }
    });

    // Click outside closes
    document.addEventListener("mousedown", e => {
        const wrap = document.getElementById("s0-search-wrap");
        if (wrap && !wrap.contains(e.target)) closeDropdown();
    });
}

// Render popular coin quick-pick chips below the search bar
function initPopularChips() {
    const container = document.getElementById("s0-popular-chips");
    if (!container) return;
    const popular = ASSET_LIST.filter(a => POPULAR_ASSETS.includes(a.sym));
    container.innerHTML = popular.map(a =>
        `<button class="s0-chip" onclick="quickPickCoin('${a.sym}', '${a.name}')">
           <span class="s0-chip-icon">${a.icon}</span>
           <span class="s0-chip-sym">${a.sym.replace("-USD","")}</span>
         </button>`
    ).join("");
}

function quickPickCoin(sym, name) {
    const inp = document.getElementById("s0-manual-input");
    if (inp) { inp.value = sym; }
    toggleClearBtn(sym);
    hideSearchError();
    closeDropdown();
}

function showDefaultDropdown() {
    const dd = document.getElementById("search-dropdown");
    if (!dd) return;
    const recent  = getRecentSearches();
    const popular = ASSET_LIST.filter(a => POPULAR_ASSETS.includes(a.sym));
    let html = "";

    if (recent.length) {
        const recentAssets = recent.map(s => ASSET_LIST.find(a => a.sym === s)).filter(Boolean);
        if (recentAssets.length) {
            html += `<div class="dd-section-header">🕐 Recent Searches</div>`;
            html += recentAssets.map(a => buildItem(a, "")).join("");
        }
    }

    html += `<div class="dd-section-header">⭐ Popular Assets</div>`;
    html += popular.map(a => buildItem(a, "")).join("");

    dd.innerHTML = html;
    dd.style.display = "block";
    bindDropdownClicks();
}

// =============================================================================
// STAGE 0 — Search button handler (crypto-only)
// =============================================================================

function showSearchError(msg) {
    const el = document.getElementById("s0-error-msg");
    if (!el) return;
    el.textContent = msg;
    el.style.display = "";
}

function hideSearchError() {
    const el = document.getElementById("s0-error-msg");
    if (el) el.style.display = "none";
}

async function manualSelectSymbol() {
    const inp = document.getElementById("s0-manual-input");
    let sym = (inp?.value || "").trim().toUpperCase();

    hideSearchError();

    if (!sym) {
        showSearchError("⚠️ Please type or select a crypto asset first.");
        inp?.focus();
        return;
    }

    // Normalize: if user typed "BTC" or "BITCOIN" without -USD, resolve it
    const knownCrypto = ASSET_LIST.filter(a => a.cat === "crypto");
    const hasDash = sym.includes("-");

    if (!hasDash) {
        // Try to match against symbol without -USD (e.g. "BTC" → "BTC-USD")
        const match = knownCrypto.find(a =>
            a.sym.replace("-USD","").toUpperCase() === sym ||
            a.name.toUpperCase() === sym
        );
        if (match) {
            sym = match.sym;
        } else {
            // Append -USD as a best-effort
            sym += "-USD";
        }
    }

    // Validate it looks like a crypto pair
    if (!sym.endsWith("-USD") && !sym.includes("-")) {
        showSearchError("⚠️ Please select a crypto asset from the dropdown.");
        return;
    }

    if (inp) inp.value = sym;
    closeDropdown();
    addRecentSearch(sym);
    toggleClearBtn(sym);

    console.log(`[Stage0] Analyzing crypto: ${sym}`);

    currentSymbol = sym;
    currentMode   = "SWING";   // crypto defaults to SWING

    await loadStage1(sym, currentMode);
}

// =============================================================================
// STAGE 1 — Market Analysis Engine
// =============================================================================

async function loadStage1(symbol, mode) {
    // ── In-flight guard — ignore if a previous analysis is still running ─
    if (_s1Loading) {
        showToast("⏳ Analysis already in progress…", "warning");
        return;
    }
    _s1Loading = true;

    // Show spinner on analyze button
    const btnText    = document.getElementById("analyze-btn-text");
    const btnSpinner = document.getElementById("analyze-btn-spinner");
    const analyzeBtn = document.getElementById("s0-analyze-btn");
    if (btnText)    btnText.style.display    = "none";
    if (btnSpinner) btnSpinner.style.display = "";
    if (analyzeBtn) analyzeBtn.disabled      = true;

    console.log(`[API] → GET /api/stage1/analyze/${symbol}?mode=${mode}`);
    console.log(`[API] → GET /api/stage2/recommend/${symbol}?mode=${mode}`);
    showToast(`🔍 Analyzing ${symbol}…`, "info");

    try {
        // Call stage1/analyze + stage2/recommend in parallel
        const [s1, s2] = await Promise.all([
            apiFetch(`/stage1/analyze/${symbol}?mode=${mode}`),
            apiFetch(`/stage2/recommend/${symbol}?mode=${mode}`)
        ]);

        if (!s1) {
            showToast(`❌ Analysis failed for ${symbol}. Check the symbol and try again.`, "error");
            showSearchError(`❌ Analysis failed for ${symbol}. Check the symbol and try again.`);
            console.error(`[API] Stage 1 returned null for ${symbol}`);
            return;
        }

        console.log(`[API] ← Stage1 response:`, s1);
        console.log(`[API] ← Stage2 response:`, s2);

        populateStage1(s1);
        if (s2) populateStage2(s2);

        // Bypass guard — symbol is valid, set before calling goToStage
        currentSymbol = symbol;
        _goToStageForce(1);
        showToast(`✅ Analysis complete: ${symbol}`, "success");
    } catch (err) {
        console.error(`[API] Analysis failed for ${symbol}`, err);
        showSearchError(`❌ Could not analyze ${symbol}. Make sure the backtest service is running.`);
        showToast("❌ Analysis failed. Check that the API service is running.", "error");

    } finally {
        _s1Loading = false;
        if (btnText)    btnText.style.display    = "";
        if (btnSpinner) btnSpinner.style.display = "none";
        if (analyzeBtn) analyzeBtn.disabled      = false;
    }
}

function populateStage1(d) {
    set("s1-sym-label", d.Symbol, "val-cyan");

    // ── Row 0: Price ─────────────────────────────────────────────────────
    set("s1-price",  fmtPrice(d.LivePrice || d.EntryPrice), "val-cyan");

    if (d.Change24h != null) {
        const c = parseFloat(d.Change24h);
        set("s1-change", `24h: ${c>=0?"▲":"▼"} ${Math.abs(c).toFixed(2)}%`, c>=0?"val-up":"val-down");
    } else {
        set("s1-change", "24h: N/A");
    }

    set("s1-vol",  fmtBig(d.Volume24h));
    set("s1-mcap", `MCap: ${fmtBig(d.MarketCap)}`);

    set("s1-health",   d.MarketHealth  || "N/A", trendColor(d.MarketHealth));
    set("s1-mode-lbl", `Mode: ${d.Mode || "N/A"}`);

    // ── Row 1: Trend ──────────────────────────────────────────────────────
    set("s1-trend",    d.Trend         || "N/A", trendColor(d.Trend));
    set("s1-tstr",     d.TrendStrength || "N/A", trendColor(d.TrendStrength));
    set("s1-tstr-sub", d.WinRate != null ? `Win Rate ${fmt(d.WinRate,1)}%` : "");
    set("s1-struct",   d.MarketStructure || "N/A", trendColor(d.Trend));
    set("s1-bos",      d.Signal || "N/A", signalColor(d.Signal));

    // ── Row 2: EMAs ───────────────────────────────────────────────────────
    const price = parseFloat(d.LivePrice || d.EntryPrice) || 0;

    set("s1-ema20",  fmtPrice(d.EMA20));
    set("s1-ema20-sub",  d.EMA20 && price ? `Price ${price > d.EMA20 ? "above ✓" : "below ✗"} EMA 20` : "Short-term trend",  price > d.EMA20 ? "val-up" : "val-down");

    set("s1-ema50",  fmtPrice(d.EMA50));
    set("s1-ema50-sub",  d.EMA50 && price ? `Price ${price > d.EMA50 ? "above ✓" : "below ✗"} EMA 50` : "Mid-term trend",  price > d.EMA50 ? "val-up" : "val-down");

    set("s1-ema200", fmtPrice(d.EMA200));
    set("s1-ema200-sub", d.EMA200 && price ? `Price ${price > d.EMA200 ? "above ✓" : "below ✗"} EMA 200` : "Long-term trend", price > d.EMA200 ? "val-up" : "val-down");

    set("s1-ema-align", d.EMAAlignment || "N/A", trendColor(d.EMAAlignment));

    // ── Row 3: Momentum ───────────────────────────────────────────────────
    const rsiV = parseFloat(d.RSI);
    set("s1-rsi",      isNaN(rsiV) ? "N/A" : fmt(rsiV, 1),
        rsiV >= 70 ? "val-down" : rsiV <= 30 ? "val-up" : "val-neutral");
    set("s1-rsi-zone", d.RSIZone || "N/A",
        (d.RSIZone || "").includes("Over") ? (d.RSIZone.includes("bought") ? "val-down" : "val-up") : "val-neutral");

    set("s1-macd",     d.MACD    || "N/A", trendColor(d.MACD));
    set("s1-macd-sub", `PF ${fmt(d.ProfitFactor, 2)}  |  ADX ${fmt(d.ADX, 1)}`);

    set("s1-bb",     d.BBPosition || "N/A");
    set("s1-bb-sub", `Sharpe ${fmt(d.Sharpe, 2)}`);

    set("s1-mtf",     d.MultiTFLabel || "N/A");
    set("s1-mtf-sub", d.MultiTFStrength != null ? `Strength: ${d.MultiTFStrength}%` : "");

    // ── Row 4: Volatility ─────────────────────────────────────────────────
    set("s1-atr",      fmtPrice(d.ATR), "val-cyan");
    set("s1-vol2",     d.Volatility  || "N/A",
        d.Volatility === "Low" ? "val-up" : d.Volatility === "Extreme" || d.Volatility === "High" ? "val-down" : "val-neutral");
    set("s1-vol2-sub", d.VolatilityPct != null ? `ATR = ${fmt(d.VolatilityPct,2)}% of price` : "");

    set("s1-support",  fmtPrice(d.Support),    "val-up");
    set("s1-resist",   fmtPrice(d.Resistance), "val-down");

    // ── Row 5: Sentiment ──────────────────────────────────────────────────
    set("s1-liq",     d.Liquidity  || "N/A",
        (d.Liquidity||"").includes("High") ? "val-up" : (d.Liquidity||"").includes("Low") ? "val-down" : "val-neutral");
    set("s1-liq-sub", d.Volume24h ? `Vol 24h: ${fmtBig(d.Volume24h)}` : "");

    set("s1-fg",     d.FearGreed || "N/A",
        (d.FearGreed||"").includes("Greed") ? "val-down" : (d.FearGreed||"").includes("Fear") ? "val-up" : "val-neutral");
    set("s1-fg-sub", d.FearGreedScore != null ? `Score: ${fmt(d.FearGreedScore,0)}/100` : "");

    set("s1-risk",     d.RiskScore != null ? fmt(d.RiskScore,0) : "N/A", riskColor(d.RiskScore));
    set("s1-risk-sub", d.RiskScore != null
        ? (d.RiskScore<=30?"Low risk":d.RiskScore<=60?"Moderate risk":"High risk") : "");

    set("s1-conf",     d.Confidence != null ? `${fmt(d.Confidence,0)}%` : "N/A", confColor(d.Confidence));
    set("s1-conf-sub", d.Confidence != null
        ? (d.Confidence>=65?"High confidence":d.Confidence>=45?"Moderate":"Low confidence") : "");

    // ── Summary ───────────────────────────────────────────────────────────
    const items = [
        { label:"Symbol",        value: d.Symbol,                   cls: "val-cyan" },
        { label:"Mode",          value: d.Mode,                     cls: "" },
        { label:"Trend",         value: d.Trend,                    cls: trendColor(d.Trend) },
        { label:"Signal",        value: d.Signal,                   cls: signalColor(d.Signal) },
        { label:"RSI",           value: d.RSI != null ? fmt(d.RSI,1) : "N/A", cls: "" },
        { label:"ADX",           value: d.ADX != null ? fmt(d.ADX,1) : "N/A", cls: d.ADX>=25?"val-up":"val-neutral" },
        { label:"Volatility",    value: d.Volatility,               cls: d.Volatility==="Low"?"val-up":"val-neutral" },
        { label:"Market Health", value: d.MarketHealth,             cls: trendColor(d.MarketHealth) },
        { label:"Liquidity",     value: d.Liquidity,                cls: "" },
        { label:"Fear & Greed",  value: d.FearGreed,                cls: "" },
        { label:"Risk Score",    value: d.RiskScore!=null?fmt(d.RiskScore,0)+"":"N/A", cls: riskColor(d.RiskScore) },
        { label:"Confidence",    value: d.Confidence!=null?fmt(d.Confidence,0)+"%":"N/A", cls: confColor(d.Confidence) },
    ];
    const sg = document.getElementById("s1-summary-grid");
    if (sg) {
        sg.innerHTML = items.map(i =>
            `<div class="summary-item">
               <span class="si-label">${i.label}</span>
               <span class="si-value ${i.cls}">${i.value || "N/A"}</span>
             </div>`).join("");
    }
}

// =============================================================================
// STAGE 2 — Trade Recommendation
// =============================================================================

function populateStage2(d) {
    s2Data = d;

    const dec    = d.Decision  || "NO TRADE";
    const signal = d.Signal    || "";
    const conf   = parseFloat(d.Confidence) || 0;

    set("s2-sym-label", d.Symbol, "val-cyan");

    // ── Decision banner class ────────────────────────────────────────────
    const banner = document.getElementById("s2-decision-banner");
    if (banner) banner.className = "decision-banner " + decisionBannerClass(dec);

    // ── Signal tag — STRONG BUY / BUY / SELL / STRONG SELL ───────────────
    const tagEl = document.getElementById("s2-signal-tag");
    if (tagEl) {
        const sig = signal.toUpperCase();
        if (sig === "STRONG BUY") {
            tagEl.textContent = "⚡ STRONG BUY";
            tagEl.className   = "dec-signal-tag sig-strong-buy";
            tagEl.style.display = "";
        } else if (sig === "BUY") {
            tagEl.textContent = "▲ BUY";
            tagEl.className   = "dec-signal-tag sig-buy";
            tagEl.style.display = "";
        } else if (sig === "STRONG SELL") {
            tagEl.textContent = "⚡ STRONG SELL";
            tagEl.className   = "dec-signal-tag sig-strong-sell";
            tagEl.style.display = "";
        } else if (sig === "SELL") {
            tagEl.textContent = "▼ SELL";
            tagEl.className   = "dec-signal-tag sig-sell";
            tagEl.style.display = "";
        } else {
            tagEl.style.display = "none";
        }
    }

    set("s2-action",   dec);
    set("s2-conf-pct", conf > 0 ? `Confidence: ${fmt(conf,0)}%` : "");
    set("s2-reason",   d.Reason || "");

    // Actionable = LONG or SHORT (even when signal is SELL/STRONG SELL the
    // decision might still be SHORT which is a valid trade direction)
    const isActionable = dec === "LONG" || dec === "SHORT";
    const setupWrap = document.getElementById("s2-setup-wrap");
    const waitWrap  = document.getElementById("s2-wait-wrap");
    const ctaWrap   = document.getElementById("s2-cta");

    if (isActionable) {
        if (setupWrap) setupWrap.style.display = "";
        if (waitWrap)  waitWrap.style.display  = "none";
        if (ctaWrap)   ctaWrap.style.display   = "";

        const isShort = dec === "SHORT";
        set("s2-dir",      isShort ? "SHORT ▼" : "LONG ▲", isShort ? "val-down" : "val-up");
        set("s2-mode-lbl", d.Mode || "N/A");
        set("s2-entry",    fmtPrice(d.Entry),    "val-cyan");
        set("s2-sl",       fmtPrice(d.StopLoss), "val-down");
        set("s2-risk-amt", d.Risk ? `Risk: ${fmtPrice(d.Risk)}` : "Risk: N/A");

        // For SHORT trades TP labels show "Target" not "profit"
        set("s2-tp1", fmtPrice(d.TP1), isShort ? "val-down" : "val-up");
        set("s2-tp2", fmtPrice(d.TP2), isShort ? "val-down" : "val-up");
        set("s2-tp3", fmtPrice(d.TP3), isShort ? "val-down" : "val-up");
        set("s2-rr",  d.RiskReward ? `1 : ${fmt(d.RiskReward,2)}` : "N/A", rrColor(d.RiskReward));

        const reasons = (d.Reason || "").split("|").map(r => r.trim()).filter(Boolean);
        const why = document.getElementById("s2-why-body");
        if (why) why.innerHTML = reasons.map(r => `<div class="why-item">• ${r}</div>`).join("");

    } else {
        if (setupWrap) setupWrap.style.display = "none";
        if (waitWrap)  waitWrap.style.display  = "";
        if (ctaWrap)   ctaWrap.style.display   = "none";
        set("s2-wait-reason", d.Reason || "Conditions not met. Wait for a stronger setup.");
    }
}

// =============================================================================
// STAGE 3 — Lock Position
// =============================================================================

async function lockPosition() {
    if (!s2Data) { showToast("Run Stage 2 analysis first.", "warning"); return; }

    const dec = s2Data.Decision || "NO TRADE";
    if (dec !== "LONG" && dec !== "SHORT") {
        showToast(`Cannot lock: decision is ${dec}. Need LONG or SHORT.`, "warning");
        return;
    }

    const payload = {
        symbol:     currentSymbol,
        direction:  dec,
        entry:      s2Data.Entry    || 0,
        stop_loss:  s2Data.StopLoss || 0,
        tp1:        s2Data.TP1      || 0,
        tp2:        s2Data.TP2      || 0,
        tp3:        s2Data.TP3      || 0,
        confidence: s2Data.Confidence || 0,
        reason:     s2Data.Reason   || "",
        mode:       currentMode,
    };

    const data = await apiFetch("/stage3/lock", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(payload),
    });

    if (!data) return;

    lockedPosition = data.Position;
    populateStage3(lockedPosition);
    goToStage(3);
    showToast(`🔒 Position locked: ${currentSymbol} ${dec}`, "success");
}

function populateStage3(pos) {
    if (!pos) return;

    set("s3-sym-label", pos.symbol, "val-cyan");
    set("s3-lock-sym",  pos.symbol, "val-cyan");
    set("s3-lock-dir",  pos.direction === "LONG" ? "LONG ▲" : "SHORT ▼",
        pos.direction === "LONG" ? "val-up" : "val-down");

    let tStr = "N/A";
    try { tStr = new Date(pos.locked_at).toLocaleTimeString(); } catch(_) {}
    set("s3-lock-time", tStr);

    set("s3-entry", fmtPrice(pos.entry),     "val-cyan");
    set("s3-sl",    fmtPrice(pos.stop_loss),  "val-down");
    set("s3-rr",    pos.risk_reward > 0 ? `1 : ${fmt(pos.risk_reward,2)}` : "N/A", rrColor(pos.risk_reward));
    set("s3-tp1",   fmtPrice(pos.tp1), "val-up");
    set("s3-tp2",   fmtPrice(pos.tp2), "val-up");
    set("s3-tp3",   fmtPrice(pos.tp3), "val-up");

    // Pre-seed Stage 4 reference
    set("s4-sym-label",  pos.symbol,           "val-cyan");
    set("s4-ref-entry",  fmtPrice(pos.entry),  "val-cyan");
    set("s4-ref-sl",     fmtPrice(pos.stop_loss), "val-down");
    set("s4-ref-tp2",    fmtPrice(pos.tp2),    "val-up");
    set("s4-ref-tp3",    fmtPrice(pos.tp3),    "val-up");
}

// =============================================================================
// STAGE 4 — AI Protection Manager
// =============================================================================

async function refreshProtection() {
    if (!lockedPosition) {
        showToast("No locked position. Complete Stages 0-3 first.", "warning");
        return;
    }

    // ── In-flight guard — skip this tick if previous call still running ──
    if (_s4Refreshing) {
        console.warn("[Stage4] Skipped refresh — previous request still in-flight");
        return;
    }
    _s4Refreshing = true;

    const btn = document.getElementById("s4-refresh-btn");
    if (btn) { btn.disabled = true; btn.textContent = "⏳ Refreshing…"; }

    const sym  = lockedPosition.symbol || currentSymbol;
    try {
        const data = await apiFetch(`/stage4/protect/${sym}`);
        if (data) populateStage4(data);
        // Also refresh top opportunities in background
        loadTopOpportunities();
    } finally {
        _s4Refreshing = false;
        if (btn) { btn.disabled = false; btn.textContent = "🔄 Refresh Now"; }
    }
}

function populateStage4(data) {
    const action = data.Action   || "HOLD";
    const reason = data.Reason   || "Monitoring…";
    const inds   = data.Indicators || {};
    const dists  = data.Distances  || {};
    const pos    = data.Position   || lockedPosition || {};

    const banner = document.getElementById("s4-action-banner");
    if (banner) banner.className = "protect-banner " + actionBannerClass(action);
    set("s4-action", action);
    set("s4-reason", reason);

    set("s4-price", fmtPrice(data.LivePrice), "val-cyan");

    const pnlF = fmtPnl(data.PnL);
    set("s4-pnl",  pnlF.text, pnlF.cls);
    set("s4-hold", data.HoldingMins != null ? `${fmt(data.HoldingMins,1)} min` : "N/A");

    const htf = inds.HigherTF || "N/A";
    set("s4-htf", htf, htf === "BULLISH" ? "val-up" : htf === "BEARISH" ? "val-down" : "val-neutral");

    // Distances
    const fD = v => v != null ? fmtPrice(Math.abs(parseFloat(v))) : "N/A";
    set("s4-d-tp1", fD(dists.to_TP1), "val-up");
    set("s4-d-tp2", fD(dists.to_TP2), "val-up");
    set("s4-d-tp3", fD(dists.to_TP3), "val-up");
    set("s4-d-sl",  fD(dists.to_SL),  "val-down");

    // Indicators
    const rsi = inds.RSI;
    set("s4-rsi", rsi != null ? fmt(rsi,1) : "N/A",
        rsi>=70?"val-down":rsi<=30?"val-up":"val-neutral");
    set("s4-rsi-zone",
        rsi>=70?"Overbought":rsi<=30?"Oversold":rsi>=60?"Bullish Zone":rsi<=40?"Bearish Zone":"Neutral",
        rsi>=70?"val-down":rsi<=30?"val-up":"val-neutral");

    const adx = inds.ADX;
    set("s4-adx", adx != null ? fmt(adx,1) : "N/A",
        adx>=25?"val-up":adx>=15?"val-neutral":"val-down");

    const macd = inds.MACD, macdS = inds.MACD_Signal;
    if (macd != null && macdS != null) {
        const bull = macd > macdS;
        set("s4-macd",     bull ? "Bullish ▲" : "Bearish ▼", bull?"val-up":"val-down");
        set("s4-macd-sub", `${fmt(macd,4)} vs ${fmt(macdS,4)}`);
    }

    const atr = inds.ATR;
    set("s4-atr", atr!=null ? fmt(atr,4) : "N/A", "val-cyan");
    set("s4-atr-sub", atr && data.LivePrice
        ? `${fmt(parseFloat(atr)/parseFloat(data.LivePrice)*100,2)}% of price`
        : "Average True Range");

    // Keep reference row in sync
    if (pos.entry) {
        set("s4-ref-entry", fmtPrice(pos.entry),     "val-cyan");
        set("s4-ref-sl",    fmtPrice(pos.stop_loss),  "val-down");
        set("s4-ref-tp2",   fmtPrice(pos.tp2),        "val-up");
        set("s4-ref-tp3",   fmtPrice(pos.tp3),        "val-up");
    }
}

function toggleAutoRefresh() {
    const on = document.getElementById("s4-auto-toggle")?.checked;
    if (on) {
        clearInterval(s4AutoTimer);
        s4AutoTimer = setInterval(refreshProtection, 60_000);
        showToast("Auto-refresh ON — every 60 s", "info");
    } else {
        clearInterval(s4AutoTimer);
        s4AutoTimer = null;
        showToast("Auto-refresh OFF", "info");
    }
}

async function closeTrade() {
    const sym = (lockedPosition?.symbol || currentSymbol || "").toUpperCase();
    if (sym) {
        await apiFetch(`/stage3/unlock/${sym}`, { method: "DELETE" }).catch(() => {});
    }
    lockedPosition = null;
    s2Data         = null;
    currentSymbol  = "";
    clearInterval(s4AutoTimer);
    s4AutoTimer    = null;
    const tog = document.getElementById("s4-auto-toggle");
    if (tog) tog.checked = false;
    showToast("✅ Trade closed. Back to Stage 0.", "success");
    goToStage(0);
}

// =============================================================================
// STAGE 4 — Top Opportunities
// =============================================================================

async function loadTopOpportunities() {
    const container = document.getElementById("s4-opportunities");
    if (!container) return;
    container.innerHTML = `<div class="opp-loading">🔍 Scanning market…</div>`;

    const data = await apiFetch(`/stage0/scanner?mode=${currentMode || "SWING"}`);
    if (!data || !data.Picks || !data.Picks.length) {
        container.innerHTML = `<div class="opp-loading">No opportunities found right now.</div>`;
        return;
    }

    // Show top 5, exclude the currently locked symbol
    const lockedSym = (lockedPosition?.symbol || "").toUpperCase();
    const picks = data.Picks
        .filter(p => p.Symbol !== lockedSym)
        .slice(0, 5);

    container.innerHTML = picks.map(p => {
        const sig    = (p.Signal || "").toUpperCase();
        const sigCls = sig === "BUY" || sig === "STRONG BUY"  ? "val-up"
                     : sig === "SELL"|| sig === "STRONG SELL" ? "val-down"
                     : "val-neutral";
        const confCls = confColor(p.Confidence);
        return `
        <div class="opp-card" onclick="quickSwitchSymbol('${p.Symbol}')">
          <div class="opp-sym">${p.Symbol.replace("-USD","")}</div>
          <div class="opp-sig ${sigCls}">${sig || "—"}</div>
          <div class="opp-price">${fmtPrice(p.LivePrice || p.Entry)}</div>
          <div class="opp-conf ${confCls}">${p.Confidence ? fmt(p.Confidence,0)+"%" : "—"}</div>
        </div>`;
    }).join("");
}

function quickSwitchSymbol(sym) {
    showToast(`🔍 Switching to ${sym}…`, "info");
    currentSymbol = sym;
    const inp = document.getElementById("s0-manual-input");
    if (inp) inp.value = sym;
    loadStage1(sym, currentMode || "SWING");
}

// =============================================================================
// STAGE 5 — Accuracy Dashboard
// =============================================================================

let _accLoading = false;

async function loadAccuracyDashboard() {
    if (_accLoading) return;
    _accLoading = true;

    try {
        const [stats, modes, trend] = await Promise.all([
            apiFetch("/dashboard_stats"),
            apiFetch("/mode_accuracy"),
            apiFetch("/accuracy_trend?limit=20"),
        ]);

        if (stats) populateAccuracyStats(stats);
        if (modes) populateAccuracyModes(modes);
        if (trend) populateAccuracyTrend(trend);
    } finally {
        _accLoading = false;
    }
}

function populateAccuracyStats(s) {
    const acc  = parseFloat(s.Accuracy) || 0;
    const wins = s.Wins   || 0;
    const loss = s.Losses || 0;
    const open = s.Open   || 0;
    const total = s.Total || 0;
    const closed = wins + loss;

    set("acc-pct",    acc > 0 ? `${fmt(acc,1)}%` : "N/A",
        acc >= 60 ? "val-up" : acc >= 40 ? "val-neutral" : "val-down");
    set("acc-total",  total);
    set("acc-wins",   wins,  "val-up");
    set("acc-losses", loss,  "val-down");
    set("acc-closed-sub", closed > 0 ? `${closed} closed trades` : "No closed trades yet");
    set("acc-open-sub",   open > 0   ? `${open} open trades`     : "No open trades");

    // Win/Loss bar
    const winBar  = document.getElementById("acc-bar-win");
    const lossBar = document.getElementById("acc-bar-loss");
    const winLbl  = document.getElementById("acc-bar-lbl-win");
    const lossLbl = document.getElementById("acc-bar-lbl-loss");
    if (winBar && lossBar && closed > 0) {
        const winPct  = (wins / closed) * 100;
        const lossPct = (loss / closed) * 100;
        winBar.style.width  = winPct  + "%";
        lossBar.style.width = lossPct + "%";
        if (winLbl)  winLbl.textContent  = `WIN ${wins}`;
        if (lossLbl) lossLbl.textContent = `LOSS ${loss}`;
    }
}

function populateAccuracyModes(modes) {
    const modeMap = {
        "INTRADAY": { valId: "acc-mode-intraday", subId: "acc-mode-intraday-sub" },
        "SWING":    { valId: "acc-mode-swing",     subId: "acc-mode-swing-sub"     },
    };
    for (const [mode, ids] of Object.entries(modeMap)) {
        const m = modes[mode];
        if (m) {
            set(ids.valId, `${fmt(m.Accuracy,1)}%`,
                m.Accuracy >= 60 ? "val-up" : m.Accuracy >= 40 ? "val-neutral" : "val-down");
            set(ids.subId, `W:${m.Wins} L:${m.Losses} (${m.Total} total)`);
        } else {
            set(ids.valId, "N/A", "val-dim");
            set(ids.subId, "No data yet");
        }
    }
}

function populateAccuracyTrend(trend) {
    const wrap = document.getElementById("acc-trend-wrap");
    const tbody = document.getElementById("acc-table-body");
    if (!wrap) return;

    const timeline = trend.Timeline || [];
    if (!timeline.length) {
        wrap.innerHTML = `<div class="acc-trend-empty">No resolved trades yet. Track predictions to build history.</div>`;
        if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="acc-empty">No predictions tracked yet.</td></tr>`;
        return;
    }

    // Sparkline-style trend dots
    const dots = timeline.map(t => {
        const cls = t.Status === "WIN" ? "trend-dot win" : "trend-dot loss";
        return `<div class="${cls}" title="${t.Stock} — ${t.Status} (${fmt(t.RunningAccuracy,1)}%)"></div>`;
    }).join("");

    const finalAcc = trend.FinalAccuracy || 0;
    wrap.innerHTML = `
      <div class="trend-dots">${dots}</div>
      <div class="trend-summary">
        Running accuracy over last ${timeline.length} trades:
        <span class="${finalAcc >= 60 ? 'val-up' : finalAcc >= 40 ? 'val-neutral' : 'val-down'}">
          ${fmt(finalAcc,1)}%
        </span>
      </div>`;

    // Table rows — most recent first
    if (tbody) {
        const rows = [...timeline].reverse().map(t => {
            const statusCls = t.Status === "WIN" ? "acc-win" : "acc-loss";
            const date = t.ResolvedAt ? t.ResolvedAt.substring(0,10) : "—";
            return `<tr>
              <td>${t.Stock}</td>
              <td>${t.Mode || "—"}</td>
              <td class="${statusCls}">${t.Status}</td>
              <td>${fmt(t.RunningAccuracy,1)}%</td>
              <td>${date}</td>
            </tr>`;
        }).join("");
        tbody.innerHTML = rows;
    }
}

// Internal nav that skips the "symbol required" guard (used after analysis completes)
function _goToStageForce(n) {
    for (let i = 0; i <= 5; i++) {
        const p = document.getElementById(`panel-${i}`);
        if (p) p.classList.add("hidden");
        const s = document.getElementById(`pipe-${i}`);
        if (s) s.classList.remove("active", "done");
    }
    const panel = document.getElementById(`panel-${n}`);
    if (panel) panel.classList.remove("hidden");
    for (let i = 0; i < n; i++) {
        const s = document.getElementById(`pipe-${i}`);
        if (s) s.classList.add("done");
    }
    const cur = document.getElementById(`pipe-${n}`);
    if (cur) cur.classList.add("active");
    const badge = document.getElementById("header-stage-badge");
    if (badge) badge.textContent = STAGE_LABELS[n] || `STAGE ${n}`;
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (n === 4 && lockedPosition) refreshProtection();
    if (n === 5) loadAccuracyDashboard();
}

// =============================================================================
// Bootstrap
// =============================================================================
document.addEventListener("DOMContentLoaded", () => {
    initSearch();        // attach full search dropdown to the manual input
    initPopularChips();  // render popular coin chips in Stage 0
    _goToStageForce(0);
});
