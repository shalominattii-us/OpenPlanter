# Cybercore Interoperability Fixture

This directory contains the versioned 2026-08-06 Cybercore opportunity batch and authoritative source-evidence batch used to prove interoperability between `shalominattii-us/sovereign-os` and Foundry.[1]

| File | SHA-256 |
|---|---|
| `2026-08-06/AEGENTIX-CYBERCORE-OPP-INTAKE-2026-08-06.json` | `cff67e819b0c417b88ff4c895c71e88683460105035d931784fa6352fdde788f` |
| `2026-08-06/source-verification-2026-08-06.json` | `216575c36d9c3784de059f793702edf45f2b01b30827512344a652999432bdb6` |

Run the fixture through the native Foundry pipeline with:

```bash
foundry-cybercore \
  --batch examples/cybercore/2026-08-06/AEGENTIX-CYBERCORE-OPP-INTAKE-2026-08-06.json \
  --evidence examples/cybercore/2026-08-06/source-verification-2026-08-06.json \
  --output-root var/opportunities/cybercore-runs \
  --evaluated-at 2026-08-06T17:32:17Z
```

The expected profile is 22 maturity outputs: five `HUMAN_REVIEW`, seven `CLOSED`, six `PROGRAM_DISCOVERY`, one `FORECAST_MONITOR`, and three `SOURCE_DISCOVERY`. Only the five human-review records may initialize Foundry execution contexts. The fixture performs no network request or external action.

## References

[1]: https://github.com/shalominattii-us/sovereign-os/tree/f92a284f6c12fbc78bf472cc6007995ea9584e31/CYBERCORE/opportunity_intake "Cybercore Opportunity Intake in sovereign-os"
