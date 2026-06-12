from __future__ import annotations

import argparse

from adapters.broker import run_calibration_report
from adapters.orders import OrderStagingLimits, write_staged_orders
from data.chains import load_option_chain_csv
from data.diagnostics import chain_diagnostics, tick_diagnostics, write_diagnostics
from data.loaders import load_tick_csv
from reports.proof import ProofThresholds, write_proof_report
from reports.quote_risk import QuoteRiskThresholds, write_quote_risk_report
from reports.stress import StressConfig, write_stress_report
from reports.sweeps import write_sweep_comparison
from research.run_leadlag import run_leadlag
from scanners.run_parity_box import run_scan
from strategies.run_leadlag_replay import run_leadlag_replay
from strategies.run_leadlag_sweep import run_leadlag_sweep
from strategies.run_parity_replay import run_parity_replay
from strategies.run_parity_sweep import run_parity_sweep
from strategies.run_surface_mm_replay import SurfaceMMReplayConfig, run_surface_mm_replay
from strategies.run_surface_mm_sweep import run_surface_mm_sweep
from strategies.run_surface_quotes import run_surface_quote_generation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hft", description="India HFT research command runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan-parity-box", help="Run executable parity/box scanner.")
    scan.add_argument("--chain", required=True)
    scan.add_argument("--futures", required=True)
    scan.add_argument("--out", required=True)
    scan.add_argument("--no-filter-session", action="store_true")
    scan.add_argument("--asof-latency-ns", type=int, default=0)
    scan.add_argument("--depth-fraction", type=float, default=0.25)

    parity = sub.add_parser("replay-parity", help="Replay parity taker strategy.")
    parity.add_argument("--chain", required=True)
    parity.add_argument("--futures", required=True)
    parity.add_argument("--out", required=True)
    parity.add_argument("--no-filter-session", action="store_true")
    parity.add_argument("--signal-limit", type=int, default=None)
    parity.add_argument("--depth-fraction", type=float, default=0.25)
    parity.add_argument("--feed-latency-us", type=float, default=0.0)
    parity.add_argument("--order-latency-us", type=float, default=0.0)

    leadlag = sub.add_parser("measure-leadlag", help="Measure lead-lag relationship.")
    leadlag.add_argument("--leader", required=True)
    leadlag.add_argument("--laggard", required=True)
    leadlag.add_argument("--out", required=True)
    leadlag.add_argument("--no-filter-session", action="store_true")
    leadlag.add_argument("--leader-tick-size", type=float, default=0.05)
    leadlag.add_argument("--laggard-tick-size", type=float, default=0.05)
    leadlag.add_argument("--delta", type=float, default=1.0)
    leadlag.add_argument("--innovation-ticks", type=float, default=2.0)

    leadlag_replay = sub.add_parser("replay-leadlag", help="Replay lead-lag taker strategy.")
    leadlag_replay.add_argument("--leader", required=True)
    leadlag_replay.add_argument("--laggard", required=True)
    leadlag_replay.add_argument("--out", required=True)
    leadlag_replay.add_argument("--no-filter-session", action="store_true")
    leadlag_replay.add_argument("--leader-tick", type=float, default=0.05)
    leadlag_replay.add_argument("--laggard-tick", type=float, default=0.05)
    leadlag_replay.add_argument("--delta", type=float, default=1.0)
    leadlag_replay.add_argument("--trigger-ticks", type=float, default=3.0)
    leadlag_replay.add_argument("--qty", type=int, default=75)

    calibration = sub.add_parser("calibrate", help="Compare simulated orders to live fills.")
    calibration.add_argument("--simulated-orders", required=True)
    calibration.add_argument("--live-fills", required=True)
    calibration.add_argument("--out", required=True)
    calibration.add_argument("--adapter", default="normalized")

    diag_ticks = sub.add_parser("diagnose-ticks", help="Run data-quality diagnostics for top-of-book ticks.")
    diag_ticks.add_argument("--ticks", required=True)
    diag_ticks.add_argument("--out", required=True)
    diag_ticks.add_argument("--tick-size", type=float, default=None)
    diag_ticks.add_argument("--market", default="india_nse_index_derivatives")
    diag_ticks.add_argument("--no-filter-session", action="store_true")

    diag_chain = sub.add_parser("diagnose-chain", help="Run data-quality diagnostics for option-chain snapshots.")
    diag_chain.add_argument("--chain", required=True)
    diag_chain.add_argument("--out", required=True)
    diag_chain.add_argument("--tick-size", type=float, default=None)
    diag_chain.add_argument("--market", default="india_nse_index_derivatives")
    diag_chain.add_argument("--no-filter-session", action="store_true")

    proof = sub.add_parser("proof-report", help="Evaluate replay output folders against proof thresholds.")
    proof.add_argument("--runs", nargs="+", required=True)
    proof.add_argument("--out", required=True)
    proof.add_argument("--run-name", action="append", dest="run_names")
    proof.add_argument("--min-net-pnl", type=float, default=0.0)
    proof.add_argument("--min-fills", type=int, default=1)
    proof.add_argument("--max-drawdown", type=float, default=None)
    proof.add_argument("--max-otr", type=float, default=None)
    proof.add_argument("--min-maker-share", type=float, default=None)
    proof.add_argument("--min-worst-regime-equity-change", type=float, default=None)
    proof.add_argument("--min-markout-mean", type=float, default=None)
    proof.add_argument("--min-spread-net", type=float, default=None)
    proof.add_argument("--fail-on-breach", action="store_true")

    leadlag_sweep = sub.add_parser("sweep-leadlag", help="Run lead-lag replay robustness sweep.")
    leadlag_sweep.add_argument("--leader", required=True)
    leadlag_sweep.add_argument("--laggard", required=True)
    leadlag_sweep.add_argument("--out", required=True)
    leadlag_sweep.add_argument("--no-filter-session", action="store_true")
    leadlag_sweep.add_argument("--leader-tick", type=float, default=0.05)
    leadlag_sweep.add_argument("--laggard-tick", type=float, default=0.05)
    leadlag_sweep.add_argument("--delta", type=float, default=1.0)
    leadlag_sweep.add_argument("--trigger-ticks", nargs="+", required=True, type=float)
    leadlag_sweep.add_argument("--feed-latency-us", nargs="+", default=[0.0], type=float)
    leadlag_sweep.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    leadlag_sweep.add_argument("--qty", type=int, default=75)
    leadlag_sweep.add_argument("--flat-after-ns", type=int, default=500_000_000)
    leadlag_sweep.add_argument("--cooloff-ns", type=int, default=0)
    leadlag_sweep.add_argument("--markout-horizons-ns", nargs="+", default=None, type=int)
    leadlag_sweep.add_argument("--min-net-pnl", type=float, default=0.0)
    leadlag_sweep.add_argument("--min-fills", type=int, default=1)
    leadlag_sweep.add_argument("--max-drawdown", type=float, default=None)
    leadlag_sweep.add_argument("--max-otr", type=float, default=None)
    leadlag_sweep.add_argument("--min-markout-mean", type=float, default=None)
    leadlag_sweep.add_argument("--fail-on-breach", action="store_true")

    parity_sweep = sub.add_parser("sweep-parity", help="Run parity replay robustness sweep.")
    parity_sweep.add_argument("--chain", required=True)
    parity_sweep.add_argument("--futures", required=True)
    parity_sweep.add_argument("--out", required=True)
    parity_sweep.add_argument("--no-filter-session", action="store_true")
    parity_sweep.add_argument("--depth-fraction", nargs="+", required=True, type=float)
    parity_sweep.add_argument("--asof-latency-ns", nargs="+", default=[0], type=int)
    parity_sweep.add_argument("--feed-latency-us", nargs="+", default=[0.0], type=float)
    parity_sweep.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    parity_sweep.add_argument("--signal-limit", type=int, default=None)
    parity_sweep.add_argument("--max-signal-age-ns", type=int, default=1_000_000)
    parity_sweep.add_argument("--max-qty", type=int, default=None)
    parity_sweep.add_argument("--min-net-pnl", type=float, default=0.0)
    parity_sweep.add_argument("--min-fills", type=int, default=1)
    parity_sweep.add_argument("--max-drawdown", type=float, default=None)
    parity_sweep.add_argument("--max-otr", type=float, default=None)
    parity_sweep.add_argument("--min-spread-net", type=float, default=None)
    parity_sweep.add_argument("--fail-on-breach", action="store_true")

    surface_mm_sweep = sub.add_parser("sweep-surface-mm", help="Run surface MM replay robustness sweep.")
    surface_mm_sweep.add_argument("--quotes", required=True)
    surface_mm_sweep.add_argument("--chain", required=True)
    surface_mm_sweep.add_argument("--out", required=True)
    surface_mm_sweep.add_argument("--no-filter-session", action="store_true")
    surface_mm_sweep.add_argument("--quote-ttl-ns", nargs="+", required=True, type=int)
    surface_mm_sweep.add_argument("--order-latency-us", nargs="+", default=[0.0], type=float)
    surface_mm_sweep.add_argument("--fill-depth-fraction", nargs="+", required=True, type=float)
    surface_mm_sweep.add_argument("--markout-horizon-ns", nargs="+", default=[1_000_000_000], type=int)
    surface_mm_sweep.add_argument("--lot-size", type=int, default=75)
    surface_mm_sweep.add_argument("--option-tick", type=float, default=0.05)
    surface_mm_sweep.add_argument("--contract-multiplier", type=float, default=1.0)
    surface_mm_sweep.add_argument("--max-quotes", type=int, default=None)
    surface_mm_sweep.add_argument("--min-net-pnl", type=float, default=0.0)
    surface_mm_sweep.add_argument("--min-fills", type=int, default=1)
    surface_mm_sweep.add_argument("--max-drawdown", type=float, default=None)
    surface_mm_sweep.add_argument("--max-otr", type=float, default=None)
    surface_mm_sweep.add_argument("--min-maker-share", type=float, default=1.0)
    surface_mm_sweep.add_argument("--min-markout-mean", type=float, default=None)
    surface_mm_sweep.add_argument("--fail-on-breach", action="store_true")

    compare_sweeps = sub.add_parser("compare-sweeps", help="Rank scenarios across multiple sweep outputs.")
    compare_sweeps.add_argument("--sweeps", nargs="+", required=True)
    compare_sweeps.add_argument("--out", required=True)
    compare_sweeps.add_argument("--label", action="append", dest="labels")
    compare_sweeps.add_argument("--group-cols", nargs="+", default=None)
    compare_sweeps.add_argument("--min-pass-rate", type=float, default=1.0)
    compare_sweeps.add_argument("--min-sweeps", type=int, default=1)
    compare_sweeps.add_argument("--min-median-net-pnl", type=float, default=0.0)
    compare_sweeps.add_argument("--max-worst-drawdown", type=float, default=None)
    compare_sweeps.add_argument("--fail-on-breach", action="store_true")

    stress = sub.add_parser("stress-replay", help="Stress replay outputs for extra costs and slippage.")
    stress.add_argument("--runs", nargs="+", required=True)
    stress.add_argument("--out", required=True)
    stress.add_argument("--run-name", action="append", dest="run_names")
    stress.add_argument("--cost-multiplier", nargs="+", default=[1.0], type=float)
    stress.add_argument("--slippage-ticks", nargs="+", default=[0.0], type=float)
    stress.add_argument("--adverse-bps", nargs="+", default=[0.0], type=float)
    stress.add_argument("--tick-size", type=float, default=0.05)
    stress.add_argument("--contract-multiplier", type=float, default=1.0)
    stress.add_argument("--min-net-pnl", type=float, default=0.0)
    stress.add_argument("--min-fills", type=int, default=1)
    stress.add_argument("--max-drawdown", type=float, default=None)
    stress.add_argument("--fail-on-breach", action="store_true")

    surface_quote = sub.add_parser("quote-surface", help="Generate surface-driven market-making quotes.")
    surface_quote.add_argument("--chain", required=True)
    surface_quote.add_argument("--futures", required=True)
    surface_quote.add_argument("--out", required=True)
    surface_quote.add_argument("--no-filter-session", action="store_true")
    surface_quote.add_argument("--asof-latency-ns", type=int, default=0)
    surface_quote.add_argument("--tte-years", type=float, default=30 / 365)
    surface_quote.add_argument("--tick-size", type=float, default=0.05)
    surface_quote.add_argument("--lot-size", type=int, default=75)
    surface_quote.add_argument("--quote-lots", type=int, default=1)
    surface_quote.add_argument("--edge-ticks", type=float, default=2.0)
    surface_quote.add_argument("--inventory-skew-ticks-per-lot", type=float, default=0.5)
    surface_quote.add_argument("--max-market-spread-ticks", type=float, default=None)
    surface_quote.add_argument("--max-quotes-per-snapshot", type=int, default=None)
    surface_quote.add_argument("--max-snapshots", type=int, default=None)

    quote_review = sub.add_parser("review-quotes", help="Review generated surface quotes for MM risk hygiene.")
    quote_review.add_argument("--quotes", required=True)
    quote_review.add_argument("--out", required=True)
    quote_review.add_argument("--min-quotes", type=int, default=1)
    quote_review.add_argument("--min-instruments", type=int, default=1)
    quote_review.add_argument("--max-marketable-quotes", type=int, default=0)
    quote_review.add_argument("--min-quote-edge", type=float, default=0.0)
    quote_review.add_argument("--min-bid-share", type=float, default=0.25)
    quote_review.add_argument("--max-bid-share", type=float, default=0.75)
    quote_review.add_argument("--max-market-spread-ticks", type=float, default=None)
    quote_review.add_argument("--max-quotes-per-instrument", type=int, default=None)
    quote_review.add_argument("--fail-on-breach", action="store_true")

    surface_mm = sub.add_parser("replay-surface-mm", help="Replay passive surface market-making quotes.")
    surface_mm.add_argument("--quotes", required=True)
    surface_mm.add_argument("--chain", required=True)
    surface_mm.add_argument("--out", required=True)
    surface_mm.add_argument("--no-filter-session", action="store_true")
    surface_mm.add_argument("--order-latency-us", type=float, default=0.0)
    surface_mm.add_argument("--quote-ttl-ns", type=int, default=1_000_000_000)
    surface_mm.add_argument("--markout-horizon-ns", type=int, default=1_000_000_000)
    surface_mm.add_argument("--fill-depth-fraction", type=float, default=1.0)
    surface_mm.add_argument("--lot-size", type=int, default=75)
    surface_mm.add_argument("--option-tick", type=float, default=0.05)
    surface_mm.add_argument("--contract-multiplier", type=float, default=1.0)
    surface_mm.add_argument("--max-quotes", type=int, default=None)

    order_stage = sub.add_parser("stage-orders", help="Stage broker-neutral orders after pre-trade checks.")
    order_stage.add_argument("--orders", required=True)
    order_stage.add_argument("--out", required=True)
    order_stage.add_argument("--source", default="orders", choices=["orders", "surface_quotes"])
    order_stage.add_argument("--adapter", default="normalized")
    order_stage.add_argument("--max-order-qty", type=int, default=None)
    order_stage.add_argument("--max-notional", type=float, default=None)
    order_stage.add_argument("--price-band-pct", type=float, default=None)
    order_stage.add_argument("--max-orders", type=int, default=None)
    order_stage.add_argument("--contract-multiplier", type=float, default=1.0)
    order_stage.add_argument("--allow-marketable", action="store_true")
    order_stage.add_argument("--fail-on-reject", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "scan-parity-box":
        result = run_scan(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            asof_latency_ns=args.asof_latency_ns,
            depth_fraction=args.depth_fraction,
        )
        print(result.report.to_string(index=False))
        return 0
    if args.command == "replay-parity":
        result = run_parity_replay(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            signal_limit=args.signal_limit,
            depth_fraction=args.depth_fraction,
            feed_latency_us=args.feed_latency_us,
            order_latency_us=args.order_latency_us,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "measure-leadlag":
        result = run_leadlag(
            leader_path=args.leader,
            laggard_path=args.laggard,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            leader_tick_size=args.leader_tick_size,
            laggard_tick_size=args.laggard_tick_size,
            delta=args.delta,
            innovation_ticks=args.innovation_ticks,
        )
        print(result.summary.latency_curve.to_string(index=False))
        return 0
    if args.command == "replay-leadlag":
        result = run_leadlag_replay(
            leader_path=args.leader,
            laggard_path=args.laggard,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            leader_tick=args.leader_tick,
            laggard_tick=args.laggard_tick,
            delta=args.delta,
            trigger_ticks=args.trigger_ticks,
            qty=args.qty,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "calibrate":
        _, summary = run_calibration_report(
            simulated_orders_path=args.simulated_orders,
            live_fills_path=args.live_fills,
            output_dir=args.out,
            adapter=args.adapter,
        )
        print(summary.to_string(index=False))
        return 0
    if args.command == "diagnose-ticks":
        ticks = load_tick_csv(args.ticks, filter_session=not args.no_filter_session, market=args.market).data
        result = write_diagnostics(tick_diagnostics(ticks, tick_size=args.tick_size, market=args.market), args.out)
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "diagnose-chain":
        chain = load_option_chain_csv(args.chain, filter_session=not args.no_filter_session, market=args.market).data
        result = write_diagnostics(chain_diagnostics(chain, tick_size=args.tick_size, market=args.market), args.out)
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "proof-report":
        result = write_proof_report(
            args.runs,
            output_dir=args.out,
            run_names=args.run_names,
            thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_maker_share=args.min_maker_share,
                min_worst_regime_equity_change=args.min_worst_regime_equity_change,
                min_markout_mean=args.min_markout_mean,
                min_spread_net=args.min_spread_net,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "sweep-leadlag":
        result = run_leadlag_sweep(
            leader_path=args.leader,
            laggard_path=args.laggard,
            output_dir=args.out,
            trigger_ticks_values=args.trigger_ticks,
            feed_latency_us_values=args.feed_latency_us,
            order_latency_us_values=args.order_latency_us,
            filter_session=not args.no_filter_session,
            leader_tick=args.leader_tick,
            laggard_tick=args.laggard_tick,
            delta=args.delta,
            qty=args.qty,
            flat_after_ns=args.flat_after_ns,
            cooloff_ns=args.cooloff_ns,
            markout_horizons_ns=args.markout_horizons_ns,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_markout_mean=args.min_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.proof.passed else 0
    if args.command == "sweep-parity":
        result = run_parity_sweep(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            depth_fraction_values=args.depth_fraction,
            asof_latency_ns_values=args.asof_latency_ns,
            feed_latency_us_values=args.feed_latency_us,
            order_latency_us_values=args.order_latency_us,
            filter_session=not args.no_filter_session,
            signal_limit=args.signal_limit,
            max_signal_age_ns=args.max_signal_age_ns,
            max_qty=args.max_qty,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_spread_net=args.min_spread_net,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.proof.passed else 0
    if args.command == "sweep-surface-mm":
        result = run_surface_mm_sweep(
            quotes_path=args.quotes,
            chain_path=args.chain,
            output_dir=args.out,
            quote_ttl_ns_values=args.quote_ttl_ns,
            order_latency_us_values=args.order_latency_us,
            fill_depth_fraction_values=args.fill_depth_fraction,
            markout_horizon_ns_values=args.markout_horizon_ns,
            filter_session=not args.no_filter_session,
            lot_size=args.lot_size,
            option_tick=args.option_tick,
            contract_multiplier=args.contract_multiplier,
            max_quotes=args.max_quotes,
            proof_thresholds=ProofThresholds(
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
                max_otr=args.max_otr,
                min_maker_share=args.min_maker_share,
                min_markout_mean=args.min_markout_mean,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.proof.passed else 0
    if args.command == "compare-sweeps":
        result = write_sweep_comparison(
            args.sweeps,
            output_dir=args.out,
            labels=args.labels,
            group_cols=args.group_cols,
            min_pass_rate=args.min_pass_rate,
            min_sweeps=args.min_sweeps,
            min_median_net_pnl=args.min_median_net_pnl,
            max_worst_drawdown=args.max_worst_drawdown,
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.has_selection else 0
    if args.command == "stress-replay":
        result = write_stress_report(
            args.runs,
            output_dir=args.out,
            run_names=args.run_names,
            config=StressConfig(
                cost_multipliers=args.cost_multiplier,
                slippage_ticks=args.slippage_ticks,
                adverse_bps=args.adverse_bps,
                tick_size=args.tick_size,
                contract_multiplier=args.contract_multiplier,
                min_net_pnl=args.min_net_pnl,
                min_fills=args.min_fills,
                max_drawdown=args.max_drawdown,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "quote-surface":
        result = run_surface_quote_generation(
            chain_path=args.chain,
            futures_path=args.futures,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            asof_latency_ns=args.asof_latency_ns,
            tte_years=args.tte_years,
            tick_size=args.tick_size,
            lot_size=args.lot_size,
            quote_lots=args.quote_lots,
            edge_ticks=args.edge_ticks,
            inventory_skew_ticks_per_lot=args.inventory_skew_ticks_per_lot,
            max_market_spread_ticks=args.max_market_spread_ticks,
            max_quotes_per_snapshot=args.max_quotes_per_snapshot,
            max_snapshots=args.max_snapshots,
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "review-quotes":
        result = write_quote_risk_report(
            args.quotes,
            output_dir=args.out,
            thresholds=QuoteRiskThresholds(
                min_quotes=args.min_quotes,
                min_instruments=args.min_instruments,
                max_marketable_quotes=args.max_marketable_quotes,
                min_quote_edge=args.min_quote_edge,
                min_bid_share=args.min_bid_share,
                max_bid_share=args.max_bid_share,
                max_market_spread_ticks=args.max_market_spread_ticks,
                max_quotes_per_instrument=args.max_quotes_per_instrument,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_breach and not result.passed else 0
    if args.command == "replay-surface-mm":
        result = run_surface_mm_replay(
            quotes_path=args.quotes,
            chain_path=args.chain,
            output_dir=args.out,
            filter_session=not args.no_filter_session,
            config=SurfaceMMReplayConfig(
                order_latency_us=args.order_latency_us,
                quote_ttl_ns=args.quote_ttl_ns,
                markout_horizon_ns=args.markout_horizon_ns,
                fill_depth_fraction=args.fill_depth_fraction,
                lot_size=args.lot_size,
                option_tick=args.option_tick,
                contract_multiplier=args.contract_multiplier,
                max_quotes=args.max_quotes,
            ),
        )
        print(result.summary.to_string(index=False))
        return 0
    if args.command == "stage-orders":
        result = write_staged_orders(
            args.orders,
            output_dir=args.out,
            source=args.source,
            adapter=args.adapter,
            limits=OrderStagingLimits(
                max_order_qty=args.max_order_qty,
                max_notional=args.max_notional,
                price_band_pct=args.price_band_pct,
                max_orders=args.max_orders,
                contract_multiplier=args.contract_multiplier,
                require_nonmarketable=not args.allow_marketable,
            ),
        )
        print(result.summary.to_string(index=False))
        return 2 if args.fail_on_reject and not result.passed else 0
    raise RuntimeError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
