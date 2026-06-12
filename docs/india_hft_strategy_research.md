# Institutional HFT Strategies for Indian Index Derivatives
## What Jane Street, Tower Research, AlphaGrep-class firms actually run — and how to backtest each one

*Research memo · June 2026 · For internal strategy development. Not investment advice. Verify all rates/rules against current SEBI/NSE/BSE circulars.*

---

## 0. The playing field you're entering

Before strategies, internalize the structure, because every strategy below is shaped by it.

**Who you're competing against.** The Indian HFT profit pool has historically been dominated by a small group: Tower Research Capital (operating in India as Shastra), AlphaGrep, Quadeye, and Graviton — by some accounts these firms at their peak captured the overwhelming majority of HFT volume and profits across NSE, BSE and MCX. Around them sit the global options giants (Optiver, IMC, Citadel Securities, Jump, and Jane Street trading via FPI entities) and strong domestic shops (iRage, NK Securities, Quantbox, Dolat, Estee). AlphaGrep publicly describes itself as one of the largest firms by volume on Indian exchanges, running systematic alpha factors on ultra-low-latency systems. Tower's DNA is latency-sensitive arbitrage across correlated instruments; AlphaGrep/Graviton/Quadeye blend market making with short-horizon statistical signals; Jane Street's global DNA is ETF/index arbitrage and options liquidity provision at massive size.

**Market structure as of mid-2026 (this changed a LOT recently — backtests must respect it):**

- **One weekly expiry per exchange** (SEBI, Nov 2024): NSE kept Nifty 50 weeklies; Bank Nifty, FinNifty, Midcap Nifty weeklies were discontinued (monthly only now). BSE kept Sensex weeklies.
- **Expiry days swapped** (Sept 1, 2025): Nifty weeklies/monthlies expire **Tuesday**; Sensex weeklies/monthlies expire **Thursday**. The week now has two distinct expiry-driven liquidity cycles on two exchanges.
- **STT shock** (April 1, 2026): futures STT 0.02% → **0.05%** of notional, sell side; options STT 0.1% → **0.15% of premium**, sell side; exercise STT 0.15% of intrinsic. Futures are now ~12+ index points of tax per round trip at Nifty 25,000 — futures are a *hedging* instrument, options are the *trading* instrument. Never take options to exercise.
- **Settlement mechanics**: index options cash-settle to the average index value over the last 30 minutes (3:00–3:30pm) on expiry day. This 30-minute window is the gravitational center of expiry-day strategies.
- **Order-to-trade ratio (OTR) penalties** at NSE, per-strategy exchange approval for co-lo algos, LPP (limit price protection) bands, and SEBI's post-Jane-Street surveillance regime (real-time expiry-day monitoring of cash–derivatives linkages).

**The asymmetry that powers everything**: Indian index options volume is a global anomaly — on heavy days Bank Nifty options alone have printed over a trillion dollars of notional against single-digit billions of underlying cash volume (ratios of ~350:1 documented in the SEBI/Jane Street analysis). A shallow cash market sets the price for a vastly deeper derivatives market. Every strategy below is, at root, a different way of monetizing the friction between those two layers.

---

## Strategy 1 — Options Market Making on the Volatility Surface
*The core business of Optiver/IMC/Jane Street-class firms; the highest-capacity, most durable edge in India.*

### The trade
You quote two-sided markets across the Nifty (NSE) and Sensex (BSE) option chains — hundreds of strikes × expiries simultaneously — and earn the spread while warehousing and recycling risk. Your quotes are not independent: every quote is derived from a single internal **fair-value engine**:

1. **Reference underlying**: micro-price of the index future (front month), corrected for cost-of-carry to a synthetic spot. The future, not the cash index, is your real-time underlying — the cash index updates too slowly.
2. **Fitted vol surface**: every few milliseconds, fit a parametric surface (SVI / SABR per expiry, or a spline in delta-space) to the option mid-prices you consider informative (tight, recently-traded strikes). The surface gives you theoretical value for *every* strike, including illiquid ones.
3. **Quote generation**: theo ± edge, where edge per strike depends on your inventory (vega, gamma, skew exposure per bucket), the strike's toxicity (how often you get run over there), time to expiry, and event risk (RBI policy, budget, expiry day).
4. **Inventory recycling**: you don't hedge per fill. You accumulate Greeks across the chain, net them internally (a sold call and a sold put partially cancel in vega), and hedge the *residual* delta in futures periodically and the residual vega/skew by leaning your quotes (skewing) so the market takes the other side for you. Leaning quotes is free; hedging in futures costs 12+ points of STT.

### Where the edge actually comes from
Spread capture is the visible part. The real edges are: (a) **queue position** — being early at a price level on liquid strikes; (b) **pull speed** — cancelling stale quotes within microseconds of a futures tick before arbitrageurs (Strategy 2 players) pick you off; (c) **surface quality** — pricing illiquid wings and the new weekly better than competitors on Monday night/Tuesday morning when the next Nifty weekly lists; (d) **inventory intelligence** — knowing which flow is informed (other HFTs) vs uninformed (retail buying lottery-ticket OTM weeklies, an enormous and well-documented flow in India).

### India-specific notes
- Retail dominates short-dated OTM options — this flow is systematically vol-overpaying, which is why net option *selling* (vega-short with disciplined risk) has been the structural P&L engine of Indian options MM. Post-2026 STT, your sell-side tax is on premium, so this remains viable; what died is hyperactive churning of futures.
- The Tuesday (NSE) / Thursday (BSE) alternation means two expiry-day gamma regimes per week on two venues. The same Sensex chain on BSE is less competitive than Nifty on NSE — wider spreads, fewer co-lo players — a deliberate place for a new desk to learn.
- OTR discipline is a first-class design constraint: every requote across 500 strikes costs OTR budget. Tiered quoting (tight + fast on ~30 active strikes, wide + lazy on wings) is standard.

### How to backtest it
This is the hardest strategy to backtest honestly, because your fills depend on adverse selection that your own presence changes. The institutional approach is layered:

- **Layer A — surface replay**: with full order-book (or at least L1 + trades) data for the whole chain plus futures ticks, rebuild your fair-value engine historically. Metric: out-of-sample pricing error of your surface vs subsequent trade prints, per strike bucket. If your theo doesn't predict the next trade price better than current mid does, you have no business quoting.
- **Layer B — markout analysis (the MM's true scorecard)**: simulate quotes with the event-driven engine (queue model + latency). For every simulated fill, compute **markouts**: (theo_t+Δ − fill price) × side, at Δ = 100ms, 1s, 10s, 60s. A market maker is profitable iff average markout + spread captured − costs > 0 per fill, bucketed by strike moneyness, time of day, and counterparty toxicity proxy (e.g., fills that occur within 50ms of a futures tick are pick-offs — measure them separately; this is your loss-to-Strategy-2 leakage).
- **Layer C — inventory simulation**: feed Layer B's fills into a portfolio Greeks simulator with your hedging rules; measure P&L decomposition: spread capture + markout − hedge cost − tax − inventory variance. Stress: expiry-day gamma, 2% index gap, vol spike.
- **Pitfalls**: assuming you'd have queue priority you wouldn't have (use queue_conservatism ≥ 1.5 initially); using your own theo as fill benchmark (circular); ignoring the pull-latency race (model: any resting quote still alive X µs after a futures move of ≥ Y ticks gets adversely filled with probability p — calibrate p from data: how often does the touch trade within X µs of a futures tick?).

---

## Strategy 2 — Lead-Lag / Latency Arbitrage (Stale-Quote Taking)
*Tower Research's classic franchise: the fastest correlated-instrument network wins.*

### The trade
Price discovery in India happens in the index future (and on expiry-adjacent days, in ATM options). Everything correlated to it — every option strike, the other index's instruments, ETFs, the cash basket, GIFT Nifty — reprices with a lag ranging from tens of microseconds (other co-lo players' quotes) to seconds (illiquid strikes, ETFs). The strategy: maintain a real-time predicted value for every laggard instrument as a function of the leader; when an observed quote deviates from predicted value by more than (spread + costs + buffer), take it.

Concrete Indian legs, ordered by competitiveness:

1. **Nifty futures → Nifty option strikes** (the bread-and-butter pick-off): futures tick up 3 points → every call is instantly worth +3×delta — lift any ask that hasn't moved. You need: per-strike live deltas (from your surface), wire-speed futures feed, and sub-100µs tick-to-trade. This is the most crowded race in the building.
2. **Nifty complex ↔ Sensex complex (NSE ↔ BSE)**: the two indices are ~99% correlated; BSE infrastructure and competition are thinner. Nifty futures move → Sensex options on BSE are stale for longer than Nifty options on NSE. Cross-exchange, so you carry legging risk and need co-lo at both.
3. **Futures → deep OTM / far-expiry strikes**: slower race (millisecond-scale), lower capacity, but win-rate is high because MMs quote these lazily. Watch LPP bands.
4. **GIFT Nifty (NSE IX) ↔ onshore Nifty** around the 9:15 open and global macro prints: GIFT trades nearly 21 hours; its level going into the onshore open and its reaction to overnight US moves leads the onshore opening auction and first minutes.
5. **Cash basket → futures** (slowest, mostly an input signal now): aggregated tick-by-tick moves of the top index constituents (HDFC Bank, Reliance, ICICI, Infosys…) nowcast the index ~constituent-latency ahead of the printed index value; use as a *feature* in the leader signal rather than a standalone arb.

### Where the edge comes from
Pure speed plus model quality: (a) the **leader signal** — not raw last-trade, but a filtered micro-price innovation (e.g., Kalman/EWMA of futures micro-price with trade-flow weighting) that distinguishes information from noise; (b) **per-instrument lag profiles** — empirically, each strike/instrument has a characteristic refresh latency distribution by market maker; (c) hardware — this strategy is the reason FPGAs exist.

### How to backtest it
The good news: this is the *most* backtestable HFT strategy, because you're a pure taker — no queue model needed, only latency honesty.

- **Step 1 — establish the lead-lag empirically**: synchronize leader and laggard feeds on exchange timestamps. Compute cross-correlation of mid-price returns at µs–ms horizons and Hasbrouck information share / Gonzalo-Granger decomposition. Deliverable: a lag distribution per laggard instrument — e.g., "after a 2-tick futures innovation, the ATM+200 call's quote updates within 300µs in 60% of events, within 2ms in 95%."
- **Step 2 — trigger replay with strict latency accounting**: for each leader innovation ≥ threshold at exchange time T: your decision happens at T + feed_latency; your order arrives at T + feed + compute + order_latency; the fill is whatever quote is *live at arrival time* — and only if it's still stale. Count the race as lost whenever the quote updated or another taker consumed it before your arrival (visible in book updates). Sweep your assumed total latency from 50µs to 2ms and plot P&L vs latency — this curve is the single most important output: it tells you whether the opportunity exists *at the latency you can actually achieve*, and it's brutally honest about whether you're competitive.
- **Step 3 — cost & risk overlay**: taker fills pay full spread-crossing + premium STT + charges; add slippage for size beyond displayed qty. For cross-exchange (NSE↔BSE) versions, model legging risk: probability the hedge leg moves before you complete it.
- **Pitfalls**: clock sync between feeds (exchange timestamps from two venues are not on the same clock — bound the skew and test sensitivity); selection bias (the stale quotes you "captured" in replay may have been cancelled in-flight — require the quote to be visibly alive at your arrival timestamp, and haircut win-rate by the fraction of races lost to faster takers, observable as the touch being consumed within your latency window).

---

## Strategy 3 — Index, Synthetic & ETF Arbitrage (Relative-Value Complex)
*Jane Street's global DNA applied to India: many instruments, one index, one fair value.*

### The trade
The same Nifty exposure trades simultaneously as: futures (3 expiries), synthetic futures at every strike (C − P + K·discount), boxes (pairs of synthetics), calendar spreads, the cash basket, and ETFs (NiftyBees etc.). Sensex duplicates this on BSE. All must satisfy no-arbitrage identities; deviations beyond the cost stack are harvestable:

1. **Put–call parity / synthetic vs future**: synthetic forward at strike K vs the listed future. Dislocations spike when one-sided retail flow hits a strike (e.g., heavy put buying cheapens the synthetic) and on expiry days. Execution: take the cheap leg(s), hedge with the future or an opposing synthetic; the position converges by construction at expiry — but you exit early (square off) to avoid exercise STT.
2. **Box spreads**: buy synthetic at K1, sell at K2; payoff is exactly (K2−K1) — a pure implied interest rate instrument. Boxes mispriced vs your funding rate are free carry; in India boxes also dislocate intraday under one-sided flow. Low risk, low capacity, computationally trivial to scan — an excellent first production strategy to validate your whole pipeline.
3. **Calendar spread arbitrage** in futures: front-vs-next basis vs cost-of-carry band; mean-reverts intraday. Post-2026 STT this needs wider bands but still trades around expiry roll periods when institutional roll flow is mechanical and predictable.
4. **ETF arb**: NiftyBees & peers vs futures/iNAV. Indian ETF books are thin, so this is small-capacity, but it's the least crowded corner and a profitable training ground. (Creation/redemption arb at scale needs AP status — Jane Street's global model — and is a later-stage build.)
5. **Cash–futures basis at size** is mostly a positional/treasury trade now (STT on the cash leg both sides + impact), used by HFT desks mainly as a *signal* (basis richness/cheapness predicts short-horizon index drift) rather than a standalone arb.

### Where the edge comes from
Not speed primarily — **completeness and cost precision**. You win by scanning *every* identity continuously, knowing your exact all-in cost per leg (the difference between a 0.8bp and 1.2bp cost assumption flips most signals), and executing multi-leg packages with minimal legging risk (NSE spread/combination order types help where available).

### How to backtest it
- Build the **identity monitor** first: a vectorized pass over historical chain data computing, at every tick, the deviation of each identity (parity per strike, each box, each calendar) from fair, *net of the full cost stack on the specific legs you'd trade*. Output: a time series of net-of-cost arbitrage opportunities — size, depth (how much displayed qty at the dislocated prices), duration (how long it persisted), and clustering (time of day, expiry proximity, vol regime).
- **Duration vs latency is the viability test**: if the median dislocation persists 50ms and your multi-leg round trip is 5ms, you can capture; if it persists 200µs you're racing Strategy-2 players for it and must price yourself accordingly.
- Then **event-replay the execution**: take the dislocations, simulate IOC legs with arrival latency against displayed depth, model partial completion (you get leg 1, leg 2's quote vanishes → you're directional for X ms — measure that cost from the data; it's the dominant risk).
- **Pitfalls**: using mid-prices to detect "arbitrage" that disappears at touchable prices (always compute on the executable side: buy at ask, sell at bid); ignoring early-exit reality (model exit at touchable prices T-minus, not hold-to-expiry); dividend and rate assumptions in parity (use the listed future to imply carry rather than assuming a rate).

---

## Strategy 4 — Short-Horizon Order-Book Alpha (Microstructure Stat-Arb)
*The AlphaGrep/Graviton/Quadeye profile: systematic signal factories on top of low-latency execution.*

### The trade
Predict the next 100ms–60s of mid-price movement of a liquid instrument (front Nifty future as signal source; liquid ATM weekly options as the *traded* instrument, for STT reasons) from microstructure features, and trade taker or maker depending on signal strength vs cost hurdle. This is "HFT stat-arb": dozens-to-hundreds of small signals combined in a linear/GBM/shallow-NN model, refit regularly.

The canonical feature families (all computable from L2 + trades):
- **Book imbalance** at multiple depths and its dynamics (level-1 OBI, depth-weighted imbalance, imbalance *changes*).
- **Trade flow**: signed volume (tick rule / aggressor flag), trade-size distribution shifts, sweep detection (multiple levels consumed in one event — informed flow).
- **Queue dynamics**: cancellation rates at the touch (MMs pulling = directional information), refill speed after depletion.
- **Cross-asset features**: the entire Strategy-2 leader set demoted to features — futures basis change, GIFT spread, constituent-basket nowcast, Sensex complex moves, USDINR (strong Nifty coupling), SGX/US futures in overlap hours.
- **Option-derived features**: net delta of aggressive options flow (retail call-buying waves create hedging pressure in futures), change in ATM IV, risk-reversal moves.
- **State/seasonality**: time-of-day (open/close/3:00–3:30 settlement window), expiry proximity (Tuesday/Thursday regimes), event flags.

### Where the edge comes from
Feature breadth + label engineering + refit discipline + an execution layer that doesn't give the alpha back. In India specifically, retail option flow is a strong, persistent, *detectable* informed-pressure signal on the future — a structural alpha source that barely exists in developed markets at this magnitude.

### How to backtest it
This is the cleanest place to apply the standard ML-for-trading discipline, then graduate to event replay:

- **Stage 1 — label engineering**: predict forward mid-price change over horizon h (grid: 100ms, 500ms, 2s, 10s, 60s), or triple-barrier labels (profit-take / stop / timeout) which map better to actual trading. Compute features strictly from data available *before* the label window (shift by your real feed latency).
- **Stage 2 — honest cross-validation**: walk-forward only; purge overlapping label windows and embargo around split boundaries (Lopez de Prado-style purged k-fold). Refit monthly/weekly as you would live. Metric: rank-IC of prediction vs realized move, and crucially **IC conditional on tradability** (signal strong enough to clear the cost hurdle — most of your IC lives in untradeable small predictions; only the tails pay).
- **Stage 3 — convert to a policy and event-replay it**: thresholded entries, position/inventory limits, cooloffs; run through the event-driven engine with latency + costs (the OBITakerStrategy in the framework is the skeleton: replace its EMA-OBI with your model score). Compare Stage-2 theoretical alpha vs Stage-3 net P&L — the gap decomposition (spread paid, latency slippage, tax, missed fills) tells you exactly where the strategy dies, if it dies.
- **Stage 4 — regime audit**: re-run by sub-period across the structural breaks (pre/post Nov-2024 weekly removal, pre/post Sep-2025 expiry swap, pre/post Apr-2026 STT). A signal that only worked pre-break is dead; do not average across breaks — that's the single most common way Indian backtests lie right now.
- **Pitfalls**: feature leakage via exchange-timestamp vs receive-timestamp confusion; autocorrelated samples inflating fit statistics; overfitting the threshold (tune on validation, report on test); ignoring that your own taker flow at size would have moved the book (cap assumed size at a fraction of displayed depth, e.g., 25–50%).

---

## Strategy 5 — Expiry-Day Flow & Settlement Dynamics
*The highest-Sharpe window of the week — and the one with a regulator now standing in it. Read the Jane Street case study below carefully.*

### The legitimate trade(s)
Every Tuesday (Nifty/NSE) and Thursday (Sensex/BSE), enormous gamma concentrates into a few hours, settlement is a *known function* (30-minute average, 3:00–3:30pm), and several flows become mechanical and predictable:

1. **Pinning/anti-pinning**: when dealers are net long gamma at a heavy strike, their hedging (sell rallies, buy dips) pins the index toward the strike into the afternoon; when net short gamma (common when retail has bought the wings and sold nothing), hedging *amplifies* moves. Estimate the market's net gamma profile from open interest + your flow classification, and trade the implied mean-reversion (pin) or breakout (anti-pin) regime in cheap same-day options.
2. **Settlement-window basis convergence**: from 3:00pm, the expiring synthetic converges to the running 30-minute average of the index — which becomes progressively *known* as the window elapses. By 3:20, ~2/3 of the settlement print is fixed arithmetic; expiring ITM options must converge to intrinsic-vs-running-average. Trading the residual mispricing against a futures hedge is a structural, fully legitimate convergence trade — it's also exactly the zone SEBI now watches hardest, so size discipline and clean economic rationale per trade matter.
3. **0-DTE vol structure**: same-day implied vol is systematically rich at the open (overnight gap premium) and decays in a predictable intraday pattern; theta-harvesting structures (short straddle/strangle with hard gamma stops, or calendarized against next week) monetize it. This is the institutionalized version of what half of Indian retail attempts; the edge is in the hedging discipline they lack.
4. **Roll-flow anticipation** (monthly): institutional futures roll concentrates in the last 2–3 sessions with predictable calendar-spread pressure patterns.

### ⚠️ Case study — what Jane Street did, and why you must not
This is the most instructive public document in Indian market microstructure: SEBI's interim order of 3 July 2025 (₹4,843.57 crore impounded; market-access ban until deposit; JS later deposited and resumed trading). Per the order, on 15+ analyzed expiry days JS ran an "**Intraday Index Manipulation**" pattern: in the morning, buy Bank Nifty constituent stocks + futures aggressively (₹4,370 crore on the flagship day, 17 Jan 2024; 15–25% of traded value in some constituents, lifting the index an estimated ~1%+), while simultaneously holding a far larger *bearish* options book (long puts / short calls — options exposures dwarfed the cash leg); then in the afternoon, dump the entire cash/futures inventory, pushing the index down into expiry settlement, profiting on the options at a multiple of the (deliberately accepted) losses on the cash leg. A second pattern, "**Extended Marking the Close**", involved concentrated selling in the last hours/minutes to soften the settlement print (e.g., ₹2,800 crore of futures selling on 10 Jul 2024 against a ₹44,000+ crore short options book). SEBI's analytical signature for manipulation: persistent loss-making in one market segment that is rational *only* because of its price impact on a much larger position in another segment, plus order placement concentrated at/above LTP (pushing, not passively providing).

Three lessons for your desk: **(1)** The flows existed because expiry-day price formation is genuinely fragile — that fragility is why the *legitimate* strategies above (pin/anti-pin, settlement convergence) have edge. **(2)** The line SEBI drew is about *causing* the move you profit from vs *forecasting* a move others cause. Your expiry models should be built explicitly on the latter; any strategy whose P&L depends on your own market impact on the index is radioactive. **(3)** Build the SEBI test into your own risk system: if any sub-book is persistently losing money in a way that's only rational because of cross-segment impact, kill it — the regulator now runs that exact query in near-real-time.

### How to backtest it
- **Event-study framework**: stack every expiry day (separately for Nifty/Tuesday and Sensex/Thursday, and separately pre/post Sep-2025 swap) in event time. Estimate: gamma-profile → afternoon-drift/pin relationships; settlement-window convergence speed of expiring synthetics; 0-DTE IV decay curves by time-of-day. Small-N problem (≈50 weekly expiries/year/index) → use both indices, use the pre-2024 multi-weekly era only for mechanism validation (different regime!), and report wide confidence intervals honestly.
- **Running-average settlement simulator**: rebuild the 3:00–3:30 average tick-by-tick; for the convergence trade, simulate the hedged book marking against the *partially-realized* average — this is pure arithmetic plus execution simulation, the most verifiable strategy in this memo.
- **Pitfalls**: regime breaks (the Nov-2024 and Sep-2025 changes altered expiry-day microstructure fundamentally — Bank Nifty weekly patterns do NOT transfer to the current Nifty Tuesday); crowding (post-Jane-Street, settlement-window behavior visibly changed as the largest player withdrew — your 2023–24 backtest overstates current dislocation sizes); your own impact (these are capacity-constrained trades; cap simulated size aggressively).

---

## Strategy 6 — Cross-Index & Dispersion Statistical Arbitrage
*The capacity diversifier: slower (seconds–minutes), runs on the same infrastructure, decorrelated P&L.*

### The trade
Two related books:

1. **Index-pair relative value**: Nifty, Bank Nifty, FinNifty, Sensex are tightly linked (Bank Nifty constituents ≈ FinNifty subset ≈ ~35% of Nifty; Sensex ≈ Nifty minus a few names). Build beta-hedged spreads (e.g., Bank Nifty vs β·Nifty via monthly futures or deep-ITM/synthetic options; Nifty vs Sensex *across exchanges*) and trade intraday mean-reversion with z-score bands, with regime filters (spreads trend, not revert, on bank-specific news — RBI days, earnings — so gate the model on an event calendar and realized-correlation monitor). The NSE–BSE pair doubles as the slow cousin of Strategy 2's cross-exchange leg.
2. **Index-vol dispersion**: implied correlation trade — sell index vol, buy constituent vol (or inverse) when index IV is rich/cheap vs the weighted constituent IV basket. In India the heavy retail demand for *index* options vs thin single-stock option liquidity makes implied correlation structurally elevated and mean-reverting; the constraint is single-stock option liquidity (only the top ~15–20 names are tradable at size) and stock options being physically settled (manage early exercise/delivery risk — exit before expiry week).

### How to backtest it
Standard stat-arb discipline at intraday frequency: cointegration/spread-stationarity tests per regime; walk-forward z-score parameters; transaction-cost-aware entry bands (the band must exceed the *four-leg* cost stack); event-calendar gating. For dispersion: reconstruct implied correlation from historical chain IVs, backtest band-trading on it with vega-weighted legs, and stress correlated drawdowns (dispersion books die in crashes when correlation → 1 — size for that day). The event-driven engine matters less here; honest cost modeling and regime discipline matter more.

---

## The Backtesting Playbook (how all of this plugs into your stack)

You already have `hft_backtest.py` (event-driven engine: latency model, queue-position maker fills, post-Apr-2026 Indian cost model). Here's the full methodology around it.

### The three-layer pipeline (institutional standard)
1. **Layer 1 — Vectorized signal research** (pandas/polars over the full history): lead-lag estimation, identity monitors, ML feature/label work, event studies. Fast iteration; *no* fill simulation; output = candidate signals with cost-aware theoretical alpha.
2. **Layer 2 — Event-driven replay** (the engine): one strategy at a time, true latency accounting, queue-conservative maker fills, full cost stack, OTR tracking, markout reports. Output = net P&L, alpha-to-net-P&L gap decomposition, latency-sensitivity curve (P&L vs assumed latency — produce this for *every* strategy; it's your competitiveness map).
3. **Layer 3 — Shadow/live calibration**: run the strategy live, orders to exchange in minimum size (or order-entry without fills where supported); compare realized fills/queue outcomes vs the simulator's predictions; recalibrate `queue_conservatism`, pick-off probabilities, and impact. *No backtest number is trusted until Layer 3 confirms the fill model within tolerance.* Budget real money for this — it's tuition.

### Data spec (what to buy/capture)
Tick-by-tick order-level data (NSE TBT feed) or at minimum full-depth snapshots + trades, exchange-timestamped, for: index futures (all expiries), full option chains (all strikes — including ones that *existed historically but are gone*: avoid strike survivorship), cash ticks for top constituents, Sensex complex from BSE, GIFT Nifty, USDINR futures. Store raw; never backtest on bar data for anything in this memo except Strategy 6.

### The five Indian-specific pitfalls (worth more than any signal)
1. **Regime breaks**: Nov-2024 (weekly consolidation), Sep-2025 (expiry-day swap), Apr-2026 (STT), Jul-2025 (Jane Street exit changed expiry-day microstructure). Every backtest must be reported per-regime; cross-break averages are fiction. Always re-run with the *current* cost model over old data.
2. **Queue optimism**: the default killer of MM backtests. Start with `queue_conservatism = 1.5–2.0` and let Layer 3 earn it down.
3. **Mid-price arbitrage mirages**: detect every opportunity at executable (touch) prices, sized to displayed depth fractions.
4. **Clock discipline**: exchange timestamp ≠ your receive timestamp ≠ your decision timestamp; cross-venue clocks differ. Thread latency through every join.
5. **Your own footprint**: any strategy whose backtest P&L scales linearly with size is mismodeled. Impose depth-fraction caps and concave capacity curves; for expiry strategies, cap hard.

### Suggested build order
Box/parity scanner (Strategy 3 — validates data + costs + execution with near-zero model risk) → lead-lag measurement (Strategy 2 Layer-1 — tells you if your latency is competitive *before* you spend on it) → options MM on the less-crowded venue/wings (Strategy 1) → microstructure alpha (Strategy 4) → expiry book (Strategy 5) and dispersion (Strategy 6) once the first three are calibrated live.

### Compliance guardrails (non-negotiable, post-2025 environment)
Exchange approval per algo; OTR monitoring in the engine and in production; LPP-band-aware order logic; the "SEBI test" kill-switch (no sub-book that loses persistently in one segment to profit cross-segment via impact); audit-grade logging of every order decision with the signal that caused it. SEBI's surveillance posture after the Jane Street order is real-time and cash-derivatives-linked, especially in the 3:00–3:30 settlement window.

---

*Engine reference: `hft_backtest.py` — extend `BacktestEngine` to multi-instrument (shared clock, per-instrument books/costs) for Strategies 2, 3, 5, 6; the single-instrument version suffices for Strategies 1 (per-strike) and 4.*
