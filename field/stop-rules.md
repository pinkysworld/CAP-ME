# Prospective field-study stop rules

Stop the experiment immediately if any of the following occurs:

- a packet is addressed to a host absent from the approved manifest;
- unrelated third-party traffic is observed or retained;
- a participant, operator, provider, or reviewer reports possible harm;
- the volume or duration limit reaches 90% unexpectedly;
- cryptographic authentication fails repeatedly without an explained test case;
- logs contain message plaintext, credentials, account identifiers, or live
  proxy addresses;
- infrastructure ownership or authorization becomes uncertain;
- a provider requests cessation;
- local law, institutional policy, or the approved protocol changes; or
- the independent safety contact cannot be reached.

After a stop, preserve only the minimum audit record, revoke test credentials,
delete collected payload data according to the approved schedule, and do not
resume until the responsible reviewers issue a written decision.
