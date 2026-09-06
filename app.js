const STORAGE_KEY = "keiba-note-records-v1";
let records = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");

const $ = (id) => document.getElementById(id);
const modal = $("modal");
const form = $("recordForm");

function yen(value) {
  return "¥" + Number(value).toLocaleString("ja-JP");
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
}

function render() {
  const investment = records.reduce((s, r) => s + r.investment, 0);
  const returns = records.reduce((s, r) => s + r.returnAmount, 0);
  const profit = returns - investment;
  const hits = records.filter(r => r.returnAmount > 0).length;
  const recovery = investment ? (returns / investment) * 100 : 0;
  const hitRate = records.length ? (hits / records.length) * 100 : 0;

  $("totalProfit").textContent = (profit >= 0 ? "+" : "") + yen(profit);
  $("totalProfit").className = profit >= 0 ? "positive" : "negative";
  $("totalInvestment").textContent = "投資 " + yen(investment);
  $("recoveryRate").textContent = recovery.toFixed(1) + "%";
  $("hitRate").textContent = hitRate.toFixed(1) + "%";
  $("raceCount").textContent = records.length;

  $("emptyState").style.display = records.length ? "none" : "block";
  const list = $("records");
  list.innerHTML = "";

  [...records].sort((a,b) => b.date.localeCompare(a.date)).forEach(r => {
    const p = r.returnAmount - r.investment;
    const el = document.createElement("div");
    el.className = "record";
    el.innerHTML = `
      <div class="record-date">${r.date}</div>
      <div>
        <div class="record-title">${r.course}${r.race}R　${r.betType}</div>
        <div class="record-detail">${escapeHtml(r.memo || "メモなし")}　/　投資 ${yen(r.investment)} → 払戻 ${yen(r.returnAmount)}</div>
      </div>
      <div class="record-profit ${p >= 0 ? "positive" : "negative"}">${p >= 0 ? "+" : ""}${yen(p)}</div>
    `;
    list.appendChild(el);
  });
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

function openModal() {
  $("date").value = new Date().toISOString().slice(0,10);
  modal.classList.remove("hidden");
  $("course").focus();
}
function closeModal() {
  modal.classList.add("hidden");
  form.reset();
}

$("addButton").addEventListener("click", openModal);
$("closeButton").addEventListener("click", closeModal);
document.querySelector(".modal-backdrop").addEventListener("click", closeModal);

form.addEventListener("submit", e => {
  e.preventDefault();
  records.push({
    id: Date.now(),
    date: $("date").value,
    course: $("course").value,
    race: Number($("race").value),
    betType: $("betType").value,
    investment: Number($("investment").value),
    returnAmount: Number($("returnAmount").value),
    memo: $("memo").value.trim()
  });
  save();
  render();
  closeModal();
});

$("clearButton").addEventListener("click", () => {
  if (!records.length) return;
  if (confirm("すべての収支データを削除します。よろしいですか？")) {
    records = [];
    save();
    render();
  }
});

render();
