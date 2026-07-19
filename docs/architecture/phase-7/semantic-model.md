# Semantic model (summary)

Entities: BusinessTerm, Metric, Dimension, JoinRule, FilterRule,
VerifiedQuestion/Query, SemanticVersion, PromotionRequest, DependencyEdge.

Metric logical plan (not SQL string) is compiled by `MetricCompiler` to
PostgreSQL, then validated by Query Gateway.
