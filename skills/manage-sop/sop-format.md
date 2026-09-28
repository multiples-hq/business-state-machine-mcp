# The SOP definition

`publish_sop_version` takes the definition as a JSON object. All three
stages must be present; any may have an empty `phases` list.

```
{"stages": {
  "quote":   {"phases": [PHASE, ...]},
  "booking": {"phases": [PHASE, ...]},
  "job":     {"phases": [PHASE, ...]}
}}

PHASE     = {"key": "...", "name": "...", "display_order": 10,
             "milestones": [MILESTONE, ...]}
MILESTONE = {"key": "...", "title": "...", "criterion": "..."}
```

- By convention, keys are lowercase words joined by dashes. Phase keys and
  milestone keys must each be unique within their stage, even across
  phases. Keep a key unchanged across versions when its meaning is
  unchanged.
- `display_order` is a whole number, unique within a stage. Leave gaps (10,
  20, 30) so a later version can slot a phase in between.
- A phase and a milestone have exactly the fields shown. An extra field is
  refused with a message that lists the required fields without naming
  the extra one.
- `name` and `version` are separate arguments of the call, not part of the
  definition. A name and version pair can be published once.

## Worked example

A small heating and air-conditioning installer. Their process, as the owner
described it: a customer asks for a price, a technician visits, an estimate
goes out; the customer signs and pays a deposit, the unit is ordered and an
install date is set; the install is done, the town inspects it, the
customer signs off and pays the balance.

```json
{"stages": {
  "quote": {"phases": [
    {"key": "estimate", "name": "Estimate", "display_order": 10, "milestones": [
      {"key": "request-received", "title": "Request received",
       "criterion": "Cited evidence shows a customer asking for a price or a visit, with the address of the work."},
      {"key": "site-visit-done", "title": "Site visit done",
       "criterion": "Cited evidence shows a technician visited the site, or the customer sent photos and measurements instead."},
      {"key": "estimate-sent", "title": "Estimate sent",
       "criterion": "Cited evidence shows the priced estimate reaching the customer."}
    ]}
  ]},
  "booking": {"phases": [
    {"key": "arrange", "name": "Arrange", "display_order": 10, "milestones": [
      {"key": "contract-signed", "title": "Contract signed",
       "criterion": "Cited evidence shows the customer signing or accepting the estimate in writing. A yes reported by phone is not enough."},
      {"key": "deposit-received", "title": "Deposit received",
       "criterion": "Cited evidence shows the deposit paid, such as a payment notice or a receipt."},
      {"key": "equipment-ordered", "title": "Equipment ordered",
       "criterion": "Cited evidence shows the unit ordered from the supplier, with an expected delivery date when one is given."},
      {"key": "install-date-set", "title": "Install date set",
       "criterion": "Cited evidence shows a date the customer agreed to."}
    ]}
  ]},
  "job": {"phases": [
    {"key": "install", "name": "Install", "display_order": 10, "milestones": [
      {"key": "install-complete", "title": "Install complete",
       "criterion": "Cited evidence shows the technician reporting the unit installed and running."},
      {"key": "inspection-passed", "title": "Inspection passed",
       "criterion": "Cited evidence shows the town's inspection passed. A booked inspection is pending, not done."}
    ]},
    {"key": "close", "name": "Close", "display_order": 20, "milestones": [
      {"key": "customer-sign-off", "title": "Customer sign-off",
       "criterion": "Cited evidence shows the customer confirming the work is finished to their satisfaction."},
      {"key": "balance-paid", "title": "Balance paid",
       "criterion": "Cited evidence shows the remaining balance paid."}
    ]}
  ]}
}}
```

The repository's `examples/` folder holds this example as a file, with two
more: an event caterer and a longer one from a freight forwarder, a
business that arranges shipping for its customers.
