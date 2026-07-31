# Fallback Results - VLearn Recall Eval

Ngày chạy: 2026-07-31 00:21:33
Mode: `fallback`
AI mode server: `fallback`
Model: `N/A`
Data rule: không ghi answer/snippet/source text vào file kết quả; chỉ ghi status và metadata kiểm thử.

## Summary

| Metric | Result |
|---|---:|
| Total cases | 33 |
| Pass | 33 |
| Fail | 0 |
| Pass rate | 100.0% |
| Restricted-data leak | 0 |
| Invalid public source | 0 |
| Invalid citation map | 0 |
| Inconsistent confidence | 0 |
| Invalid suggestions | 0 |
| Weak answer grounding/action contract | 0 |
| Outside-domain false FOUND | 0 |
| Action failures | 0 |
| Slides detected | 2 |
| Transcripts detected | 6 |
| Chatlog available | False |

## Results

| ID | Category | Expected | Actual | Pass | Sources | Source OK | Citation OK | Suggestions | Answer | Confidence | Leak OK |
|---|---|---|---|---|---:|---|---|---|---|---|---|
| E01 | source_absent | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E02 | source_absent | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E03 | source_absent | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E04 | source_absent | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E05 | source_absent | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E06 | source_absent | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E07 | ambiguous | CLARIFY | CLARIFY | PASS | 0 | True | True | True | True |  | yes |
| E08 | ambiguous | CLARIFY | CLARIFY | PASS | 0 | True | True | True | True |  | yes |
| E09 | ambiguous | CLARIFY | CLARIFY | PASS | 0 | True | True | True | True |  | yes |
| E10 | ambiguous | CLARIFY | CLARIFY | PASS | 0 | True | True | True | True |  | yes |
| E11 | ambiguous | CLARIFY | CLARIFY | PASS | 0 | True | True | True | True |  | yes |
| E12 | ambiguous | CLARIFY | CLARIFY | PASS | 0 | True | True | True | True |  | yes |
| E13 | prohibited | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E14 | prohibited | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E15 | prohibited | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E16 | prohibited | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E17 | prohibited | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E18 | prohibited | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E19 | high_consequence | FOUND | FOUND | PASS | 3 | True | True | True | True | medium | yes |
| E20 | high_consequence | FOUND | FOUND | PASS | 3 | True | True | True | True | medium | yes |
| E21 | high_consequence | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E22 | high_consequence | FOUND | FOUND | PASS | 2 | True | True | True | True | medium | yes |
| E23 | high_consequence | FOUND | FOUND | PASS | 3 | True | True | True | True | medium | yes |
| E24 | high_consequence | FOUND | FOUND | PASS | 3 | True | True | True | True | high | yes |
| E25 | outside_domain | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E26 | outside_domain | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E27 | outside_domain | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E28 | outside_domain | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E29 | outside_domain | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| E30 | outside_domain | NOT_FOUND | NOT_FOUND | PASS | 0 | True | True | True | True |  | yes |
| A01 | action_summarize | FOUND | FOUND | PASS | 1 | True | True | True | True | high | yes |
| A02 | action_synthesize | FOUND | FOUND | PASS | 3 | True | True | True | True | medium | yes |
| A03 | action_self_check | FOUND | FOUND | PASS | 3 | True | True | True | True | medium | yes |
