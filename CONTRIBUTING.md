# Contributing to arcanus

## Branch naming (enforced server-side)

Every branch must start with one of these prefixes — a GitHub **ruleset** rejects the
push/creation of anything else, so an off-pattern branch can't slip through:

`feat/` `fix/` `chore/` `docs/` `refactor/` `test/` `ci/` `perf/` `build/` `style/`
`revert/` `release/` `hotfix/`

Examples: `feat/cursor-pagination`, `fix/null-criteria`, `ci/release-automation`.

The `codex/` and `copilot/` prefixes are also allowed because this repo is worked on with
those agents; release-please's own `release-please--branches--main` is allowlisted too.
The source of truth for the rule is [.github/rulesets/branch-naming.json](.github/rulesets/branch-naming.json)
(see its header in `CONTRIBUTING` for how to apply/update it).

> Branch names are hygiene only — they do **not** drive releases. The version bump and
> changelog come entirely from your **commit / PR titles** (next section).

## Releases are automated — do not bump the version by hand

Versioning and publishing to PyPI are driven by
[release-please](https://github.com/googleapis/release-please). You no longer edit
`version` in `pyproject.toml`, create git tags, or draft GitHub Releases manually.

How it works:

1. Land changes on `main` using **Conventional Commit** messages (see below).
2. release-please keeps an open **release PR** titled like `chore: release 0.0.23`. It
   bumps the version in `pyproject.toml` and regenerates `CHANGELOG.md` from your commits.
3. When you're ready to ship, **merge that release PR**. release-please creates the
   `vX.Y.Z` tag and GitHub Release, and the [`Release` workflow](.github/workflows/publish.yml)
   builds the package, publishes it to PyPI via Trusted Publishing, and attaches the
   wheel + sdist to the GitHub Release.

That's it — one merge per release.

## Conventional Commits

release-please decides the next version and the changelog entirely from commit messages,
so they must follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Meaning | Version effect (while `0.x`) |
| --- | --- | --- |
| `fix:` | Bug fix | patch (`0.0.22` → `0.0.23`) |
| `feat:` | New feature | patch (`0.0.22` → `0.0.23`) |
| `feat!:` / `BREAKING CHANGE:` in body | Breaking change | minor (`0.0.22` → `0.1.0`) |
| `chore:` `docs:` `refactor:` `test:` `ci:` `perf:` `build:` `style:` | Maintenance | no release; shown in the changelog |

> While the package is pre-1.0 the bump policy is intentionally conservative
> (`feat:` stays in the patch line). Once the project reaches `1.0.0`, remove
> `bump-minor-pre-major` / `bump-patch-for-minor-pre-major` from
> [`release-please-config.json`](release-please-config.json) to get standard
> `feat:`→minor / `feat!:`→major semantics.

### Squash merges use the PR title

This repo merges PRs by **squash**, so the squashed commit subject is the **PR title**.
Prefer a valid Conventional Commit (e.g. `feat: add cursor pagination`) — release-please
only bumps the version and writes a changelog entry for titles it can parse. The
[`PR Title` check](.github/workflows/pr-title-lint.yml) posts a warning on a non-conventional
title but **does not block the merge**, so such a PR simply won't appear in the changelog.
