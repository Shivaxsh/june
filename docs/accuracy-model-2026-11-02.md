# Accuracy model evaluation — 2 November 2026

## Candidate selection

Use the explicit `qwen3:4b-instruct-2507-q4_K_M` tag for the direct-answer candidate. The registry's generic `qwen3:4b` tag currently maps to the thinking-only variant, not this Instruct variant. See the [official tags](https://ollama.com/library/qwen3/tags) and the [Instruct model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507).

The thinking-only candidate declared only `true` in its supported thinking metadata. Requests with `think:false`, a soft control, a local template profile and direct rendering did not produce suitable short answers. That interrupted run is a compatibility failure, not a completed accuracy score. In supported thinking mode, it answered the threading question correctly after **126.853 seconds**. It is unsuitable for June's current voice-response budget and was removed during cleanup.

The Instruct candidate passed the direct-answer smoke check and the original **28/28** acceptance cases, using the existing application prompt, personality and memory flow. Manual review confirmed the actual async follow-up correctly denied creating another thread. CPU-loop and Promise.all paraphrases also answered correctly. Ordinary PC-planning advice asked about the workload instead of refusing the task. These are fixed examples, not proof of perfect general accuracy.

An additional purchase-advice check still suggested GPUs without verified current market information. Application-owned capability routing now asks for a dated shortlist/prices before ranking hardware, while leaving ordinary explanations, PC planning and supplied-option comparisons available to the model. This does not connect a shopping or browsing service.

## Speed and readiness

In the first acceptance run, the actual async follow-up produced first text at **852 ms** and completed at **11.328 seconds**. The initial full-prompt React request produced first text at **35.487 seconds**; it includes startup/prompt processing. These are service-level observations, not physical finish-speaking-to-audible-answer measurements. The expanded run finished **28/29**: long-conversation turn 7 produced the expected word but exceeded the 180-second request limit, so it failed. The normal web/backend services were paused during the run, after a status check had triggered a competing default-model warm-up. This was not a fully controlled timing comparison. System diagnostics recorded memory pressure and a CPU speed limit of 64%; they do not establish the cause of the timeout. No default-model switch is being made on this evidence.

The model loads and runs on this Intel Mac with 8 GB RAM, but the larger model increases CPU work. The earlier median ≤3.5-second/p95 ≤6-second voice targets remain unverified for it. Selecting an accuracy profile does not close the full voice-latency gate or advance the roadmap automatically.

## Local setup and rollback

Set `JUNE_MODEL=qwen3:4b-instruct-2507-q4_K_M` in ignored `.env.local`, run `npm run model:pull` if needed, then restart June. Keep `num_ctx=4096`; the model's advertised larger context is not an appropriate default for this Mac. The lightweight rollback is `JUNE_MODEL=qwen2.5:1.5b`, followed by restarting June. The selected model is displayed by the live status interface.

No training, automatic memory approval, cloud provider, account key or hardware purchase is involved. The current model and candidate remain outside Git. Acceptance writes only to private database clones; the live database is preserved.

## Storage cleanup

Free space increased from approximately **8.2 GiB to 17 GiB** after removing rejected trial models, the unused compatibility environment, build cache and redundant test database copies. The pending useful Instruct download was resumed from cache. After it completed, about **15 GiB** remained. The working Qwen2.5 model, Whisper, native voice helper, source, live data and recovery backups were retained. No unrelated personal files or projects were removed.

## Regression verification

The final 302-test Python run had 301 successes and one native-worker startup timeout in test setup (a two-second readiness deadline). An immediate focused rerun passed all five native-worker tests in 9.148 seconds. This is recorded as a timing-sensitive test failure, not an entirely clean full-suite run. No deadline was relaxed to hide it. The application was restarted and its page returned HTTP 200; status reported the unchanged `qwen2.5:1.5b` model ready.
