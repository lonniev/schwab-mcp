- `restore_oauth_session` now hands back an `OAuthSituation` carrying the
  provider's own status and error code, not a bare string. `_resolution_for`
  switches on `situation.code`, and the three Schwab-side literals
  (`no_account_hash`, `operator_not_configured`, `no_credentials`) wrap at the
  call site. Behaviour is unchanged for Schwab patrons except that OAuth
  failures now carry evidence — and an `invalid_client` refusal of the
  operator's own app credentials no longer reaches patrons as "your session
  expired" with an invitation to re-authorize.
