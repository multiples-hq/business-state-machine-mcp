---
title: Known limits
description: What the ledger does not do.
---

# Known limits

- No authentication and no per-user permissions.
- The ledger keeps no SOP of its own: nothing is published or adopted until
  you do it.
- An instruction written into a memo is prose for the next reader. It is not
  an SOP rule, and there is no SOP text scoped to one operator.
- An outside reference number cannot be withdrawn or corrected.
- Only jobs can carry document requirements.
- Addresses are plain identifier rows. Which address a party uses in which
  role is not recorded.
- No file deletion and no cleanup of stored files.
- Money is a record for operations, not accounting: no tax filing, no
  currency conversion, no bank feed, no check against an accounting app.
- One charge line covering several jobs must be split into one line per job
  by the agent.
- A bill with no lines cannot be waived: it has no charge to judge. Reissue
  it with a stated total of 0 and the reason.
- A bill recorded without its work links gains them only by a reissue that
  names them in `work`.
- A line put on the wrong charge is replaced by 0 and recorded again on the
  right one; the empty charge stays.
- A settled bill linked to no work, and its payment, appear in no read.
- Parties recorded twice before `find_parties` existed stay separate.
- No user interface. The server calls no outside system and sends nothing.
