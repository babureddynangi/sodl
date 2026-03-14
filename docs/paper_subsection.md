# Paper Subsection: MVP Implementation (Ready to Paste)

## Suggested placement: after Section 5.5 (Implementation Status)

---

### 5.6 Limited AWS MVP: Partition Advisor Mechanism (H1)

To complement the simulation-backed architectural analysis, we implemented a
limited AWS MVP focused on the partition-advisor mechanism (H1, Section 12.1).
The MVP used Amazon S3, AWS Glue Data Catalog, and Amazon Athena to compare a
migration-time partitioning baseline against a workload-informed repartitioned
layout under controlled synthetic workloads.

**Setup.** A synthetic corpus of 5 million financial transaction records was
generated and loaded into two configurations: (i) a *baseline* layout
partitioned by transaction date, reproducing the common lift-and-shift
antipattern in which the partition key is chosen at migration time without
workload analysis; and (ii) an *optimized* layout partitioned by
`merchant_category`, the column recommended by the information-gain-scoring
partition advisor (Section 5.3) after analysing the 21-query
benchmark set. The partition advisor identified `merchant_category` as the
highest-scoring candidate, appearing as a filter predicate in a majority of
benchmark queries.

**Results.** Over 21 benchmark queries executed 3 times each
against Amazon Athena (workgroup with CloudWatch metrics enabled), the optimized
layout reduced mean query engine latency by **42.9%**
(1,421 ms → 812 ms) and
mean bytes scanned by **85.0%**
(29.1 MB → 4.4 MB).
Query correctness was verified by row-count equivalence across both layouts.

**H1 assessment.** The H1 threshold of ≥30% mean latency reduction was
met. 
The result is consistent with the conservative production range of 30–60%
from Section 7.3 ; the baseline
partition key in this experiment is a clean date-only key with no pre-existing
misconfiguration, which places the achievable gain toward the lower end of the
conservative range.

**Scope.** This MVP provides mechanism-level feasibility evidence for H1 only.
It does not implement the full SODL control plane: there is no Kinesis ingestion,
SageMaker Feature Store, LSTM–Markov predictor, confidence-gated autonomy
scheduler, or Iceberg metadata-only partition evolution. Those components remain
at the status documented in Section 5.5. The MVP uses Hive-style Glue external
tables rather than Iceberg; production deployment would use Iceberg's
metadata-only partition evolution capability to avoid the data rewrite performed
in this MVP. A production field study (Section 12) is the required next step
toward a fully integrated, production-validated contribution.

*(MVP code and raw results available at: [repository URL])*

---

## Notes on wording

- Do not change "directional" or "mechanism-level feasibility" — these are
  deliberate hedges that match the paper's existing claim discipline (Section 2.2).
- If lat_reduction >= 30%: change "directionally supported" → "met".
- The row-count equivalence check is important: it supports the correctness claim.
- The Iceberg caveat is required: the paper's H1 mechanism relies on Iceberg
  partition evolution; this MVP approximates it with pre-generated layouts.
