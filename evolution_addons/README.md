# Additional engineering: free-only routing policy

This is a **standalone, non-operational** policy module. It does not call OpenRouter, activate JCode, handle API keys, or install anything. It selects candidate `:free` model IDs only when both prompt and completion prices are explicitly zero and tool support is advertised (unless disabled for non-tool tasks). Missing metadata fails closed.

Before real integration, fetch current catalog metadata through an authenticated and authorized provider client, verify all billable pricing dimensions and provider terms, apply strict retry/cost limits, and run integration tests. The router's `openrouter/free` alias is deliberately not treated as a guaranteed zero-cost endpoint by this validator; use independently verified concrete free IDs.

Run: `python3 -m unittest evolution_addons.test_free_router`

All original sources are preserved. No phone deployment, live model execution, or training is performed.
