# MVP-A Staging Branch Archive

Date: 2026-07-18
Branch: `integration/bi-rmp-v2-staging-v2`
Remote: `origin`

## Archived State

The MVP-A staging branch state sealed for functional acceptance is:

- Commit: `987882de6cea81dd68dc62fd0dd833117fc7a7f1`
- Short commit: `987882d`
- Subject: `docs: record gate a7 staging acceptance`
- Author date: `2026-07-18T21:25:02+08:00`
- Tree: `b3a2553af3bc0df855679c49e4a540d4d86b931b`
- Remote branch: `origin/integration/bi-rmp-v2-staging-v2`

Latest sealed history at archive time:

```text
987882d docs: record gate a7 staging acceptance
6d6afe7 fix: complete gate a6 dashboard staging readback
b72d1a4 testdata: add mvp a3 fictional fixture
b490482 docs: record gate a2.1 rls closure
91060c7 docs: freeze mvp 0 acceptance scope
```

## Reconstructing The Archived State

To inspect the sealed state without moving any branch:

```powershell
git fetch origin
git switch --detach 987882de6cea81dd68dc62fd0dd833117fc7a7f1
```

To return to the integration branch:

```powershell
git switch integration/bi-rmp-v2-staging-v2
```

## Archive Boundary

The archived commit is the A7-accepted application and staging verification state. Gate A8 adds only release, rollback, and archive documentation on top of that state.

No database credential, service role key, `.env.staging` content, deployment artifact, crawler output, n8n execution output, LINE payload, or production deployment result is included in this archive.
