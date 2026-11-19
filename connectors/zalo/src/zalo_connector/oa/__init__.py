"""Zalo Official Accounts: not available yet. An OA account can be created and its keys stored (sealed, like
every credential), so the dashboard and the storage are ready; no channel runs for it.

What the channel will need, from Zalo's OA documentation (check it again before building):

* OAuth v4: an access token lives about 25 hours and is renewed with the refresh token, which works once and
  comes back new on every renewal, so the new one must be stored before the old one is lost;
* webhook: events come signed in ``X-ZEvent-Signature`` (sha256 of app id + body + timestamp + the OA secret
  key), checked before parsing, like the bot webhook;
* sending: customer-service messages only within Zalo's window after the user's last message; anything later
  is a paid ZNS template, which this plugin must not send on its own.
"""

from __future__ import annotations

from typing import Final

NOT_AVAILABLE: Final = "Zalo OA chưa chạy được: khóa đã lưu, kênh sẽ có ở bản sau."
