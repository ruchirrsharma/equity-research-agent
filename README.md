# Equity Research Agent

A [Claude Code](https://code.claude.com) subagent that works like a buy-side equity research analyst. It pulls live fundamentals and price history, computes its own risk statistics, builds a DCF with sensitivity grids, and writes a research note with cited sources.

## What it does

- **Fundamentals**: price, market cap, EV, multiples, margins, returns, balance sheet, analyst targets, several years of annual revenue, earnings, cash flow, capex and free cash flow, trailing-twelve-month (TTM) totals, and the last 5-6 quarters.
- **Risk stats** (vs a benchmark, SPY by default): CAGR, annual and downside volatility, Sharpe, Sortino, beta, Jensen's alpha, correlation, tracking error, information ratio, max and current drawdown with dates, 95% daily VaR/CVaR, and rolling 1-year beta.
- **DCF**: two-stage free-cash-flow-to-firm model built on TTM free cash flow, tax rate and interest (falling back to the latest annual report when quarterly data is missing). Growth fades from stage 1 to terminal. WACC comes from CAPM (live 10-year Treasury yield) plus after-tax cost of debt. It returns fair value per share, upside vs price, the terminal value's share of EV, and two 5x5 sensitivity grids (WACC × terminal growth, WACC × stage-1 growth).
- **Judgment**: the agent checks the default inputs before trusting them. It normalizes distorted cash flow years, overrides growth or beta when needed, runs bear and bull cases, and flags results that depend mostly on assumptions.
- **Context**: it searches the web for recent earnings, guidance and news, and cites each source.

Market data comes from Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance).

## Install

Requires Claude Code and Python 3.10+.

```bash
git clone https://github.com/ruchirrsharma/equity-research-agent.git
cd equity-research-agent
./install.sh
```

This copies the agent to `~/.claude/agents/` and the toolkit to `~/.claude/tools/equity-research/`, then installs the Python dependencies into a private virtual environment there.

## Use

Start a new Claude Code session, then:

- Ask by name: *"Use the equity-research-analyst agent to analyze AAPL."*
- @-mention it: type `@`, pick `equity-research-analyst`, then add your request.
- Or describe the task: *"Value NVDA with a DCF"* or *"Compare KO and PEP's risk."*

To run a whole session as the agent:

```bash
claude --agent equity-research-analyst
```

## Toolkit on its own

The calculations also work without Claude. Every command prints JSON.

```bash
~/.claude/tools/equity-research/eqr fundamentals MSFT
~/.claude/tools/equity-research/eqr risk MSFT --years 5 --benchmark SPY
~/.claude/tools/equity-research/eqr dcf MSFT --growth 0.10 --terminal 0.025 --fcf 75e9
~/.claude/tools/equity-research/eqr all MSFT
```

| Flag | Meaning | Default |
|---|---|---|
| `--years` | Risk lookback / DCF explicit years | 5 |
| `--benchmark` | Benchmark ticker for risk stats | SPY |
| `--rf` | Risk-free rate | live 10-year yield |
| `--growth` | Stage-1 FCF growth | latest quarter's YoY revenue growth, clipped to -5%..25% |
| `--terminal` | Terminal growth | 2.5% |
| `--wacc` | WACC override | calculated |
| `--fcf` | Base-year FCF override | TTM FCF |
| `--erp` | Equity risk premium | 5% |
| `--beta` | Beta override | Yahoo beta (`all` uses the computed beta) |

## Notes

- Default DCF outputs are mechanical starting points. TTM free cash flow can still be distorted by heavy capex or one-off items.
- Yahoo usually adds a newly reported quarter a few days after earnings. Until then, TTM figures end one quarter earlier. The agent is told to review and adjust these inputs. If you run the toolkit directly, do the same.
- FCFF DCF fits poorly for banks, insurers, REITs and pre-profit companies. The agent says so and uses other methods.
- Yahoo Finance data is unofficial and can have gaps or errors.

**This is an analysis tool, not investment advice.**

## Layout

```
agents/equity-research-analyst.md   # subagent definition (prompt, tools, workflow, output format)
tools/equity-research/eqr           # launcher that uses the private venv
tools/equity-research/eqr.py        # fundamentals, risk and DCF calculations
tools/equity-research/requirements.txt
install.sh
```

## License

[MIT](LICENSE)
