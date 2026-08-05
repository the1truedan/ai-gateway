# Public security + smoke

## Branch protection

`main` should disallow force-push and deletion. Required status check: **`smoke`**
(after the workflow has run green at least once).

Solo maintainers may push directly when PR reviews are not required; protection
still prevents history rewrite.

## What CI smoke means

| Claim | CI |
|-------|-----|
| Compose files validate | Yes (`docker compose config`) |
| LiteLLM YAML parses | Yes |
| Services Python compiles | Yes |
| Full Headroom→LiteLLM→GPU lab | **No** — local only |
| Live spend / keys | **No** — never put secrets in git |

Honest wording: **CI smoke green** = production-*adjacent* glue readiness, not identical to a private home lab.
