# DB Securities opposing-LOC testbed protocol

Use a test account, one share, and a session where cancellation can be observed
safely. Save redacted request hashes, response codes, order numbers, timestamps,
app screenshots, and final cancellation status as evidence.

1. Reconcile holdings, available cash, and all open orders.
2. Submit one-share LOC sell after the 04:00 America/New_York premarket open.
3. Confirm a broker order number and that the app shows the order.
4. After the 09:30 regular open, reconcile again and submit one-share LOC buy
   for the same symbol without cancelling the sell.
5. Confirm two independently queryable order numbers.
6. Query both filled and unfilled states through every continuation page.
7. Correct each order once, then cancel each order and verify terminal status.
8. Repeat one request to determine whether DB Securities supplies a duplicate
   key or creates another order. Never repeat this step in a live account.
9. Simulate a client timeout after submission and prove that inquiry, without
   resubmission, resolves the result.
10. Reconcile holdings, cash, and open orders to their starting state.

Only an entirely successful run may be recorded with:

```powershell
app capability verify --opposing-loc-confirmed --evidence "redacted report path and date"
```
