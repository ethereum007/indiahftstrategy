import json

import pandas as pd

from hft_cli import main
from strategies.run_imbalance_replay import run_imbalance_replay


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def imbalance_ticks():
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    ts2 = ns_ist("2026-06-10 09:15:00.000200")
    ts3 = ns_ist("2026-06-10 09:15:00.000300")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts3, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
        ]
    )


def write_candidate(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "imbalance",
                "failed_checks": [],
                "replay_defaults": {
                    "entry_imbalance": 0.6,
                    "min_microprice_edge_ticks": 0.25,
                    "hold_ns": 1_000_000,
                    "markout_horizons_ns": [100_000],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_run_imbalance_replay_writes_outputs_and_signals(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_replay"
    imbalance_ticks().to_csv(ticks_path, index=False)

    replay = run_imbalance_replay(
        ticks_path=ticks_path,
        output_dir=out_dir,
        tick_size=0.05,
        qty=75,
        entry_imbalance=0.6,
        exit_imbalance=0.15,
        min_microprice_edge_ticks=0.25,
        hold_ns=1_000_000,
        cooloff_ns=1_000_000,
        markout_horizons_ns=[100_000],
    )

    assert replay.result.engine.orders_sent == 2
    assert replay.summary.iloc[0]["fills"] == 2
    assert set(replay.signals["action"]) == {"entry", "exit_decay"}
    assert not replay.markouts.empty
    assert (out_dir / "fills.csv").exists()
    assert (out_dir / "equity.csv").exists()
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "signals.csv").exists()
    assert (out_dir / "markouts.csv").exists()
    assert (out_dir / "pnl_decomposition.csv").exists()
    assert (out_dir / "spread_pairs.csv").exists()
    assert (out_dir / "spread_summary.csv").exists()
    assert (out_dir / "residual_inventory.csv").exists()
    assert (out_dir / "fills_by_regime.csv").exists()
    assert (out_dir / "equity_by_regime.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_replay_writes_summary(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_replay"
    imbalance_ticks().to_csv(ticks_path, index=False)

    code = main(
        [
            "replay-imbalance",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "--exit-imbalance",
            "0.15",
            "--min-microprice-edge-ticks",
            "0.25",
            "--hold-ns",
            "1000000",
            "--cooloff-ns",
            "1000000",
        ]
    )

    summary = pd.read_csv(out_dir / "summary.csv")
    assert code == 0
    assert int(summary.loc[0, "fills"]) == 2


def test_cli_imbalance_replay_uses_candidate_config(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    candidate_dir = tmp_path / "edge_sweep"
    out_dir = tmp_path / "imbalance_replay"
    imbalance_ticks().to_csv(ticks_path, index=False)
    write_candidate(candidate_dir)

    code = main(
        [
            "replay-imbalance",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--candidate-config",
            str(candidate_dir),
            "--cooloff-ns",
            "1000000",
        ]
    )

    summary = pd.read_csv(out_dir / "summary.csv")
    markouts = pd.read_csv(out_dir / "markouts.csv")
    assert code == 0
    assert int(summary.loc[0, "fills"]) == 2
    assert set(markouts["horizon_ns"]) == {100_000}
