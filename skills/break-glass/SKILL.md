---
name: break-glass
description: Move a running job onto a different SOP version - a break_glass recovery procedure when the job has gone off its normal path, or a newer standard version when the process changed mid-flight - with the person's explicit approval, then re-judge its milestones from evidence already recorded. Use when a job was cancelled, damaged, needs a redo or is disputed, or when running jobs must follow a revised SOP.
---

Goal: the job follows the procedure it is really on, its history intact,
and its new milestones judged from what the ledger already knows.

## What the ledger allows

- Only a job can change its SOP version, whether it stands alone or sits
  under a booking. A quote or a booking keeps the version its chain
  started with, to the end; say so if the person asks.
- The change is a new adoption that names the current one. Nothing is
  deleted: the earlier adoption stays readable, and milestones the new
  version leaves out stay as history, never marked done.
- A retired version cannot be adopted.

## Steps

1. **Confirm the need.** Read `read_case_brief` for the job. Say to the
   person what happened and why the current procedure no longer fits,
   citing the evidence.
2. **Choose the target.** `list_sop_versions` with status `active`, and tag
   `break_glass` for a recovery procedure or tag `standard` for a newer
   version; a retired version is refused. Show the person the candidates by
   name and let them choose. A good target copies, word for word, the
   job's milestones up to the break point, so the job keeps them. If none
   fits, stop and write one first with the `manage-sop` skill, as a fork
   of the job's current SOP. Never choose for them.
3. **Record the approval.** Their yes, word for word, as evidence, linked
   to the job with `about_work`. The adoption must cite it.
4. **Adopt.** `read_work_sop` gives the current adoption's ID and its
   milestones; `read_sop_version` gives the target's job stage. Call
   `adopt_sop_version` on the job with `expected_previous_adoption_id` set
   to the current adoption, a reason in plain words, and evidence IDs for
   both the approval and the evidence that made the change necessary.
   Bind every phase and milestone of the job stage. To keep a milestone
   and its judgments, bind its existing milestone ID and its phase's
   existing phase ID, both shown by `read_work_sop`. That works only when
   the title, the criterion and the phase name are unchanged; anything
   else gets a new ID. A stale
   `expected_previous_adoption_id` is refused: read again and retry.
5. **Re-judge from what is recorded.** `read_work_sop` again: its
   `current_adoption` holds the milestones to judge now, and the dropped
   ones stay as history; judge only the current ones. One `record_review`
   judging those the recorded evidence
   already settles, citing it, with a memo saying which version the job
   moved to, why, and on whose approval. Record nothing new from the
   inbox here; new updates go through `update-the-state-machine`.
6. **Review what is owed.** `read_work_money` for the job. What is owed
   to the business stays. Charges recorded before the move are marked;
   put each open one the business owes to the person and ask whether it
   still stands. Record their answer as in the `update-the-state-machine`
   skill's money page.
7. **Read back and hand over.** `read_case_brief` again, then
   `call-to-action` for the job.

## Several jobs at once

When a revised SOP should apply to running jobs, list the jobs on the old
version from `list_work` (each entry shows `sop_version_id`) and show the
person the list first. Move each job on its own, with its own adoption
and memo; one approval may cover the list if the person gives it for the
list, and is cited by each.

## Never

- Never move a job without the person's explicit yes.
- Never move a quote or booking; the ledger refuses it.
- Never mark a dropped milestone done to tidy up; it stays as history.

Done when: the job's current adoption is the version the person chose, the
read-back shows the new milestones judged where evidence allowed, and one
memo explains the move.
