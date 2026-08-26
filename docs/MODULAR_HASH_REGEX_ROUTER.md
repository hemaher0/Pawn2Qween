<!--
SPDX-FileCopyrightText: Copyright 2026 hemaher0
SPDX-License-Identifier: Apache-2.0
-->

# Modular Hash-Regex Router

## Purpose

The modular hash-regex router is a prompt-only model router built from small,
independently understandable prediction modules. It combines a shared
content representation with tier-specific quality estimators and a
budget-aware allocator.

The design has three runtime goals:

1. make every decision from prompt or message content only;
2. keep learned state in compact aggregate artifacts rather than per-prompt
   records; and
3. allow one tier's quality model or safety policy to change without changing
   the other tiers.

The router does not need model outputs, expected answers, evaluation outcomes,
source labels, task labels, or a prompt registry while routing.

## Runtime data flow

```text
prompt or messages
        |
        v
hash-regex feature vector
        |
        +--------------------+
        |                    |
        v                    v
base quality and cost     source probabilities
        |                    |
        +----------+---------+
                   |
                   v
        tier-specific quality surface
                   |
                   v
       budget-aware batch allocation
                   |
                   v
              model decision
```

Feature extraction and learned prediction are row-local. Budget allocation is
batch-level because the cost limit applies to the complete submission for a
tier.

## Shared content representation

Each episode is converted to the same representation used by the public
hash-regex baseline:

- explicit prompt-shape features, such as log character count, log word
  count, message count, code markers, math markers, and numeric density; and
- signed feature-hashed word unigrams and bigrams.

The raw vector is standardized with the mean and scale stored in the base
artifact. The runtime uses the same standardized vector for every downstream
module. Reusing one representation avoids separate tokenizers, embedding
models, and runtime model dependencies.

## Source inference

A multinomial linear classifier maps the standardized content vector to a
probability distribution over coarse source classes:

```text
source_probability = softmax(source_intercept + source_weights * features)
```

The classifier is a content model, not a registry lookup. Its output depends
only on the current prompt or messages. The runtime artifact stores classifier
classes and aggregate coefficients; it does not store prompt digests or
source assignments for individual training rows.

The probability vector is used in two ways:

- soft source correction uses the complete probability distribution; and
- cell residual modules use the highest-probability class as a coarse group.

This separation lets uncertain source predictions contribute smoothly to the
base estimate while keeping the small residual tables easy to inspect.

## Quality modules

All quality values are clipped to the closed interval `[0, 1]` after their
corrections are applied.

### Ridge quality

The base artifact contains one linear ridge head per model. These heads
produce an absolute quality estimate from the standardized hash-regex vector.

### Soft source residual

For each source class and model, offline fitting estimates a smoothed average
error of the ridge prediction. At runtime, the correction is the
probability-weighted mean of those class residuals:

```text
soft_source_residual[model]
    = sum(source_probability[class] * residual[class, model])

source_quality[model]
    = ridge_quality[model] + soft_source_residual[model]
```

Residual estimates use a fixed prior count. The prior shrinks small groups
toward zero instead of allowing a few observations to create a large offset.

### Binomial quality

The binomial module treats an observed quality and its generation count as
success and failure mass. It fits one strongly regularized logistic head per
model rather than treating every aggregate quality target as an equally reliable
continuous target:

```text
binomial_quality[model] = sigmoid(intercept[model] + weights[model] * features)
```

The same soft source residual is added to this prediction. This preserves the
stable coarse correction while allowing observation counts to influence the
linear fit.

### Source-by-length residual

The length module partitions standardized log character count at fixed
quartile thresholds. A cell is the pair:

```text
(inferred_source_class, length_bin)
```

Each populated cell stores one smoothed residual per model relative to
`source_quality`. The resulting surface is:

```text
length_quality = source_quality + length_cell_residual
```

This module represents a small nonlinear interaction: prompt length can mean
different things for different coarse content families.

### Source-by-numeric-density residual

The numeric module applies the same cell construction to standardized numeric
density:

```text
(inferred_source_class, numeric_density_bin)
```

Its residual is fitted relative to the binomial surface:

```text
numeric_quality = binomial_quality + numeric_cell_residual
```

Duplicate quartile thresholds are collapsed, so the artifact contains only
bins that the fitted scalar distribution can distinguish. Missing cells have
a zero correction.

## Tier composition

The router selects one complete quality surface per tier:

| Tier | Quality surface |
| --- | --- |
| Fast | source-by-numeric-density residual over binomial quality |
| Balanced | source-by-length residual over ridge quality |
| Premium | source-by-numeric-density residual over binomial quality |

Tier composition is explicit artifact configuration rather than implicit
branching spread across the runtime. A module can therefore be replaced for
one tier without changing feature extraction, cost prediction, or the other
tiers.

## Cost prediction and allocation

Cost prediction remains separate from quality prediction. The base artifact
contains one log-cost head per model. Predicted costs are exponentiated and
made monotonic so that the runtime never predicts a stronger model to cost
less than a weaker model.

For each tier, the allocator considers the complete batch and assigns models
under a predicted cost ceiling. The allocator uses content-derived quality
utilities and deterministic tie-breaking; episode identifiers and input
position do not provide decision signal.

Fast and Balanced use the safety ratios declared by the base artifact.
Premium applies an additional upgrade-headroom scale of `0.90`. The scale is
applied only to budget above the all-light baseline:

```text
guarded_ratio = 1 + 0.90 * (base_target_ratio - 1)
```

With a Premium budget multiplier of `4` and a base safety ratio of `0.925`,
the base target ratio is `3.7` and the guarded target ratio is `3.43`. This
leaves the all-light cost unchanged and reduces only discretionary upgrade
headroom.

After the main Premium allocation, the existing conservative AX31 fill step
may replace remaining light selections when the replacement improves
predicted quality and stays inside its own safety ceiling. Existing non-light
selections are preserved by that step.

## Artifact boundary

The modular artifact contains aggregate model state only:

- source classifier classes, intercepts, and coefficients;
- binomial head intercepts and coefficients;
- source, length-cell, and numeric-cell residual tables;
- scalar bin thresholds and smoothing configuration;
- tier-to-module assignments and Premium headroom configuration; and
- the expected base-artifact identity and protocol identity.

It must not contain prompts, messages, episode identifiers, per-row feature
vectors, prompt digests, model responses, expected answers, or per-row
outcomes.

The runtime validates the complete artifact schema, vector dimensions, finite
numeric values, known model and tier identifiers, and the binding to the base
artifact. Unknown fields are rejected so that misspelled or unsupported
configuration cannot silently change routing behavior.

## Determinism and isolation

For a fixed input batch, policy, base artifact, and modular artifact, routing
is deterministic. Reordering a batch may reorder the output decisions, but it
must not change the model selected for the same content. Changing episode
identifiers must not change content decisions.

The runtime accepts neither outcomes nor a source registry. Offline fitting
and online routing are separate boundaries: fitting may consume approved
training outcomes and source labels, while the runtime consumes only the
submission input, tier, policy, and aggregate artifacts.

## Operational inspection

A routing plan should expose bounded, non-sensitive summary state for local
verification:

- selected tier and quality module;
- effective safety ratio;
- predicted batch cost ratio; and
- per-model decision counts.

These summaries explain which configured path ran without exposing prompt
content or creating high-cardinality telemetry. Artifact and policy validation
errors fail closed with a non-zero command exit.
