# Extra trusted certificates for calendar feeds

Every `*.pem` file here is appended to the standard CA bundle when the app
downloads iCal feeds (`core/feeds.py`, `ca_bundle()`).

Why: some servers (e.g. `webtimetables.royalholloway.ac.uk`) send only their own
certificate and omit the intermediate CA certificate. Browsers quietly fetch the
missing piece; Python does not, so verification fails. Adding the *public*
intermediate certificate here lets the app verify those servers properly -
TLS verification stays fully enabled.

Only put public CA certificates here, never private keys.

| File | Issuer | Expires |
|------|--------|---------|
| `sectigo-public-server-authentication-ca-ov-r36.pem` | Sectigo Public Server Authentication Root R46 | 2036-03-21 |

To add another one: find the "CA Issuers" URL in the failing server's certificate
(`openssl s_client -connect host:443 | openssl x509 -noout -text`), download it,
convert with `openssl x509 -inform DER -in file.crt -out certs/name.pem`.
