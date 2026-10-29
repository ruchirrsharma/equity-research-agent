#!/usr/bin/env python3
"""Equity research toolkit: live fundamentals, risk stats, and a DCF with sensitivity grid.

Usage:
  eqr.py fundamentals TICKER
  eqr.py risk TICKER [--years 5] [--benchmark SPY] [--rf 0.043]
  eqr.py dcf TICKER [--growth 0.08] [--terminal 0.025] [--wacc 0.09] [--years 5]
                    [--fcf BASE_FCF] [--erp 0.05] [--rf 0.043]
  eqr.py all TICKER [same flags]

Every command prints JSON. Data comes from Yahoo Finance via yfinance.
"""
import argparse
import json
import math
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")  # yfinance re-enables pandas warnings on import


# ---------- helpers ----------

def _num(x):
    try:
        if x is None:
            return None
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _row(df, *names):
    """First matching row from a yfinance statement, newest column first."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def _latest(df, *names):
    r = _row(df, *names)
    if r is None:
        return None
    r = r.dropna()
    return _num(r.iloc[0]) if len(r) else None


def _series(df, *names):
    r = _row(df, *names)
    if r is None:
        return {}
    return {str(k.date() if hasattr(k, "date") else k): _num(v) for k, v in r.dropna().items()}


def _quarters(df, *names):
    """Quarterly values for the first matching row, newest first, as [(date, value)]."""
    r = _row(df, *names)
    if r is None:
        return []
    return [(k, _num(v)) for k, v in r.dropna().sort_index(ascending=False).items() if _num(v) is not None]


def _ttm(df, *names):
    """Sum of the 4 latest quarters, or None if they are not 4 consecutive quarters."""
    q = _quarters(df, *names)[:4]
    if len(q) < 4:
        return None
    span = (q[0][0] - q[3][0]).days
    if not 250 <= span <= 300:  # 3 quarter gaps ~ 273 days; reject holes in the data
        return None
    return sum(v for _, v in q)


def risk_free_rate(default=0.043):
    """10y Treasury yield from ^TNX, falling back to a default."""
    try:
        h = yf.Ticker("^TNX").history(period="5d")["Close"].dropna()
        if len(h):
            return float(h.iloc[-1]) / 100.0
    except Exception:
        pass
    return default


# ---------- fundamentals ----------

def fundamentals(ticker):
    t = yf.Ticker(ticker)
    info = t.info or {}
    inc, cf, bs = t.financials, t.cashflow, t.balance_sheet

    keys = [
        "longName", "sector", "industry", "currency", "currentPrice", "marketCap",
        "enterpriseValue", "sharesOutstanding", "beta", "trailingPE", "forwardPE",
        "priceToBook", "enterpriseToEbitda", "enterpriseToRevenue", "pegRatio",
        "grossMargins", "operatingMargins", "profitMargins", "returnOnEquity",
        "returnOnAssets", "revenueGrowth", "earningsGrowth", "dividendYield",
        "payoutRatio", "totalCash", "totalDebt", "debtToEquity", "currentRatio",
        "freeCashflow", "operatingCashflow", "targetMeanPrice", "targetLowPrice",
        "targetHighPrice", "recommendationKey", "numberOfAnalystOpinions",
        "fiftyTwoWeekLow", "fiftyTwoWeekHigh",
    ]
    snapshot = {k: info.get(k) for k in keys}

    cfo = _series(cf, "Operating Cash Flow", "Total Cash From Operating Activities")
    capex = _series(cf, "Capital Expenditure", "Capital Expenditures")
    fcf = {y: (cfo[y] + capex.get(y, 0)) for y in cfo if cfo[y] is not None and capex.get(y) is not None}

    history = {
        "revenue": _series(inc, "Total Revenue"),
        "operating_income": _series(inc, "Operating Income", "EBIT"),
        "net_income": _series(inc, "Net Income", "Net Income Common Stockholders"),
        "ebitda": _series(inc, "EBITDA", "Normalized EBITDA"),
        "interest_expense": _series(inc, "Interest Expense", "Interest Expense Non Operating"),
        "tax_provision": _series(inc, "Tax Provision"),
        "pretax_income": _series(inc, "Pretax Income"),
        "operating_cash_flow": cfo,
        "capex": capex,
        "free_cash_flow": fcf,
        "cash": _series(bs, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
        "total_debt": _series(bs, "Total Debt"),
        "stockholders_equity": _series(bs, "Stockholders Equity", "Total Equity Gross Minority Interest"),
    }

    rev = [v for _, v in sorted(history["revenue"].items()) if v]
    cagr = None
    if len(rev) >= 2 and rev[0] > 0:
        cagr = (rev[-1] / rev[0]) ** (1 / (len(rev) - 1)) - 1

    # Quarterly statements: trailing twelve months and recent quarterly trend
    qinc, qcf, qbs = t.quarterly_financials, t.quarterly_cashflow, t.quarterly_balance_sheet
    q_cfo = _quarters(qcf, "Operating Cash Flow", "Total Cash From Operating Activities")
    q_capex = dict(_quarters(qcf, "Capital Expenditure", "Capital Expenditures"))
    q_rev = _quarters(qinc, "Total Revenue")
    ttm_cfo = _ttm(qcf, "Operating Cash Flow", "Total Cash From Operating Activities")
    ttm_capex = _ttm(qcf, "Capital Expenditure", "Capital Expenditures")
    ttm = {
        "as_of_quarter": str(q_cfo[0][0].date()) if q_cfo else None,
        "revenue": _ttm(qinc, "Total Revenue"),
        "operating_income": _ttm(qinc, "Operating Income", "EBIT"),
        "net_income": _ttm(qinc, "Net Income", "Net Income Common Stockholders"),
        "ebitda": _ttm(qinc, "EBITDA", "Normalized EBITDA"),
        "interest_expense": _ttm(qinc, "Interest Expense"),
        "tax_provision": _ttm(qinc, "Tax Provision"),
        "pretax_income": _ttm(qinc, "Pretax Income"),
        "operating_cash_flow": ttm_cfo,
        "capex": ttm_capex,
        "free_cash_flow": ttm_cfo + ttm_capex if ttm_cfo is not None and ttm_capex is not None else None,
        "cash_latest_quarter": _latest(qbs, "Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
        "cash_and_short_term_investments_latest_quarter": _latest(qbs, "Cash Cash Equivalents And Short Term Investments"),
        "long_term_investments_latest_quarter": _latest(qbs, "Investments And Advances"),
        "total_debt_latest_quarter": _latest(qbs, "Total Debt"),
    }
    if ttm["interest_expense"] is None:
        ttm["interest_expense"] = _ttm(qinc, "Interest Expense Non Operating")

    # Analyst consensus revenue growth: current fiscal year (0y) and next (+1y)
    consensus = {}
    try:
        est = t.revenue_estimate
        for period in ("0y", "+1y"):
            if est is not None and period in est.index:
                consensus[period] = {"growth": _num(est.loc[period, "growth"]),
                                     "analysts": _num(est.loc[period, "numberOfAnalysts"])}
    except Exception:
        pass
    quarterly = {
        "revenue": {str(d.date()): v for d, v in q_rev},
        "operating_income": {str(d.date()): v for d, v in _quarters(qinc, "Operating Income", "EBIT")},
        "net_income": {str(d.date()): v for d, v in _quarters(qinc, "Net Income", "Net Income Common Stockholders")},
        "free_cash_flow": {str(d.date()): v + q_capex[d] for d, v in q_cfo if d in q_capex},
    }

    # Latest quarter's revenue vs the same quarter a year earlier
    yoy = None
    if len(q_rev) >= 5 and q_rev[4][1] and 330 <= (q_rev[0][0] - q_rev[4][0]).days <= 400:
        yoy = q_rev[0][1] / q_rev[4][1] - 1

    latest_annual = max(history["revenue"]) if history["revenue"] else None
    return {"ticker": ticker.upper(), "snapshot": snapshot, "history": history,
            "ttm": ttm, "quarterly": quarterly,
            "derived": {"revenue_cagr": cagr, "revenue_yoy_latest_quarter": yoy,
                        "consensus_revenue_growth": consensus,
                        "latest_annual_period": latest_annual}}


# ---------- risk ----------

def risk(ticker, years=5, benchmark="SPY", rf=None):
    rf = risk_free_rate() if rf is None else rf
    px = yf.download([ticker, benchmark], period=f"{years}y", auto_adjust=True,
                     progress=False)["Close"].dropna()
    if px.empty or ticker.upper() not in [c.upper() for c in px.columns]:
        raise SystemExit(f"No price history for {ticker}")
    px.columns = [c.upper() for c in px.columns]
    s, b = px[ticker.upper()], px[benchmark.upper()]
    rs, rb = s.pct_change().dropna(), b.pct_change().dropna()

    n = len(rs)
    ann = 252
    total = s.iloc[-1] / s.iloc[0] - 1
    cagr = (1 + total) ** (ann / n) - 1
    vol = rs.std() * np.sqrt(ann)
    downside = rs[rs < 0].std() * np.sqrt(ann)
    cov = np.cov(rs, rb)
    beta = cov[0, 1] / cov[1, 1]
    bench_cagr = (b.iloc[-1] / b.iloc[0]) ** (ann / n) - 1
    alpha = cagr - (rf + beta * (bench_cagr - rf))
    dd = s / s.cummax() - 1
    trough = dd.idxmin()
    peak = s[:trough].idxmax()
    var95 = np.percentile(rs, 5)
    cvar95 = rs[rs <= var95].mean()
    te = (rs - rb).std() * np.sqrt(ann)

    # rolling 1y beta, sampled at the end of each quarter
    roll = pd.concat([rs, rb], axis=1).dropna()
    rc = roll.iloc[:, 0].rolling(252).cov(roll.iloc[:, 1])
    rv = roll.iloc[:, 1].rolling(252).var()
    rbeta = (rc / rv).dropna().resample("QE").last()

    return {
        "ticker": ticker.upper(), "benchmark": benchmark.upper(),
        "period": f"{s.index[0].date()} to {s.index[-1].date()}", "trading_days": n,
        "risk_free_rate": rf,
        "last_price": float(s.iloc[-1]),
        "total_return": float(total), "cagr": float(cagr), "benchmark_cagr": float(bench_cagr),
        "annual_volatility": float(vol), "downside_volatility": float(downside),
        "sharpe": float((cagr - rf) / vol) if vol else None,
        "sortino": float((cagr - rf) / downside) if downside else None,
        "beta": float(beta), "jensens_alpha": float(alpha),
        "correlation": float(np.corrcoef(rs, rb)[0, 1]),
        "tracking_error": float(te),
        "information_ratio": float((cagr - bench_cagr) / te) if te else None,
        "max_drawdown": float(dd.min()), "max_drawdown_peak": str(peak.date()),
        "max_drawdown_trough": str(trough.date()),
        "current_drawdown": float(dd.iloc[-1]),
        "var_95_daily": float(var95), "cvar_95_daily": float(cvar95),
        "rolling_1y_beta_quarterly": {str(k.date()): round(float(v), 3) for k, v in rbeta.items()},
    }


# ---------- DCF ----------

DEBT_SPREAD = 0.01  # spread over risk-free when a company reports no interest expense


def _dcf_value(fcf0, g_start, g_term, wacc, years, net_debt, shares):
    """Two-stage FCFF DCF. Growth fades linearly from g_start to g_term over `years`."""
    if wacc <= g_term:
        return None
    fcf, pv = fcf0, 0.0
    flows = []
    for t in range(1, years + 1):
        g = g_start + (g_term - g_start) * (t - 1) / max(years - 1, 1)
        fcf *= 1 + g
        disc = fcf / (1 + wacc) ** t
        pv += disc
        flows.append({"year": t, "growth": g, "fcf": fcf, "pv": disc})
    tv = fcf * (1 + g_term) / (wacc - g_term)
    pv_tv = tv / (1 + wacc) ** years
    ev = pv + pv_tv
    equity = ev - net_debt
    return {"flows": flows, "pv_explicit": pv, "terminal_value": tv, "pv_terminal": pv_tv,
            "enterprise_value": ev, "equity_value": equity,
            "per_share": equity / shares if shares else None,
            "terminal_share_of_ev": pv_tv / ev if ev else None}


def dcf(ticker, growth=None, terminal=0.025, wacc=None, years=5, fcf=None,
        erp=0.05, rf=None, beta=None, kd=None, exclude_investments=False):
    f = fundamentals(ticker)
    snap, hist = f["snapshot"], f["history"]
    rf = risk_free_rate() if rf is None else rf
    notes = []

    ttm = f["ttm"]

    # Base FCF: trailing twelve months, else latest annual; warn if far from the 3y annual average
    fcf_hist = [v for _, v in sorted(hist["free_cash_flow"].items(), reverse=True) if v is not None]
    if fcf is not None:
        fcf_source = "override (--fcf)"
    elif ttm["free_cash_flow"] is not None:
        fcf, fcf_source = ttm["free_cash_flow"], f"TTM through {ttm['as_of_quarter']}"
    elif fcf_hist:
        fcf = fcf_hist[0]
        fcf_source = f"annual, fiscal year ending {f['derived']['latest_annual_period']}"
        notes.append("Quarterly cash flow unavailable; base FCF is the latest annual figure and may be stale.")
    else:
        raise SystemExit("No free cash flow history; pass --fcf")
    if fcf_hist and fcf_source != "override (--fcf)":
        avg3 = sum(fcf_hist[:3]) / len(fcf_hist[:3])
        if avg3 and abs(fcf / avg3 - 1) > 0.3:
            notes.append(f"Base FCF ({fcf:,.0f}) differs from 3y annual average ({avg3:,.0f}) by >30%; consider --fcf.")
    if fcf <= 0:
        notes.append("Base FCF is negative or zero; a DCF on this base is not meaningful without --fcf.")

    # Growth: average of analyst consensus revenue growth (this FY and next) and the
    # historical annual revenue CAGR, so one unusual quarter can't swing the default.
    # Falls back to latest-quarter YoY growth only when none of those exist. Clipped.
    growth_inputs = {}
    if growth is None:
        d = f["derived"]
        cons = d["consensus_revenue_growth"]
        for label, val in (("consensus current FY", cons.get("0y", {}).get("growth")),
                           ("consensus next FY", cons.get("+1y", {}).get("growth")),
                           ("historical annual CAGR", d["revenue_cagr"])):
            if val is not None:
                growth_inputs[label] = val
        if growth_inputs:
            cand = sum(growth_inputs.values()) / len(growth_inputs)
            src = "average of " + ", ".join(f"{k} {v:.1%}" for k, v in growth_inputs.items())
        elif d["revenue_yoy_latest_quarter"] is not None:
            cand = d["revenue_yoy_latest_quarter"]
            growth_inputs["latest-quarter YoY"] = cand
            src = "latest-quarter YoY revenue growth only; noisy"
        else:
            cand, src = 0.05, "no data; flat 5% fallback"
        growth = max(min(cand, 0.25), -0.05)
        notes.append(f"Stage-1 growth defaulted to {growth:.1%} ({src}; clipped to -5%..25%).")

    # WACC via CAPM + after-tax cost of debt
    price, shares = _num(snap.get("currentPrice")), _num(snap.get("sharesOutstanding"))
    mcap = _num(snap.get("marketCap")) or (price * shares if price and shares else None)
    debt = _num(snap.get("totalDebt")) or 0.0
    # Cash: cash + short-term investments, plus long-term investments (marketable securities,
    # equity stakes) as non-operating assets in the EV-to-equity bridge
    cash = ttm["cash_and_short_term_investments_latest_quarter"] or _num(snap.get("totalCash")) or 0.0
    lt_inv = 0.0 if exclude_investments else (ttm["long_term_investments_latest_quarter"] or 0.0)
    if lt_inv and mcap and lt_inv / mcap > 0.05:
        notes.append(f"Long-term investments ({lt_inv:,.0f}) are {lt_inv / mcap:.0%} of market cap and are added "
                     "to equity value; check they are financial assets, or pass --exclude-investments.")
    net_debt = debt - cash - lt_inv
    b = beta if beta is not None else (_num(snap.get("beta")) or 1.0)
    ke = rf + b * erp
    # Pre-tax cost of debt: override, else TTM interest / debt, else the latest annual
    # report's interest (only that year, never an older one), else risk-free + spread
    interest, kd_source = ttm["interest_expense"], "TTM interest expense / total debt"
    if interest is None:
        latest_year = f["derived"]["latest_annual_period"]
        interest = hist["interest_expense"].get(latest_year)
        kd_source = f"interest expense for fiscal year ending {latest_year} / total debt"
    if kd is not None:
        kd_pre, kd_source = kd, "override (--kd)"
    elif not debt:
        kd_pre, kd_source = rf, "no debt"
    elif interest:
        kd_pre = min(max(abs(interest) / debt, rf), 0.15)
    else:
        kd_pre = rf + DEBT_SPREAD
        kd_source = f"risk-free rate + {DEBT_SPREAD:.0%} spread (interest expense not reported)"
        notes.append(f"Interest expense is not reported; pre-tax cost of debt assumed at risk-free + "
                     f"{DEBT_SPREAD:.0%} = {kd_pre:.2%}. Pass --kd to set it.")
    tax = None
    if ttm["tax_provision"] is not None and ttm["pretax_income"]:
        tax = ttm["tax_provision"] / ttm["pretax_income"]
    else:
        tp = sorted(hist["tax_provision"].items(), reverse=True)
        pt = dict(hist["pretax_income"])
        if tp and pt.get(tp[0][0]):
            tax = tp[0][1] / pt[tp[0][0]]
    tax = min(max(tax if tax is not None else 0.21, 0.0), 0.35)
    kd_after = kd_pre * (1 - tax)
    wd = debt / (debt + mcap) if mcap and debt else 0.0
    wacc_calc = (1 - wd) * ke + wd * kd_after
    used_wacc = wacc if wacc is not None else wacc_calc

    base = _dcf_value(fcf, growth, terminal, used_wacc, years, net_debt, shares)
    if base is None:
        raise SystemExit("WACC must exceed terminal growth")

    # Sensitivity grid: WACC +/-2% in 1% steps x terminal growth 1.5%..3.5%
    waccs = [round(used_wacc + d, 4) for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    tgs = [round(terminal + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    grid = {}
    for w in waccs:
        grid[f"{w:.2%}"] = {}
        for g in tgs:
            v = _dcf_value(fcf, growth, g, w, years, net_debt, shares)
            grid[f"{w:.2%}"][f"{g:.2%}"] = round(v["per_share"], 2) if v and v["per_share"] else None

    # Second grid: WACC x stage-1 growth
    gs = [round(growth + d, 4) for d in (-0.04, -0.02, 0, 0.02, 0.04)]
    grid2 = {}
    for w in waccs:
        grid2[f"{w:.2%}"] = {}
        for g in gs:
            v = _dcf_value(fcf, g, terminal, w, years, net_debt, shares)
            grid2[f"{w:.2%}"][f"{g:.2%}"] = round(v["per_share"], 2) if v and v["per_share"] else None

    if base["terminal_share_of_ev"] and base["terminal_share_of_ev"] > 0.8:
        notes.append("Terminal value is >80% of EV; the result is driven mostly by terminal assumptions.")

    ps = base["per_share"]
    return {
        "ticker": ticker.upper(), "currency": snap.get("currency"),
        "assumptions": {
            "base_fcf": fcf, "base_fcf_source": fcf_source, "stage1_growth": growth, "growth_inputs": growth_inputs, "terminal_growth": terminal,
            "explicit_years": years, "risk_free_rate": rf, "equity_risk_premium": erp,
            "beta": b, "cost_of_equity": ke, "pre_tax_cost_of_debt": kd_pre, "cost_of_debt_source": kd_source, "tax_rate": tax,
            "debt_weight": wd, "wacc_calculated": wacc_calc, "wacc_used": used_wacc,
            "total_debt": debt, "cash_and_short_term_investments": cash,
            "long_term_investments": lt_inv, "net_debt": net_debt, "shares": shares,
        },
        "valuation": base,
        "current_price": price,
        "upside": (ps / price - 1) if ps and price else None,
        "sensitivity_wacc_x_terminal_growth": grid,
        "sensitivity_wacc_x_stage1_growth": grid2,
        "notes": notes,
    }


# ---------- CLI ----------

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["fundamentals", "risk", "dcf", "all"])
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=5, help="risk lookback / DCF explicit years")
    p.add_argument("--benchmark", default="SPY")
    p.add_argument("--rf", type=float, help="risk-free rate (default: live 10y yield)")
    p.add_argument("--growth", type=float, help="stage-1 FCF growth")
    p.add_argument("--terminal", type=float, default=0.025)
    p.add_argument("--wacc", type=float)
    p.add_argument("--fcf", type=float, help="base-year free cash flow override")
    p.add_argument("--erp", type=float, default=0.05)
    p.add_argument("--beta", type=float, help="beta override (default: Yahoo beta)")
    p.add_argument("--kd", type=float, help="pre-tax cost of debt override")
    p.add_argument("--exclude-investments", action="store_true",
                   help="do not add long-term investments to equity value")
    a = p.parse_args()

    if a.command == "fundamentals":
        out = fundamentals(a.ticker)
    elif a.command == "risk":
        out = risk(a.ticker, a.years, a.benchmark, a.rf)
    elif a.command == "dcf":
        out = dcf(a.ticker, a.growth, a.terminal, a.wacc, a.years, a.fcf, a.erp, a.rf, a.beta,
                  a.kd, a.exclude_investments)
    else:
        r = risk(a.ticker, a.years, a.benchmark, a.rf)
        out = {"risk": r,
               "dcf": dcf(a.ticker, a.growth, a.terminal, a.wacc, a.years, a.fcf, a.erp,
                          r["risk_free_rate"], a.beta if a.beta is not None else r["beta"],
                          a.kd, a.exclude_investments)}
    json.dump(out, sys.stdout, indent=2, default=str)
    print()


if __name__ == "__main__":
    main()
