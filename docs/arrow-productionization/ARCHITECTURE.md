# Production Architecture

```text
Arrow/fake transport -> decoder -> normalizer -> event queue -> recorder
                                                      |
                                                      v
Market event -> causal features -> AlphaForecast -> portfolio -> OrderIntent
                                                               |
                                                               v
                  kill switch <- independent risk -> ValidatedOrder
                                                               |
                                                               v
                  journal <- OMS -> execution policy -> router -> BrokerAdapter
                                                               |
                                                     Arrow adapter (disabled)
```

Broker-neutral contracts live in `trading/contracts.py`. Strategies may depend on those contracts but must not import `brokers.arrow`. Socket callbacks decode, normalize, and enqueue; they never invoke strategy code.

The Arrow adapter accepts transports as dependencies, enabling deterministic authentication, disconnect, retry, malformed-packet, duplicate, rate-limit, and lifecycle tests without credentials. Production order methods fail closed pending external certification. Shadow execution shares the feature/risk/OMS path but has no broker reference.

Every boundary uses explicit timestamps rather than a generic `timestamp`. `TraceContext` carries session, strategy, signal, intent, client, broker, and exchange identifiers through the path.

The normalized recorder uses Hive-style partitions (`date/exchange/segment/instrument`) and newline-delimited append-only records. Parquet compaction can be added downstream without changing the capture contract.
