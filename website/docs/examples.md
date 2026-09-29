---
title: Example SOPs
description: Three example SOPs from different trades.
---

# Example SOPs

Three example SOPs from different trades. They show the shape and the style
of criteria. None is a default, and none describes a real company: write
your own before real use (see [Write your SOP](guides/write-your-sop.md)).

| File | Business |
| --- | --- |
| [`hvac-installer-sop.json`](https://github.com/multiples-hq/business-state-machine-mcp/blob/main/examples/hvac-installer-sop.json) | A heating and air-conditioning installer: estimate, arrange, install, close. |
| [`event-caterer-sop.json`](https://github.com/multiples-hq/business-state-machine-mcp/blob/main/examples/event-caterer-sop.json) | An event caterer: proposal, confirm and plan the event, serve, settle. |
| [`freight-forwarder-sop.json`](https://github.com/multiples-hq/business-state-machine-mcp/blob/main/examples/freight-forwarder-sop.json) | A freight forwarder, which arranges shipping for its customers. The longest of the three. |

Each file is ready to pass to `publish_sop_version` as its `definition`.
The format is in
[`skills/manage-sop/sop-format.md`](https://github.com/multiples-hq/business-state-machine-mcp/blob/main/skills/manage-sop/sop-format.md).
