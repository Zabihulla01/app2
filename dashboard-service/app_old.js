const API_URL = "http://100.53.40.154:8008";

let currentStock = "AAPL";

async function loadDashboard(stock = currentStock){

    currentStock = stock;

const rankRes = await fetch(`${API_URL}/rank/${stock}`);
const rankData = await rankRes.json();

const rankingBody =
    document.querySelector("#ranking-table tbody");

rankingBody.innerHTML = "";

rankData.Ranking.forEach(item => {

    rankingBody.innerHTML += `
    <tr>
        <td>${item[0]}</td>
        <td>${item[1]}</td>
    </tr>
    `;

});

const strategyLabels =
    rankData.Ranking.map(item => item[0]);

const strategyValues =
    rankData.Ranking.map(item => item[1]);

document.getElementById("best-strategy").innerText =
    rankData.Best;

const ctx = document.getElementById("equityChart");

const backtestRes =
    await fetch(`${API_URL}/backtest/${stock}`);

const backtestData =
    await backtestRes.json();
const scanRes =
    await fetch(`${API_URL}/scanner`);

const scanData =
    await scanRes.json();

document.getElementById("scanner-results").innerHTML =
    scanData.TopStocks
    .map(
        s => `
        <div style="margin:6px 0">
            <b>${s.Stock}</b>
            <span style="color:lime">
                ${s.Confidence}%
            </span>
        </div>
        `
    )
    .join("");

document.getElementById("winrate").innerText =
    backtestData.WinRate + "%";

document.getElementById("pf").innerText =
    backtestData.ProfitFactor;

document.getElementById("sharpe").innerText =
    backtestData.Sharpe;

document.getElementById("riskscore").innerText =
    backtestData.RiskScore;

document.getElementById("trades").innerText =
    backtestData.Trades;

document.getElementById("drawdown").innerText =
    backtestData.MaxDrawdown + "%";
document.getElementById("stoploss").innerText =
    "$" + backtestData.StopLoss;

document.getElementById("target").innerText =
    "$" + backtestData.Target;
document.getElementById("stoploss").style.color =
    "red";

document.getElementById("target").style.color =
    "lime";
document.getElementById("entryprice").innerText =
    "$" + backtestData.EntryPrice;

document.getElementById("riskreward").innerText =
    "1 : " + backtestData.RiskReward;
document.getElementById("confidence").innerText =
    backtestData.Confidence + "%";
const conf = backtestData.Confidence;

if(conf >= 80){
    document.getElementById("confidence").style.color = "lime";
}
else if(conf >= 60){
    document.getElementById("confidence").style.color = "yellow";
}
else{
    document.getElementById("confidence").style.color = "red";
}

document.getElementById("finalcapital").innerText =
    "$" + backtestData.FinalCapital;

document.getElementById("benchmark").innerText =
    backtestData.BenchmarkReturn + "%";

document.getElementById("netprofit").innerText =
    "$" + backtestData.NetProfit;

document.getElementById("lossstreak").innerText =
    backtestData.MaxLossStreak;

let signal = "WAIT";

if(backtestData.RiskScore >= 85){

    signal = "STRONG BUY";

}
else if(backtestData.RiskScore >= 70){

    signal = "BUY";

}
else if(backtestData.RiskScore >= 50){

    signal = "HOLD";

}
else{

    signal = "AVOID";

}

const rec =
    document.getElementById("recommendation");

rec.innerText = signal;

if(signal === "STRONG BUY"){

    rec.style.color = "lime";

}
else if(signal === "BUY"){

    rec.style.color = "green";

}
else if(signal === "HOLD"){

    rec.style.color = "orange";

}
else{

    rec.style.color = "red";

}

const strategyCtx =
    document.getElementById("strategyChart");

if(
    window.strategyChart &&
    typeof window.strategyChart.destroy === "function"
){
    window.strategyChart.destroy();
}

window.strategyChart = new Chart(strategyCtx, {

    type: "bar",

    data: {

        labels: strategyLabels,

        datasets: [{

            label: "Profit Factor",

            data: strategyValues

        }]

    }

});

if(window.myChart){
    window.myChart.destroy();
}


window.myChart = new Chart(ctx, {

    type: "line",

    data: {

        labels: backtestData.Dates,

        datasets: [{

            label: "Equity",

            data: backtestData.EquityCurve,

            borderColor: "#00d4ff",

            tension: 0.4

        }]

    }

});

}



loadDashboard();

function showNotification(message){

const box =
    document.getElementById("notification");

box.innerText = message;

box.style.display = "block";

setTimeout(() => {

    box.style.display = "none";

}, 3000);


}



setInterval(loadDashboard, 30000);
function analyzeStock(){

    const stock =
        document.getElementById("stockSelect")
        .value
        .trim();

    if(!stock){

        alert("Enter Stock");

        return;
    }

    loadDashboard(stock);

}
