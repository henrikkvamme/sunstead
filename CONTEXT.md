# Sanitas

Sanitas describes how medicine availability depends on upstream supply conditions, and how supply risk becomes meaningful when it threatens patient care.

## Language

**Care Impact**:
The patient-care consequence of reduced Medicine Availability. Care Impact is used to explain why supply risk matters, but individual patients are not represented in the graph.
_Avoid_: Patient node, patient profile, persona

**Medicine**:
A treatment product that a patient or care provider needs to be available. A Medicine can depend on many upstream components.
_Avoid_: Drug, product, SKU

**Medicine Availability**:
The ability for a care provider to obtain the medicine needed for treatment when it is needed.
_Avoid_: Stock level, inventory

**Supply Risk**:
A condition in the upstream supply network that may threaten Medicine Availability.
_Avoid_: Alert, incident, disruption

**Demand Signal**:
Evidence that demand for a Medicine may increase enough to threaten Medicine Availability. Demand Signals can include trend data, prescribing shifts, public attention, seasonal patterns, or new clinical guidance.
_Avoid_: Popularity, hype, demand spike

**Availability Risk Level**:
The severity of Supply Risk based on how likely it is to threaten Medicine Availability. The level is primarily shown visually, such as through color or emphasis, and is not a measure of how severe an external event is in general.
_Avoid_: Alert level, event severity, crisis severity

**Risk Profile**:
A compact explanation of the main availability drivers for one Medicine, such as supply fragility, demand pressure, evidence strength, and recommended action. The Risk Profile keeps secondary signals visible without requiring every signal to appear as a graph node.
_Avoid_: Score breakdown, metrics panel, status summary

**Medicine Risk Graph**:
A graph centered on one Medicine that shows the upstream components, suppliers, places, and external signals that explain its Supply Risk.
_Avoid_: Supply tree, dependency map, graph view

**Medicine Risk Network**:
A graph across many Medicines that shows shared upstream dependencies and where Supply Risk can affect multiple medicines at once.
_Avoid_: Overview graph, global graph, network map

**Network Overview**:
The opening view of the Medicine Risk Network. Medicines sit near the center, upstream dependencies and Evidence Sources sit farther out, and active risk paths visually flow inward toward affected medicines.
_Avoid_: Landing view, intro graph, global map

**Graph Layout**:
The visual placement of graph data for a specific view or transition. Graph Layout can be crafted for clarity while the underlying graph data remains source-driven.
_Avoid_: Hardcoded graph, fake graph, canvas design

**Place**:
A location or logistics node in the graph, such as a country, facility, region, or port. The detailed panel can describe the specific place type when needed.
_Avoid_: Facility node, country node, route node

**Evidence Source**:
An external source that supports why a node or relationship appears in the risk view. Evidence Sources can include news articles, public shortage notices, disaster alerts, regulatory notices, supplier information, demand indicators, or trend data.
_Avoid_: Reference, citation, article

**Evidence Satellite**:
A compact source node attached to the graph node it supports. Evidence Satellites can be highlighted when relevant, but opening the external Evidence Source is a deliberate action from the detail panel.
_Avoid_: Source node, article node, citation bubble

**Graph Investigation**:
A user-led exploration of a node in the Medicine Risk Network or Medicine Risk Graph. A Graph Investigation shows progress before agents add relevant nodes, relationships, Evidence Satellites, or risk-profile changes to the graph.
_Avoid_: Chat, drilldown, assistant conversation

**Risk Path**:
The chain of nodes and relationships that explains how a Supply Risk reaches a Medicine. A Risk Path is used to show why a selected node matters for Medicine Availability.
_Avoid_: Direct neighborhood, highlighted edges, dependency path

**Graph Intelligence Agent**:
An agent that searches for Evidence Sources, evaluates their relevance, and automatically adds relevant evidence and risk-profile changes to the graph. The core supplier chain is expected to already be mapped before a user starts a Graph Investigation.
_Avoid_: Bot, scraper, background job

**Graph Change Timeline**:
A chronological record of meaningful changes made to the graph, including new Evidence Sources, new relationships, added nodes, and Availability Risk Level changes.
_Avoid_: Agent log, activity feed, audit trail

## Example dialogue

**Domain expert**: The pitch can start with one patient story, but the product should not represent individual patients.

**Developer**: So the Medicine Risk Network helps us spot which medicines are exposed, and the Medicine Risk Graph explains one critical medicine in detail.

**Domain expert**: Exactly. Care Impact is the explanation layer: if a critical component has a Supply Risk, that can threaten Medicine Availability for patients who depend on the medicine.

**Developer**: Should the broad network use the same layout as the detailed graph?

**Domain expert**: No. The Network Overview should make shared dependencies visible around the medicines, while the detailed Medicine Risk Graph should explain one Risk Path clearly.

**Developer**: Can the demo use handcrafted positions?

**Domain expert**: Yes, as Graph Layout. The graph data should still keep the same node and relationship shape that can later be backed by a real graph database.

**Developer**: Should the critical medicine already stand out in the Network Overview?

**Domain expert**: Yes. It should glow in the warning color so the presenter can click it and transition into the focused Medicine Risk Graph.

**Developer**: So if a flood appears in red, it is red because of its effect on Medicine Availability, not because all floods are classified as red.

**Domain expert**: Yes. Keep the graph clean: show the Risk Path visually, and put secondary context like stable demand signals in the Risk Profile unless they become active drivers.

**Domain expert**: Correct. And if I click the flood node, I need to see the Evidence Sources and start a Graph Investigation if I want the agents to look deeper.

**Developer**: Should clicking a source leave the graph immediately?

**Domain expert**: No. Click the Evidence Satellite to inspect it in the detail panel, then use an explicit action to open the external Evidence Source.

**Developer**: When a user investigates a node, should we only show nearby nodes?

**Domain expert**: Show the Risk Path back to the Medicine so the relevance is immediately clear.

**Developer**: Where should the details appear?

**Domain expert**: A selected node opens a stable investigation panel; hover previews can stay lightweight near the graph.

**Developer**: When the agents add new information, should we show their internal work?

**Domain expert**: Show the Graph Change Timeline instead: what changed in the graph, what source supports it, and how the Availability Risk Level changed.

**Developer**: Should investigations update instantly?

**Domain expert**: No. Show a short progress sequence, then animate new evidence, connections, and risk-profile changes into place. The supplier chain should already be mapped.
