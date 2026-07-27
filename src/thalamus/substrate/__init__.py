"""Storage kernel: schema, Gremlin writer, Gremlin reader.

Everything here sits BELOW the federation contract. Code in this package knows
about nodes, edges, and Gremlin — not about experts, scopes, or trust tiers.
Scoping is enforced above it (docs/01-federation-contract.md).
"""
