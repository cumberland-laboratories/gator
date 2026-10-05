# Decision Request: Enable Live Candidate Verification for Coding-Loop Approval

## Decision Needed

The reviewer runtime needs authority to create and remove the repository's transient `.git/index.lock` during Gator's required live staged-tree verification. Please grant that scoped permission or direct an approved alternative verification path.

## Context

The submitted coding-loop candidate remains `756f50bbcd96c81dac7cf40a13e9bf0a387ad8ef`, and its source review and focused tests are complete. The reviewer independently ran `git write-tree`; it failed with:

`fatal: Unable to create 'C:/Users/curator/code2/gator/.git/index.lock': Permission denied`

`gator loop submit-review --approve` failed for the same reason. Approval must verify the live index and HEAD at submission time; an earlier diff cannot substitute for this binding check. The Draftor reports no extant index lock and no running Git process. The environment grants read access to `.git`, but this operation requires temporary write access to the lock file.

## Options Considered

1. Grant scoped Git-index lock write access to this reviewer runtime — preserves the established loop approval contract.
2. End or pause the loop and have the Architect perform a separately authorized verification/approval workflow — avoids changing permissions but leaves the current CLI reviewer unable to complete its role.
3. Repeat revision submissions without new authority — rejected because it would recreate the same `git_busy` refusal without increasing assurance.

## Recommendation

Grant scoped permission for Git to create/remove `.git/index.lock` in this repository for the review operation. Then the reviewer can rerun status and submit the already-reviewed candidate for normal approval.

## Consequence of Delay

The loop remains blocked. The implementation cannot receive the required coding-loop approval, even though its source review and focused verification are complete.
