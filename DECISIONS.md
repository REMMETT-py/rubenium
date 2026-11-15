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

## 1.8
- The login form lives inside the welcome card (the card grows to hold it), not under it.
- The hidden code on the Launch button was removed.
- Account deletion: its own small window (typing needs the keyboard; the menu never takes it from a game). The
  username must be typed exactly, then the button needs two clicks and a hold. The server checks the name again.
- Quit is a small link at the bottom of Settings (with a confirmation) and stays in the tray menu.
- Lantern Lift, Monsoon and Electric banner are gone for good; every version of their files is still recognised
  so the original game file is restored for anyone who had one on.

## 2.0 (the online economy)
- Hard reset: every account starts at 500 coins and 3 keys (006_fresh_start.sql). No import of old progress.
- Progression: 3 balls (Classic 0 h, White Gold 30 h, Gold 100 h), 3 rings (Line 0 h, White Gold 40 h, Gold 125 h),
  8 themes (0, 2, 12, 20, 55, 75, 150, 200 h). Not tradeable, never sold.
- Colours of the menu (colour 1, colour 2, the music's colours) are free for everyone.
- Black / White / Gold badges and the 5 Exotic badges only come from cases (and, later, trading).
- The casino shows the bet leaving at once and the prize when the animation ends; the server did both already.
- A round left open (app closed mid-hand) is picked up again the next time that game is started.
- Not in 2.0 yet: the 10 balls / 10 lines / 5 fonts / shop themes, quests, the minigame, trading, the market.
