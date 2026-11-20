# Checks and comparison with the paper

The evidence behind the decisions: tests, numbers from the runs, and how the results compare with the paper. D numbers refer to `../decisions.md` (D1-D37) and to the decisions file of each later part, e.g. `../volatility_provider/decisions.md` (D38 on); P numbers refer to `../paper_model.md`.

The checks are split by part, one file each. Section numbers run across all the files and do not change, so a reference such as "validation, section 12" can be found from the table below. Results of the volatility provider trials (D39, D40) are recorded in `../volatility_provider/decisions.md`.

| Section | Topic | File |
|---|---|---|
| 1 | 1. Model checks | [`phase1_reproduction.md`](phase1_reproduction.md) |
| 2 | 2. Choice of price (D11) | [`phase1_reproduction.md`](phase1_reproduction.md) |
| 3 | 3. Fig. 2 | [`phase1_reproduction.md`](phase1_reproduction.md) |
| 4 | 4. Fig. 3 | [`phase1_reproduction.md`](phase1_reproduction.md) |
| 5 | 5. Fig. 4 | [`phase1_reproduction.md`](phase1_reproduction.md) |
| 6 | 6. Code versions | [`phase1_reproduction.md`](phase1_reproduction.md) |
| 7 | 7. Bugs found and fixed | [`phase1_reproduction.md`](phase1_reproduction.md) |
| 8 | 8. Shock test on the basic model | [`shock_tests.md`](shock_tests.md) |
| 9 | 9. Shock test with different provider types (first look) | [`shock_tests.md`](shock_tests.md) |
| 10 | 10. Shock test with value traders | [`shock_tests.md`](shock_tests.md) |
| 11 | 11. What value traders do to the price in normal times (first look) | [`value_traders.md`](value_traders.md) |
| 12 | 12. Value trader sweep, and the switch to a true value | [`value_traders.md`](value_traders.md) |
| 13 | 13. Agent types in normal times (no value traders) | [`agent_types.md`](agent_types.md) |
| 14 | 14. Value trader sweep with the true value: final results | [`value_traders.md`](value_traders.md) |
| 15 | 15. Momentum traders (first look) | [`momentum_traders.md`](momentum_traders.md) |
| 16 | 16. News event study (first look) | [`news_and_poisson.md`](news_and_poisson.md) |
| 17 | 17. Poisson trader event study (first look) | [`news_and_poisson.md`](news_and_poisson.md) |
| 18 | 18. Momentum trader sweep (cluster) | [`momentum_traders.md`](momentum_traders.md) |
| 19 | 19. Phase diagram sweep (cluster) | [`phase_diagram.md`](phase_diagram.md) |
