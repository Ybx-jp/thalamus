---
name: validate-ui-prototype-graph
description: Validate a Penpot or other interactive UI prototype as a directed graph before calling it complete. Use when adding, revising, or reviewing prototype navigation, state flows, index pages, or isolated frames.
---

# Validate a UI Prototype Graph

Treat prototype links as a directed graph and validate them with NetworkX. Visual inspection and clicking a few paths do not establish reachability.

## Define the graph honestly

- A node belongs to the product graph only when it depicts a real member or state of the UI prototype.
- Indexes, anatomy/redline boards, coverage cards, annotations, and “outside this prototype” pages are support artifacts. They are not product nodes.
- A support artifact may link to frames for authoring convenience, but its edges must be removed before any connectivity, reachability, component, hub, or path claim.
- Never use an index page to connect otherwise isolated flows. An index does not count as a hub, entry point, bridge, or return path.
- Every hub or articulation point reported for the product graph must therefore be an actual UI screen or state. A non-UI hub is a failed prototype topology.

Build `G_full` from every frame and prototype transition, classify every frame as `ui` or `support`, then derive the graph under test:

```python
G = G_full.subgraph(ui_frame_ids).copy()
```

Do not merely remove the index node after computing paths; derive the induced UI-only graph first.

## NetworkX checks

Run all of these before handoff:

```python
import networkx as nx

assert nx.number_weakly_connected_components(G) == 1
assert not list(nx.isolates(G))

reachable = nx.descendants(G, entry_frame_id) | {entry_frame_id}
assert reachable == set(G.nodes)

for node in nx.articulation_points(G.to_undirected()):
    assert node in ui_frame_ids
```

Also report, by frame name:

- weakly connected components;
- isolates;
- zero-in-degree and zero-out-degree frames;
- frames unreachable from each real UI entry point;
- strongly connected components;
- the ten highest-degree nodes;
- articulation points in the undirected projection.

Weak connectivity is not enough for a prototype someone is meant to click through. Remove
support nodes and the generic out-of-scope card, then verify every UI frame has an outgoing
UI transition and a directed path back to a real stable surface such as the feature's list
or application entry:

```python
product = G.subgraph(ui_frame_ids - {outside_frame_id}).copy()
assert not [node for node in product if product.out_degree(node) == 0]

for node in product:
    assert any(nx.has_path(product, node, target) for target in return_targets)
```

Audit every transition into the out-of-scope card by source frame and control name. Keep it
only when that destination is genuinely undesigned and explicitly excluded from the
prototype—hunk inspection or a keyboard the handoff leaves unspecified, for example. A
designed state that merely lacks a path must be connected to that state, not sent out of
bounds. If an unimplemented control does nothing by design, leave it disabled or without a
target rather than manufacturing an escape route.

A legitimate exogenous state, such as an error or empty result selected by runtime data rather than a tap, still needs an explicit semantic transition from a real UI state in the validation graph. Record system/data transitions separately from clickable transitions; do not route them through a support page.

## Repair and recheck

Fix the prototype through real UI transitions. Do not add invisible links whose only purpose is to satisfy the graph check, and do not promote an authoring index into product navigation.

After edits, extract the graph again from the live prototype and rerun NetworkX. Preserve both the pre-fix findings and the passing post-fix summary in the handoff or review note.

The invariant is: **remove every support artifact and its edges; the remaining UI prototype still forms the intended reachable flow.**
