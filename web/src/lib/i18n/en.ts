/** English is the source of truth: every key lives here, hi.ts and mr.ts fall back to it for anything missing. */
export const en = {
  // navigation and shell
  'nav.dashboard': 'Dashboard', 'nav.trips': 'Trips', 'nav.review': 'Review', 'nav.billing': 'Billing', 'nav.import': 'Import', 'nav.drivers': 'Drivers', 'nav.progress': 'Build progress',
  'shell.signOut': 'Sign out', 'shell.language': 'Language',
  'common.loading': 'Loading…', 'common.close': 'Close', 'common.cancel': 'Cancel', 'common.none': 'None.', 'unit.days': ' days', 'unit.d': ' d', 'unit.crore': 'crore', 'unit.lakh': 'lakh',
  // statuses
  'status.pending': 'Awaiting POD', 'status.uploaded': 'Checking', 'status.verified': 'Verified', 'status.needs_review': 'Needs review',
  'status.retake_requested': 'Retake', 'status.rejected': 'Rejected', 'status.billed': 'Billed',
  // login
  'login.identifier': 'Email or phone', 'login.secret': 'Password or PIN', 'login.submit': 'Sign in', 'login.busy': 'Signing in…',
  'login.wrong': 'Wrong login or password.', 'login.offline': 'Cannot reach the server.', 'login.progress': 'See build progress',
  // trips
  'trips.error': 'Could not load trips.', 'trips.total': 'Trips', 'trips.verified': 'Verified', 'trips.needsReview': 'Needs review', 'trips.retake': 'Retake',
  'trips.trip': 'Trip', 'trips.client': 'Client', 'trips.vehicle': 'Vehicle', 'trips.to': 'To', 'trips.freight': 'Freight', 'trips.delivered': 'Delivered',
  'trips.pod': 'POD', 'trips.uploadLink': 'Upload link', 'trips.hired': 'hired', 'trips.sendLink': 'Send link', 'trips.link': 'Link', 'trips.share': 'Share',
  // review queue
  'review.title': 'Review queue', 'review.sub': 'PODs the system will not verify on its own. Oldest first.', 'review.empty': 'Nothing waiting for review.',
  'review.error': 'Could not load the review queue.', 'review.hoursAgo': '{n} h ago', 'review.daysAgo': '{n} days ago',
  // review reasons
  'reason.shortage_or_damage': 'Shortage / damage remark', 'reason.low_confidence': 'Low AI confidence', 'reason.date_missing': 'Delivery date not read',
  'reason.retake_cap_reached': 'Driver already retook twice', 'reason.ai_unavailable': 'AI was unavailable', 'reason.stamp_missing': 'Stamp not visible',
  'reason.signature_missing': 'Signature not visible', 'reason.lr_mismatch': 'LR number does not match', 'reason.unreadable': 'Photo unreadable', 'reason.not_a_pod': 'Does not look like a POD',
  // review detail
  'rd.loadFail': 'Could not load this POD.', 'rd.saveFail': 'Could not save. Try again.', 'rd.attempt': 'Attempt {n}', 'rd.confidence': 'AI confidence {n}%',
  'rd.check': 'Check against the photo', 'rd.lr': 'LR number', 'rd.lrUnread': 'LR number could not be read - type it from the photo (trip LR is {lr}).',
  'rd.lrDiff': 'Differs from trip LR {lr} - approval will be refused.', 'rd.date': 'Delivery date', 'rd.qty': 'Quantity received', 'rd.remarks': 'Remarks on the paper',
  'rd.shortage': 'Shortage or damage recorded', 'rd.note': 'Note (optional)', 'rd.approve': 'Approve', 'rd.retake': 'Retake', 'rd.reject': 'Reject', 'rd.confirmReject': 'Confirm reject',
  'rd.retakeLimit': 'Retake limit reached', 'rd.footer': 'Approving does not send an invoice. Retakes left for the driver: {n}.',
  // dashboard
  'dash.error': 'Could not load the dashboard.', 'dash.md': 'Business overview', 'dash.ops': 'Operations', 'dash.sub': 'Trips delivered in the last {days} days · {n} trips',
  'dash.window': 'Time window', 'dash.last': 'Last {n} days', 'dash.digest': 'Download digest', 'dash.demo': 'Showing illustrative DEMO data (trips coded DEMO-…). These figures are not real performance.',
  'dash.pod24': 'PODs in system within 24 h', 'dash.invoice': 'POD to invoice', 'dash.lost': 'Lost or disputed PODs', 'dash.cash': 'Cash freed by faster billing',
  'dash.onTarget': 'On target', 'dash.below': 'Below target', 'dash.noData': 'No data yet', 'dash.target': 'target {v}', 'dash.was': 'Was {v} before CargoOne',
  'dash.needsInvoiced': 'Needs invoiced trips', 'dash.interest': '≈ {amt} interest saved a year at {pct}%', 'dash.calc': '{d} days sooner × {amt} yearly freight ÷ 365',
  'dash.awaiting': 'awaiting human review', 'dash.ready': 'verified, ready to bill', 'dash.risk': 'freight at risk (POD missing 7+ days or rejected)',
  'dash.missing': 'Trips without a POD', 'dash.missingSub': '{n} trips · {amt} freight · by days since delivery', 'dash.allHave': 'Every delivered trip has its POD.',
  'dash.branches': 'Branches', 'dash.branchesSub': 'Last window, per branch', 'dash.branch': 'Branch', 'dash.within24': 'Within 24 h', 'dash.toInvoice': 'To invoice', 'dash.missingCol': 'Missing',
  'dash.c1': 'PODs within 24 h of delivery', 'dash.c1sub': 'Share of delivered trips, by week', 'dash.c1unit': 'PODs within 24 hours (%)', 'dash.c1target': 'Target {v}%',
  'dash.c2': 'Days from POD to invoice', 'dash.c2sub': 'Average, by week the invoice was raised', 'dash.c2unit': 'Days from POD to invoice', 'dash.c2target': 'Target {v} days',
  'dash.oldest': 'Oldest trips still without a POD', 'dash.oldestSub': 'Chase these first', 'dash.cTrip': 'Trip', 'dash.cClient': 'Client', 'dash.cVehicle': 'Vehicle', 'dash.cDriver': 'Driver', 'dash.cDays': 'Days', 'dash.cFreight': 'Freight',
  'chart.weekOf': 'Week of', 'chart.noData': 'no data', 'chart.table': 'View as table',
  // billing
  'bill.title': 'Billing', 'bill.sub': 'Verified PODs, ready to invoice. Nothing is sent to a client automatically.', 'bill.error': 'Could not load billing data.',
  'bill.tabReady': 'Ready to bill', 'bill.tabInvoices': 'Invoices', 'bill.emptyReady': 'No verified PODs waiting to be billed.', 'bill.emptyInvoices': 'No invoices yet.',
  'bill.oldest': 'oldest waiting {n} days', 'bill.include': 'Include {code}', 'bill.count': '{a} of {b} {unit}', 'bill.trip': 'trip', 'bill.trips': 'trips',
  'bill.create': 'Create invoice', 'bill.creating': 'Creating…', 'bill.createFail': 'Could not create the invoice.', 'bill.dlFail': 'Download failed. Try again.',
  'bill.invoice': 'Invoice', 'bill.client': 'Client', 'bill.period': 'Period', 'bill.tripsCol': 'Trips', 'bill.total': 'Total', 'bill.exported': 'Exported', 'bill.download': 'Download', 'bill.notYet': 'Not yet',
  'bill.note': "The PDF includes each trip's POD photo. Tally XML imports as a Sales voucher; the party and freight ledgers must already exist in Tally.",
  // import
  'imp.title': 'Import trips', 'imp.sub': "Upload the day's trips as CSV or Excel, with LR and e-way bill numbers. Re-uploading the same file is safe.", 'imp.template': 'Download template',
  'imp.choose': 'Choose a .csv or .xlsx file', 'imp.columns': 'Columns: Trip ID, Client, Vehicle, Destination, Freight, LR No, E-way Bill No (optional: Origin, Delivery Date, Branch, Driver Phone)',
  'imp.create': 'Create clients that do not exist yet (billing cycle starts as weekly)', 'imp.working': 'Working…', 'imp.readFail': 'Could not read the file.', 'imp.failed': 'Import failed.',
  'imp.done': 'Imported: {c} new, {u} updated, {n} already up to date', 'imp.doneSkipped': ', {n} left unchanged', 'imp.doneErrors': '{n} row(s) were not imported - see the list you checked, fix them in the sheet and upload again.',
  'imp.view': 'View trips', 'imp.result': 'Check result', 'imp.willCreate': 'will be created', 'imp.willUpdate': 'will be updated', 'imp.upToDate': 'already up to date', 'imp.leftUnchanged': 'left unchanged', 'imp.problems': 'rows with problems',
  'imp.alsoNew': 'Also new', 'imp.fix': 'Fix these rows in your sheet', 'imp.row': 'Row', 'imp.tripCol': 'Trip', 'imp.problemCol': 'Problem', 'imp.firstN': 'Showing the first {n} of {total}.',
  'imp.btn': 'Import {n} trips', 'imp.btn1': 'Import 1 trip', 'imp.nothing': 'Nothing to import', 'imp.skippedNote': 'Rows with problems are skipped; the rest are imported.',
  // dialogs
  'ul.title': 'Upload link', 'ul.intro': 'The driver opens the link on any phone, takes the photo, and is done. No app, no login. It works for this trip only.',
  'ul.phone': "Driver's mobile (optional)", 'ul.lang': 'Message language', 'ul.phoneBad': 'Enter the mobile number with 10–15 digits, or leave it empty.', 'ul.createFail': 'Could not create the link.',
  'ul.create': 'Create link', 'ul.createSms': 'Create link and send SMS', 'ul.creating': 'Creating…', 'ul.copy': 'Copy', 'ul.copied': 'Copied',
  'ul.valid': 'Valid until {when}. Creating a new link cancels this one.', 'ul.revoke': 'Revoke this link',
  'cl.title': 'Share with client', 'cl.intro': 'The client opens the link and sees the signed receipt photo, LR number and delivery date. Nothing else: no amounts, no other trips, no way to change anything.',
  'cl.create': 'Create link', 'cl.createNew': 'Create a new link (cancels the old one)', 'cl.log': 'Access log', 'cl.created': 'Created {when}', 'cl.revoked': 'revoked', 'cl.expired': 'expired',
  'cl.until': 'until {when}', 'cl.notOpened': 'not opened yet', 'cl.opened': 'opened {n}× (last {when})', 'cl.revoke': 'Revoke access', 'cl.createFail': 'Could not create the link.',
  // account
  'acct.title': 'Account', 'acct.change': 'Change password', 'acct.current': 'Current password', 'acct.new': 'New password', 'acct.again': 'New password again',
  'acct.hint': 'At least 10 characters, with letters. Not your name or a common word.', 'acct.mismatch': 'The two new passwords are not the same.', 'acct.saving': 'Saving…',
  'acct.done': 'Password changed. Your other devices were signed out.', 'acct.offline': 'Could not reach the server.',
  // drivers
  'drv.title': 'Drivers', 'drv.sub': 'A driver forgot their PIN? Reset it here, then read the temporary PIN to them. They choose their own at the next sign-in.', 'drv.error': 'Could not load drivers.',
  'drv.name': 'Name', 'drv.phone': 'Phone', 'drv.branch': 'Branch', 'drv.status': 'Status', 'drv.locked': 'Locked', 'drv.temp': 'Has a temporary PIN', 'drv.ok': 'OK', 'drv.reset': 'Reset PIN',
  'drv.confirmTitle': "Reset {name}'s PIN?", 'drv.confirmBody': 'Their old PIN stops working and any phone they are signed in on is signed out. Check you are speaking to {name} before you read out the new PIN.',
  'drv.resetting': 'Resetting…', 'drv.resetFail': 'Could not reset the PIN.', 'drv.tempFor': 'Temporary PIN for {name}', 'drv.tempNote': 'Read it out now. It is shown only once and cannot be looked up later. The driver will be asked to choose their own PIN after signing in with it.',
  // planning
  "nav.planning": "Planning", "state.planned": "Planned", "state.in_transit": "On the road", "state.delivered": "Delivered", "state.cancelled": "Cancelled", "plan.title": "Trip planning", "plan.sub": "Who is driving what, and when. Clashes are flagged before they happen.", "plan.new": "New trip", "plan.error": "Could not load the planning board.", "plan.today": "Today", "plan.unscheduled": "On the road or without a time", "plan.noVehicles": "No vehicles yet.", "plan.legend": "Legend", "plan.client": "Client", "plan.vehicle": "Vehicle", "plan.driver": "Driver", "plan.noDriver": "No driver yet", "plan.origin": "From", "plan.destination": "To", "plan.freight": "Freight (₹)", "plan.lr": "LR number", "plan.eway": "E-way bill (12 digits)", "plan.start": "Start", "plan.end": "End (optional)", "plan.create": "Create trip", "plan.creating": "Creating…", "plan.save": "Save changes", "plan.saving": "Saving…", "plan.bookAnyway": "Book anyway", "plan.cancelTrip": "Cancel this trip", "plan.confirmCancel": "Cancel {code}? The driver will no longer see it.", "plan.keep": "Keep it", "plan.readOnly": "This trip has started, so it can no longer be re-planned.", "plan.failed": "Could not save the trip.", "plan.hiredTag": "hired", "plan.opens": "Trip {code}",
} as const

export type Key = keyof typeof en
