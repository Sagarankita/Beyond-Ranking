# Optional Network DEA and multi-period planning assessment

The evidence gate was evaluated before implementing either extension.

## Network DEA: `deferred_evidence_gap`

- rows are synthetic and not a documented comparable peer cohort
- no observed intermediate stage-link variables

Network DEA was not implemented because the data contain no observed intermediate stage links and do not represent a documented comparable peer cohort. Creating stage links from the existing cross-sectional synthetic columns would add unsupported assumptions.

## Multi-period planning: `deferred_evidence_gap`

- rows are synthetic rather than observed longitudinal records
- no period/year column

Multi-period optimization was not implemented because there are no period identifiers, repeated units, observed carry-over resources, or defensible time-lag estimates. Replicating a single synthetic cross-section would not create longitudinal evidence.

## Evidence needed to resume

For Network DEA, collect comparable units with stage-specific inputs, observed intermediate links, final outputs, and an agreed treatment of shared resources. For multi-period planning, collect repeated departmental periods with stable identifiers, per-period constraints, carry-over resources, and documented outcome lags.
