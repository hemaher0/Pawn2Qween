<!--
SPDX-FileCopyrightText: Copyright 2026 SK TELECOM CO., LTD.
SPDX-FileCopyrightText: Copyright 2026 hemaher0

SPDX-License-Identifier: Apache-2.0
-->

# Contributing

## Contribution status

This repository does not accept external contributions. Unsolicited patches
and pull requests will not be reviewed or merged.

## Maintainer changes and DCO

Every commit must certify the
[Developer Certificate of Origin 1.1](https://developercertificate.org/)
with the contributor's own sign-off:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use:

```console
git commit --signoff
```

Do not sign off for another person. This project uses DCO, not a Contributor
License Agreement. Changes accepted into the repository are licensed under
Apache-2.0 unless a file states otherwise.

## Public disclosure

Every artifact considered for a public commit or release, including code,
documentation, data, CI configuration, and release artifacts, must satisfy all
of these conditions:

- its authorship, source, and redistribution rights are established;
- it is safe to disclose outside its original working context; and
- it has durable value for understanding, reviewing, reproducing, operating,
  or maintaining the public project.

Do not publish credentials, personal data, internal locations or
infrastructure, and non-public URLs. Also exclude private evaluation inputs or
results, embargoed vulnerability details, raw AI conversation or reasoning
records, confidential business material, and third-party material without
established redistribution rights.

If authorship, redistribution rights, confidentiality, or disclosure timing is
uncertain, the material must remain non-public until the uncertainty is
resolved. A sanitized public decision may preserve a durable conclusion or
general risk only when it cannot disclose or reconstruct the excluded source
information.

Non-public working evidence may remain in the ignored local `references/`
workspace. Ignoring a path is not a disclosure approval: verify that the file
is not staged or tracked, and keep every public artifact understandable without
linking to inaccessible confidential details.

## Clean-room and data boundary

Only independently authored material, or third-party material with verified
compatible redistribution rights, may be added. Do not add:

- code, Git history, documents, paths, or other artifacts copied from an
  internal repository or evaluation system;
- private evaluation composition, split mappings, outcomes, model outputs,
  gold answers, reasoning traces, failed generations, serving logs, or
  operational errors;
- credentials, internal hostnames, storage paths, or non-public URLs;
- dataset content that is not approved for redistribution, including
  `source-fetch-only` material; or
- third-party code, data, or documentation without its exact source, license
  evidence, attribution, and required notices.

Dataset changes must follow [`DATA_LICENSES.md`](DATA_LICENSES.md) and
[`data/sources/README.md`](data/sources/README.md). The repository's
Apache-2.0 license does not relicense datasets.

## Verification

Keep changes within the public scope described in
[`docs/DATA_CARD.md`](docs/DATA_CARD.md), use the repository's SPDX conventions,
preserve third-party notices, and run the checks in
[`DEVELOPING.md`](DEVELOPING.md) before committing.
