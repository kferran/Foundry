# Carry forward: one "open since" stamp per item

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #84.

## 1. Problem

`carry_forward.py` reads a carried item's first date from a trailing `_(open since YYYY-MM-DD)_` stamp. The brief rewrites that stamp with an age, `_(open since 2026-10-06, 3 days)_`, which the pattern does not match. The next carry keeps the old stamp in the text and appends a new one dated the carry day, so the item gains a second, newer stamp, and later briefs count its age from that date. Seen on 2026-10-08 and 2026-10-09: 16 items had an extra stamp, and the brief corrected them by hand and flagged it in the friction matrix both days.

## 2. Change

- The stamp pattern accepts an optional age suffix (`, N day` or `, N days`) and is not anchored to the end of the line.
- Every stamp is removed from the item's text, and the item keeps the **earliest** date among its stamps, so an item that already has two stamps heals on its next carry.
- The output stays `<item> _(open since YYYY-MM-DD)_`. The brief adds the age as before.

## 3. Tests

pytest (`test_carry_forward.py`): an item stamped with an age suffix keeps its date and gets one stamp; an item with two stamps keeps the earlier date and one stamp. Both fail before the change. Bound tools: pytest and the gate.
