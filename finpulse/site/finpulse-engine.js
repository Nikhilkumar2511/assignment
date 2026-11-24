/* FINPULSE AI engine for the browser and Node.
 *
 * A direct port of finpulse_engine/student.py, business.py, warning_model.py and the template
 * part of explain.py. tests/test_js_parity.py runs both versions on the same inputs and fails
 * if they disagree, so change the Python and this file together.
 *
 * Nothing here talks to a server. Every figure is computed in the visitor's own browser.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.FinPulse = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MODEL = {"version": "0.1-synthetic", "features": ["spent_share", "time_share", "need_ratio_tagged", "need_ratio_recent", "fixed_share", "largest_spend_share"], "mean": [0.5201167217403352, 0.4080892926698372, 1.1618273872726546, 1.4520581984247163, 0.18954033881830712, 0.0982488112110599], "std": [0.1797311914790245, 0.15170977411340847, 1.1951408352112924, 1.3081533807596482, 0.04032764977574349, 0.07722147887511586], "weights": [2.8330467084122413, -1.890153518061813, 0.867968005912925, 0.07481832510415226, -0.2757120638391371, -0.892304339016022], "bias": -1.0461340810309052, "threshold": 0.32, "trained_on": "113,813 synthetic student-months, seed 101", "label": "balance under 5% of the allowance on or before five days from month end"};
  const SAMPLES = {"student": {"allowance": 10000, "today": 18, "month_days": 30, "savings_goal": 500, "transactions": [{"day": 1, "amount": 700, "category": "Travel", "fixed": true}, {"day": 1, "amount": 180, "category": "Food beyond the mess"}, {"day": 2, "amount": 650, "category": "Phone and subscriptions", "fixed": true}, {"day": 2, "amount": 150, "category": "Food beyond the mess"}, {"day": 3, "amount": 400, "category": "Study material", "fixed": true}, {"day": 3, "amount": 220, "category": "Food beyond the mess"}, {"day": 4, "amount": 160, "category": "Food beyond the mess"}, {"day": 5, "amount": 120, "category": "Other"}, {"day": 6, "amount": 240, "category": "Food beyond the mess"}, {"day": 6, "amount": 450, "category": "Outings"}, {"day": 7, "amount": 260, "category": "Food beyond the mess"}, {"day": 7, "amount": 500, "category": "Outings"}, {"day": 8, "amount": 140, "category": "Food beyond the mess"}, {"day": 9, "amount": 170, "category": "Food beyond the mess"}, {"day": 9, "amount": 900, "category": "Shopping"}, {"day": 10, "amount": 200, "category": "Food beyond the mess"}, {"day": 11, "amount": 150, "category": "Food beyond the mess"}, {"day": 12, "amount": 180, "category": "Other"}, {"day": 13, "amount": 230, "category": "Food beyond the mess"}, {"day": 13, "amount": 400, "category": "Outings"}, {"day": 14, "amount": 250, "category": "Food beyond the mess"}, {"day": 14, "amount": 550, "category": "Outings"}, {"day": 15, "amount": 160, "category": "Food beyond the mess"}, {"day": 16, "amount": 180, "category": "Food beyond the mess"}, {"day": 16, "amount": 600, "category": "Shopping"}, {"day": 17, "amount": 210, "category": "Food beyond the mess"}, {"day": 18, "amount": 300, "category": "Food beyond the mess"}]}, "business": {"period_months": 1, "revenue": 1200000, "cogs": 720000, "operating_expenses": 330000, "depreciation": 20000, "interest": 30000, "tax": 0, "cash": 90000, "receivables": 2600000, "inventory": 900000, "payables": 800000, "short_term_debt": 600000, "long_term_debt": 1200000, "equity": 1500000, "prior": {"revenue": 1000000, "cogs": 560000, "operating_expenses": 290000, "depreciation": 20000, "interest": 30000, "tax": 0}}, "invest": {"discount_rate": 0.12, "cash": 900000, "reserve": 300000, "options": [{"name": "Second packing line", "initial_cost": 500000, "cash_flows": [180000, 200000, 220000, 220000]}, {"name": "New delivery van", "initial_cost": 400000, "cash_flows": [110000, 120000, 120000, 120000]}, {"name": "Warehouse extension", "initial_cost": 800000, "cash_flows": [260000, 300000, 320000, 320000]}]}};

  class InputError extends Error {}
  const isNum = v => typeof v === "number" && isFinite(v);
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k) && o[k] !== null && o[k] !== undefined;

  /* Python's round(): correctly rounded on the exact value, ties to the even digit. */
  function pyRound(x, n) {
    n = n || 0;
    if (!isFinite(x)) return x;
    const a = Math.abs(x);
    const exact = a.toFixed(Math.min(n + 30, 100));
    const dot = exact.indexOf(".");
    const frac = exact.slice(dot + 1);
    let out = Number(a.toFixed(n));                       // half-up on the exact value
    if (/^50*$/.test(frac.slice(n))) {                    // an exact tie: go to the even digit
      const last = n ? Number(frac[n - 1]) : Number(exact[dot - 1]);
      if (last % 2 === 0) out = Number(exact.slice(0, dot) + (n ? "." + frac.slice(0, n) : ""));
    }
    return x < 0 ? -out : out;
  }
  const fix = (x, n) => pyRound(x, n).toFixed(n);
  function inr(x) {
    const n = pyRound(x, 0);
    return (n < 0 ? "-" : "") + Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }
  const round50 = x => pyRound(x / 50, 0) * 50;
  const sum = a => a.reduce((s, v) => s + v, 0);

  /* ------------------------------------------------------------------ early-warning model */
  const FLOOR_SHARE = 0.05, HORIZON_GAP = 5;
  function features(flexible, fixed, day, allowance, monthDays) {
    const spentFlex = sum(flexible.slice(0, day)), spentFixed = sum(fixed.slice(0, day));
    const balance = allowance - spentFlex - spentFixed;
    const room = balance - FLOOR_SHARE * allowance;
    const togo = Math.max(monthDays - HORIZON_GAP - day, 0);
    const w = Math.min(7, day);
    let recent = 0;
    for (let i = day - w; i < day; i++) recent += flexible[i] + fixed[i];
    recent /= w;
    const safeRoom = Math.max(room, 1e-9 * allowance + 1e-9);
    const clip = v => Math.min(Math.max(v, 0), 5);
    return [(spentFlex + spentFixed) / allowance, day / monthDays, clip(spentFlex / day * togo / safeRoom),
            clip(recent * togo / safeRoom), spentFixed / allowance, Math.max.apply(null, flexible.slice(0, day)) / allowance];
  }
  function predict(x) {
    let z = MODEL.bias;
    for (let i = 0; i < x.length; i++) z += (x[i] - MODEL.mean[i]) / MODEL.std[i] * MODEL.weights[i];
    return 1 / (1 + Math.exp(-Math.min(Math.max(z, -30), 30)));
  }

  /* ------------------------------------------------------------------ student module */
  const ESSENTIAL = ["food", "mess", "grocer", "meal", "travel", "transport", "bus", "study", "book",
                     "health", "medic", "rent", "phone", "recharge", "data", "fee"];
  const isEssential = name => ESSENTIAL.some(w => name.toLowerCase().includes(w));

  function diagnoseStudent(p) {
    const allowance = p.allowance, monthDays = Math.trunc(has(p, "month_days") ? p.month_days : 30), today = p.today;
    if (!isNum(allowance) || allowance <= 0) throw new InputError("allowance must be a number above zero");
    if (!(monthDays >= 28 && monthDays <= 31)) throw new InputError("month_days must be between 28 and 31");
    if (!Number.isInteger(today) || today < 1 || today > monthDays)
      throw new InputError(`today must be a whole day between 1 and ${monthDays}`);

    const flexible = new Array(monthDays).fill(0), fixed = new Array(monthDays).fill(0);
    const byCat = new Map();
    const cat = name => { if (!byCat.has(name)) byCat.set(name, { amount: 0, fixed_amount: 0 }); return byCat.get(name); };
    const quality = [];
    (p.transactions || []).forEach((t, idx) => {
      const i = idx + 1, day = t.day, amount = t.amount;
      if (!Number.isInteger(day) || !isNum(amount)) throw new InputError(`transaction ${i}: day and amount are required numbers`);
      if (amount < 0) throw new InputError(`transaction ${i}: amount cannot be negative`);
      if (day < 1 || day > today) throw new InputError(`transaction ${i}: day ${day} is outside 1 to ${today} (no future spending)`);
      const category = String(t.category || "").trim() || "Uncategorised";
      const isFixed = Boolean(t.fixed);
      (isFixed ? fixed : flexible)[day - 1] += amount;
      const c = cat(category);
      c.amount += amount;
      if (isFixed) c.fixed_amount += amount;
    });
    let upcoming = 0;
    (p.upcoming_fixed || []).forEach((u, idx) => {
      if (!isNum(u.amount) || u.amount < 0) throw new InputError(`upcoming_fixed ${idx + 1}: amount must be zero or more`);
      upcoming += u.amount;
      const c = cat(String(u.category || "").trim() || "Upcoming bills");
      c.upcoming = (c.upcoming || 0) + u.amount;
    });

    const spentFlex = sum(flexible), spentFixed = sum(fixed);
    const spent = spentFlex + spentFixed;
    const balance = allowance - spent;
    const daysLeft = monthDays - today;
    const floor = FLOOR_SHARE * allowance;
    const result = {
      mode: "student",
      summary: { allowance, today, month_days: monthDays, spent: pyRound(spent, 2), balance: pyRound(balance, 2),
                 days_left: daysLeft, spent_share: pyRound(spent / allowance, 4), time_share: pyRound(today / monthDays, 4) },
      data_quality: quality, findings: [],
    };
    if (spent === 0) {
      result.health = { score: null, status: "Insufficient evidence" };
      result.findings.push({
        priority: "Insufficient evidence", title: "No spending recorded yet", evidence: { transactions: 0 },
        rationale: "A diagnosis needs at least a few days of recorded spending.",
        next_step: "Record each spend with a day, an amount and a category, then run the diagnosis again." });
      return result;
    }
    if (balance < 0) quality.push("Recorded spending is higher than the allowance. Check for a duplicate or a mistyped amount.");

    const pace = spent / today, paceFlex = spentFlex / today;
    const w = Math.min(7, today);
    let recent = 0;
    for (let i = today - w; i < today; i++) recent += flexible[i] + fixed[i];
    const paceRecent = recent / w;
    const lasts = pace === 0 || balance / pace >= daysLeft;
    let runOut = (lasts || balance <= 0) ? null : today + Math.floor(balance / pace) + 1;
    if (balance <= 0) runOut = today;
    const available = balance - upcoming;
    const safe = daysLeft > 0 ? available / daysLeft : available;
    const shortfall = Math.max(0, pace * daysLeft + upcoming - balance);
    result.pace = { per_day: pyRound(pace, 2), per_day_excluding_fixed: pyRound(paceFlex, 2), last_7_days_per_day: pyRound(paceRecent, 2) };
    result.run_out = { day: runOut, safe_to_spend_per_day: pyRound(Math.max(safe, 0), 2),
                       shortfall_at_current_pace: pyRound(shortfall, 2), upcoming_fixed: pyRound(upcoming, 2) };

    const horizon = monthDays - HORIZON_GAP;
    let prob, basis;
    if (balance < floor) { prob = 1.0; basis = "fact: the balance is already under 5% of the allowance"; }
    else if (today >= horizon) { prob = 0.0; basis = "fact: the warning window has passed with the balance above the floor"; }
    else { prob = predict(features(flexible, fixed, today, allowance, monthDays)); basis = `model ${MODEL.version}`; }
    const ruleC = balance >= floor && today < horizon && paceFlex * (horizon - today) > balance - floor;
    const flag = prob >= MODEL.threshold;
    result.warning = { probability: pyRound(prob, 3), flag, threshold: MODEL.threshold, simple_rule_flag: ruleC, basis,
                       meaning: `Chance that the balance falls under ${inr(floor)} on or before day ${horizon}.` };
    const score = pyRound(100 * (1 - prob), 0);
    result.health = { score, status: score >= 70 ? "On track" : score >= 40 ? "Watch" : "At risk" };

    const cats = [];
    byCat.forEach((v, name) => {
      if (v.amount === 0) return;
      cats.push({ category: name, amount: pyRound(v.amount, 2), share: pyRound(v.amount / spent, 4),
                  fixed: v.fixed_amount === v.amount, essential: isEssential(name) });
    });
    cats.sort((a, b) => b.amount - a.amount);
    result.categories = cats;
    const flexCats = cats.filter(c => !c.fixed);

    const f = result.findings;
    const urgent = flag || runOut !== null;
    if (urgent) {
      const when = runOut ? `on day ${runOut}` : `before day ${horizon}`;
      f.push({ priority: "Urgent action", title: `Money is on course to run out ${when}`,
               evidence: { balance: pyRound(balance, 2), pace_per_day: pyRound(pace, 2), days_left: daysLeft, warning_probability: pyRound(prob, 3) },
               rationale: `At ${inr(pace)} a day the balance of ${inr(balance)} does not cover the ${daysLeft} days left.`,
               next_step: `Hold spending to ${inr(Math.floor(Math.max(safe, 0)))} a day for the rest of the month.` });
    }
    if (flexCats.length >= 1) {
      const top = flexCats.slice(0, 2);
      const totalTop = sum(top.map(c => c.amount));
      const evidence = {};
      top.forEach(c => { evidence[c.category] = c.amount; });
      f.push({ priority: urgent ? "Investigate and improve" : "Monitor",
               title: `${top.map(c => c.category).join(" and ")} take ${fix(100 * totalTop / spent, 0)}% of spending`,
               evidence, rationale: "These are the largest flexible categories, so a cut here moves the result most.",
               next_step: "Set a weekly limit for each and check it every Sunday." });
    }
    const loose = sum(cats.filter(c => ["uncategorised", "other", "misc", "miscellaneous"].includes(c.category.toLowerCase())).map(c => c.amount));
    if (loose / spent > 0.15)
      f.push({ priority: "Investigate and improve", title: `${fix(100 * loose / spent, 0)}% of spending has no clear category`,
               evidence: { uncategorised_amount: pyRound(loose, 2) },
               rationale: "Money you cannot name is money you cannot plan.", next_step: "Tag each spend when you make it." });
    if (!flag && runOut === null) {
      const projectedEnd = balance - pace * daysLeft - upcoming;
      f.push({ priority: "Monitor", title: "Spending is on pace to last the month",
               evidence: { projected_month_end_balance: pyRound(projectedEnd, 2) },
               rationale: `At ${inr(pace)} a day about ${inr(Math.max(projectedEnd, 0))} remains at month end.`,
               next_step: "Move part of the expected surplus to savings on the day the next allowance arrives." });
    }
    result.next_month_budget = budget(p, allowance, monthDays, today, cats, byCat, f);
    return result;
  }

  function budget(p, allowance, monthDays, today, cats, byCat, findings) {
    const fixedLines = cats.filter(c => c.fixed).map(c => ({ line: c.category, amount: c.amount + (byCat.get(c.category).upcoming || 0) }));
    byCat.forEach((v, name) => { if (v.amount === 0 && v.upcoming) fixedLines.push({ line: name, amount: v.upcoming }); });
    const fixedTotal = sum(fixedLines.map(l => l.amount));
    let savings = has(p, "savings_goal") ? p.savings_goal : 0.05 * allowance;
    let buffer = (has(p, "buffer_share") ? p.buffer_share : 0.10) * allowance;
    if (fixedTotal + savings + buffer > allowance) {
      const over = fixedTotal + savings + buffer - allowance;
      const cutS = Math.min(savings, over);
      savings -= cutS;
      buffer = Math.max(0, buffer - (over - cutS));
      findings.push({ priority: "Investigate and improve", title: "Fixed bills leave little room for savings",
                      evidence: { fixed_bills: pyRound(fixedTotal, 2), allowance },
                      rationale: "Fixed bills, the buffer and the savings goal together exceed the allowance.",
                      next_step: "Review recurring bills and subscriptions first." });
    }
    const pool = Math.max(0, allowance - fixedTotal - savings - buffer);
    const flex = cats.filter(c => !c.fixed);
    const projected = {}, alloc = {}, weight = {};
    flex.forEach(c => { projected[c.category] = c.amount / today * monthDays; alloc[c.category] = projected[c.category]; });
    const need = sum(flex.map(c => projected[c.category])) - pool;
    if (need > 0) {
      flex.forEach(c => { weight[c.category] = (c.essential ? 0.5 : 1.0) * projected[c.category]; });
      let remaining = need, active = flex.map(c => c.category);
      while (remaining > 1e-6 && active.length) {
        const totalW = sum(active.map(k => weight[k]));
        let spill = 0;
        const still = [];
        active.forEach(k => {
          const cut = remaining * weight[k] / totalW;
          if (cut >= alloc[k]) { spill += cut - alloc[k]; alloc[k] = 0; }
          else { alloc[k] -= cut; still.push(k); }
        });
        active = still;
        remaining = spill;
      }
    }
    const lines = fixedLines.map(l => ({ line: l.line, amount: round50(l.amount), type: "fixed" }));
    flex.forEach(c => lines.push({ line: c.category, amount: round50(alloc[c.category]), type: "flexible",
                                   change_vs_current_pace: round50(alloc[c.category] - projected[c.category]) }));
    lines.push({ line: "Emergency buffer", amount: round50(buffer), type: "buffer" });
    lines.push({ line: "Savings", amount: round50(savings + (need > 0 ? 0 : -need)), type: "savings" });
    const drift = allowance - sum(lines.map(l => l.amount));
    const target = lines.slice().sort((a, b) => b.amount - a.amount).find(l => l.type === "flexible") || lines[lines.length - 1];
    target.amount += drift;
    const flexibleTotal = sum(lines.filter(l => l.type === "flexible").map(l => l.amount));
    return { lines, total: sum(lines.map(l => l.amount)),
             flexible_per_day: pyRound(flexibleTotal / monthDays, 2), flexible_per_week: pyRound(flexibleTotal / monthDays * 7, 2),
             method: "Fixed bills are kept. A buffer and savings are set aside. Flexible categories start from " +
                     "this month's pace and are cut to fit, with essential categories cut at half the rate of the rest." };
  }

  function savingsScenarios(monthly, months, rates) {
    if (!isNum(monthly) || !isNum(months) || monthly < 0 || months <= 0)
      throw new InputError("monthly saving must be zero or more and months must be above zero");
    const scenarios = (rates || [0.0, 0.06, 0.12]).map(annual => {
      const r = annual / 12;
      const value = r === 0 ? monthly * months : monthly * (Math.pow(1 + r, months) - 1) / r;
      return { annual_rate: annual, value: pyRound(value, 2) };
    });
    return { paid_in: pyRound(monthly * months, 2), scenarios,
             note: "Hypothetical rates with end-of-month deposits. Not a forecast and not investment advice." };
  }

  /* ------------------------------------------------------------------ business module */
  const DEFAULT_THRESHOLDS = {
    gross_margin: [0.10, 0.40], operating_margin: [0.00, 0.20], net_margin: [0.00, 0.10],
    current_ratio: [1.0, 2.0], quick_ratio: [0.5, 1.0], cash_cover_months: [1.0, 3.0],
    debt_to_equity: [2.0, 0.5], interest_coverage: [1.5, 5.0],
    receivable_days: [90, 30], inventory_days: [120, 45], cash_conversion_cycle: [90, 30],
  };
  const AREAS = [
    ["Profitability", 0.30, ["gross_margin", "operating_margin", "net_margin"]],
    ["Liquidity", 0.30, ["current_ratio", "quick_ratio", "cash_cover_months"]],
    ["Solvency", 0.20, ["debt_to_equity", "interest_coverage"]],
    ["Efficiency", 0.20, ["receivable_days", "inventory_days", "cash_conversion_cycle"]],
  ];
  const NUMERIC_FIELDS = ["revenue", "cogs", "operating_expenses", "depreciation", "interest", "tax", "total_costs",
    "net_profit", "cash", "receivables", "inventory", "other_current_assets", "payables",
    "short_term_debt", "other_current_liabilities", "long_term_debt", "equity"];
  const MAY_BE_NEGATIVE = ["net_profit", "equity"];
  const OTHER_FIELDS = ["period_months", "prior", "thresholds", "currency", "name"];
  const UNITS = { gross_margin: "share", operating_margin: "share", net_margin: "share", current_ratio: "times",
    quick_ratio: "times", cash_cover_months: "months", debt_to_equity: "times", interest_coverage: "times",
    receivable_days: "days", inventory_days: "days", payable_days: "days", cash_conversion_cycle: "days", working_capital: "currency" };
  const scoreOf = (v, poor, good) => good === poor ? 50 : Math.max(0, Math.min(100, 100 * (v - poor) / (good - poor)));

  function clean(data, quality, label) {
    const out = {};
    NUMERIC_FIELDS.forEach(key => {
      const v = data[key];
      if (v === null || v === undefined) return;
      if (typeof v !== "number" || !isFinite(v)) throw new InputError(`${label}${key} must be a number`);
      if (v < 0 && !MAY_BE_NEGATIVE.includes(key)) throw new InputError(`${label}${key} cannot be negative`);
      out[key] = v;
    });
    const unknown = Object.keys(data).filter(k => !NUMERIC_FIELDS.includes(k) && !OTHER_FIELDS.includes(k)).sort();
    if (unknown.length) quality.push(`Ignored unknown fields: ${unknown.join(", ")}.`);
    return out;
  }

  function metricsOf(d, periodDays, assumptions) {
    const m = {};
    const rev = d.revenue;
    const hasAll = (...keys) => keys.every(k => k in d);
    const opt = key => {
      if (!(key in d)) { assumptions.push(`${key} was not provided and is treated as zero.`); return 0; }
      return d[key];
    };
    const or0 = key => (key in d ? d[key] : 0);
    let ebit = null;
    if (rev && hasAll("cogs")) m.gross_margin = (rev - d.cogs) / rev;
    if (rev && hasAll("cogs", "operating_expenses")) {
      const ebitda = rev - d.cogs - d.operating_expenses;
      m.operating_margin = ebitda / rev;
      ebit = ebitda - opt("depreciation");
    }
    let net = null;
    if ("net_profit" in d) net = d.net_profit;
    else if (rev !== undefined && "total_costs" in d) net = rev - d.total_costs;
    else if (ebit !== null) net = ebit - opt("interest") - opt("tax");
    if (rev && net !== null) { m.net_margin = net / rev; m._net_profit = net; }
    if (ebit !== null && or0("interest") > 0) { m.interest_coverage = ebit / d.interest; m._ebit = ebit; }

    if (hasAll("cash", "receivables", "payables")) {
      const ca = d.cash + d.receivables + or0("inventory") + or0("other_current_assets");
      const cl = d.payables + or0("short_term_debt") + or0("other_current_liabilities");
      ["inventory", "short_term_debt"].forEach(k => {
        if (!(k in d)) assumptions.push(`${k} was not provided and is treated as zero in the liquidity ratios.`);
      });
      m.working_capital = ca - cl;
      if (cl > 0) { m.current_ratio = ca / cl; m.quick_ratio = (d.cash + d.receivables) / cl; }
    }
    let monthlyCost = null;
    if (hasAll("cogs", "operating_expenses")) monthlyCost = (d.cogs + d.operating_expenses + or0("interest")) / (periodDays / 30);
    else if ("total_costs" in d) monthlyCost = d.total_costs / (periodDays / 30);
    if ("cash" in d && monthlyCost) m.cash_cover_months = d.cash / monthlyCost;

    if (hasAll("equity") && ("long_term_debt" in d || "short_term_debt" in d) && d.equity > 0)
      m.debt_to_equity = (or0("long_term_debt") + or0("short_term_debt")) / d.equity;

    if (rev && "receivables" in d) m.receivable_days = d.receivables / rev * periodDays;
    if (d.cogs && "inventory" in d) m.inventory_days = d.inventory / d.cogs * periodDays;
    if (d.cogs && "payables" in d) m.payable_days = d.payables / d.cogs * periodDays;
    if ("receivable_days" in m && "inventory_days" in m && "payable_days" in m)
      m.cash_conversion_cycle = m.receivable_days + m.inventory_days - m.payable_days;
    return m;
  }

  function diagnoseBusiness(p) {
    const quality = [], assumptions = [];
    const periodMonths = has(p, "period_months") ? p.period_months : 1;
    if (!isNum(periodMonths) || periodMonths <= 0) throw new InputError("period_months must be above zero");
    const periodDays = 30 * periodMonths;
    const d = clean(p, quality, "");
    if (!("revenue" in d)) throw new InputError("revenue is required");
    const thresholds = Object.assign({}, DEFAULT_THRESHOLDS);
    Object.entries(p.thresholds || {}).forEach(([k, v]) => {
      if (!(k in thresholds) || !Array.isArray(v) || v.length !== 2)
        throw new InputError(`thresholds.${k} must be a known metric with [poor, good]`);
      thresholds[k] = [Number(v[0]), Number(v[1])];
    });

    const m = metricsOf(d, periodDays, assumptions);
    const netProfit = "_net_profit" in m ? m._net_profit : null, ebit = "_ebit" in m ? m._ebit : null;
    delete m._net_profit; delete m._ebit;

    const metricsOut = [], areasOut = [], scores = {};
    let weighted = 0, weightSum = 0;
    Object.entries(m).forEach(([name, value]) => {
      const entry = { metric: name, value: pyRound(value, 4), unit: UNITS[name] || "" };
      if (name in thresholds) {
        const [poor, good] = thresholds[name];
        const s = scoreOf(value, poor, good);
        scores[name] = s;
        Object.assign(entry, { score: pyRound(s, 1), band: s >= 70 ? "good" : s >= 40 ? "watch" : "poor", poor_at: poor, good_at: good });
      }
      metricsOut.push(entry);
    });
    const missingByArea = {};
    AREAS.forEach(([area, weight, names]) => {
      const have = names.filter(n => n in scores).map(n => scores[n]);
      const missing = names.filter(n => !(n in scores));
      if (missing.length) missingByArea[area] = missing;
      if (have.length) {
        const a = sum(have) / have.length;
        areasOut.push({ area, score: pyRound(a, 1), metrics_used: have.length, metrics_missing: missing });
        weighted += weight * a; weightSum += weight;
      } else areasOut.push({ area, score: null, metrics_used: 0, metrics_missing: missing });
    });
    const enough = areasOut.filter(a => a.score !== null).length >= 2;
    const overall = enough ? pyRound(weighted / weightSum, 1) : null;
    const status = overall === null ? "Insufficient evidence" : overall >= 70 ? "Healthy" : overall >= 45 ? "Watch" : "At risk";

    const f = [];
    const g = k => (k in m ? m[k] : null);
    const margin = g("net_margin"), cover = g("cash_cover_months"), quick = g("quick_ratio"), current = g("current_ratio");
    const cashPoor = (cover !== null && cover < 1) || (quick !== null && quick < 0.5) || (current !== null && current < 1);
    const pick = (keys, digits) => { const ev = {}; keys.forEach(k => { if (g(k) !== null) ev[k] = pyRound(g(k), digits); }); return ev; };
    if (margin !== null && margin < 0)
      f.push({ area: "Profitability", priority: "Urgent action", title: "The business is making a loss",
               evidence: { net_margin: pyRound(margin, 4), net_profit: pyRound(netProfit, 2) },
               rationale: "Costs are higher than revenue for this period.",
               next_step: "Split costs into avoidable and unavoidable, and check contribution margin by product before cutting." });
    if (margin !== null && margin > 0 && cashPoor) {
      const ev = Object.assign({ net_margin: pyRound(margin, 4) }, pick(["cash_cover_months", "quick_ratio", "current_ratio", "receivable_days"], 2));
      f.push({ area: "Liquidity", priority: "Urgent action", title: "Profitable on paper but short of cash", evidence: ev,
               rationale: "Profit is positive, yet cash on hand does not cover near-term payments. Profit is not cash.",
               next_step: "Review receivable ageing, chase the oldest invoices, and line up payment dates against cash." });
    } else if (cashPoor)
      f.push({ area: "Liquidity", priority: "Urgent action", title: "Cash does not cover near-term payments",
               evidence: pick(["cash_cover_months", "quick_ratio", "current_ratio"], 2),
               rationale: "Liquid assets are low against current liabilities or monthly costs.",
               next_step: "Build a week-by-week cash plan before committing to new spending." });

    const prior = p.prior;
    if (prior && typeof prior === "object" && !Array.isArray(prior)) {
      const pr = clean(prior, quality, "prior.");
      const pm = metricsOf(pr, periodDays, []);
      if (pr.revenue && d.revenue > pr.revenue) {
        const growth = d.revenue / pr.revenue - 1;
        for (const [key, label] of [["gross_margin", "gross margin"], ["net_margin", "net margin"]]) {
          if (key in m && key in pm && pm[key] - m[key] >= 0.02) {
            const ev = { revenue_growth: pyRound(growth, 4) };
            ev[`${key}_now`] = pyRound(m[key], 4); ev[`${key}_before`] = pyRound(pm[key], 4);
            if ("cogs" in d && pr.cogs) ev.cogs_growth = pyRound(d.cogs / pr.cogs - 1, 4);
            if ("operating_expenses" in d && pr.operating_expenses) ev.operating_expense_growth = pyRound(d.operating_expenses / pr.operating_expenses - 1, 4);
            f.push({ area: "Profitability", priority: "Investigate and improve", title: `Sales are growing but ${label} is falling`, evidence: ev,
                     rationale: `Revenue rose ${fix(100 * growth, 1)}% while ${label} fell ${fix(100 * (pm[key] - m[key]), 1)} points, so costs grew faster than sales.`,
                     next_step: "Compare cost growth with sales growth line by line, and check discounts and product mix." });
            break;
          }
        }
      }
    }
    const de = g("debt_to_equity"), cov = g("interest_coverage");
    if ((de !== null && de > 2) || (cov !== null && cov < 1.5)) {
      const ev = pick(["debt_to_equity", "interest_coverage"], 2);
      if (cov !== null && ebit !== null) ev.interest_coverage_if_ebit_falls_20pct = pyRound(0.8 * ebit / d.interest, 2);
      f.push({ area: "Solvency", priority: cov !== null && cov < 1.5 ? "Urgent action" : "Investigate and improve",
               title: "Debt is putting pressure on the business", evidence: ev,
               rationale: "Borrowing is high against equity, or earnings cover interest only narrowly.",
               next_step: "Map repayment dates against expected cash, and avoid new borrowing until coverage improves." });
    }
    const rd = g("receivable_days");
    if (rd !== null && rd > 60) {
      const locked = (rd - 45) * d.revenue / periodDays;
      f.push({ area: "Efficiency", priority: "Investigate and improve", title: "Customers are slow to pay",
               evidence: { receivable_days: pyRound(rd, 1), cash_released_at_45_days: pyRound(locked, 2) },
               rationale: `Collecting in 45 days instead of ${fix(rd, 0)} would release about ${inr(locked)} of cash.`,
               next_step: "Age the receivables and agree payment terms with the largest overdue customers." });
    }
    const inv = g("inventory_days");
    if (inv !== null && inv > 90)
      f.push({ area: "Efficiency", priority: "Investigate and improve", title: "Stock is moving slowly",
               evidence: { inventory_days: pyRound(inv, 1) },
               rationale: "Stock on hand covers more than three months of sales at cost.",
               next_step: "List the slowest items and decide whether to discount, bundle or stop reordering them." });
    if (!cashPoor && (cover || 0) >= 3 && (current || 0) >= 1.5 && (margin || 0) >= 0.05)
      f.push({ area: "Investment", priority: "Evaluate investment", title: "The business has room to consider investing",
               evidence: { cash_cover_months: pyRound(cover, 2), current_ratio: pyRound(current, 2), net_margin: pyRound(margin, 4) },
               rationale: "Margins are positive and cash covers at least three months of costs.",
               next_step: "Compare options on NPV, IRR and payback with the investment appraisal, keeping the cash reserve intact." });
    const good = metricsOut.filter(e => e.band === "good");
    if (good.length) {
      const ev = {};
      good.forEach(e => { ev[e.metric] = e.value; });
      f.push({ area: "Overall", priority: "Monitor", title: "Strengths to keep watching", evidence: ev,
               rationale: "These measures are in the healthy range under the thresholds used.",
               next_step: "Track them each period so a decline shows early." });
    }
    if (Object.keys(missingByArea).length)
      f.push({ area: "Data", priority: "Insufficient evidence", title: "Some measures could not be calculated", evidence: missingByArea,
               rationale: "The inputs for these measures were not supplied, so no value is shown for them.",
               next_step: "Add the missing balance sheet or cost figures and run the diagnosis again." });
    const order = ["Urgent action", "Investigate and improve", "Evaluate investment", "Monitor", "Insufficient evidence"];
    f.sort((a, b) => order.indexOf(a.priority) - order.indexOf(b.priority));

    let health = { score: overall, status };
    if (overall !== null && overall > 44 && f.some(x => x.priority === "Urgent action"))
      health = { score: 44.0, status: "At risk", score_before_cap: overall, note: "Capped at 44 because at least one finding needs urgent action." };

    return { mode: "business",
             summary: { revenue: d.revenue, net_profit: netProfit === null ? null : pyRound(netProfit, 2), period_months: periodMonths },
             health, areas: areasOut, metrics: metricsOut, findings: f,
             assumptions: Array.from(new Set(assumptions)).sort(), data_quality: quality,
             thresholds_note: "Default thresholds are general rules of thumb. They vary by industry and can be overridden." };
  }

  /* ------------------------------------------------------------------ investment appraisal */
  const npv = (rate, flows) => flows.reduce((s, cf, t) => s + cf / Math.pow(1 + rate, t), 0);
  function irr(flows) {
    let lo = -0.99, hi = 10.0;
    if (npv(lo, flows) * npv(hi, flows) > 0) return null;
    for (let i = 0; i < 200; i++) {
      const mid = (lo + hi) / 2;
      if (npv(lo, flows) * npv(mid, flows) <= 0) hi = mid; else lo = mid;
    }
    return (lo + hi) / 2;
  }
  function payback(cost, inflows) {
    let total = 0;
    for (let i = 0; i < inflows.length; i++) {
      const cf = inflows[i];
      if (cf > 0 && total + cf >= cost) return i + (cost - total) / cf;
      total += cf;
    }
    return null;
  }
  function appraiseInvestments(p) {
    const rate = p.discount_rate, options = p.options || [], cash = p.cash, reserve = has(p, "reserve") ? p.reserve : 0.0;
    if (!isNum(rate) || !(rate > -0.5 && rate < 1)) throw new InputError("discount_rate is required, as a decimal such as 0.12");
    if (!options.length) throw new InputError("at least one option is required");
    const out = options.map((o, idx) => {
      const i = idx + 1, cost = o.initial_cost, inflows = o.cash_flows;
      if (!isNum(cost) || cost <= 0 || !Array.isArray(inflows) || !inflows.length)
        throw new InputError(`option ${i}: initial_cost above zero and a list of yearly cash_flows are required`);
      if (!inflows.every(isNum)) throw new InputError(`option ${i}: cash_flows must be numbers`);
      const flows = [-cost].concat(inflows);
      const value = npv(rate, flows), r = irr(flows), pb = payback(cost, inflows);
      const entry = { name: o.name || `Option ${i}`, initial_cost: cost, npv: pyRound(value, 2), irr: r === null ? null : pyRound(r, 4),
                      payback_years: pb === null ? null : pyRound(pb, 2), profitability_index: pyRound((value + cost) / cost, 3),
                      npv_if_cash_flows_20pct_lower: pyRound(npv(rate, [-cost].concat(inflows.map(c => 0.8 * c))), 2) };
      if (isNum(cash)) { entry.cash_after = pyRound(cash - cost, 2); entry.keeps_reserve = cash - cost >= reserve; }
      entry.verdict = entry.keeps_reserve === false ? "Does not keep the cash reserve"
        : value <= 0 ? "Rejects: negative NPV"
        : entry.npv_if_cash_flows_20pct_lower <= 0 ? "Fragile: NPV turns negative if cash flows are 20% lower"
        : "Worth evaluating further";
      return entry;
    });
    const rank = e => (e.verdict !== "Worth evaluating further" ? 1 : 0);
    out.sort((a, b) => rank(a) - rank(b) || b.npv - a.npv);
    return { mode: "investment", discount_rate: rate, options: out,
             cash_check: isNum(cash) ? "applied" : "not applied: cash was not provided",
             note: "This ranks the company's own project options on the cash flows supplied. " +
                   "It is decision support, not a recommendation to buy any security." };
  }

  /* ------------------------------------------------------------------ plain-language explanation */
  function explain(result) {
    const health = result.health || {}, parts = [];
    if (result.mode === "student") {
      const s = result.summary;
      if (health.score === null || health.score === undefined)
        return "There is not enough recorded spending yet to give a diagnosis. Add your spends and try again.";
      const r = result.run_out, w = result.warning;
      parts.push(`You have spent ${inr(s.spent)} of ${inr(s.allowance)} by day ${s.today}, which leaves ${inr(s.balance)} for ${s.days_left} days.`);
      parts.push(r.day ? `At your current pace of ${inr(result.pace.per_day)} a day the money runs out on day ${r.day}.`
                       : `At your current pace of ${inr(result.pace.per_day)} a day the money lasts the month.`);
      parts.push(`To reach month end you can spend ${inr(Math.trunc(r.safe_to_spend_per_day))} a day.`);
      parts.push(`The chance of running short is ${fix(100 * w.probability, 0)}%, so your status is ${health.status}.`);
      const flex = (result.categories || []).filter(c => !c.fixed).slice(0, 2);
      if (flex.length) parts.push("Your largest flexible spending is " + flex.map(c => `${c.category} (${inr(c.amount)})`).join(" and ") + ", so start there.");
    } else if (result.mode === "business") {
      if (health.score === null || health.score === undefined) parts.push("There is not enough data for an overall health score.");
      else parts.push(`Overall financial health is ${fix(health.score, 0)} out of 100, which is ${health.status}.`);
      const scored = (result.areas || []).filter(a => a.score !== null);
      if (scored.length) parts.push("By area: " + scored.map(a => `${a.area} ${fix(a.score, 0)}`).join(", ") + ".");
      (result.findings || []).slice(0, 3).forEach(x => parts.push(`${x.priority}: ${x.title}. ${x.next_step}`));
    } else return "";
    return parts.join(" ");
  }

  return { diagnoseStudent, diagnoseBusiness, appraiseInvestments, savingsScenarios, explain, inr, pyRound,
           InputError, MODEL, SAMPLES, DEFAULT_THRESHOLDS };
});
