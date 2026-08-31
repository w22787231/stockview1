(function (root) {
  "use strict";

  const finite = value => Number.isFinite(Number(value));
  const average = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;

  function liquidityJudgment(candles) {
    const rows = (candles || []).filter(c => finite(c.c) && finite(c.v) && Number(c.v) >= 0).slice(-60);
    if (rows.length < 20) return { label: "資料不足", tone: "neutral", reasons: ["至少需要 20 個交易日的收盤價與成交量。"] };

    const turnover = rows.map(c => Number(c.c) * Number(c.v));
    const recent = average(turnover.slice(-20));
    const baseline = average(turnover.slice(Math.max(0, turnover.length - 40), -20)) || recent;
    const ratio = baseline > 0 ? recent / baseline : null;
    let score = 0;
    const reasons = [];

    if (recent >= 1e7) { score += 2; reasons.push("近 20 日平均成交額達可交易水準。"); }
    else if (recent < 1e6) { score -= 2; reasons.push("近 20 日平均成交額偏低，進出成本與滑價風險較高。"); }
    else reasons.push("近 20 日平均成交額居中，仍應依委託金額確認可交易性。");

    if (ratio != null && ratio >= 0.8) { score += 1; reasons.push("近期量能未明顯低於前期。 "); }
    else if (ratio != null && ratio < 0.5) { score -= 1; reasons.push("近期量能較前期萎縮逾半。 "); }
    else reasons.push("近期量能較前期略有變化。 ");

    const label = score >= 2 ? "流動性佳" : score <= -1 ? "流動性風險高" : "流動性中等";
    return { label, tone: score >= 2 ? "good" : score <= -1 ? "risk" : "neutral", reasons, avgDollarVolume: recent, volumeRatio: ratio };
  }

  function valuationJudgment(metrics) {
    const m = metrics || {};
    let score = 0, inputs = 0;
    const reasons = [];
    const assess = (value, low, high, title) => {
      if (!finite(value) || Number(value) <= 0) return;
      inputs += 1;
      if (Number(value) <= low) { score += 1; reasons.push(title + "位於較低區間。"); }
      else if (Number(value) >= high) { score -= 1; reasons.push(title + "位於較高區間。"); }
      else reasons.push(title + "位於中間區間。");
    };

    assess(m.pe, 15, 35, "本益比");
    assess(m.forwardPe, 20, 35, "前瞻本益比");
    assess(m.peg, 1.2, 2.5, "PEG");
    if (finite(m.rev_growth)) {
      inputs += 1;
      if (Number(m.rev_growth) >= 0.1) { score += 1; reasons.push("營收維持雙位數成長。"); }
      else if (Number(m.rev_growth) < 0) { score -= 1; reasons.push("營收呈現衰退。 "); }
    }
    if (finite(m.roe)) {
      inputs += 1;
      if (Number(m.roe) >= 0.12) { score += 1; reasons.push("ROE 顯示資本效率尚佳。"); }
      else if (Number(m.roe) < 0.05) { score -= 1; reasons.push("ROE 偏低，估值折價可能有基本面原因。 "); }
    }
    if (!inputs) return { label: "資料不足", tone: "neutral", reasons: ["缺少 PE、PEG、成長或 ROE 資料，無法進行相對估值判讀。"] };

    const label = score >= 2 ? "相對偏低" : score <= -2 ? "相對偏高" : "估值合理";
    return { label, tone: score >= 2 ? "good" : score <= -2 ? "risk" : "neutral", reasons, score, inputs };
  }

  root.StockJudgments = { liquidityJudgment, valuationJudgment };
})(window);
