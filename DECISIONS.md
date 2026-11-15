# Decisions

Choices made where the request left room, newest last.

## Accounts (1.7)
- The app is Python (PyQt6), not Electron. "Secure storage" is Windows data protection (DPAPI): the saved login
  can only be read by the same Windows user on the same PC. File: `%USERPROFILE%\.rubenium\Rubenium\session.dat`.
- Supabase needs an e-mail, so a username becomes `<username in lower case>@users.rubenium.app`. No mail is ever
  sent. "Confirm email" must be OFF in Supabase.
- Usernames: 3 to 10 letters or numbers, unique whatever the capitals. The database refuses any account that does
  not follow this (a trigger on new users), so nobody can make an odd account by calling the server directly.
- No password recovery (there is no e-mail). The project owner can reset a password by hand in Supabase
  (Authentication > Users). An optional e-mail can be added later.
- Login rate limits are Supabase's own (per IP).
- Only the publishable key is in the app. The secret key is never used by the app or stored in this repository.
- Time played is counted by the server: one heartbeat a minute while the app is in use (music playing, or mouse /
  keyboard used in the last 10 minutes), at most one minute per minute, one PC at a time per account.
- Offline with a saved login: the app still launches and works; the time simply is not counted.
- Log out is on the welcome screen. Settings also has "Log out", which closes Rubenium (the next start asks to
  log in).
- Style is locked: strong glow, black background, round corners.
- Coins, items and games are still stored on the PC in 1.7. They move to the server in the next stages; the
  one-time import of old progress happens then.
