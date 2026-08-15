# GA4 and GBP console hour — Lou gate

This is an execution checklist, not evidence that account changes happened.
Never print the service-account identity or key material into a receipt.

1. Enable Analytics Data and Admin APIs in `local-lead-machine-498016`.
2. Grant the service-account identity Viewer access to GA4 property `541970582`.
3. Designate only `booking_completed` as the primary key event. Keep
   `book_click` as a micro-conversion.
4. Make one controlled Zenbooker test booking. Confirm the return includes
   `booking_session`; DebugView must show exactly one `booking_completed`, with
   no personal data.
5. Enable enhanced measurement for scroll and history-based page changes.
   Verify `page_view`, `user_engagement`, and a 90% `scroll`. If SPA page views
   remain absent, prepare a draft site PR for route-change tracking.
6. Select the exact `accounts/*/locations/*` GBP resource and set the protected
   `GBP_LOCATION_ID` Actions variable. Do not guess or commit the resource.
7. Run read-only `fmd-seo sync --source ga4` and `--source gbp`; preserve the
   receipts and read back the observations.

Exit only when GA4 reads are authorized, the booking event appears exactly once,
engagement events are visible, and GBP reads the selected location. No revenue
attribution claim is allowed before that point.
