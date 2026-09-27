# WA0O build of the privacyIDEA Authenticator

Fork of [privacyidea/pi-authenticator](https://github.com/privacyidea/pi-authenticator) (Apache-2.0, see LICENSE.txt),
built for WA0O's own privacyIDEA so **push notifications** work: the store app is compiled against NetKnights'
Firebase project (`privacyidea-4c8c1`) and only their paid SLA reaches it. This build uses our own Firebase project.

Branches: `master` = untouched upstream mirror; `wa0o` = our changes (rebase onto upstream to update).

Changes on `wa0o` (kept minimal on purpose):
- iOS bundle id `com.wa0o.piauthenticator`, team `V829EBE8HH`, manual signing with profile "WA0O Authenticator App Store"
  (Release-netknights), push entitlement `production`, display name "WA0O Auth".
- `ios/config/netknights/GoogleService-Info.plist` -> WA0O Firebase project (until then: upstream's, polling only).
- `.github/workflows/wa0o-testflight.yml` -> signed .ipa + optional TestFlight upload (upstream workflows disabled here).
- TestFlight builds expire after 90 days: re-run the workflow with `-f upload=true` before then.
