# Setup (for the project owner)

1. Supabase > Authentication > Sign In / Providers > Email: switch **Confirm email** OFF, Save.
2. Supabase > SQL Editor > New query: paste the whole content of each file in `supabase/migrations/`
   (in number order) and press **Run**. Running a file twice does no harm.
3. Never share the secret key (`sb_secret_...`). If it was shared, Settings > API Keys > delete it and create a new one.
4. Updating from 2.1: run only `008_ultimate_update.sql` (it already contains 007). Do not run 006 again.
5. Updating from 2.2: run only `009_parking_no_gold.sql`.
