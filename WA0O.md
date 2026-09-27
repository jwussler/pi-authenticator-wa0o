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

## tools/ - headless Chrome for Apple's web-only steps (09/27/2026, NOT working yet)
`tools/cdp.py` (tiny CDP driver: in-process iframe contexts, secrets only into verified password fields, trusted
key/mouse input) and `tools/apple_setup.py` (App Store Connect sign-in + 2FA via a code file on T:).
Result 09/27: Apple ID step works (`/appleauth/auth/signin/init` 200) but after the password Apple's own script never
sends `/signin/complete` - Enter, script click and a real CDP mouse click all ignored, no error shown. Looks like
Apple's automation/headless detection. Next ideas if revisited: headed Chrome under Xvfb, or a persistent profile
that already holds an Apple "trusted browser" cookie. Until then the web steps (new app record, APNs key) are manual.
