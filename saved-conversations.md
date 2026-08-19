The core mechanic
When you ask for a 50-question paper, the harness doesn't just generate 50 questions and hope. It works in two phases:

Phase 1 — the main pass. It creates 50 "slots" (one per question needed), split across subjects per the plan. Each slot asks the model to draft one question, then runs it through gates: is it valid Hindi, are the 4 options distinct, and — the strict one — is the claimed fact actually quotable from the retrieved book passages (the "grounding" check). If a slot fails all its internal retries, it's dropped and logged.

Phase 2 — topup. After the main pass, if the paper is short, it generates replacement questions on fresh topics to fill the holes.

What the numbers are telling us
Look at this test: 50 requested, 50 generated — a full paper. But look at the drops column: hindi had 7 drops, uk-geography had 8, general-gk had 6. Add them up — 30 slots failed and got dropped along the way, yet the paper still came out complete at 50/50.

That's the key insight: a "drop" is not a missing question. It's a discarded attempt that got replaced. The 30 drops here were all successfully backfilled, so the final paper is whole. The drops list is a record of wasted effort, not of holes in the paper.
